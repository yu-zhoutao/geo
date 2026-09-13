from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
import copy
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import signal
import socket
import sqlite3
from typing import Any, Protocol
from uuid import uuid4

import httpx

from app.config import Settings, get_settings
from app.models import EventEnvelope, RuntimeStatus
from app.services.agent_assets import AgentAssetBundle, AgentAssetService
from app.services.agent_identity import build_agent_prompt_identity_overlay, load_agent_identity_map
from app.services.geospatial_runtime import geospatial_environment_variables
from app.services.geospatial_mcp_server import build_geospatial_mcp_config
from app.services.runtime_environment import configure_runtime_environment
from app.services.providers import ModelProviderConfig, resolve_model_provider_config
from app.services.session_store import SessionStore
from app.services.tool_identity import canonical_tool_name, resolve_tool_identity

configure_runtime_environment()

EVIDENCE_TOOL_LABELS: dict[str, str] = {
    'dataset_profile': '记录数据画像',
    'verification_fact': '记录验证事实',
    'parameter_snapshot': '记录参数快照',
    'claim_trace': '记录声明追踪',
}
STREAM_SNAPSHOT_POLL_SECONDS = 5.0


@dataclass(slots=True)
class RuntimeSessionRequest:
    session_id: str
    prompt: str
    workspace_path: Path
    answer: str | None = None
    question_request_id: str | None = None
    question_answers: list[str] | None = None
    geospatial_context_id: str | None = None
    runtime_session_id: str | None = None
    attached_data_directories: list[dict[str, Any]] | None = None
    processed_tool_part_ids: set[str] | None = None


@dataclass(slots=True)
class RuntimeSessionResult:
    runtime_session_id: str | None = None
    trace_path: str | None = None


class AgentRuntimeClient(Protocol):
    @property
    def is_ready(self) -> bool: ...

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    def status(self) -> RuntimeStatus: ...

    async def abort_session(self, runtime_session_id: str) -> None: ...

    async def run_session(
        self,
        request: RuntimeSessionRequest,
        emit: Callable[[EventEnvelope], Awaitable[None]],
    ) -> RuntimeSessionResult: ...

    async def fetch_session_messages(self, runtime_session_id: str) -> list[dict[str, Any]]: ...


class NullAgentRuntimeClient:
    def __init__(self, settings: Settings | None = None, detail: str | None = None) -> None:
        self.settings = settings or get_settings()
        self.detail = detail or 'Model provider not configured for OpenCode runtime.'

    @property
    def is_ready(self) -> bool:
        return False

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    def status(self) -> RuntimeStatus:
        return RuntimeStatus(status='stopped', label=self.settings.runtime_label, detail=self.detail)

    async def abort_session(self, runtime_session_id: str) -> None:
        return None

    async def run_session(
        self,
        request: RuntimeSessionRequest,
        emit: Callable[[EventEnvelope], Awaitable[None]],
    ) -> RuntimeSessionResult:
        raise RuntimeError(self.detail)

    async def fetch_session_messages(self, runtime_session_id: str) -> list[dict[str, Any]]:
        return []


def build_agent_runtime_client(settings: Settings | None = None) -> AgentRuntimeClient:
    resolved = settings or get_settings()
    if resolve_model_provider_config(resolved) is None:
        return NullAgentRuntimeClient(settings=resolved)
    return OpenCodeAgentRuntimeClient(settings=resolved)


class OpenCodeAgentRuntimeClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.process: asyncio.subprocess.Process | None = None
        self._client: httpx.AsyncClient | None = None
        self._port: int | None = None
        self._process_group_id: int | None = None
        self._asset_service = AgentAssetService(self.settings.resolved_agent_asset_root())
        self._asset_bundle: AgentAssetBundle | None = None
        self._server_root = self.settings.resolved_runtime_config_root().expanduser().resolve()
        self._server_root.mkdir(parents=True, exist_ok=True)

    @property
    def is_ready(self) -> bool:
        return self.process is not None and self.process.returncode is None and self._client is not None

    async def start(self) -> None:
        if self.is_ready:
            return
        self._port = self._select_port()
        env = self._build_server_env(port=self._port)
        self.process = await asyncio.create_subprocess_exec(
            self.settings.opencode_binary,
            'serve',
            '--port',
            str(self._port),
            '--hostname',
            self.settings.opencode_hostname,
            cwd=str(self._server_root / 'workspace'),
            env=env,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )
        self._process_group_id = self.process.pid
        try:
            await self._wait_for_health()
        except BaseException:
            await self.stop()
            raise
        self._client = httpx.AsyncClient(base_url=self._base_url(), timeout=120.0, trust_env=False)

    async def stop(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        process_group_id = self._process_group_id
        process = self.process
        if process is None:
            return
        if process_group_id is not None:
            await self._terminate_process_group(process_group_id=process_group_id, process=process)
            self._process_group_id = None
            return
        if process.returncode is not None:
            return
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=10)
        except TimeoutError:
            process.kill()
            await process.wait()

    async def _terminate_process_group(self, *, process_group_id: int, process: asyncio.subprocess.Process) -> None:
        group_signaled = self._signal_process_group(process_group_id, signal.SIGTERM)
        if process.returncode is None:
            try:
                await asyncio.wait_for(process.wait(), timeout=10)
            except TimeoutError:
                self._signal_process_group(process_group_id, signal.SIGKILL)
                await process.wait()
                return
        if group_signaled and self._process_group_exists(process_group_id):
            self._signal_process_group(process_group_id, signal.SIGKILL)

    def _signal_process_group(self, process_group_id: int, requested_signal: signal.Signals) -> bool:
        try:
            os.killpg(process_group_id, requested_signal)
        except ProcessLookupError:
            return False
        return True

    def _process_group_exists(self, process_group_id: int) -> bool:
        try:
            os.killpg(process_group_id, 0)
        except ProcessLookupError:
            return False
        return True

    def status(self) -> RuntimeStatus:
        if self.process is None:
            return RuntimeStatus(status='starting', label=self.settings.runtime_label, detail='OpenCode runtime not started yet.')
        if self.process.returncode is not None:
            return RuntimeStatus(status='stopped', label=self.settings.runtime_label, detail='OpenCode runtime is stopped.')
        return RuntimeStatus(status='ready', label=self.settings.runtime_label, pid=self.process.pid, detail='OpenCode runtime is ready.')

    async def abort_session(self, runtime_session_id: str) -> None:
        if self._client is None:
            await self.start()
        if self._client is None:
            raise RuntimeError('OpenCode HTTP client is not available')
        response = await self._client.post(f'/session/{runtime_session_id}/abort')
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in {404, 410}:
                raise

    async def fetch_session_messages(self, runtime_session_id: str) -> list[dict[str, Any]]:
        if self._client is None:
            return self._fetch_session_messages_from_db(runtime_session_id)
        try:
            response = await self._client.get(f'/session/{runtime_session_id}/message')
            response.raise_for_status()
        except httpx.HTTPError:
            return self._fetch_session_messages_from_db(runtime_session_id)
        payload = response.json()
        if not isinstance(payload, list):
            return []
        messages: list[dict[str, Any]] = []
        for item in payload:
            if isinstance(item, dict):
                messages.append(self._normalize_message(item))
        return messages

    def _fetch_session_messages_from_db(self, runtime_session_id: str) -> list[dict[str, Any]]:
        database_path = self._server_root / '.local' / 'share' / 'opencode' / 'opencode.db'
        if not database_path.exists():
            return []
        try:
            with sqlite3.connect(f'file:{database_path}?mode=ro', uri=True, timeout=1.0) as connection:
                connection.row_factory = sqlite3.Row
                message_rows = connection.execute(
                    '''
                    SELECT id, data
                    FROM message
                    WHERE session_id = ?
                    ORDER BY time_created, id
                    ''',
                    (runtime_session_id,),
                ).fetchall()
                part_rows = connection.execute(
                    '''
                    SELECT id, message_id, data
                    FROM part
                    WHERE session_id = ?
                    ORDER BY time_created, id
                    ''',
                    (runtime_session_id,),
                ).fetchall()
        except sqlite3.Error:
            return []

        parts_by_message: dict[str, list[dict[str, Any]]] = {}
        for row in part_rows:
            try:
                part = json.loads(str(row['data']))
            except json.JSONDecodeError:
                continue
            if not isinstance(part, dict):
                continue
            part['id'] = row['id']
            part['messageID'] = row['message_id']
            part['sessionID'] = runtime_session_id
            parts_by_message.setdefault(str(row['message_id']), []).append(part)

        messages: list[dict[str, Any]] = []
        for row in message_rows:
            try:
                info = json.loads(str(row['data']))
            except json.JSONDecodeError:
                continue
            if not isinstance(info, dict):
                continue
            info['id'] = row['id']
            try:
                messages.append(
                    self._normalize_message({
                        'info': info,
                        'parts': parts_by_message.get(str(row['id']), []),
                    })
                )
            except (KeyError, TypeError, ValueError):
                continue
        return messages

    async def run_session(
        self,
        request: RuntimeSessionRequest,
        emit: Callable[[EventEnvelope], Awaitable[None]],
    ) -> RuntimeSessionResult:
        await self.start()
        if self._client is None:
            raise RuntimeError('OpenCode HTTP client is not available')

        runtime_session_id = request.runtime_session_id
        if request.question_request_id is not None:
            if runtime_session_id is None:
                raise RuntimeError('Runtime question reply requires an existing runtime session')
            await emit(EventEnvelope(type='session.runtime_session', payload={'runtime_session_id': runtime_session_id}))
            reply_answers = [[answer] for answer in (request.question_answers or []) if answer]
            if not reply_answers and request.answer:
                reply_answers = [[request.answer]]
            reply_response = await self._client.post(
                f'/question/{request.question_request_id}/reply',
                json={'answers': reply_answers},
            )
            reply_response.raise_for_status()
            await self._poll_session(runtime_session_id=runtime_session_id, request=request, emit=emit)
            trace_path = self._session_trace_path(runtime_session_id)
            trace_path.parent.mkdir(parents=True, exist_ok=True)
            trace_path.write_text(
                json.dumps(
                    {
                        'runtime_session_id': runtime_session_id,
                        'geospatial_context_id': request.geospatial_context_id,
                        'server_root': str(self._server_root),
                        'workspace_path': str(request.workspace_path),
                        'attached_data_directories': request.attached_data_directories or [],
                        'question_request_id': request.question_request_id,
                        'question_answers': request.question_answers or ([request.answer] if request.answer else []),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding='utf-8',
            )
            return RuntimeSessionResult(runtime_session_id=runtime_session_id, trace_path=str(trace_path))
        if runtime_session_id is None:
            session_response = await self._client.post('/session', json={})
            session_response.raise_for_status()
            runtime_session_id = session_response.json()['id']
        request.runtime_session_id = runtime_session_id
        await emit(EventEnvelope(type='session.runtime_session', payload={'runtime_session_id': runtime_session_id}))

        parts = [
            {'type': 'text', 'text': request.prompt if request.answer is None else request.answer},
        ]
        provider = self._require_provider_config()
        message_payload: dict[str, Any] = {
            'agent': 'geo',
            'model': {
                'providerID': provider.opencode_provider,
                'modelID': provider.model,
            },
            'parts': parts,
        }
        try:
            prompt_response = await self._client.post(
                f'/session/{runtime_session_id}/prompt_async',
                json=message_payload,
            )
            prompt_response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if runtime_session_id is None or exc.response.status_code not in {404, 410}:
                raise
            session_response = await self._client.post('/session', json={})
            session_response.raise_for_status()
            runtime_session_id = session_response.json()['id']
            request.runtime_session_id = runtime_session_id
            await emit(EventEnvelope(type='session.runtime_session', payload={'runtime_session_id': runtime_session_id}))
            retry_response = await self._client.post(
                f'/session/{runtime_session_id}/prompt_async',
                json=message_payload,
            )
            retry_response.raise_for_status()
        await self._poll_session(runtime_session_id=runtime_session_id, request=request, emit=emit)
        trace_path = self._session_trace_path(runtime_session_id)
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        trace_path.write_text(
            json.dumps(
                {
                    'runtime_session_id': runtime_session_id,
                    'geospatial_context_id': request.geospatial_context_id,
                    'server_root': str(self._server_root),
                    'workspace_path': str(request.workspace_path),
                    'attached_data_directories': request.attached_data_directories or [],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding='utf-8',
        )
        return RuntimeSessionResult(runtime_session_id=runtime_session_id, trace_path=str(trace_path))

    def _select_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((self.settings.opencode_hostname, 0))
            return int(sock.getsockname()[1])

    def _build_server_env(self, *, port: int) -> dict[str, str]:
        env = copy.deepcopy(os.environ)
        workspace = self._server_root / 'workspace'
        workspace.mkdir(parents=True, exist_ok=True)
        legacy_workspace_config = workspace / 'config.json'
        if legacy_workspace_config.exists():
            legacy_workspace_config.unlink()
        env['XDG_CONFIG_HOME'] = str(self._server_root / '.config')
        env['XDG_DATA_HOME'] = str(self._server_root / '.local' / 'share')
        env['XDG_STATE_HOME'] = str(self._server_root / '.local' / 'state')
        env['XDG_CACHE_HOME'] = str(self._server_root / '.cache')
        env['OPENCODE_TEST_HOME'] = str(self._server_root)
        env['OPENCODE_DISABLE_PROJECT_CONFIG'] = '1'
        env['OPENCODE_DISABLE_CLAUDE_CODE_PROMPT'] = '1'
        env.update(
            geospatial_environment_variables(
                settings=self.settings,
                workspace_path=workspace,
            )
        )
        env['GEO_AGENT_ATTACHED_DATA_DIRS_JSON'] = '[]'
        self._write_global_config_file(port=port)
        provider = self._require_provider_config()
        auth_file = self._server_root / '.local' / 'share' / 'opencode' / 'auth.json'
        auth_file.parent.mkdir(parents=True, exist_ok=True)
        auth_file.write_text(
            json.dumps({provider.opencode_provider: {'type': 'api', 'key': provider.api_key}}, ensure_ascii=False),
            encoding='utf-8',
        )
        return env

    async def _wait_for_health(self) -> None:
        async with httpx.AsyncClient(base_url=self._base_url(), timeout=10.0, trust_env=False) as client:
            for _ in range(120):
                if self.process is not None and self.process.returncode is not None:
                    raise RuntimeError('OpenCode server exited before becoming healthy')
                try:
                    response = await client.get('/global/health')
                    if response.status_code == 200:
                        return
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.25)
        raise RuntimeError('OpenCode server did not become healthy in time')

    def _base_url(self) -> str:
        return f'http://{self.settings.opencode_hostname}:{self._port or 0}'

    def _global_config_path(self) -> Path:
        return self._server_root / '.config' / 'opencode' / 'opencode.json'

    def _runtime_bundle_root(self) -> Path:
        return self._server_root / '.config' / 'opencode'

    def _load_asset_bundle(self) -> AgentAssetBundle:
        if self._asset_bundle is None:
            self._asset_bundle = self._asset_service.load_bundle()
        return self._asset_bundle

    def _write_global_config_file(self, *, port: int) -> Path:
        config_path = self._global_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        bundle = self._load_asset_bundle()
        self._asset_service.materialize_runtime_bundle(bundle, self._runtime_bundle_root())
        config_path.write_text(
            json.dumps(self._build_runtime_config(port=port, cors_origin=self.settings.frontend_origin, bundle=bundle), ensure_ascii=False, indent=2),
            encoding='utf-8',
        )
        return config_path

    def _build_runtime_config(self, *, port: int, cors_origin: str, bundle: AgentAssetBundle | None = None) -> dict[str, Any]:
        resolved_bundle = bundle or self._load_asset_bundle()
        provider = self._require_provider_config()
        config: dict[str, Any] = {
            '$schema': 'https://opencode.ai/config.json',
            'enabled_providers': [provider.opencode_provider],
            'model': provider.opencode_model,
            'small_model': provider.small_model,
            'default_agent': 'geo',
            'share': 'disabled',
            'autoupdate': False,
            'formatter': False,
            'snapshot': False,
            'server': {
                'hostname': self.settings.opencode_hostname,
                'port': port,
                'mdns': False,
                'cors': [cors_origin],
            },
            'watcher': {
                'ignore': ['.git/**', '.runtime/**', '.opencode/**', 'node_modules/**', 'dist/**'],
            },
            'tools': {
                'bash': True,
                'codesearch': False,
                'todowrite': False,
                'write': False,
                'edit': False,
                'webfetch': False,
                'websearch': False,
                'lsp': False,
            },
            'permission': {
                'read': {
                    '*': 'allow',
                    '*.env': 'deny',
                    '*.env.*': 'deny',
                    '*.env.example': 'allow',
                },
                'bash': 'allow',
                'edit': 'deny',
                'todowrite': 'deny',
                'webfetch': 'deny',
                'websearch': 'deny',
                'external_directory': 'allow',
                'doom_loop': 'deny',
            },
            'mcp': {
                'geospatial': build_geospatial_mcp_config(self.settings),
            },
            'agent': self._build_agent_config(resolved_bundle),
        }
        if provider.opencode_provider_config is not None:
            config['provider'] = {provider.opencode_provider: provider.opencode_provider_config}
        return config

    def _require_provider_config(self) -> ModelProviderConfig:
        provider = resolve_model_provider_config(self.settings)
        if provider is None:
            raise RuntimeError(f'{self.settings.model_provider} provider is not configured for OpenCode runtime')
        return provider

    def _build_agent_config(self, bundle: AgentAssetBundle) -> dict[str, Any]:
        config: dict[str, Any] = {
            'general': {'disable': True},
            'explore': {'disable': True},
        }
        for agent in bundle.agents.values():
            skill_permissions = {skill: 'allow' for skill in agent.skills}
            if agent.runtime_name == 'geo':
                skill_permissions['openspec-*'] = 'deny'
            skill_permissions['*'] = 'deny'
            identity_overlay = build_agent_prompt_identity_overlay(agent.runtime_name)
            prompt_parts = [
                part
                for part in (
                    identity_overlay,
                    self._skill_guidance_prompt(agent.skills),
                    agent.prompt,
                )
                if part
            ]
            prompt = '\n\n'.join(prompt_parts)
            config[agent.runtime_name] = {
                'description': agent.description,
                'mode': agent.mode,
                'prompt': prompt,
                'tools': {'skill': True},
                'permission': {
                    'read': {
                        '*': 'allow',
                        '*.env': 'deny',
                        '*.env.*': 'deny',
                        '*.env.example': 'allow',
                    },
                    'bash': 'allow',
                    'edit': 'deny',
                    'todowrite': 'deny',
                    'webfetch': 'deny',
                    'websearch': 'deny',
                    'external_directory': 'allow',
                    'doom_loop': 'deny',
                    'skill': skill_permissions,
                },
            }
        return config

    def _skill_guidance_prompt(self, skills: tuple[str, ...]) -> str:
        if not skills:
            return ''
        skill_list = ', '.join(f'`{skill}`' for skill in skills)
        return (
            '# Professional Geospatial Skills\n'
            f'Before method-sensitive geospatial work, read and apply relevant bundled professional geospatial skills for this role: {skill_list}.\n'
            'Use skills selectively for CRS, data audit, preprocessing, spatial analysis, cartography, verification, and reporting decisions. '
            'They are role guidance, not a fixed workflow or a rewrite of the user request.\n'
            'When the runtime exposes explicit skill-use metadata, make actual skill usage visible through that runtime skill tool output.'
        )

    async def _poll_session(
        self,
        *,
        runtime_session_id: str,
        request: RuntimeSessionRequest,
        emit: Callable[[EventEnvelope], Awaitable[None]],
    ) -> None:
        if self._client is None:
            raise RuntimeError('OpenCode HTTP client is not available')
        seen_message_ids: set[str] = set()
        seen_tool_part_ids: set[str] = set(request.processed_tool_part_ids or set())
        seen_runtime_error_message_ids: set[str] = set()
        attached_dirs = request.attached_data_directories or []
        previous_normalized_messages: list[dict[str, Any]] = []
        normalized_session_status = 'running'
        last_session_title: str | None = None
        last_question_request_id: str | None = None

        async def emit_and_track(envelope: EventEnvelope) -> None:
            nonlocal normalized_session_status
            if envelope.type == 'session.status' and isinstance(envelope.payload, dict):
                status_value = envelope.payload.get('status')
                if isinstance(status_value, str):
                    normalized_session_status = status_value
            await emit(envelope)

        if await self._stream_session_events(
            runtime_session_id=runtime_session_id,
            request=request,
            emit=emit_and_track,
        ):
            return

        saw_runtime_activity = False
        while True:
            session_detail_response = await self._client.get(f'/session/{runtime_session_id}')
            session_detail_response.raise_for_status()
            session_title = self._session_title(session_detail_response.json())
            if session_title and session_title != last_session_title:
                last_session_title = session_title
                await emit_and_track(EventEnvelope(type='session.title', payload={'title': session_title, 'runtime_session_id': runtime_session_id}))

            status_response = await self._client.get('/session/status')
            status_response.raise_for_status()
            status_payload = status_response.json().get(runtime_session_id)
            status_type = status_payload.get('type') if isinstance(status_payload, dict) else status_payload

            messages_response = await self._client.get(f'/session/{runtime_session_id}/message')
            messages_response.raise_for_status()
            messages = messages_response.json()
            if status_type == 'busy' or any(message['info']['role'] == 'assistant' for message in messages):
                saw_runtime_activity = True
            normalized_messages = [self._normalize_message(message) for message in messages]
            await emit_and_track(EventEnvelope(type='session.messages', payload=normalized_messages))
            for updated_message in self._message_updates(previous_normalized_messages, normalized_messages):
                await emit_and_track(EventEnvelope(type='session.message_delta', payload=updated_message))
            previous_normalized_messages = copy.deepcopy(normalized_messages)

            for message in messages:
                message_id = message['info']['id']
                if message_id not in seen_message_ids:
                    seen_message_ids.add(message_id)
                await self._emit_message_side_effects(
                    message=message,
                    attached_dirs=attached_dirs,
                    seen_tool_part_ids=seen_tool_part_ids,
                    emit=emit_and_track,
                    session_context_id=request.geospatial_context_id,
                )
            if await self._emit_runtime_message_errors(
                messages=messages,
                runtime_session_id=runtime_session_id,
                seen_message_ids=seen_runtime_error_message_ids,
                emit=emit_and_track,
            ):
                return

            pending_question = await self._fetch_pending_question(runtime_session_id=runtime_session_id)
            if pending_question is not None and pending_question['id'] != last_question_request_id:
                last_question_request_id = pending_question['id']
                await emit_and_track(EventEnvelope(type='session.question', payload=pending_question))
                await emit_and_track(EventEnvelope(type='session.status', payload={'status': 'waiting_for_input'}))

            if saw_runtime_activity and status_type != 'busy':
                if normalized_session_status in {'waiting_for_input', 'failed'}:
                    return
                if self._has_pending_runtime_continuation(messages):
                    await asyncio.sleep(0.5)
                    continue
                await emit_and_track(EventEnvelope(type='session.status', payload={'status': 'completed'}))
                return
            await asyncio.sleep(0.5)

    async def _stream_session_events(
        self,
        *,
        runtime_session_id: str,
        request: RuntimeSessionRequest,
        emit: Callable[[EventEnvelope], Awaitable[None]],
    ) -> bool:
        if self._client is None:
            raise RuntimeError('OpenCode HTTP client is not available')
        stream = getattr(self._client, 'stream', None)
        if not callable(stream):
            return False

        seen_tool_part_ids: set[str] = set(request.processed_tool_part_ids or set())
        attached_dirs = request.attached_data_directories or []
        state: dict[str, Any] = {
            'normalized_session_status': 'running',
            'last_session_title': None,
            'saw_runtime_activity': False,
            'last_question_request_id': None,
            'active_task_session_ids': set(),
            'task_raw_messages_by_session': {},
            'task_raw_message_order_by_session': {},
            'seen_runtime_error_message_ids': set(),
        }
        raw_messages_by_id: dict[str, dict[str, Any]] = {}
        raw_message_order: list[str] = []

        async def emit_and_track(envelope: EventEnvelope) -> None:
            if envelope.type == 'session.status' and isinstance(envelope.payload, dict):
                status_value = envelope.payload.get('status')
                if isinstance(status_value, str):
                    state['normalized_session_status'] = status_value
            await emit(envelope)

        try:
            async with stream('GET', '/global/event') as response:
                response.raise_for_status()

                session_detail_response = await self._client.get(f'/session/{runtime_session_id}')
                session_detail_response.raise_for_status()
                session_title = self._session_title(session_detail_response.json())
                if session_title:
                    state['last_session_title'] = session_title
                    await emit_and_track(EventEnvelope(type='session.title', payload={'title': session_title, 'runtime_session_id': runtime_session_id}))

                status_response = await self._client.get('/session/status')
                status_response.raise_for_status()
                status_type = self._runtime_session_status_type(status_response.json(), runtime_session_id)

                messages_response = await self._client.get(f'/session/{runtime_session_id}/message')
                messages_response.raise_for_status()
                messages = messages_response.json()
                if status_type == 'busy' or any(message['info']['role'] == 'assistant' for message in messages):
                    state['saw_runtime_activity'] = True
                for message in messages:
                    message_id = str(message['info']['id'])
                    raw_messages_by_id[message_id] = copy.deepcopy(message)
                    raw_message_order.append(message_id)
                normalized_messages = [self._normalize_message(raw_messages_by_id[message_id]) for message_id in raw_message_order]
                await emit_and_track(EventEnvelope(type='session.messages', payload=normalized_messages))
                for normalized_message in normalized_messages:
                    await emit_and_track(EventEnvelope(type='session.message_delta', payload=normalized_message))
                for message in messages:
                    await self._emit_message_side_effects(
                        message=message,
                        attached_dirs=attached_dirs,
                        seen_tool_part_ids=seen_tool_part_ids,
                        emit=emit_and_track,
                        session_context_id=request.geospatial_context_id,
                        stream_state=state,
                    )
                seen_runtime_error_message_ids = state.get('seen_runtime_error_message_ids')
                if isinstance(seen_runtime_error_message_ids, set):
                    if await self._emit_runtime_message_errors(
                        messages=messages,
                        runtime_session_id=runtime_session_id,
                        seen_message_ids=seen_runtime_error_message_ids,
                        emit=emit_and_track,
                    ):
                        return True

                if state['saw_runtime_activity'] and status_type != 'busy':
                    if state['normalized_session_status'] in {'waiting_for_input', 'failed'}:
                        return True
                    if not self._has_pending_runtime_continuation(messages):
                        await emit_and_track(EventEnvelope(type='session.status', payload={'status': 'completed'}))
                        return True

                line_queue: asyncio.Queue[str | BaseException | None] = asyncio.Queue()

                async def read_stream_lines() -> None:
                    try:
                        async for stream_line in response.aiter_lines():
                            await line_queue.put(stream_line)
                    except BaseException as exc:
                        await line_queue.put(exc)
                    finally:
                        await line_queue.put(None)

                reader_task = asyncio.create_task(read_stream_lines())
                try:
                    while True:
                        try:
                            line_or_signal = await asyncio.wait_for(
                                line_queue.get(),
                                timeout=STREAM_SNAPSHOT_POLL_SECONDS,
                            )
                        except asyncio.TimeoutError:
                            if await self._sync_runtime_snapshot_and_maybe_complete(
                                runtime_session_id=runtime_session_id,
                                raw_messages_by_id=raw_messages_by_id,
                                raw_message_order=raw_message_order,
                                state=state,
                                attached_dirs=attached_dirs,
                                seen_tool_part_ids=seen_tool_part_ids,
                                emit=emit_and_track,
                                session_context_id=request.geospatial_context_id,
                            ):
                                return True
                            continue
                        if isinstance(line_or_signal, BaseException):
                            raise line_or_signal
                        if line_or_signal is None:
                            break
                        line = line_or_signal
                        event = self._parse_runtime_global_event(line)
                        if event is None:
                            continue
                        finished = await self._apply_runtime_global_event(
                            runtime_session_id=runtime_session_id,
                            event=event,
                            raw_messages_by_id=raw_messages_by_id,
                            raw_message_order=raw_message_order,
                            state=state,
                            attached_dirs=attached_dirs,
                            seen_tool_part_ids=seen_tool_part_ids,
                            emit=emit_and_track,
                            session_context_id=request.geospatial_context_id,
                        )
                        if finished:
                            return True
                finally:
                    if not reader_task.done():
                        reader_task.cancel()
                        with suppress(asyncio.CancelledError):
                            await reader_task
        except (AttributeError, httpx.HTTPError, json.JSONDecodeError, KeyError, ValueError):
            return False

        return False

    async def _sync_runtime_snapshot_and_maybe_complete(
        self,
        *,
        runtime_session_id: str,
        raw_messages_by_id: dict[str, dict[str, Any]],
        raw_message_order: list[str],
        state: dict[str, Any],
        attached_dirs: list[dict[str, Any]],
        seen_tool_part_ids: set[str],
        emit: Callable[[EventEnvelope], Awaitable[None]],
        session_context_id: str | None = None,
    ) -> bool:
        if self._client is None:
            raise RuntimeError('OpenCode HTTP client is not available')
        status_response = await self._client.get('/session/status')
        status_response.raise_for_status()
        status_type = self._runtime_session_status_type(status_response.json(), runtime_session_id)
        if status_type == 'busy':
            return False

        messages_response = await self._client.get(f'/session/{runtime_session_id}/message')
        messages_response.raise_for_status()
        snapshot = messages_response.json()
        if not isinstance(snapshot, list):
            return False
        messages: list[dict[str, Any]] = [message for message in snapshot if isinstance(message, dict)]
        if not messages:
            return False
        if any(
            isinstance(message.get('info'), dict) and message['info'].get('role') == 'assistant'
            for message in messages
        ):
            state['saw_runtime_activity'] = True

        for message in messages:
            info = message.get('info')
            if not isinstance(info, dict):
                continue
            raw_message_id = info.get('id')
            if not isinstance(raw_message_id, str) or not raw_message_id:
                continue
            raw_messages_by_id[raw_message_id] = copy.deepcopy(message)
            if raw_message_id not in raw_message_order:
                raw_message_order.append(raw_message_id)

        normalized_messages = [
            self._normalize_message(raw_messages_by_id[message_id])
            for message_id in raw_message_order
        ]
        await emit(EventEnvelope(type='session.messages', payload=normalized_messages))
        for normalized_message in normalized_messages:
            await emit(EventEnvelope(type='session.message_delta', payload=normalized_message))
        for message in messages:
            await self._emit_message_side_effects(
                message=message,
                attached_dirs=attached_dirs,
                seen_tool_part_ids=seen_tool_part_ids,
                emit=emit,
                session_context_id=session_context_id,
                stream_state=state,
            )
        seen_runtime_error_message_ids = state.get('seen_runtime_error_message_ids')
        if isinstance(seen_runtime_error_message_ids, set):
            if await self._emit_runtime_message_errors(
                messages=messages,
                runtime_session_id=runtime_session_id,
                seen_message_ids=seen_runtime_error_message_ids,
                emit=emit,
            ):
                return True

        if state['saw_runtime_activity']:
            if state['normalized_session_status'] in {'waiting_for_input', 'failed'}:
                return True
            if not self._has_pending_runtime_continuation(list(raw_messages_by_id.values())):
                await emit(EventEnvelope(type='session.status', payload={'status': 'completed'}))
                return True
        return False

    async def _apply_runtime_global_event(
        self,
        *,
        runtime_session_id: str,
        event: dict[str, Any],
        raw_messages_by_id: dict[str, dict[str, Any]],
        raw_message_order: list[str],
        state: dict[str, Any],
        attached_dirs: list[dict[str, Any]],
        seen_tool_part_ids: set[str],
        emit: Callable[[EventEnvelope], Awaitable[None]],
        session_context_id: str | None = None,
    ) -> bool:
        payload = event.get('payload')
        if not isinstance(payload, dict):
            return False
        event_type = payload.get('type')
        properties = payload.get('properties')
        if not isinstance(event_type, str) or not isinstance(properties, dict):
            return False
        event_session_id = self._runtime_event_session_id(properties)
        if event_session_id != runtime_session_id:
            active_task_session_ids = state.get('active_task_session_ids')
            if isinstance(event_session_id, str) and isinstance(active_task_session_ids, set) and event_session_id in active_task_session_ids:
                await self._apply_task_child_runtime_event(
                    task_session_id=event_session_id,
                    event_type=event_type,
                    properties=properties,
                    state=state,
                    attached_dirs=attached_dirs,
                    seen_tool_part_ids=seen_tool_part_ids,
                    emit=emit,
                    session_context_id=session_context_id,
                )
            return False

        if event_type == 'session.updated':
            info = properties.get('info')
            if isinstance(info, dict):
                session_title = self._session_title(info)
                if session_title and session_title != state['last_session_title']:
                    state['last_session_title'] = session_title
                    await emit(EventEnvelope(type='session.title', payload={'title': session_title, 'runtime_session_id': runtime_session_id}))
            return False

        if event_type == 'session.status':
            status = properties.get('status')
            status_type = status.get('type') if isinstance(status, dict) else status
            if status_type == 'busy':
                state['saw_runtime_activity'] = True
                return False
            if state['saw_runtime_activity']:
                if state['normalized_session_status'] in {'waiting_for_input', 'failed'}:
                    return True
                if self._has_pending_runtime_continuation(list(raw_messages_by_id.values())):
                    return False
                await emit(EventEnvelope(type='session.status', payload={'status': 'completed'}))
                return True
            return False

        if event_type == 'session.idle':
            if state['saw_runtime_activity']:
                if state['normalized_session_status'] in {'waiting_for_input', 'failed'}:
                    return True
                if self._has_pending_runtime_continuation(list(raw_messages_by_id.values())):
                    return False
                await emit(EventEnvelope(type='session.status', payload={'status': 'completed'}))
                return True
            return False

        if event_type == 'question.asked':
            question_payload = self._runtime_question_payload(properties)
            if question_payload is None:
                return False
            state['saw_runtime_activity'] = True
            state['last_question_request_id'] = question_payload['id']
            await emit(EventEnvelope(type='session.question', payload=question_payload))
            await emit(EventEnvelope(type='session.status', payload={'status': 'waiting_for_input'}))
            return False

        updated_message: dict[str, Any] | None = None
        if event_type == 'message.updated':
            info = properties.get('info')
            if isinstance(info, dict):
                updated_message = self._upsert_raw_message(raw_messages_by_id, raw_message_order, info)
                if info.get('role') == 'assistant':
                    state['saw_runtime_activity'] = True
        elif event_type == 'message.part.updated':
            part = properties.get('part')
            if isinstance(part, dict):
                updated_message = self._upsert_raw_message_part(raw_messages_by_id, raw_message_order, part)
        elif event_type == 'message.part.delta':
            message_id = properties.get('messageID')
            part_id = properties.get('partID')
            field = properties.get('field')
            delta = properties.get('delta')
            if isinstance(message_id, str) and isinstance(part_id, str) and isinstance(field, str) and isinstance(delta, str):
                updated_message = self._apply_raw_message_part_delta(raw_messages_by_id, message_id=message_id, part_id=part_id, field=field, delta=delta)

        if updated_message is None:
            return False

        await self._emit_message_side_effects(
            message=updated_message,
            attached_dirs=attached_dirs,
            seen_tool_part_ids=seen_tool_part_ids,
            emit=emit,
            session_context_id=session_context_id,
            stream_state=state,
        )
        if self._should_emit_runtime_message_delta(updated_message):
            await emit(EventEnvelope(type='session.message_delta', payload=self._normalize_message(updated_message)))
        seen_runtime_error_message_ids = state.get('seen_runtime_error_message_ids')
        if isinstance(seen_runtime_error_message_ids, set):
            if await self._emit_runtime_message_errors(
                messages=[updated_message],
                runtime_session_id=runtime_session_id,
                seen_message_ids=seen_runtime_error_message_ids,
                emit=emit,
            ):
                return True
        if (
            self._is_finished_assistant_message(updated_message)
            and state['saw_runtime_activity']
            and state['normalized_session_status'] not in {'waiting_for_input', 'failed'}
            and not self._has_pending_runtime_continuation(list(raw_messages_by_id.values()))
        ):
            await emit(EventEnvelope(type='session.status', payload={'status': 'completed'}))
            return True
        return False

    async def _apply_task_child_runtime_event(
        self,
        *,
        task_session_id: str,
        event_type: str,
        properties: dict[str, Any],
        state: dict[str, Any],
        attached_dirs: list[dict[str, Any]],
        seen_tool_part_ids: set[str],
        emit: Callable[[EventEnvelope], Awaitable[None]],
        session_context_id: str | None = None,
    ) -> None:
        raw_messages_by_session = state.get('task_raw_messages_by_session')
        raw_message_order_by_session = state.get('task_raw_message_order_by_session')
        if not isinstance(raw_messages_by_session, dict) or not isinstance(raw_message_order_by_session, dict):
            return

        raw_messages_by_id = raw_messages_by_session.setdefault(task_session_id, {})
        raw_message_order = raw_message_order_by_session.setdefault(task_session_id, [])
        if not isinstance(raw_messages_by_id, dict) or not isinstance(raw_message_order, list):
            return

        updated_message: dict[str, Any] | None = None
        if event_type == 'message.updated':
            info = properties.get('info')
            if isinstance(info, dict):
                updated_message = self._upsert_raw_message(raw_messages_by_id, raw_message_order, info)
        elif event_type == 'message.part.updated':
            part = properties.get('part')
            if isinstance(part, dict):
                updated_message = self._upsert_raw_message_part(raw_messages_by_id, raw_message_order, part)
        elif event_type == 'message.part.delta':
            message_id = properties.get('messageID')
            part_id = properties.get('partID')
            field = properties.get('field')
            delta = properties.get('delta')
            if isinstance(message_id, str) and isinstance(part_id, str) and isinstance(field, str) and isinstance(delta, str):
                updated_message = self._apply_raw_message_part_delta(raw_messages_by_id, message_id=message_id, part_id=part_id, field=field, delta=delta)

        if updated_message is None:
            return

        info = updated_message.get('info')
        if isinstance(info, dict) and info.get('role') == 'assistant':
            state['saw_runtime_activity'] = True

        await self._emit_message_side_effects(
            message=updated_message,
            attached_dirs=attached_dirs,
            seen_tool_part_ids=seen_tool_part_ids,
            emit=emit,
            session_context_id=session_context_id,
            stream_state=state,
        )
        if not isinstance(info, dict) or info.get('role') == 'user':
            return
        if self._should_emit_runtime_message_delta(updated_message):
            normalized_child_message = self._normalize_message(updated_message)
            normalized_child_message['id'] = f'inline-{normalized_child_message["id"]}-{task_session_id}'
            await emit(EventEnvelope(type='session.message_delta', payload=normalized_child_message))

    def _parse_runtime_global_event(self, line: str) -> dict[str, Any] | None:
        if not line.startswith('data:'):
            return None
        payload = line.removeprefix('data:').strip()
        if not payload:
            return None
        event = json.loads(payload)
        return event if isinstance(event, dict) else None

    def _runtime_event_session_id(self, properties: dict[str, Any]) -> str | None:
        session_id = properties.get('sessionID')
        if isinstance(session_id, str) and session_id.strip():
            return session_id.strip()
        for key in ('info', 'part'):
            nested = properties.get(key)
            if not isinstance(nested, dict):
                continue
            for nested_key in ('sessionID', 'sessionId', 'session_id'):
                nested_session_id = nested.get(nested_key)
                if isinstance(nested_session_id, str) and nested_session_id.strip():
                    return nested_session_id.strip()
        return None

    def _runtime_session_status_type(self, status_payload: object, runtime_session_id: str) -> str | None:
        if not isinstance(status_payload, dict):
            return None
        session_status = status_payload.get(runtime_session_id)
        if isinstance(session_status, dict):
            status_type = session_status.get('type')
            return status_type if isinstance(status_type, str) else None
        return session_status if isinstance(session_status, str) else None

    def _upsert_raw_message(
        self,
        raw_messages_by_id: dict[str, dict[str, Any]],
        raw_message_order: list[str],
        info: dict[str, Any],
    ) -> dict[str, Any]:
        message_id = str(info['id'])
        message = raw_messages_by_id.get(message_id)
        if message is None:
            message = {
                'info': copy.deepcopy(info),
                'parts': [],
            }
            raw_messages_by_id[message_id] = message
            raw_message_order.append(message_id)
            return message
        message['info'] = {
            **message.get('info', {}),
            **copy.deepcopy(info),
        }
        return message

    def _upsert_raw_message_part(
        self,
        raw_messages_by_id: dict[str, dict[str, Any]],
        raw_message_order: list[str],
        part: dict[str, Any],
    ) -> dict[str, Any] | None:
        message_id = part.get('messageID')
        if not isinstance(message_id, str):
            return None
        message = raw_messages_by_id.get(message_id)
        if message is None:
            return None
        parts = message.setdefault('parts', [])
        part_id = str(part.get('id', ''))
        for index, existing in enumerate(parts):
            if existing.get('id') == part_id:
                parts[index] = copy.deepcopy(part)
                return message
        parts.append(copy.deepcopy(part))
        return message

    def _apply_raw_message_part_delta(
        self,
        raw_messages_by_id: dict[str, dict[str, Any]],
        *,
        message_id: str,
        part_id: str,
        field: str,
        delta: str,
    ) -> dict[str, Any] | None:
        message = raw_messages_by_id.get(message_id)
        if message is None:
            return None
        for part in message.get('parts', []):
            if part.get('id') != part_id:
                continue
            current = part.get(field)
            part[field] = f'{current or ""}{delta}' if isinstance(current, str) or current is None else current
            return message
        return None

    def _should_emit_runtime_message_delta(self, message: dict[str, Any]) -> bool:
        if message.get('info', {}).get('role') != 'user':
            return True
        return len(message.get('parts', [])) > 0

    def _has_active_tool_parts(self, messages: list[dict[str, Any]]) -> bool:
        return any(
            self._is_active_tool_part(part)
            for message in messages
            for part in message.get('parts', [])
            if isinstance(part, dict)
        )

    def _has_pending_runtime_continuation(self, messages: list[dict[str, Any]]) -> bool:
        if self._has_active_tool_parts(messages):
            return True
        for message in reversed(messages):
            info = message.get('info')
            if not isinstance(info, dict) or info.get('role') != 'assistant':
                continue
            finish = info.get('finish')
            if finish == 'tool-calls':
                return True
            parts = [part for part in message.get('parts', []) if isinstance(part, dict)]
            if finish is None and not parts:
                return True
            return False
        return False

    def _is_finished_assistant_message(self, message: dict[str, Any]) -> bool:
        info = message.get('info')
        return isinstance(info, dict) and info.get('role') == 'assistant' and info.get('finish') == 'stop'

    def _is_active_tool_part(self, part: dict[str, Any]) -> bool:
        if part.get('type') != 'tool':
            return False
        state = part.get('state')
        if not isinstance(state, dict):
            return False
        status = state.get('status')
        if not isinstance(status, str):
            return False
        return status.strip().lower() in {'pending', 'queued', 'running', 'in_progress', 'started'}

    def _tool_part_ready_for_side_effects(self, part: dict[str, Any]) -> bool:
        if part.get('type') != 'tool' or self._is_active_tool_part(part):
            return False
        state = part.get('state')
        if not isinstance(state, dict):
            return False
        output = state.get('output')
        if output is not None and output != '':
            return True
        status = state.get('status')
        if not isinstance(status, str):
            return False
        return status.strip().lower() in {'completed', 'failed', 'error'}

    def _tool_part_tracking_keys(self, *, message: dict[str, Any], part: dict[str, Any]) -> set[str]:
        part_id = str(part.get('id', '')).strip()
        keys = {part_id} if part_id else set()
        state = part.get('state') if isinstance(part.get('state'), dict) else {}
        signature = {
            'message_id': str(message.get('info', {}).get('id') or message.get('id') or ''),
            'tool': str(part.get('tool', '')),
            'input': state.get('input'),
            'output': state.get('output'),
        }
        keys.add(f'signature:{json.dumps(signature, ensure_ascii=False, sort_keys=True, default=str)}')
        return keys

    async def _emit_message_side_effects(
        self,
        *,
        message: dict[str, Any],
        attached_dirs: list[dict[str, Any]],
        seen_tool_part_ids: set[str],
        emit: Callable[[EventEnvelope], Awaitable[None]],
        session_context_id: str | None = None,
        stream_state: dict[str, Any] | None = None,
    ) -> None:
        for part in message['parts']:
            if part.get('type') != 'tool':
                continue
            part_keys = self._tool_part_tracking_keys(message=message, part=part)
            if part_keys & seen_tool_part_ids:
                continue
            tool_name = self._canonical_tool_name(part)
            if tool_name == 'task' and self._is_active_tool_part(part):
                await self._emit_task_tool_side_effects(
                    parent_message=message,
                    part=part,
                    attached_dirs=attached_dirs,
                    seen_tool_part_ids=seen_tool_part_ids,
                    emit=emit,
                    session_context_id=session_context_id,
                    stream_state=stream_state,
                )
                continue
            if not self._tool_part_ready_for_side_effects(part):
                continue
            if tool_name == 'task':
                task_inlined = await self._emit_task_tool_side_effects(
                    parent_message=message,
                    part=part,
                    attached_dirs=attached_dirs,
                    seen_tool_part_ids=seen_tool_part_ids,
                    emit=emit,
                    session_context_id=session_context_id,
                    stream_state=stream_state,
                )
                if task_inlined:
                    seen_tool_part_ids.update(part_keys)
                if task_inlined:
                    continue
            output = part.get('state', {}).get('output')
            payload = self._tool_output_payload(output)
            if payload is None and tool_name not in {'get_session_context', 'record_run_evidence', 'update_todos'}:
                continue
            seen_tool_part_ids.update(part_keys)
            tool_meta = self._tool_meta_for_part(part)
            if tool_name != 'record_run_evidence':
                await emit(
                    EventEnvelope(
                        type='session.timeline_entry',
                        payload={
                            'id': f'timeline-{uuid4().hex[:8]}',
                            'kind': 'status',
                            'text': f'工具执行：{tool_meta["tool_label"]}',
                            'created_at': datetime.now(UTC).isoformat(),
                        },
                    )
                )
            if payload is not None:
                payload.setdefault('attached_data_directories', attached_dirs)
            if tool_name == 'record_run_evidence':
                if payload is not None:
                    artifact = payload.get('artifact')
                    if isinstance(artifact, dict):
                        await emit(EventEnvelope(type='session.artifact', payload=artifact))
                    evidence = payload.get('evidence')
                    if isinstance(evidence, dict):
                        await self._emit_evidence_timeline_entry(record=evidence, emit=emit)
                    failed = payload.get('status') == 'failed'
                    failure_summary = str(payload.get('summary') or '证据记录失败。')
                else:
                    await self._emit_registered_artifacts_from_store(session_context_id=session_context_id, emit=emit)
                    await self._emit_registered_evidence_from_store(session_context_id=session_context_id, emit=emit)
                    failed = self._tool_output_is_error(output)
                    failure_summary = '证据记录失败。'
                if failed:
                    await emit(EventEnvelope(type='session.timeline_entry', payload={
                        'id': f'timeline-{uuid4().hex[:8]}',
                        'kind': 'status',
                        'text': failure_summary,
                        'created_at': datetime.now(UTC).isoformat(),
                    }))
                    await emit(EventEnvelope(type='session.issue', payload=self._tool_failure_issue_payload(
                        title='证据记录失败',
                        detail=failure_summary,
                        recoverable=True,
                    )))
            if tool_name == 'update_todos':
                if self._tool_output_is_error(output):
                    await emit(EventEnvelope(type='session.timeline_entry', payload={
                        'id': f'timeline-{uuid4().hex[:8]}',
                        'kind': 'status',
                        'text': '待办更新失败。',
                        'created_at': datetime.now(UTC).isoformat(),
                    }))
                    await emit(EventEnvelope(type='session.issue', payload=self._tool_failure_issue_payload(
                        title='待办更新失败',
                        detail='待办更新工具返回错误，当前任务列表可能不是最新状态。',
                        recoverable=True,
                    )))
                    continue
                input_payload = part.get('state', {}).get('input')
                plan_payload = payload if payload is not None else input_payload
                if isinstance(plan_payload, dict):
                    plan_group = self._plan_group_payload(message=message, payload=plan_payload)
                    if plan_group['entries']:
                        await emit(EventEnvelope(type='session.plan_group', payload=plan_group))

    async def _emit_registered_artifacts_from_store(
        self,
        *,
        session_context_id: str | None,
        emit: Callable[[EventEnvelope], Awaitable[None]],
    ) -> None:
        if session_context_id is None:
            return
        context = SessionStore(settings=self.settings).load_geospatial_session_context(session_context_id)
        if context is None:
            return
        for artifact in context.artifacts:
            await emit(EventEnvelope(type='session.artifact', payload=artifact.model_dump(mode='json')))

    async def _emit_registered_evidence_from_store(
        self,
        *,
        session_context_id: str | None,
        emit: Callable[[EventEnvelope], Awaitable[None]],
    ) -> None:
        if session_context_id is None:
            return
        store = SessionStore(settings=self.settings)
        context = store.load_geospatial_session_context(session_context_id)
        if context is None:
            return
        for record in store.list_geospatial_evidence_records(context.id):
            await self._emit_evidence_timeline_entry(record=record, emit=emit)

    async def _emit_evidence_timeline_entry(
        self,
        *,
        record: dict[str, object],
        emit: Callable[[EventEnvelope], Awaitable[None]],
    ) -> None:
        record_type = str(record.get('record_type') or '')
        if record_type == 'artifact':
            return
        record_id = str(record.get('id') or uuid4().hex[:8])
        title = str(record.get('title') or '运行证据')
        description = record.get('description')
        category = record.get('category')
        data = record.get('data')
        provenance = record.get('provenance')
        created_at = str(record.get('created_at') or datetime.now(UTC).isoformat())
        await emit(EventEnvelope(type='session.timeline_entry', payload={
            'id': f'evidence-{record_id}',
            'kind': 'evidence',
            'text': title,
            'title': title,
            'detail': str(description) if description is not None else None,
            'record_type': record_type,
            'category': str(category) if category is not None else None,
            'evidence_record_id': record_id,
            'created_at': created_at,
            'data': data if isinstance(data, dict) else {},
            'provenance': provenance if isinstance(provenance, dict) else {},
        }))

    def _tool_output_is_error(self, output: object) -> bool:
        return isinstance(output, str) and output.lstrip().startswith('<error ')

    def _tool_failure_issue_payload(self, *, title: str, detail: str, recoverable: bool) -> dict[str, Any]:
        return {
            'id': f'issue-{uuid4().hex[:8]}',
            'type': 'tool_failure',
            'severity': 'error',
            'source': 'mcp',
            'title': title,
            'detail': detail,
            'created_at': datetime.now(UTC).isoformat(),
            'recoverable': recoverable,
        }

    async def _emit_runtime_message_errors(
        self,
        *,
        messages: list[dict[str, Any]],
        runtime_session_id: str,
        seen_message_ids: set[str],
        emit: Callable[[EventEnvelope], Awaitable[None]],
    ) -> bool:
        emitted_error = False
        for message in messages:
            info = message.get('info')
            if not isinstance(info, dict):
                continue
            message_id = info.get('id')
            if not isinstance(message_id, str) or message_id in seen_message_ids:
                continue
            detail = self._runtime_message_error_detail(message)
            if detail is None:
                continue
            seen_message_ids.add(message_id)
            issue = self._runtime_message_error_issue_payload(
                detail=detail,
                runtime_session_id=runtime_session_id,
                message_id=message_id,
            )
            await emit(EventEnvelope(type='session.issue', payload=issue))
            emitted_error = True
        if emitted_error:
            await emit(EventEnvelope(type='session.status', payload={'status': 'failed'}))
        return emitted_error

    def _runtime_message_error_issue_payload(
        self,
        *,
        detail: str,
        runtime_session_id: str,
        message_id: str,
    ) -> dict[str, Any]:
        return {
            'id': f'issue-{uuid4().hex[:8]}',
            'type': 'runtime_error',
            'severity': 'error',
            'source': 'opencode',
            'title': 'OpenCode 模型调用失败',
            'detail': detail,
            'created_at': datetime.now(UTC).isoformat(),
            'runtime_session_id': runtime_session_id,
            'message_id': message_id,
            'recoverable': True,
        }

    def _runtime_message_error_detail(self, message: dict[str, Any]) -> str | None:
        info = message.get('info')
        if not isinstance(info, dict):
            return None
        error = info.get('error')
        if not isinstance(error, dict):
            return None

        parts: list[str] = []
        name = error.get('name')
        if isinstance(name, str) and name.strip():
            parts.append(name.strip())

        data = error.get('data')
        if isinstance(data, dict):
            error_message = data.get('message')
            if isinstance(error_message, str) and error_message.strip():
                parts.append(error_message.strip())
            status_code = data.get('statusCode')
            if isinstance(status_code, str) and status_code.strip():
                parts.append(f'status_code={status_code.strip()}')
            elif isinstance(status_code, int) and not isinstance(status_code, bool):
                parts.append(f'status_code={status_code}')
            metadata = data.get('metadata')
            if isinstance(metadata, dict):
                url = metadata.get('url')
                if isinstance(url, str) and url.strip():
                    parts.append(f'url={url.strip()}')
        elif data is not None:
            parts.append(str(data))

        return '; '.join(parts) or 'OpenCode message includes an error payload.'

    async def _emit_task_tool_side_effects(
        self,
        *,
        parent_message: dict[str, Any],
        part: dict[str, Any],
        attached_dirs: list[dict[str, Any]],
        seen_tool_part_ids: set[str],
        emit: Callable[[EventEnvelope], Awaitable[None]],
        session_context_id: str | None = None,
        stream_state: dict[str, Any] | None = None,
    ) -> bool:
        if self._client is None:
            return False
        task_session_id = self._task_session_id_from_part(part)
        if not task_session_id:
            return False
        self._track_task_session(stream_state=stream_state, task_session_id=task_session_id)

        try:
            response = await self._client.get(f'/session/{task_session_id}/message')
            response.raise_for_status()
            raw_child_messages = response.json()
        except Exception:
            return False
        if not isinstance(raw_child_messages, list):
            return False
        self._track_task_session(stream_state=stream_state, task_session_id=task_session_id, raw_child_messages=raw_child_messages)

        await emit(
            EventEnvelope(
                type='session.message_delta',
                payload=self._inline_subtask_message(
                    parent_message=parent_message,
                    part=part,
                    task_session_id=task_session_id,
                    raw_child_messages=raw_child_messages,
                ),
            )
        )

        for child_message in raw_child_messages:
            if not isinstance(child_message, dict):
                continue
            info = child_message.get('info')
            if not isinstance(info, dict) or info.get('role') == 'user':
                continue

            normalized_child_message = self._normalize_message(child_message)
            normalized_child_message['id'] = f'inline-{normalized_child_message["id"]}-{task_session_id}'
            await emit(EventEnvelope(type='session.message_delta', payload=normalized_child_message))
            await self._emit_message_side_effects(
                message=child_message,
                attached_dirs=attached_dirs,
                seen_tool_part_ids=seen_tool_part_ids,
                emit=emit,
                session_context_id=session_context_id,
                stream_state=stream_state,
            )
        return True

    def _normalize_message(self, message: dict[str, Any]) -> dict[str, Any]:
        return {
            'id': message['info']['id'],
            'role': message['info']['role'],
            'agent': message['info'].get('agent'),
            'created_at': datetime.fromtimestamp(message['info']['time']['created'] / 1000, tz=UTC).isoformat(),
            'parts': [self._normalize_part(part) for part in message.get('parts', [])],
        }

    def _message_updates(self, previous_messages: list[dict[str, Any]], current_messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        previous_by_id = {message['id']: message for message in previous_messages}
        updates: list[dict[str, Any]] = []
        for message in current_messages:
            previous = previous_by_id.get(message['id'])
            if previous != message:
                updates.append(copy.deepcopy(message))
        return updates

    def _session_title(self, payload: object) -> str | None:
        if not isinstance(payload, dict):
            return None
        title = payload.get('title')
        if not isinstance(title, str):
            return None
        normalized = title.strip()
        return normalized or None

    def _plan_group_payload(self, *, message: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        agent = str(message.get('info', {}).get('agent') or 'geo')
        identity = load_agent_identity_map().get(agent)
        entries: list[dict[str, str]] = []
        allowed_statuses = {'pending', 'in_progress', 'completed', 'blocked'}
        raw_entries = payload.get('entries', [])
        if not isinstance(raw_entries, list):
            raw_entries = payload.get('todos', [])
        if not isinstance(raw_entries, list):
            raw_entries = []
        for index, entry in enumerate(raw_entries, start=1):
            if not isinstance(entry, dict):
                continue
            raw_label = entry.get('content') if isinstance(entry.get('content'), str) else entry.get('label')
            if not isinstance(raw_label, str) or not raw_label.strip():
                continue
            raw_status = entry.get('status')
            status = raw_status if raw_status in allowed_statuses else 'pending'
            raw_id = entry.get('id')
            entry_id = raw_id.strip() if isinstance(raw_id, str) and raw_id.strip() else f'plan-{index}'
            entries.append({'id': entry_id, 'label': raw_label.strip(), 'status': str(status)})
        return {
            'id': agent,
            'agent': agent,
            'label': identity.label if identity is not None else agent,
            'entries': entries,
            'updated_at': datetime.now(UTC).isoformat(),
        }

    def _normalize_part(self, part: dict[str, Any]) -> dict[str, Any]:
        normalized = copy.deepcopy(part)
        if normalized.get('type') != 'tool':
            return normalized
        state = normalized.setdefault('state', {})
        if not isinstance(state, dict):
            return normalized
        meta = state.get('meta')
        if not isinstance(meta, dict):
            meta = {}
        meta.update(self._tool_meta_for_part(normalized))
        state['meta'] = meta
        return normalized

    def _tool_meta_for_part(self, part: dict[str, Any]) -> dict[str, str]:
        raw_tool = str(part.get('tool', ''))
        identity = resolve_tool_identity(raw_tool)
        label = identity.label
        if identity.name == 'record_run_evidence':
            label = self._record_run_evidence_tool_label(part) or label
        return {
            'raw_tool': raw_tool,
            'tool_name': identity.name,
            'tool_family': identity.family,
            'tool_label': label,
            'tool_summary': identity.summary,
            'tool_icon': identity.icon,
        }

    def _record_run_evidence_tool_label(self, part: dict[str, Any]) -> str | None:
        state = part.get('state')
        if not isinstance(state, dict):
            return None
        input_payload = state.get('input')
        if not isinstance(input_payload, dict):
            return None
        record_type = str(input_payload.get('record_type') or '')
        if record_type == 'artifact':
            artifact_stage = str(input_payload.get('artifact_stage') or '')
            if artifact_stage == 'final':
                return '记录最终产物'
            if artifact_stage == 'intermediate':
                return '记录中间产物'
            return '记录产物'
        return EVIDENCE_TOOL_LABELS.get(record_type)

    def _canonical_tool_name(self, part: dict[str, Any]) -> str:
        return canonical_tool_name(str(part.get('tool', '')))

    def _tool_output_payload(self, output: object) -> dict[str, Any] | None:
        if isinstance(output, dict):
            return copy.deepcopy(output)
        if not isinstance(output, str):
            return None
        try:
            payload = json.loads(output)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        return payload

    def _task_session_id_from_part(self, part: dict[str, Any]) -> str | None:
        state = part.get('state')
        if not isinstance(state, dict):
            return None
        task_session_id = self._task_session_id_from_output(state.get('output'))
        if task_session_id:
            return task_session_id
        metadata = state.get('metadata')
        if isinstance(metadata, dict):
            task_session_id = self._first_task_session_id(metadata)
            if task_session_id:
                return task_session_id
        return self._first_task_session_id(state)

    def _task_session_id_from_output(self, output: object) -> str | None:
        if isinstance(output, dict):
            for key in ('task_id', 'session_id', 'sessionId', 'sessionID'):
                value = output.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            return None
        if not isinstance(output, str):
            return None
        for line in output.splitlines():
            stripped = line.strip()
            if not stripped.startswith('task_id:'):
                continue
            session_id = stripped.removeprefix('task_id:').strip().split(' ', maxsplit=1)[0]
            return session_id or None
        return None

    def _first_task_session_id(self, payload: dict[str, Any]) -> str | None:
        for key in ('task_id', 'taskId', 'session_id', 'sessionId', 'sessionID'):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _track_task_session(
        self,
        *,
        stream_state: dict[str, Any] | None,
        task_session_id: str,
        raw_child_messages: list[Any] | None = None,
    ) -> None:
        if stream_state is None:
            return
        active_task_session_ids = stream_state.get('active_task_session_ids')
        if isinstance(active_task_session_ids, set):
            active_task_session_ids.add(task_session_id)
        if raw_child_messages is None:
            return

        raw_messages_by_session = stream_state.get('task_raw_messages_by_session')
        raw_message_order_by_session = stream_state.get('task_raw_message_order_by_session')
        if not isinstance(raw_messages_by_session, dict) or not isinstance(raw_message_order_by_session, dict):
            return
        raw_messages_by_id = raw_messages_by_session.setdefault(task_session_id, {})
        raw_message_order = raw_message_order_by_session.setdefault(task_session_id, [])
        if not isinstance(raw_messages_by_id, dict) or not isinstance(raw_message_order, list):
            return
        for child_message in raw_child_messages:
            if not isinstance(child_message, dict):
                continue
            info = child_message.get('info')
            if not isinstance(info, dict):
                continue
            message_id = info.get('id')
            if not isinstance(message_id, str):
                continue
            raw_messages_by_id[message_id] = copy.deepcopy(child_message)
            if message_id not in raw_message_order:
                raw_message_order.append(message_id)

    def _inline_subtask_message(
        self,
        *,
        parent_message: dict[str, Any],
        part: dict[str, Any],
        task_session_id: str,
        raw_child_messages: list[Any],
    ) -> dict[str, Any]:
        input_state = part.get('state', {}).get('input')
        input_payload = input_state if isinstance(input_state, dict) else {}
        first_child_user = next(
            (
                child_message for child_message in raw_child_messages
                if isinstance(child_message, dict)
                and isinstance(child_message.get('info'), dict)
                and child_message['info'].get('role') == 'user'
            ),
            None,
        )
        first_child_assistant = next(
            (
                child_message for child_message in raw_child_messages
                if isinstance(child_message, dict)
                and isinstance(child_message.get('info'), dict)
                and child_message['info'].get('role') == 'assistant'
            ),
            None,
        )
        prompt = input_payload.get('prompt')
        if not isinstance(prompt, str) or not prompt.strip():
            prompt = self._first_text_part_text(first_child_user)
        description = input_payload.get('description')
        if not isinstance(description, str):
            description = None
        child_agent = input_payload.get('subagent_type')
        if not isinstance(child_agent, str) or not child_agent.strip():
            child_agent = self._message_agent(first_child_assistant) or self._message_agent(first_child_user)

        created_at = self._message_created_at(first_child_user) or self._message_created_at(first_child_assistant) or self._message_created_at(parent_message) or datetime.now(UTC)
        return {
            'id': f'inline-subtask-{task_session_id}',
            'role': 'system',
            'agent': None,
            'created_at': created_at.isoformat(),
            'parts': [
                {
                    'type': 'subtask',
                    'state': {
                        'task_session_id': task_session_id,
                        'parent_agent': self._message_agent(parent_message),
                        'child_agent': child_agent,
                        'description': description,
                        'prompt': prompt,
                    },
                }
            ],
        }

    def _first_text_part_text(self, message: object) -> str | None:
        if not isinstance(message, dict):
            return None
        parts = message.get('parts')
        if not isinstance(parts, list):
            return None
        for part in parts:
            if not isinstance(part, dict) or part.get('type') != 'text':
                continue
            text = part.get('text')
            if isinstance(text, str) and text.strip():
                return text
        return None

    def _message_created_at(self, message: object) -> datetime | None:
        if not isinstance(message, dict):
            return None
        info = message.get('info')
        if not isinstance(info, dict):
            return None
        time = info.get('time')
        if not isinstance(time, dict):
            return None
        created = time.get('created')
        if not isinstance(created, int | float):
            return None
        return datetime.fromtimestamp(created / 1000, tz=UTC)

    def _message_agent(self, message: object) -> str | None:
        if not isinstance(message, dict):
            return None
        info = message.get('info')
        if not isinstance(info, dict):
            return None
        agent = info.get('agent')
        if not isinstance(agent, str) or not agent.strip():
            return None
        return agent

    async def _fetch_pending_question(self, *, runtime_session_id: str) -> dict[str, Any] | None:
        if self._client is None:
            return None
        for path in ('/question', '/question/'):
            try:
                response = await self._client.get(path)
                response.raise_for_status()
                payload = response.json()
            except Exception:
                continue
            if not isinstance(payload, list):
                continue
            for item in payload:
                if not isinstance(item, dict):
                    continue
                if item.get('sessionID') != runtime_session_id:
                    continue
                question_payload = self._runtime_question_payload(item)
                if question_payload is not None:
                    return question_payload
        return None

    def _runtime_question_payload(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        request_id = payload.get('requestID') or payload.get('id')
        raw_questions = payload.get('questions')
        if not isinstance(request_id, str) or not isinstance(raw_questions, list):
            return None
        questions: list[dict[str, Any]] = []
        for index, raw_question in enumerate(raw_questions):
            if not isinstance(raw_question, dict):
                continue
            question_text = str(raw_question.get('question') or '').strip()
            if not question_text:
                continue
            header = str(raw_question.get('header') or f'问题 {index + 1}').strip() or f'问题 {index + 1}'
            options: list[dict[str, Any]] = []
            for raw_option in raw_question.get('options', []):
                if isinstance(raw_option, str):
                    label = raw_option.strip()
                    if label:
                        options.append({'label': label, 'description': None})
                    continue
                if not isinstance(raw_option, dict):
                    continue
                label = str(raw_option.get('label') or '').strip()
                if not label:
                    continue
                description = raw_option.get('description')
                options.append({
                    'label': label,
                    'description': str(description).strip() if isinstance(description, str) and description.strip() else None,
                })
            questions.append(
                {
                    'header': header,
                    'question': question_text,
                    'options': options,
                }
            )
        if not questions:
            return None
        return {
            'id': request_id,
            'prompt': questions[0]['question'],
            'source': 'runtime',
            'questions': questions,
        }

    def _session_trace_path(self, runtime_session_id: str) -> Path:
        return self._server_root / 'runtime-traces' / runtime_session_id
