from __future__ import annotations

import asyncio
import json
from pathlib import Path
import signal
import sqlite3

import httpx
import pytest

from app.config import Settings
from app.models import RuntimeStatus
from app.services.runtime import RuntimeManager


class StubRuntimeClient:
    def __init__(self, status: RuntimeStatus) -> None:
        self._status = status
        self.started = False

    @property
    def is_ready(self) -> bool:
        return self._status.status == 'ready'

    async def start(self) -> None:
        self.started = True
        return None

    async def stop(self) -> None:
        return None

    def status(self) -> RuntimeStatus:
        return self._status


class FakeRuntimeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self.payload


class FakeRuntimeHttpClient:
    def __init__(
        self,
        *,
        statuses: list[object],
        message_snapshots: list[list[dict[str, object]]],
        session_details: list[dict[str, object]] | None = None,
        questions: list[object] | None = None,
    ) -> None:
        self._statuses = list(statuses)
        self._message_snapshots = list(message_snapshots)
        self._session_details = list(session_details or [])
        self._questions = list(questions or [])

    async def get(self, path: str) -> FakeRuntimeResponse:
        if path == '/session/status':
            return FakeRuntimeResponse(self._statuses.pop(0))
        if path == '/question':
            return FakeRuntimeResponse(self._questions.pop(0))
        if path.startswith('/session/') and path.endswith('/message'):
            return FakeRuntimeResponse(self._message_snapshots.pop(0))
        if path.startswith('/session/'):
            if self._session_details:
                return FakeRuntimeResponse(self._session_details.pop(0))
            session_id = path.removeprefix('/session/')
            return FakeRuntimeResponse({'id': session_id, 'title': 'Runtime session'})
        raise AssertionError(f'unexpected path: {path}')


class FakeTaskTranscriptHttpClient:
    def __init__(self, *, child_messages: list[dict[str, object]]) -> None:
        self.child_messages = child_messages
        self.get_paths: list[str] = []

    async def get(self, path: str) -> FakeRuntimeResponse:
        self.get_paths.append(path)
        if path == '/session/ses_child_task/message':
            return FakeRuntimeResponse(self.child_messages)
        raise AssertionError(f'unexpected path: {path}')


class FakeRuntimeEventStream:
    def __init__(self, lines: list[str]) -> None:
        self._lines = list(lines)

    async def __aenter__(self) -> 'FakeRuntimeEventStream':
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    def raise_for_status(self) -> None:
        return None

    async def aiter_lines(self):
        for line in self._lines:
            yield line
            await asyncio.sleep(0)


class FakeBlockingRuntimeEventStream(FakeRuntimeEventStream):
    async def aiter_lines(self):
        for line in self._lines:
            yield line
            await asyncio.sleep(0)
        await asyncio.Future()


class FakeStreamingRuntimeHttpClient(FakeRuntimeHttpClient):
    def __init__(self, *, statuses: list[object], message_snapshots: list[list[dict[str, object]]], session_details: list[dict[str, object]], global_event_lines: list[str]) -> None:
        super().__init__(statuses=statuses, message_snapshots=message_snapshots, session_details=session_details)
        self._global_event_lines = list(global_event_lines)

    def stream(self, method: str, path: str) -> FakeRuntimeEventStream:
        if method != 'GET' or path != '/global/event':
            raise AssertionError(f'unexpected stream request: {method} {path}')
        return FakeRuntimeEventStream(self._global_event_lines)


class FakeBlockingStreamingRuntimeHttpClient(FakeStreamingRuntimeHttpClient):
    def stream(self, method: str, path: str) -> FakeBlockingRuntimeEventStream:
        if method != 'GET' or path != '/global/event':
            raise AssertionError(f'unexpected stream request: {method} {path}')
        return FakeBlockingRuntimeEventStream(self._global_event_lines)


class FakeRunSessionHttpClient:
    def __init__(self) -> None:
        self.posts: list[tuple[str, object]] = []

    async def post(self, path: str, json: object) -> FakeRuntimeResponse:
        self.posts.append((path, json))
        if path == '/session':
            return FakeRuntimeResponse({'id': 'runtime-session-1'})
        if path == '/session/runtime-session-1/prompt_async':
            return FakeRuntimeResponse({'accepted': True})
        raise AssertionError(f'unexpected path: {path}')


class FakeAbortSessionHttpClient:
    def __init__(self) -> None:
        self.posts: list[tuple[str, object | None]] = []

    async def post(self, path: str, json: object | None = None) -> FakeRuntimeResponse:
        self.posts.append((path, json))
        if path == '/session/runtime-session-1/abort':
            return FakeRuntimeResponse(True)
        raise AssertionError(f'unexpected path: {path}')


class FakeStaleAbortSessionHttpClient(FakeAbortSessionHttpClient):
    async def post(self, path: str, json: object | None = None) -> FakeRuntimeResponse:
        self.posts.append((path, json))
        if path == '/session/runtime-session-1/abort':
            response = FakeRuntimeResponse({'error': 'missing'})
            response.status_code = 404

            def raise_for_status() -> None:
                request = httpx.Request('POST', path)
                reply = httpx.Response(status_code=404, request=request)
                raise httpx.HTTPStatusError('stale runtime session', request=request, response=reply)

            response.raise_for_status = raise_for_status  # type: ignore[method-assign]
            return response
        raise AssertionError(f'unexpected path: {path}')


class FakeRetryingRunSessionHttpClient:
    def __init__(self) -> None:
        self.posts: list[tuple[str, object]] = []

    async def post(self, path: str, json: object) -> FakeRuntimeResponse:
        self.posts.append((path, json))
        if path == '/session/stale-session/prompt_async':
            response = FakeRuntimeResponse({'error': 'missing'})
            response.status_code = 404

            def raise_for_status() -> None:
                request = httpx.Request('POST', path)
                reply = httpx.Response(status_code=404, request=request)
                raise httpx.HTTPStatusError('stale runtime session', request=request, response=reply)

            response.raise_for_status = raise_for_status  # type: ignore[method-assign]
            return response
        if path == '/session':
            return FakeRuntimeResponse({'id': 'runtime-session-2'})
        if path == '/session/runtime-session-2/prompt_async':
            return FakeRuntimeResponse({'accepted': True})
        raise AssertionError(f'unexpected path: {path}')


class FakeQuestionReplyHttpClient:
    def __init__(self) -> None:
        self.posts: list[tuple[str, object]] = []

    async def post(self, path: str, json: object) -> FakeRuntimeResponse:
        self.posts.append((path, json))
        if path == '/question/question-request-1/reply':
            return FakeRuntimeResponse({'accepted': True})
        raise AssertionError(f'unexpected path: {path}')


class FakeOpenCodeProcess:
    def __init__(self, *, pid: int = 2468, returncode: int | None = None) -> None:
        self.pid = pid
        self.returncode = returncode
        self.terminated = False
        self.killed = False

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True

    async def wait(self) -> int:
        if self.returncode is None:
            self.returncode = 0
        return self.returncode


class FakeClosableRuntimeHttpClient:
    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_runtime_manager_reports_missing_provider_as_not_ready(tmp_path: Path) -> None:
    settings = Settings(state_dir=tmp_path / '.state', glm_api_key=None)
    runtime = RuntimeManager(settings=settings)

    status = await runtime.ensure_ready()

    assert status.status == 'stopped'
    assert status.detail is not None
    assert 'provider' in status.detail.lower()


@pytest.mark.asyncio
async def test_runtime_manager_reports_missing_deepseek_provider_as_not_ready(tmp_path: Path) -> None:
    settings = Settings(state_dir=tmp_path / '.state', model_provider='deepseek', deepseek_api_key=None)
    runtime = RuntimeManager(settings=settings)

    status = await runtime.ensure_ready()

    assert status.status == 'stopped'
    assert status.detail is not None
    assert 'provider' in status.detail.lower()


@pytest.mark.asyncio
async def test_runtime_manager_uses_injected_real_runtime_client_status(tmp_path: Path) -> None:
    settings = Settings(state_dir=tmp_path / '.state', glm_api_key='test-key')
    runtime = RuntimeManager(
        settings=settings,
        runtime_client=StubRuntimeClient(RuntimeStatus(status='ready', label='opencode-runtime', detail='server ready')),
    )

    status = await runtime.ensure_ready()

    assert status.status == 'ready'
    assert status.label == 'opencode-runtime'
    assert status.detail == 'server ready'


@pytest.mark.asyncio
async def test_runtime_manager_starts_runtime_while_geospatial_provisioning_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import runtime as runtime_module

    release_provisioning = asyncio.Event()

    def fake_package_readiness(_settings: Settings) -> dict[str, object]:
        return {
            'status': 'not_ready',
            'python_version': '3.12',
            'project_path': str(tmp_path / 'geo-python'),
            'environment_path': str(tmp_path / 'geo-python' / '.venv'),
            'uv_bin': 'uv',
            'packages': [],
        }

    async def fake_provisioning(_settings: Settings, on_log) -> dict[str, object]:
        await on_log('Resolving geospatial packages')
        await release_provisioning.wait()
        return {
            'status': 'ready',
            'progress': 1.0,
            'logs': ['Resolving geospatial packages', 'Installed geospatial packages'],
            'returncode': 0,
        }

    monkeypatch.setattr(runtime_module, 'package_readiness', fake_package_readiness)
    monkeypatch.setattr(runtime_module, 'provision_geospatial_python_environment_streaming', fake_provisioning)
    runtime_client = StubRuntimeClient(RuntimeStatus(status='ready', label='opencode-runtime', detail='server ready'))
    runtime = RuntimeManager(
        settings=Settings(state_dir=tmp_path / '.state', glm_api_key='test-key', geospatial_python_auto_provision=True),
        runtime_client=runtime_client,
    )

    await asyncio.wait_for(runtime.start(), timeout=0.2)
    await asyncio.sleep(0)

    status = runtime.geospatial_environment_status()
    assert runtime_client.started is True
    assert status['status'] == 'provisioning'
    assert 'Resolving geospatial packages' in status['logs']

    release_provisioning.set()
    final_status = await runtime.ensure_geospatial_environment()
    assert final_status['status'] == 'ready'


@pytest.mark.asyncio
async def test_runtime_manager_start_returns_before_geospatial_readiness_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import runtime as runtime_module

    start_returned = False

    def fake_package_readiness(_settings: Settings) -> dict[str, object]:
        if not start_returned:
            raise AssertionError('geospatial package validation blocked runtime startup')
        return {
            'status': 'ready',
            'python_version': '3.12',
            'project_path': str(tmp_path / 'geo-python'),
            'environment_path': str(tmp_path / 'geo-python' / '.venv'),
            'uv_bin': 'uv',
            'packages': [],
        }

    async def fake_provisioning(_settings: Settings, on_log) -> dict[str, object]:
        await on_log('Managed geospatial Python environment is ready')
        return {
            'status': 'ready',
            'progress': 1.0,
            'logs': ['Managed geospatial Python environment is ready'],
            'returncode': 0,
        }

    monkeypatch.setattr(runtime_module, 'package_readiness', fake_package_readiness)
    monkeypatch.setattr(runtime_module, 'provision_geospatial_python_environment_streaming', fake_provisioning)
    runtime = RuntimeManager(
        settings=Settings(state_dir=tmp_path / '.state', glm_api_key='test-key', geospatial_python_auto_provision=True),
        runtime_client=StubRuntimeClient(RuntimeStatus(status='ready', label='opencode-runtime', detail='server ready')),
    )

    await asyncio.wait_for(runtime.start(), timeout=0.2)
    start_returned = True
    await asyncio.sleep(0)

    assert runtime.status().status == 'ready'

    await runtime.stop()


@pytest.mark.asyncio
async def test_opencode_runtime_starts_managed_server_in_process_group(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.agent_runtime import OpenCodeAgentRuntimeClient

    captured_kwargs: dict[str, object] = {}

    async def fake_create_subprocess_exec(*_args: object, **kwargs: object) -> FakeOpenCodeProcess:
        captured_kwargs.update(kwargs)
        return FakeOpenCodeProcess()

    async def fake_wait_for_health(_runtime: OpenCodeAgentRuntimeClient) -> None:
        return None

    monkeypatch.setattr(asyncio, 'create_subprocess_exec', fake_create_subprocess_exec)
    monkeypatch.setattr(OpenCodeAgentRuntimeClient, '_wait_for_health', fake_wait_for_health)
    runtime = OpenCodeAgentRuntimeClient(Settings(app_support_dir=tmp_path / 'geo-agent', glm_api_key='test-key'))

    await runtime.start()

    assert captured_kwargs['start_new_session'] is True
    assert runtime._process_group_id == 2468

    await runtime.stop()


@pytest.mark.asyncio
async def test_opencode_runtime_stop_terminates_managed_process_group_after_parent_exit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import agent_runtime
    from app.services.agent_runtime import OpenCodeAgentRuntimeClient

    signals: list[tuple[int, int]] = []

    def fake_killpg(process_group_id: int, requested_signal: int) -> None:
        if requested_signal == 0:
            raise ProcessLookupError
        signals.append((process_group_id, requested_signal))

    monkeypatch.setattr(agent_runtime.os, 'killpg', fake_killpg)
    runtime = OpenCodeAgentRuntimeClient(Settings(app_support_dir=tmp_path / 'geo-agent', glm_api_key='test-key'))
    runtime.process = FakeOpenCodeProcess(returncode=0)  # type: ignore[assignment]
    runtime._process_group_id = 2468
    runtime._client = FakeClosableRuntimeHttpClient()  # type: ignore[assignment]

    await runtime.stop()

    assert runtime._client is None
    assert signals == [(2468, signal.SIGTERM)]


@pytest.mark.asyncio
async def test_runtime_manager_reports_phase_estimated_provisioning_progress(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import runtime as runtime_module

    logs_emitted = asyncio.Event()
    release_provisioning = asyncio.Event()

    def fake_package_readiness(_settings: Settings) -> dict[str, object]:
        return {
            'status': 'not_ready',
            'python_version': '3.12',
            'project_path': str(tmp_path / 'geo-python'),
            'environment_path': str(tmp_path / 'geo-python' / '.venv'),
            'uv_bin': 'uv',
            'packages': [],
        }

    async def fake_provisioning(_settings: Settings, on_log) -> dict[str, object]:
        await on_log('Resolving package metadata')
        await on_log('Downloading wheels')
        await on_log('Installing rasterio')
        logs_emitted.set()
        await release_provisioning.wait()
        return {
            'status': 'ready',
            'progress': 1.0,
            'logs': ['Resolved package metadata', 'Installed rasterio'],
            'returncode': 0,
        }

    monkeypatch.setattr(runtime_module, 'package_readiness', fake_package_readiness)
    monkeypatch.setattr(runtime_module, 'provision_geospatial_python_environment_streaming', fake_provisioning)
    runtime = RuntimeManager(
        settings=Settings(state_dir=tmp_path / '.state', glm_api_key='test-key', geospatial_python_auto_provision=True),
        runtime_client=StubRuntimeClient(RuntimeStatus(status='ready', label='opencode-runtime', detail='server ready')),
    )

    await runtime.start()
    await asyncio.wait_for(logs_emitted.wait(), timeout=1)

    status = runtime.geospatial_environment_status()
    assert status['status'] == 'provisioning'
    assert status['progress'] == 0.35
    assert 'Installing rasterio' in status['logs']

    release_provisioning.set()
    final_status = await runtime.ensure_geospatial_environment()
    assert final_status['status'] == 'ready'
    assert final_status['progress'] == 1.0


@pytest.mark.asyncio
async def test_runtime_manager_does_not_report_full_progress_when_provisioning_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import runtime as runtime_module

    def fake_package_readiness(_settings: Settings) -> dict[str, object]:
        return {
            'status': 'not_ready',
            'python_version': '3.12',
            'project_path': str(tmp_path / 'geo-python'),
            'environment_path': str(tmp_path / 'geo-python' / '.venv'),
            'uv_bin': 'uv',
            'packages': [],
        }

    async def fake_provisioning(_settings: Settings, on_log) -> dict[str, object]:
        await on_log('Installing rasterio')
        return {
            'status': 'failed',
            'progress': 1.0,
            'logs': ['Installing rasterio', 'uv sync failed'],
            'returncode': 1,
        }

    monkeypatch.setattr(runtime_module, 'package_readiness', fake_package_readiness)
    monkeypatch.setattr(runtime_module, 'provision_geospatial_python_environment_streaming', fake_provisioning)
    runtime = RuntimeManager(
        settings=Settings(state_dir=tmp_path / '.state', glm_api_key='test-key', geospatial_python_auto_provision=True),
        runtime_client=StubRuntimeClient(RuntimeStatus(status='ready', label='opencode-runtime', detail='server ready')),
    )

    await runtime.start()
    final_status = await runtime.ensure_geospatial_environment()

    assert final_status['status'] == 'failed'
    assert final_status['progress'] == 0.35
    assert 'ERROR: uv sync failed with exit code 1.' in final_status['logs']


@pytest.mark.asyncio
async def test_runtime_manager_preserves_phase_progress_when_provisioning_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import runtime as runtime_module

    def fake_package_readiness(_settings: Settings) -> dict[str, object]:
        return {
            'status': 'not_ready',
            'python_version': '3.12',
            'project_path': str(tmp_path / 'geo-python'),
            'environment_path': str(tmp_path / 'geo-python' / '.venv'),
            'uv_bin': 'uv',
            'packages': [],
        }

    async def fake_provisioning(_settings: Settings, on_log) -> dict[str, object]:
        await on_log('Installing rasterio')
        raise RuntimeError('uv sync failed')

    monkeypatch.setattr(runtime_module, 'package_readiness', fake_package_readiness)
    monkeypatch.setattr(runtime_module, 'provision_geospatial_python_environment_streaming', fake_provisioning)
    runtime = RuntimeManager(
        settings=Settings(state_dir=tmp_path / '.state', glm_api_key='test-key', geospatial_python_auto_provision=True),
        runtime_client=StubRuntimeClient(RuntimeStatus(status='ready', label='opencode-runtime', detail='server ready')),
    )

    await runtime.start()
    final_status = await runtime.ensure_geospatial_environment()

    assert final_status['status'] == 'failed'
    assert final_status['progress'] == 0.35
    assert final_status['detail'] == 'uv sync failed'
    assert 'ERROR: uv sync failed' in final_status['logs']


@pytest.mark.asyncio
async def test_runtime_manager_reports_validation_timeout_as_error_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import runtime as runtime_module

    def fake_package_readiness(_settings: Settings) -> dict[str, object]:
        return {
            'status': 'not_ready',
            'python_version': '3.12',
            'project_path': str(tmp_path / 'geo-python'),
            'environment_path': str(tmp_path / 'geo-python' / '.venv'),
            'uv_bin': 'uv',
            'packages': [],
        }

    async def fake_provisioning(_settings: Settings, on_log) -> dict[str, object]:
        await on_log('Validating managed geospatial Python imports.')
        return {
            'status': 'failed',
            'progress': 0.9,
            'logs': ['Validating managed geospatial Python imports.'],
            'returncode': 0,
            'package_readiness': {
                'status': 'failed',
                'validation': {
                    'status': 'failed',
                    'reason': 'validation_timeout',
                    'missing_packages': [],
                    'import_failures': [],
                    'logs': ['Managed geospatial Python validation timed out after 120 seconds.'],
                },
            },
        }

    monkeypatch.setattr(runtime_module, 'package_readiness', fake_package_readiness)
    monkeypatch.setattr(runtime_module, 'provision_geospatial_python_environment_streaming', fake_provisioning)
    runtime = RuntimeManager(
        settings=Settings(state_dir=tmp_path / '.state', glm_api_key='test-key', geospatial_python_auto_provision=True),
        runtime_client=StubRuntimeClient(RuntimeStatus(status='ready', label='opencode-runtime', detail='server ready')),
    )

    await runtime.start()
    final_status = await runtime.ensure_geospatial_environment()

    assert final_status['status'] == 'failed'
    assert final_status['progress'] == 0.9
    assert 'ERROR: Managed geospatial Python validation timed out after 120 seconds.' in final_status['logs']
    assert not any('Missing geospatial packages' in line for line in final_status['logs'])


def test_opencode_runtime_trace_path_uses_app_support_storage(tmp_path: Path) -> None:
    from app.services.agent_runtime import OpenCodeAgentRuntimeClient

    support_dir = tmp_path / 'support'
    runtime = OpenCodeAgentRuntimeClient(Settings(state_dir=tmp_path / '.state', app_support_dir=support_dir, glm_api_key='test-key'))

    trace_path = runtime._session_trace_path('ses_abc123')

    assert trace_path == support_dir / 'runtime-traces' / 'ses_abc123'


def test_opencode_runtime_builds_geo_focused_config(tmp_path: Path) -> None:
    from app.services.agent_runtime import OpenCodeAgentRuntimeClient

    runtime = OpenCodeAgentRuntimeClient(Settings(state_dir=tmp_path / '.state', glm_api_key='test-key'))

    config = runtime._build_runtime_config(port=43111, cors_origin='http://127.0.0.1:5173')

    assert config['default_agent'] == 'geo'
    assert config['enabled_providers'] == ['zhipuai']
    assert config['model'] == 'zhipuai/glm-5.1'
    assert config['small_model'] == 'zhipuai/glm-4.7-flash'
    assert config['provider']['zhipuai']['npm'] == '@ai-sdk/openai-compatible'
    assert config['provider']['zhipuai']['options']['baseURL'] == 'https://open.bigmodel.cn/api/paas/v4'
    assert config['provider']['zhipuai']['options']['apiKey'] == 'test-key'
    assert 'glm-5.1' in config['provider']['zhipuai']['models']
    assert 'glm-4.7-flash' in config['provider']['zhipuai']['models']
    assert 'geo' in config['agent']
    assert {
        'request-triage',
        'study-design',
        'data-audit',
        'spatial-prep',
        'operator-kde',
        'operator-interpolation',
        'operator-spatial-hotspot',
        'evidence-cartography',
        'report-synthesizer',
        'skeptical-review',
    }.issubset(config['agent'])
    assert config['server']['port'] == 43111
    assert config['server']['cors'] == ['http://127.0.0.1:5173']
    assert 'instructions' not in config
    assert config['tools']['bash'] is True
    assert config['tools']['todowrite'] is False
    assert config['tools']['webfetch'] is False
    assert config['tools']['websearch'] is False
    assert config['permission']['edit'] == 'deny'
    assert config['permission']['todowrite'] == 'deny'
    assert config['permission']['webfetch'] == 'deny'
    assert config['permission']['websearch'] == 'deny'
    assert config['permission']['external_directory'] == 'allow'
    assert config['permission']['doom_loop'] == 'deny'
    assert config['permission']['read']['*.env'] == 'deny'
    assert config['permission']['read']['*.env.*'] == 'deny'
    assert '"ask"' not in json.dumps(config['permission'])
    assert config['agent']['geo']['permission']['bash'] == 'allow'
    assert config['agent']['geo']['permission']['edit'] == 'deny'
    assert config['agent']['geo']['permission']['todowrite'] == 'deny'
    assert config['agent']['geo']['permission']['external_directory'] == 'allow'
    assert config['agent']['geo']['permission']['doom_loop'] == 'deny'
    assert config['agent']['geo']['permission']['read']['*.env'] == 'deny'
    assert config['agent']['geo']['permission']['read']['*.env.*'] == 'deny'
    for agent in config['agent'].values():
        if isinstance(agent, dict) and 'permission' in agent:
            assert '"ask"' not in json.dumps(agent['permission'])
    assert 'geospatial' in config['mcp']
    assert config['mcp']['geospatial']['type'] == 'local'
    assert config['mcp']['geospatial']['enabled'] is True
    assert config['mcp']['geospatial']['command'][-12:] == [
        '--state-dir',
        str(tmp_path / '.state'),
        '--app-support-dir',
        str(runtime.settings.resolved_app_support_dir().expanduser().resolve()),
        '--database-path',
        str(runtime.settings.resolved_database_path().expanduser().resolve()),
        '--workspace-root',
        str(runtime.settings.resolved_workspace_root().expanduser().resolve()),
        '--geospatial-python-project',
        str(runtime.settings.resolved_geospatial_python_project().expanduser().resolve()),
        '--geospatial-python-version',
        '3.12',
    ]
    assert all(not key.startswith('GEO_AGENT_') for key in config['mcp']['geospatial']['environment'])
    assert 'orchestrator' in config['agent']['geo']['description'].lower()
    assert config['agent']['request-triage']['mode'] == 'subagent'
    assert config['agent']['skeptical-review']['mode'] == 'subagent'
    assert config['agent']['geo']['tools']['skill'] is True
    assert config['agent']['geo']['permission']['skill']['geospatial-request-triage'] == 'allow'
    assert config['agent']['geo']['permission']['skill']['openspec-*'] == 'deny'
    assert '空间主理人' in config['agent']['geo']['prompt']
    assert '需求分诊师' in config['agent']['geo']['prompt']
    assert '插值分析师' in config['agent']['geo']['prompt']
    assert '统计热点分析师' in config['agent']['geo']['prompt']
    assert '需求分诊师' in config['agent']['request-triage']['prompt']
    assert 'IDW' in config['agent']['operator-interpolation']['prompt']
    assert 'Gi*' in config['agent']['operator-spatial-hotspot']['prompt']
    assert '结果审查官' in config['agent']['skeptical-review']['prompt']
    assert 'update_todos' in config['agent']['geo']['prompt']
    assert 'proceed, clarify, repair, or stop' in config['agent']['geo']['prompt'].lower()
    assert 'read and apply relevant bundled professional geospatial skills' in config['agent']['geo']['prompt']
    assert 'geospatial-request-triage' in config['agent']['geo']['prompt']
    assert 'todowrite' not in config['agent']['geo']['prompt'].lower()


def test_opencode_runtime_injects_geospatial_environment(tmp_path: Path) -> None:
    from app.services.agent_runtime import OpenCodeAgentRuntimeClient

    runtime = OpenCodeAgentRuntimeClient(Settings(app_support_dir=tmp_path / 'geo-agent', glm_api_key='test-key'))

    env = runtime._build_server_env(port=43111)

    assert env['GEO_AGENT_REPO_ROOT'].endswith('geo-agent')
    assert env['GEO_AGENT_UV_BIN']
    assert env['GEO_AGENT_GEO_PYTHON_PROJECT'].endswith('app/runtime_assets/geospatial-python')
    assert env['GEO_AGENT_GEO_PYTHON_VERSION'] == '3.12'
    assert env['UV_PROJECT_ENVIRONMENT'] == str(tmp_path / 'geo-agent' / 'runtime' / 'geospatial-python' / '.venv')
    assert env['GEO_AGENT_WORKSPACE_PATH'] == str(tmp_path / 'geo-agent' / 'workspace')
    assert env['GEO_AGENT_SESSION_CONTEXT_ID'] == ''
    assert 'GEO_AGENT_ARTIFACT_DIR' not in env
    assert env['GEO_AGENT_ATTACHED_DATA_DIRS_JSON'] == '[]'


def test_opencode_runtime_resolves_default_runtime_paths_before_starting_server(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.agent_runtime import OpenCodeAgentRuntimeClient

    monkeypatch.chdir(tmp_path)
    runtime = OpenCodeAgentRuntimeClient(Settings(glm_api_key='test-key'))

    env = runtime._build_server_env(port=43111)

    assert Path(env['OPENCODE_TEST_HOME']).is_absolute()
    assert Path(env['XDG_CONFIG_HOME']).is_absolute()
    assert Path(env['XDG_DATA_HOME']).is_absolute()
    assert Path(env['XDG_STATE_HOME']).is_absolute()
    assert Path(env['XDG_CACHE_HOME']).is_absolute()
    assert Path(env['UV_PROJECT_ENVIRONMENT']).is_absolute()
    assert Path(env['GEO_AGENT_WORKSPACE_PATH']).is_absolute()


@pytest.mark.asyncio
async def test_opencode_runtime_run_session_forwards_only_user_prompt(tmp_path: Path) -> None:
    from app.services.agent_runtime import OpenCodeAgentRuntimeClient, RuntimeSessionRequest

    workspace = tmp_path / 'workspace'
    workspace.mkdir(parents=True, exist_ok=True)
    runtime = OpenCodeAgentRuntimeClient(Settings(state_dir=tmp_path / '.state', glm_api_key='test-key'))
    fake_client = FakeRunSessionHttpClient()
    runtime._client = fake_client

    async def fake_start() -> None:
        return None

    async def fake_poll_session(*, runtime_session_id: str, request: RuntimeSessionRequest, emit) -> None:
        return None

    runtime.start = fake_start  # type: ignore[method-assign]
    runtime._poll_session = fake_poll_session  # type: ignore[method-assign]

    await runtime.run_session(
        RuntimeSessionRequest(
            session_id='session-1',
            prompt='对北京出租车轨迹做 KDE 热点分析',
            workspace_path=workspace,
        ),
        emit=_discard_event,
    )

    prompt_call = next(payload for path, payload in fake_client.posts if path == '/session/runtime-session-1/prompt_async')

    assert prompt_call['agent'] == 'geo'
    assert prompt_call['model'] == {'providerID': 'zhipuai', 'modelID': 'glm-5.1'}
    assert prompt_call['parts'] == [{'type': 'text', 'text': '对北京出租车轨迹做 KDE 热点分析'}]


@pytest.mark.asyncio
async def test_opencode_runtime_recreates_stale_runtime_session_before_prompting(tmp_path: Path) -> None:
    from app.services.agent_runtime import OpenCodeAgentRuntimeClient, RuntimeSessionRequest

    workspace = tmp_path / 'workspace'
    workspace.mkdir(parents=True, exist_ok=True)
    runtime = OpenCodeAgentRuntimeClient(Settings(state_dir=tmp_path / '.state', glm_api_key='test-key'))
    fake_client = FakeRetryingRunSessionHttpClient()
    runtime._client = fake_client

    async def fake_start() -> None:
        return None

    async def fake_poll_session(*, runtime_session_id: str, request: RuntimeSessionRequest, emit) -> None:
        return None

    runtime.start = fake_start  # type: ignore[method-assign]
    runtime._poll_session = fake_poll_session  # type: ignore[method-assign]

    result = await runtime.run_session(
        RuntimeSessionRequest(
            session_id='session-1',
            prompt='对北京出租车轨迹做 KDE 热点分析',
            workspace_path=workspace,
            runtime_session_id='stale-session',
        ),
        emit=_discard_event,
    )

    assert [path for path, _ in fake_client.posts] == [
        '/session/stale-session/prompt_async',
        '/session',
        '/session/runtime-session-2/prompt_async',
    ]
    assert result.runtime_session_id == 'runtime-session-2'


@pytest.mark.asyncio
async def test_opencode_runtime_replies_to_runtime_question_requests(tmp_path: Path) -> None:
    from app.services.agent_runtime import OpenCodeAgentRuntimeClient, RuntimeSessionRequest

    workspace = tmp_path / 'workspace'
    workspace.mkdir(parents=True, exist_ok=True)
    runtime = OpenCodeAgentRuntimeClient(Settings(state_dir=tmp_path / '.state', glm_api_key='test-key'))
    fake_client = FakeQuestionReplyHttpClient()
    runtime._client = fake_client

    async def fake_start() -> None:
        return None

    async def fake_poll_session(*, runtime_session_id: str, request: RuntimeSessionRequest, emit) -> None:
        return None

    runtime.start = fake_start  # type: ignore[method-assign]
    runtime._poll_session = fake_poll_session  # type: ignore[method-assign]

    await runtime.run_session(
        RuntimeSessionRequest(
            session_id='session-1',
            prompt='对北京出租车轨迹做 KDE 热点分析',
            workspace_path=workspace,
            runtime_session_id='runtime-session-1',
            question_request_id='question-request-1',
            question_answers=['使用默认北京市区县边界'],
        ),
        emit=_discard_event,
    )

    assert fake_client.posts == [
        ('/question/question-request-1/reply', {'answers': [['使用默认北京市区县边界']]}),
    ]


@pytest.mark.asyncio
async def test_opencode_runtime_aborts_running_session_via_http_api(tmp_path: Path) -> None:
    from app.services.agent_runtime import OpenCodeAgentRuntimeClient

    runtime = OpenCodeAgentRuntimeClient(Settings(state_dir=tmp_path / '.state', glm_api_key='test-key'))
    fake_client = FakeAbortSessionHttpClient()
    runtime._client = fake_client

    await runtime.abort_session('runtime-session-1')

    assert fake_client.posts == [('/session/runtime-session-1/abort', None)]


@pytest.mark.asyncio
async def test_opencode_runtime_ignores_stale_abort_for_finished_session(tmp_path: Path) -> None:
    from app.services.agent_runtime import OpenCodeAgentRuntimeClient

    runtime = OpenCodeAgentRuntimeClient(Settings(state_dir=tmp_path / '.state', glm_api_key='test-key'))
    fake_client = FakeStaleAbortSessionHttpClient()
    runtime._client = fake_client

    await runtime.abort_session('runtime-session-1')

    assert fake_client.posts == [('/session/runtime-session-1/abort', None)]


def test_opencode_runtime_normalizes_tool_family_metadata(tmp_path: Path) -> None:
    from app.services.agent_runtime import OpenCodeAgentRuntimeClient

    runtime = OpenCodeAgentRuntimeClient(Settings(state_dir=tmp_path / '.state', glm_api_key='test-key'))

    message = runtime._normalize_message(
        {
            'info': {
                'id': 'msg-1',
                'role': 'assistant',
                'agent': 'geo',
                'time': {'created': 1710000000000},
            },
            'parts': [
                {
                    'type': 'tool',
                    'tool': 'geospatial_record_run_evidence',
                    'state': {
                        'input': {'record_type': 'artifact', 'title': 'KDE 热点图'},
                        'output': '{"status":"completed"}',
                    },
                }
            ],
        }
    )

    assert message['parts'][0]['state']['meta']['tool_family'] == 'evidence'
    assert message['parts'][0]['state']['meta']['tool_label'] == '记录产物'
    assert message['parts'][0]['state']['meta']['tool_icon'] == 'file-text'
    assert message['parts'][0]['state']['meta']['tool_name'] == 'record_run_evidence'
    assert message['parts'][0]['state']['meta']['raw_tool'] == 'geospatial_record_run_evidence'


def test_runtime_tool_identity_canonicalizes_known_and_unknown_names() -> None:
    from app.services.tool_identity import canonical_tool_name, resolve_tool_identity

    assert canonical_tool_name('geospatial_geospatial_get_session_context') == 'get_session_context'
    assert canonical_tool_name('mcp__geospatial__record_run_evidence') == 'record_run_evidence'

    known = resolve_tool_identity('mcp__geospatial__record_run_evidence')
    unknown = resolve_tool_identity('runtime_new_tool')

    assert known.label == '记录证据'
    assert known.family == 'evidence'
    assert known.icon == 'file-text'
    assert unknown.label == '运行时工具'
    assert unknown.family == 'tool'


def test_opencode_runtime_detects_incremental_message_updates(tmp_path: Path) -> None:
    from app.services.agent_runtime import OpenCodeAgentRuntimeClient

    runtime = OpenCodeAgentRuntimeClient(Settings(state_dir=tmp_path / '.state', glm_api_key='test-key'))

    previous_messages = [
        {
            'id': 'msg-assistant-1',
            'role': 'assistant',
            'agent': 'geo',
            'created_at': '2026-03-28T00:00:01+00:00',
            'parts': [{'type': 'text', 'text': '正在分析北京 FCD 数据'}],
        }
    ]
    current_messages = [
        {
            'id': 'msg-assistant-1',
            'role': 'assistant',
            'agent': 'geo',
            'created_at': '2026-03-28T00:00:01+00:00',
            'parts': [{'type': 'text', 'text': '正在分析北京 FCD 数据\n\n已完成 KDE 算子。'}],
        }
    ]

    updates = runtime._message_updates(previous_messages, current_messages)

    assert updates == [current_messages[0]]


@pytest.mark.asyncio
async def test_opencode_runtime_inlines_task_child_session_messages_into_parent_transcript(tmp_path: Path) -> None:
    from app.services.agent_runtime import OpenCodeAgentRuntimeClient

    runtime = OpenCodeAgentRuntimeClient(Settings(state_dir=tmp_path / '.state', glm_api_key='test-key'))
    runtime._client = FakeTaskTranscriptHttpClient(
        child_messages=[
            {
                'info': {
                    'id': 'msg-child-user',
                    'role': 'user',
                    'agent': 'request-triage',
                    'time': {'created': 1710000000500},
                },
                'parts': [
                    {
                        'id': 'part-child-user',
                        'type': 'text',
                        'text': '请做一个自我介绍，说明你的角色、职责和能力。',
                    },
                ],
            },
            {
                'info': {
                    'id': 'msg-child-assistant',
                    'role': 'assistant',
                    'agent': 'request-triage',
                    'time': {'created': 1710000001000},
                },
                'parts': [
                    {
                        'id': 'part-child-assistant',
                        'type': 'text',
                        'text': '我是 Request Triage，负责识别请求目标并补齐执行前缺失的信息。',
                    },
                ],
            },
        ]
    )

    emitted: list[tuple[str, object]] = []
    await runtime._emit_message_side_effects(
        message={
            'info': {
                'id': 'msg-parent-assistant',
                'role': 'assistant',
                'agent': 'geo',
                'time': {'created': 1710000000000},
            },
            'parts': [
                {
                    'id': 'part-parent-task',
                    'type': 'tool',
                    'tool': 'task',
                    'state': {
                        'input': {
                            'description': 'Request-triage agent 自我介绍',
                            'prompt': '请做一个自我介绍，说明你的角色、职责和能力。',
                            'subagent_type': 'request-triage',
                        },
                        'output': 'task_id: ses_child_task\n\n<task_result>done</task_result>',
                    },
                },
            ],
        },
        attached_dirs=[],
        seen_tool_part_ids=set(),
        emit=lambda envelope: _collect_event(emitted, envelope.type, envelope.payload),
    )

    message_deltas = [
        payload for event_type, payload in emitted
        if event_type == 'session.message_delta' and isinstance(payload, dict)
    ]

    assert runtime._client.get_paths == ['/session/ses_child_task/message']  # type: ignore[union-attr]
    assert any(
        payload.get('id', '').startswith('inline-subtask-')
        and payload.get('role') == 'system'
        and payload.get('parts', [{}])[0].get('type') == 'subtask'
        and payload.get('parts', [{}])[0].get('state', {}).get('prompt') == '请做一个自我介绍，说明你的角色、职责和能力。'
        for payload in message_deltas
    )
    assert any(
        payload.get('id', '').startswith('inline-msg-child-assistant')
        and payload.get('agent') == 'request-triage'
        and payload.get('parts', [{}])[0].get('text') == '我是 Request Triage，负责识别请求目标并补齐执行前缺失的信息。'
        for payload in message_deltas
    )
    assert not any(payload.get('id', '').startswith('inline-msg-child-user') for payload in message_deltas)


@pytest.mark.asyncio
async def test_opencode_runtime_streams_running_task_child_session_messages(tmp_path: Path) -> None:
    from app.services.agent_runtime import OpenCodeAgentRuntimeClient, RuntimeSessionRequest

    workspace = tmp_path / 'workspace'
    workspace.mkdir(parents=True, exist_ok=True)

    def runtime_event(payload: dict[str, object]) -> str:
        return f'data: {json.dumps({"directory": "/tmp/workspace", "payload": payload}, ensure_ascii=False)}'

    runtime = OpenCodeAgentRuntimeClient(Settings(state_dir=tmp_path / '.state', glm_api_key='test-key'))
    runtime._client = FakeStreamingRuntimeHttpClient(
        statuses=[{'ses-parent': {'type': 'busy'}}],
        session_details=[{'id': 'ses-parent', 'title': 'Runtime title'}],
        message_snapshots=[
            [
                {
                    'info': {'id': 'msg-user-1', 'role': 'user', 'agent': 'geo', 'time': {'created': 1710000000000}},
                    'parts': [{'type': 'text', 'text': '继续审查热力图', 'id': 'part-user-1'}],
                },
                {
                    'info': {'id': 'msg-parent-assistant', 'role': 'assistant', 'agent': 'geo', 'time': {'created': 1710000001000}},
                    'parts': [],
                },
            ],
            [],
        ],
        global_event_lines=[
            runtime_event({
                'type': 'message.part.updated',
                'properties': {
                    'sessionID': 'ses-parent',
                    'part': {
                        'id': 'part-parent-task',
                        'messageID': 'msg-parent-assistant',
                        'sessionID': 'ses-parent',
                        'type': 'tool',
                        'tool': 'task',
                        'state': {
                            'status': 'running',
                            'input': {
                                'description': '审查热力图结果合理性',
                                'prompt': '检查 KDE 热力图是否合理。',
                                'subagent_type': 'reviewer',
                            },
                            'metadata': {'sessionId': 'ses_child_task'},
                        },
                    },
                    'time': 1710000001000,
                },
            }),
            runtime_event({
                'type': 'message.updated',
                'properties': {
                    'sessionID': 'ses_child_task',
                    'info': {
                        'id': 'msg-child-assistant',
                        'role': 'assistant',
                        'agent': 'reviewer',
                        'time': {'created': 1710000001500},
                    },
                },
            }),
            runtime_event({
                'type': 'message.part.updated',
                'properties': {
                    'sessionID': 'ses_child_task',
                    'part': {
                        'id': 'part-child-text',
                        'messageID': 'msg-child-assistant',
                        'sessionID': 'ses_child_task',
                        'type': 'text',
                        'text': '我正在核查热点是否落在合理区域。',
                    },
                    'time': 1710000001500,
                },
            }),
        ],
    )

    emitted: list[tuple[str, object]] = []
    streamed = await runtime._stream_session_events(
        runtime_session_id='ses-parent',
        request=RuntimeSessionRequest(session_id='session-1', prompt='继续审查热力图', workspace_path=workspace),
        emit=lambda envelope: _collect_event(emitted, envelope.type, envelope.payload),
    )

    message_deltas = [
        payload for event_type, payload in emitted
        if event_type == 'session.message_delta' and isinstance(payload, dict)
    ]

    assert streamed is False
    assert any(
        payload.get('id') == 'inline-subtask-ses_child_task'
        and payload.get('parts', [{}])[0].get('state', {}).get('description') == '审查热力图结果合理性'
        for payload in message_deltas
    )
    assert any(
        payload.get('id') == 'inline-msg-child-assistant-ses_child_task'
        and payload.get('agent') == 'reviewer'
        and any(part.get('text') == '我正在核查热点是否落在合理区域。' for part in payload.get('parts', []))
        for payload in message_deltas
    )


@pytest.mark.asyncio
async def test_opencode_runtime_uses_global_event_deltas_for_true_text_streaming(tmp_path: Path) -> None:
    from app.services.agent_runtime import OpenCodeAgentRuntimeClient, RuntimeSessionRequest

    workspace = tmp_path / 'workspace'
    workspace.mkdir(parents=True, exist_ok=True)

    runtime = OpenCodeAgentRuntimeClient(Settings(state_dir=tmp_path / '.state', glm_api_key='test-key'))
    runtime._client = FakeStreamingRuntimeHttpClient(
        statuses=[{'ses-1': {'type': 'busy'}}, {'ses-1': {'type': 'idle'}}],
        session_details=[{'id': 'ses-1', 'title': 'Runtime title'}],
        message_snapshots=[[
            {
                'info': {'id': 'msg-user-1', 'role': 'user', 'agent': 'geo', 'time': {'created': 1710000000000}},
                'parts': [{'type': 'text', 'text': '请回复测试成功', 'id': 'part-user-1'}],
            },
            {
                'info': {'id': 'msg-assistant-1', 'role': 'assistant', 'agent': 'geo', 'time': {'created': 1710000001000}},
                'parts': [],
            },
        ], [
            {
                'info': {'id': 'msg-user-1', 'role': 'user', 'agent': 'geo', 'time': {'created': 1710000000000}},
                'parts': [{'type': 'text', 'text': '请回复测试成功', 'id': 'part-user-1'}],
            },
            {
                'info': {'id': 'msg-assistant-1', 'role': 'assistant', 'agent': 'geo', 'time': {'created': 1710000001000}},
                'parts': [],
            },
        ]],
        global_event_lines=[
            'data: {"directory":"/tmp/workspace","payload":{"type":"message.part.updated","properties":{"sessionID":"ses-1","part":{"id":"part-assistant-text","messageID":"msg-assistant-1","sessionID":"ses-1","type":"text","text":""},"time":1710000001000}}}',
            'data: {"directory":"/tmp/workspace","payload":{"type":"message.part.delta","properties":{"sessionID":"ses-1","messageID":"msg-assistant-1","partID":"part-assistant-text","field":"text","delta":"测"}}}',
            'data: {"directory":"/tmp/workspace","payload":{"type":"message.part.delta","properties":{"sessionID":"ses-1","messageID":"msg-assistant-1","partID":"part-assistant-text","field":"text","delta":"试成功"}}}',
            'data: {"directory":"/tmp/workspace","payload":{"type":"session.status","properties":{"sessionID":"ses-1","status":{"type":"idle"}}}}',
        ],
    )

    emitted: list[tuple[str, object]] = []
    await runtime._poll_session(
        runtime_session_id='ses-1',
        request=RuntimeSessionRequest(session_id='session-1', prompt='请回复测试成功', workspace_path=workspace),
        emit=lambda envelope: _collect_event(emitted, envelope.type, envelope.payload),
    )

    assistant_deltas = [
        payload for event_type, payload in emitted
        if event_type == 'session.message_delta' and isinstance(payload, dict) and payload.get('id') == 'msg-assistant-1'
    ]

    assert any(part.get('text') == '测' for payload in assistant_deltas for part in payload.get('parts', []))
    assert any(part.get('text') == '测试成功' for payload in assistant_deltas for part in payload.get('parts', []))


@pytest.mark.asyncio
async def test_opencode_runtime_marks_message_info_error_as_failed_status(tmp_path: Path) -> None:
    from app.services.agent_runtime import OpenCodeAgentRuntimeClient, RuntimeSessionRequest

    workspace = tmp_path / 'workspace'
    workspace.mkdir(parents=True, exist_ok=True)

    runtime = OpenCodeAgentRuntimeClient(Settings(state_dir=tmp_path / '.state', glm_api_key='test-key'))
    runtime._client = FakeStreamingRuntimeHttpClient(
        statuses=[{'ses-1': {'type': 'busy'}}],
        session_details=[{'id': 'ses-1', 'title': 'Runtime title'}],
        message_snapshots=[[
            {
                'info': {'id': 'msg-user-1', 'role': 'user', 'agent': 'geo', 'time': {'created': 1710000000000}},
                'parts': [{'type': 'text', 'text': '继续完成任务', 'id': 'part-user-1'}],
            }
        ]],
        global_event_lines=[
            'data: ' + json.dumps({
                'directory': '/tmp/workspace',
                'payload': {
                    'type': 'message.updated',
                    'properties': {
                        'sessionID': 'ses-1',
                        'info': {
                            'id': 'msg-assistant-1',
                            'role': 'assistant',
                            'agent': 'geo',
                            'time': {
                                'created': 1710000001000,
                                'completed': 1710000001500,
                            },
                            'error': {
                                'name': 'APIError',
                                'data': {
                                    'message': (
                                        'The `reasoning_content` in the thinking mode must be passed back '
                                        'to the API.'
                                    ),
                                    'statusCode': 400,
                                    'metadata': {
                                        'url': 'https://api.deepseek.com/chat/completions',
                                    },
                                },
                            },
                        },
                    },
                },
            }),
            'data: ' + json.dumps({
                'directory': '/tmp/workspace',
                'payload': {
                    'type': 'session.status',
                    'properties': {'sessionID': 'ses-1', 'status': {'type': 'idle'}},
                },
            }),
        ],
    )

    emitted: list[tuple[str, object]] = []
    streamed = await runtime._stream_session_events(
        runtime_session_id='ses-1',
        request=RuntimeSessionRequest(
            session_id='session-1',
            prompt='继续完成任务',
            workspace_path=workspace,
        ),
        emit=lambda envelope: _collect_event(emitted, envelope.type, envelope.payload),
    )

    issues = [payload for event_type, payload in emitted if event_type == 'session.issue']
    statuses = [payload for event_type, payload in emitted if event_type == 'session.status']

    assert streamed is True
    assert any(
        isinstance(issue, dict)
        and issue.get('type') == 'runtime_error'
        and issue.get('source') == 'opencode'
        and 'reasoning_content' in str(issue.get('detail'))
        for issue in issues
    )
    assert {'status': 'failed'} in statuses


@pytest.mark.asyncio
async def test_opencode_runtime_keeps_session_running_while_tool_part_is_running(tmp_path: Path) -> None:
    from app.services.agent_runtime import OpenCodeAgentRuntimeClient, RuntimeSessionRequest

    workspace = tmp_path / 'workspace'
    workspace.mkdir(parents=True, exist_ok=True)

    runtime = OpenCodeAgentRuntimeClient(Settings(state_dir=tmp_path / '.state', glm_api_key='test-key'))
    runtime._client = FakeStreamingRuntimeHttpClient(
        statuses=[{'ses-1': {'type': 'busy'}}],
        session_details=[{'id': 'ses-1', 'title': 'Runtime title'}],
        message_snapshots=[[
            {
                'info': {'id': 'msg-user-1', 'role': 'user', 'agent': 'geo', 'time': {'created': 1710000000000}},
                'parts': [{'type': 'text', 'text': '运行一个较长任务', 'id': 'part-user-1'}],
            },
            {
                'info': {'id': 'msg-assistant-1', 'role': 'assistant', 'agent': 'geo', 'time': {'created': 1710000001000}},
                'parts': [],
            },
        ]],
        global_event_lines=[
            'data: {"directory":"/tmp/workspace","payload":{"type":"message.part.updated","properties":{"sessionID":"ses-1","part":{"id":"part-tool-1","messageID":"msg-assistant-1","sessionID":"ses-1","type":"tool","tool":"runtime_long_task","state":{"status":"running","input":{"prompt":"运行较长任务"}}},"time":1710000001000}}}',
            'data: {"directory":"/tmp/workspace","payload":{"type":"session.status","properties":{"sessionID":"ses-1","status":{"type":"idle"}}}}',
            'data: {"directory":"/tmp/workspace","payload":{"type":"message.part.updated","properties":{"sessionID":"ses-1","part":{"id":"part-tool-1","messageID":"msg-assistant-1","sessionID":"ses-1","type":"tool","tool":"runtime_long_task","state":{"status":"completed","input":{"prompt":"运行较长任务"},"output":"done"}},"time":1710000002000}}}',
            'data: {"directory":"/tmp/workspace","payload":{"type":"message.part.updated","properties":{"sessionID":"ses-1","part":{"id":"part-final-text","messageID":"msg-assistant-1","sessionID":"ses-1","type":"text","text":"较长任务已完成。"},"time":1710000003000}}}',
            'data: {"directory":"/tmp/workspace","payload":{"type":"session.status","properties":{"sessionID":"ses-1","status":{"type":"idle"}}}}',
        ],
    )

    emitted: list[tuple[str, object]] = []
    await runtime._poll_session(
        runtime_session_id='ses-1',
        request=RuntimeSessionRequest(session_id='session-1', prompt='运行一个较长任务', workspace_path=workspace),
        emit=lambda envelope: _collect_event(emitted, envelope.type, envelope.payload),
    )

    assistant_deltas = [
        payload for event_type, payload in emitted
        if event_type == 'session.message_delta' and isinstance(payload, dict) and payload.get('id') == 'msg-assistant-1'
    ]
    statuses = [payload for event_type, payload in emitted if event_type == 'session.status']

    assert any(part.get('text') == '较长任务已完成。' for payload in assistant_deltas for part in payload.get('parts', []))
    assert statuses == [{'status': 'completed'}]


@pytest.mark.asyncio
async def test_opencode_runtime_waits_for_incomplete_assistant_shell_before_completing(tmp_path: Path) -> None:
    from app.services.agent_runtime import OpenCodeAgentRuntimeClient, RuntimeSessionRequest

    workspace = tmp_path / 'workspace'
    workspace.mkdir(parents=True, exist_ok=True)

    def event(payload: dict[str, object]) -> str:
        return f'data: {json.dumps(payload, ensure_ascii=False)}'

    runtime = OpenCodeAgentRuntimeClient(Settings(state_dir=tmp_path / '.state', glm_api_key='test-key'))
    runtime._client = FakeStreamingRuntimeHttpClient(
        statuses=[{'ses-1': {'type': 'busy'}}],
        session_details=[{'id': 'ses-1', 'title': 'Runtime title'}],
        message_snapshots=[[
            {
                'info': {'id': 'msg-user-1', 'role': 'user', 'agent': 'geo', 'time': {'created': 1710000000000}},
                'parts': [{'type': 'text', 'text': '更新待办后继续执行', 'id': 'part-user-1'}],
            },
            {
                'info': {'id': 'msg-assistant-1', 'role': 'assistant', 'agent': 'geo', 'time': {'created': 1710000001000}},
                'parts': [],
            },
        ]],
        global_event_lines=[
            event({
                'directory': '/tmp/workspace',
                'payload': {
                    'type': 'session.status',
                    'properties': {'sessionID': 'ses-1', 'status': {'type': 'idle'}},
                },
            }),
            event({
                'directory': '/tmp/workspace',
                'payload': {
                    'type': 'message.part.updated',
                    'properties': {
                        'sessionID': 'ses-1',
                        'part': {
                            'id': 'part-update-todos',
                            'messageID': 'msg-assistant-1',
                            'sessionID': 'ses-1',
                            'type': 'tool',
                            'tool': 'geospatial_update_todos',
                            'state': {
                                'status': 'completed',
                                'input': {'entries': [{'content': '检查 CRS', 'status': 'pending'}]},
                                'output': '<todos status="updated"><todo status="pending">检查 CRS</todo></todos>',
                            },
                        },
                        'time': 1710000002000,
                    },
                },
            }),
            event({
                'directory': '/tmp/workspace',
                'payload': {
                    'type': 'message.updated',
                    'properties': {
                        'sessionID': 'ses-1',
                        'info': {
                            'id': 'msg-assistant-1',
                            'role': 'assistant',
                            'agent': 'geo',
                            'time': {'created': 1710000001000, 'completed': 1710000002500},
                            'finish': 'tool-calls',
                        },
                    },
                },
            }),
            event({
                'directory': '/tmp/workspace',
                'payload': {
                    'type': 'session.status',
                    'properties': {'sessionID': 'ses-1', 'status': {'type': 'idle'}},
                },
            }),
            event({
                'directory': '/tmp/workspace',
                'payload': {
                    'type': 'message.updated',
                    'properties': {
                        'sessionID': 'ses-1',
                        'info': {'id': 'msg-assistant-2', 'role': 'assistant', 'agent': 'geo', 'time': {'created': 1710000003000}},
                    },
                },
            }),
            event({
                'directory': '/tmp/workspace',
                'payload': {
                    'type': 'message.part.updated',
                    'properties': {
                        'sessionID': 'ses-1',
                        'part': {
                            'id': 'part-final-text',
                            'messageID': 'msg-assistant-2',
                            'sessionID': 'ses-1',
                            'type': 'text',
                            'text': '待办已更新，继续执行数据核验。',
                        },
                        'time': 1710000003500,
                    },
                },
            }),
            event({
                'directory': '/tmp/workspace',
                'payload': {
                    'type': 'message.updated',
                    'properties': {
                        'sessionID': 'ses-1',
                        'info': {
                            'id': 'msg-assistant-2',
                            'role': 'assistant',
                            'agent': 'geo',
                            'time': {'created': 1710000003000, 'completed': 1710000004000},
                            'finish': 'stop',
                        },
                    },
                },
            }),
            event({
                'directory': '/tmp/workspace',
                'payload': {
                    'type': 'session.status',
                    'properties': {'sessionID': 'ses-1', 'status': {'type': 'idle'}},
                },
            }),
        ],
    )

    emitted: list[tuple[str, object]] = []
    await runtime._poll_session(
        runtime_session_id='ses-1',
        request=RuntimeSessionRequest(session_id='session-1', prompt='更新待办后继续执行', workspace_path=workspace),
        emit=lambda envelope: _collect_event(emitted, envelope.type, envelope.payload),
    )

    assistant_deltas = [
        payload for event_type, payload in emitted
        if event_type == 'session.message_delta' and isinstance(payload, dict)
    ]
    statuses = [payload for event_type, payload in emitted if event_type == 'session.status']

    assert any(
        part.get('tool') == 'geospatial_update_todos'
        and part.get('state', {}).get('input', {}).get('entries') == [{'content': '检查 CRS', 'status': 'pending'}]
        for payload in assistant_deltas
        for part in payload.get('parts', [])
    )
    assert any(part.get('text') == '待办已更新，继续执行数据核验。' for payload in assistant_deltas for part in payload.get('parts', []))
    assert statuses == [{'status': 'completed'}]


@pytest.mark.asyncio
async def test_opencode_runtime_completes_on_finished_assistant_message_without_idle_event(tmp_path: Path) -> None:
    from app.services.agent_runtime import OpenCodeAgentRuntimeClient, RuntimeSessionRequest

    workspace = tmp_path / 'workspace'
    workspace.mkdir(parents=True, exist_ok=True)

    def event(payload: dict[str, object]) -> str:
        return f'data: {json.dumps(payload, ensure_ascii=False)}'

    runtime = OpenCodeAgentRuntimeClient(Settings(state_dir=tmp_path / '.state', glm_api_key='test-key'))
    runtime._client = FakeStreamingRuntimeHttpClient(
        statuses=[{'ses-1': {'type': 'busy'}}],
        session_details=[{'id': 'ses-1', 'title': 'Runtime title'}],
        message_snapshots=[[
            {
                'info': {'id': 'msg-user-1', 'role': 'user', 'agent': 'geo', 'time': {'created': 1710000000000}},
                'parts': [{'type': 'text', 'text': '生成最终报告', 'id': 'part-user-1'}],
            },
            {
                'info': {'id': 'msg-assistant-1', 'role': 'assistant', 'agent': 'geo', 'time': {'created': 1710000001000}},
                'parts': [],
            },
        ]],
        global_event_lines=[
            event({
                'directory': '/tmp/workspace',
                'payload': {
                    'type': 'message.part.updated',
                    'properties': {
                        'sessionID': 'ses-1',
                        'part': {
                            'id': 'part-final-text',
                            'messageID': 'msg-assistant-1',
                            'sessionID': 'ses-1',
                            'type': 'text',
                            'text': '最终报告已生成。',
                        },
                        'time': 1710000002000,
                    },
                },
            }),
            event({
                'directory': '/tmp/workspace',
                'payload': {
                    'type': 'message.updated',
                    'properties': {
                        'sessionID': 'ses-1',
                        'info': {
                            'id': 'msg-assistant-1',
                            'role': 'assistant',
                            'agent': 'geo',
                            'time': {'created': 1710000001000, 'completed': 1710000003000},
                            'finish': 'stop',
                        },
                    },
                },
            }),
        ],
    )

    emitted: list[tuple[str, object]] = []
    streamed = await runtime._stream_session_events(
        runtime_session_id='ses-1',
        request=RuntimeSessionRequest(session_id='session-1', prompt='生成最终报告', workspace_path=workspace),
        emit=lambda envelope: _collect_event(emitted, envelope.type, envelope.payload),
    )

    statuses = [payload for event_type, payload in emitted if event_type == 'session.status']

    assert streamed is True
    assert statuses == [{'status': 'completed'}]


@pytest.mark.asyncio
async def test_opencode_runtime_completes_from_idle_snapshot_when_stream_misses_final_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.services.agent_runtime as agent_runtime_module
    from app.services.agent_runtime import OpenCodeAgentRuntimeClient, RuntimeSessionRequest

    workspace = tmp_path / 'workspace'
    workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(agent_runtime_module, 'STREAM_SNAPSHOT_POLL_SECONDS', 0.01)

    runtime = OpenCodeAgentRuntimeClient(Settings(state_dir=tmp_path / '.state', glm_api_key='test-key'))
    runtime._client = FakeBlockingStreamingRuntimeHttpClient(
        statuses=[
            {'ses-1': {'type': 'busy'}},
            {},
        ],
        session_details=[{'id': 'ses-1', 'title': 'Runtime title'}],
        message_snapshots=[
            [
                {
                    'info': {'id': 'msg-user-1', 'role': 'user', 'agent': 'geo', 'time': {'created': 1710000000000}},
                    'parts': [{'type': 'text', 'text': '生成最终报告', 'id': 'part-user-1'}],
                },
                {
                    'info': {'id': 'msg-assistant-1', 'role': 'assistant', 'agent': 'geo', 'time': {'created': 1710000001000}},
                    'parts': [
                        {
                            'id': 'part-task',
                            'messageID': 'msg-assistant-1',
                            'sessionID': 'ses-1',
                            'type': 'tool',
                            'tool': 'task',
                            'state': {'status': 'running', 'input': {'description': '最终审查'}},
                        },
                    ],
                },
            ],
            [
                {
                    'info': {'id': 'msg-user-1', 'role': 'user', 'agent': 'geo', 'time': {'created': 1710000000000}},
                    'parts': [{'type': 'text', 'text': '生成最终报告', 'id': 'part-user-1'}],
                },
                {
                    'info': {
                        'id': 'msg-assistant-1',
                        'role': 'assistant',
                        'agent': 'geo',
                        'time': {'created': 1710000001000, 'completed': 1710000002000},
                        'finish': 'tool-calls',
                    },
                    'parts': [
                        {
                            'id': 'part-task',
                            'messageID': 'msg-assistant-1',
                            'sessionID': 'ses-1',
                            'type': 'tool',
                            'tool': 'task',
                            'state': {'status': 'completed', 'input': {'description': '最终审查'}, 'output': 'done'},
                        },
                    ],
                },
                {
                    'info': {
                        'id': 'msg-assistant-2',
                        'role': 'assistant',
                        'agent': 'geo',
                        'time': {'created': 1710000003000, 'completed': 1710000004000},
                        'finish': 'stop',
                    },
                    'parts': [
                        {
                            'id': 'part-final-text',
                            'messageID': 'msg-assistant-2',
                            'sessionID': 'ses-1',
                            'type': 'text',
                            'text': '最终报告已生成。',
                        },
                    ],
                },
            ],
        ],
        global_event_lines=[],
    )

    emitted: list[tuple[str, object]] = []
    streamed = await runtime._stream_session_events(
        runtime_session_id='ses-1',
        request=RuntimeSessionRequest(session_id='session-1', prompt='生成最终报告', workspace_path=workspace),
        emit=lambda envelope: _collect_event(emitted, envelope.type, envelope.payload),
    )

    statuses = [payload for event_type, payload in emitted if event_type == 'session.status']
    message_deltas = [
        payload for event_type, payload in emitted
        if event_type == 'session.message_delta' and isinstance(payload, dict)
    ]

    assert streamed is True
    assert statuses == [{'status': 'completed'}]
    assert any(payload.get('id') == 'msg-assistant-2' for payload in message_deltas)


@pytest.mark.asyncio
async def test_opencode_runtime_recovers_messages_from_opencode_database(tmp_path: Path) -> None:
    from app.services.agent_runtime import OpenCodeAgentRuntimeClient

    app_support_dir = tmp_path / 'app-support'
    database_path = app_support_dir / '.local' / 'share' / 'opencode' / 'opencode.db'
    database_path.parent.mkdir(parents=True)
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            '''
            CREATE TABLE message (
                id text PRIMARY KEY,
                session_id text NOT NULL,
                time_created integer NOT NULL,
                time_updated integer NOT NULL,
                data text NOT NULL
            );
            CREATE TABLE part (
                id text PRIMARY KEY,
                message_id text NOT NULL,
                session_id text NOT NULL,
                time_created integer NOT NULL,
                time_updated integer NOT NULL,
                data text NOT NULL
            );
            '''
        )
        connection.execute(
            'INSERT INTO message VALUES (?, ?, ?, ?, ?)',
            (
                'msg-assistant-1',
                'runtime-session-1',
                1710000001000,
                1710000002000,
                json.dumps({'role': 'assistant', 'agent': 'geo', 'time': {'created': 1710000001000, 'completed': 1710000002000}, 'finish': 'stop'}),
            ),
        )
        connection.execute(
            'INSERT INTO part VALUES (?, ?, ?, ?, ?, ?)',
            (
                'part-text-1',
                'msg-assistant-1',
                'runtime-session-1',
                1710000001500,
                1710000001500,
                json.dumps({'type': 'text', 'text': '从 OpenCode 数据库恢复。'}, ensure_ascii=False),
            ),
        )

    runtime = OpenCodeAgentRuntimeClient(Settings(app_support_dir=app_support_dir, glm_api_key='test-key'))

    messages = await runtime.fetch_session_messages('runtime-session-1')

    assert messages == [
        {
            'id': 'msg-assistant-1',
            'role': 'assistant',
            'agent': 'geo',
            'created_at': '2024-03-09T16:00:01+00:00',
            'parts': [
                {
                    'id': 'part-text-1',
                    'messageID': 'msg-assistant-1',
                    'sessionID': 'runtime-session-1',
                    'type': 'text',
                    'text': '从 OpenCode 数据库恢复。',
                }
            ],
        }
    ]


@pytest.mark.asyncio
async def test_opencode_runtime_preserves_record_evidence_artifact_events(tmp_path: Path) -> None:
    from app.services.agent_runtime import OpenCodeAgentRuntimeClient, RuntimeSessionRequest

    workspace = tmp_path / 'workspace'
    workspace.mkdir(parents=True, exist_ok=True)
    evidence_payload = {
        'status': 'completed',
        'summary': '已记录运行证据。',
        'tool': {'name': 'record_run_evidence', 'family': 'evidence'},
        'session_context_id': 'context-1',
        'record_id': 'evidence-1',
        'record_type': 'artifact',
        'artifact': {
            'id': 'artifact-1',
            'title': 'KDE 热点图',
            'path': 'outputs/map.png',
            'kind': 'map',
            'description': '最终热点图。',
            'format': 'png',
            'artifact_stage': 'final',
            'display_hint': 'image',
            'evidence_record_id': 'evidence-1',
            'provenance': {},
        },
    }

    runtime = OpenCodeAgentRuntimeClient(Settings(state_dir=tmp_path / '.state', glm_api_key='test-key'))
    runtime._client = FakeRuntimeHttpClient(
        statuses=[{'ses-1': {'type': 'busy'}}, {'ses-1': {'type': 'idle'}}],
        message_snapshots=[[
            {
                'info': {'id': 'msg-assistant-1', 'role': 'assistant', 'agent': 'geo', 'time': {'created': 1710000000000}},
                'parts': [
                    {
                        'id': 'tool-evidence',
                        'type': 'tool',
                        'tool': 'geospatial_record_run_evidence',
                        'state': {
                            'input': {'record_type': 'artifact', 'title': 'KDE 热点图'},
                            'output': json.dumps(evidence_payload, ensure_ascii=False),
                        },
                    }
                ],
            }
        ], [
            {
                'info': {'id': 'msg-assistant-1', 'role': 'assistant', 'agent': 'geo', 'time': {'created': 1710000000000}},
                'parts': [
                    {
                        'id': 'tool-evidence',
                        'type': 'tool',
                        'tool': 'geospatial_record_run_evidence',
                        'state': {
                            'input': {'record_type': 'artifact', 'title': 'KDE 热点图'},
                            'output': json.dumps(evidence_payload, ensure_ascii=False),
                        },
                    }
                ],
            }
        ]],
    )

    emitted: list[tuple[str, object]] = []
    await runtime._poll_session(
        runtime_session_id='ses-1',
        request=RuntimeSessionRequest(session_id='session-1', prompt='记录产物', workspace_path=workspace),
        emit=lambda envelope: _collect_event(emitted, envelope.type, envelope.payload),
    )

    artifacts = [payload for event_type, payload in emitted if event_type == 'session.artifact']
    assert artifacts == [evidence_payload['artifact']]


@pytest.mark.asyncio
async def test_opencode_runtime_preserves_non_artifact_evidence_details(tmp_path: Path) -> None:
    from app.services.agent_runtime import OpenCodeAgentRuntimeClient, RuntimeSessionRequest

    workspace = tmp_path / 'workspace'
    workspace.mkdir(parents=True, exist_ok=True)
    evidence_payload = {
        'status': 'completed',
        'summary': '已记录运行证据。',
        'tool': {'name': 'record_run_evidence', 'family': 'evidence'},
        'session_context_id': 'context-1',
        'record_id': 'evidence-1',
        'record_type': 'verification_fact',
        'evidence': {
            'id': 'evidence-1',
            'record_type': 'verification_fact',
            'title': '制图诚实性检查',
            'description': '比例尺、图例和 CRS 说明完整。',
            'category': 'cartography',
            'created_at': '2026-04-21T10:00:00+00:00',
            'data': {
                'status': 'passed',
                'reason_code': 'map_honesty_checked',
                'checked_inputs': ['haidian_heatmap.png', 'haidian_kde_density.tif'],
                'conclusion': '地图标注和投影说明可复核。',
            },
            'provenance': {'command': 'uv run python scripts/review_map.py'},
        },
    }

    runtime = OpenCodeAgentRuntimeClient(Settings(state_dir=tmp_path / '.state', glm_api_key='test-key'))
    runtime._client = FakeRuntimeHttpClient(
        statuses=[{'ses-1': {'type': 'busy'}}, {'ses-1': {'type': 'idle'}}],
        message_snapshots=[[
            {
                'info': {'id': 'msg-assistant-1', 'role': 'assistant', 'agent': 'geo', 'time': {'created': 1710000000000}},
                'parts': [
                    {
                        'id': 'tool-evidence',
                        'type': 'tool',
                        'tool': 'geospatial_record_run_evidence',
                        'state': {
                            'input': {'record_type': 'verification_fact', 'title': '制图诚实性检查'},
                            'output': json.dumps(evidence_payload, ensure_ascii=False),
                        },
                    }
                ],
            }
        ], [
            {
                'info': {'id': 'msg-assistant-1', 'role': 'assistant', 'agent': 'geo', 'time': {'created': 1710000000000}},
                'parts': [
                    {
                        'id': 'tool-evidence',
                        'type': 'tool',
                        'tool': 'geospatial_record_run_evidence',
                        'state': {
                            'input': {'record_type': 'verification_fact', 'title': '制图诚实性检查'},
                            'output': json.dumps(evidence_payload, ensure_ascii=False),
                        },
                    }
                ],
            }
        ]],
    )

    emitted: list[tuple[str, object]] = []
    await runtime._poll_session(
        runtime_session_id='ses-1',
        request=RuntimeSessionRequest(session_id='session-1', prompt='记录验证事实', workspace_path=workspace),
        emit=lambda envelope: _collect_event(emitted, envelope.type, envelope.payload),
    )

    evidence_events = [payload for event_type, payload in emitted if event_type == 'session.timeline_entry' and payload['kind'] == 'evidence']
    assert evidence_events == [
        {
            'id': 'evidence-evidence-1',
            'kind': 'evidence',
            'text': '制图诚实性检查',
            'title': '制图诚实性检查',
            'detail': '比例尺、图例和 CRS 说明完整。',
            'record_type': 'verification_fact',
            'category': 'cartography',
            'evidence_record_id': 'evidence-1',
            'created_at': '2026-04-21T10:00:00+00:00',
            'data': evidence_payload['evidence']['data'],
            'provenance': evidence_payload['evidence']['provenance'],
        }
    ]


@pytest.mark.asyncio
async def test_opencode_runtime_streams_structured_question_requests_from_global_events(tmp_path: Path) -> None:
    from app.services.agent_runtime import OpenCodeAgentRuntimeClient, RuntimeSessionRequest

    workspace = tmp_path / 'workspace'
    workspace.mkdir(parents=True, exist_ok=True)

    runtime = OpenCodeAgentRuntimeClient(Settings(state_dir=tmp_path / '.state', glm_api_key='test-key'))
    runtime._client = FakeStreamingRuntimeHttpClient(
        statuses=[{'ses-1': {'type': 'busy'}}, {'ses-1': {'type': 'idle'}}],
        session_details=[{'id': 'ses-1', 'title': 'Runtime title'}],
        message_snapshots=[[
            {
                'info': {'id': 'msg-user-1', 'role': 'user', 'agent': 'geo', 'time': {'created': 1710000000000}},
                'parts': [{'type': 'text', 'text': 'Need a study area decision', 'id': 'part-user-1'}],
            },
        ], [
            {
                'info': {'id': 'msg-user-1', 'role': 'user', 'agent': 'geo', 'time': {'created': 1710000000000}},
                'parts': [{'type': 'text', 'text': 'Need a study area decision', 'id': 'part-user-1'}],
            },
        ]],
        global_event_lines=[
            'data: {"directory":"/tmp/workspace","payload":{"type":"message.updated","properties":{"sessionID":"ses-1","info":{"id":"msg-assistant-1","role":"assistant","agent":"geo","time":{"created":1710000001000}}}}}',
            'data: {"directory":"/tmp/workspace","payload":{"type":"question.asked","properties":{"id":"question-request-1","sessionID":"ses-1","questions":[{"header":"研究区","question":"请选择研究区范围","options":[{"label":"使用默认北京市区县边界","description":"使用系统默认行政区边界继续执行"}]},{"header":"输出语言","question":"报告使用什么语言","options":[{"label":"中文","description":"使用简体中文生成最终报告"}]}]}}}',
            'data: {"directory":"/tmp/workspace","payload":{"type":"session.status","properties":{"sessionID":"ses-1","status":{"type":"idle"}}}}',
        ],
    )

    emitted: list[tuple[str, object]] = []
    await runtime._poll_session(
        runtime_session_id='ses-1',
        request=RuntimeSessionRequest(session_id='session-1', prompt='Need a study area decision', workspace_path=workspace),
        emit=lambda envelope: _collect_event(emitted, envelope.type, envelope.payload),
    )

    questions = [payload for event_type, payload in emitted if event_type == 'session.question']
    statuses = [payload for event_type, payload in emitted if event_type == 'session.status']

    assert questions == [
        {
            'id': 'question-request-1',
            'prompt': '请选择研究区范围',
            'source': 'runtime',
            'questions': [
                {
                    'header': '研究区',
                    'question': '请选择研究区范围',
                    'options': [
                        {
                            'label': '使用默认北京市区县边界',
                            'description': '使用系统默认行政区边界继续执行',
                        }
                    ],
                },
                {
                    'header': '输出语言',
                    'question': '报告使用什么语言',
                    'options': [
                        {
                            'label': '中文',
                            'description': '使用简体中文生成最终报告',
                        }
                    ],
                },
            ],
        }
    ]
    assert {'status': 'waiting_for_input'} in statuses
    assert {'status': 'completed'} not in statuses


@pytest.mark.asyncio
async def test_opencode_runtime_polls_pending_questions_from_runtime_question_endpoint(tmp_path: Path) -> None:
    from app.services.agent_runtime import OpenCodeAgentRuntimeClient, RuntimeSessionRequest

    workspace = tmp_path / 'workspace'
    workspace.mkdir(parents=True, exist_ok=True)

    runtime = OpenCodeAgentRuntimeClient(Settings(state_dir=tmp_path / '.state', glm_api_key='test-key'))
    runtime._client = FakeRuntimeHttpClient(
        statuses=[{'ses-1': {'type': 'busy'}}, {'ses-1': {'type': 'idle'}}],
        session_details=[{'id': 'ses-1', 'title': 'Runtime title'}, {'id': 'ses-1', 'title': 'Runtime title'}],
        message_snapshots=[[
            {
                'info': {'id': 'msg-user-1', 'role': 'user', 'agent': 'geo', 'time': {'created': 1710000000000}},
                'parts': [{'type': 'text', 'text': 'Need a study area decision', 'id': 'part-user-1'}],
            },
            {
                'info': {'id': 'msg-assistant-1', 'role': 'assistant', 'agent': 'geo', 'time': {'created': 1710000001000}},
                'parts': [{
                    'type': 'tool',
                    'tool': 'question',
                    'id': 'part-tool-1',
                    'state': {'status': 'running', 'input': {'questions': []}},
                }],
            },
        ], [
            {
                'info': {'id': 'msg-user-1', 'role': 'user', 'agent': 'geo', 'time': {'created': 1710000000000}},
                'parts': [{'type': 'text', 'text': 'Need a study area decision', 'id': 'part-user-1'}],
            },
            {
                'info': {'id': 'msg-assistant-1', 'role': 'assistant', 'agent': 'geo', 'time': {'created': 1710000001000}},
                'parts': [{
                    'type': 'tool',
                    'tool': 'question',
                    'id': 'part-tool-1',
                    'state': {'status': 'running', 'input': {'questions': []}},
                }],
            },
        ]],
        questions=[[
            {
                'id': 'question-request-1',
                'sessionID': 'ses-1',
                'questions': [
                    {
                        'header': '研究区',
                        'question': '请选择研究区范围',
                        'options': [{'label': '使用默认北京市区县边界', 'description': '使用系统默认行政区边界继续执行'}],
                    }
                ],
            }
        ], [
            {
                'id': 'question-request-1',
                'sessionID': 'ses-1',
                'questions': [
                    {
                        'header': '研究区',
                        'question': '请选择研究区范围',
                        'options': [{'label': '使用默认北京市区县边界', 'description': '使用系统默认行政区边界继续执行'}],
                    }
                ],
            }
        ]],
    )

    emitted: list[tuple[str, object]] = []
    await runtime._poll_session(
        runtime_session_id='ses-1',
        request=RuntimeSessionRequest(session_id='session-1', prompt='Need a study area decision', workspace_path=workspace),
        emit=lambda envelope: _collect_event(emitted, envelope.type, envelope.payload),
    )

    questions = [payload for event_type, payload in emitted if event_type == 'session.question']
    statuses = [payload for event_type, payload in emitted if event_type == 'session.status']

    assert questions == [
        {
            'id': 'question-request-1',
            'prompt': '请选择研究区范围',
            'source': 'runtime',
            'questions': [
                {
                    'header': '研究区',
                    'question': '请选择研究区范围',
                    'options': [
                        {
                            'label': '使用默认北京市区县边界',
                            'description': '使用系统默认行政区边界继续执行',
                        }
                    ],
                }
            ],
        }
    ]
    assert {'status': 'waiting_for_input'} in statuses
    assert {'status': 'completed'} not in statuses


@pytest.mark.asyncio
async def test_opencode_runtime_poll_session_emits_context_and_evidence_tool_events(tmp_path: Path) -> None:
    from app.models import GeospatialSessionContext
    from app.services.geospatial_mcp_server import format_get_session_context_output, format_record_run_evidence_output, get_session_context_payload, record_run_evidence_payload
    from app.services.agent_runtime import OpenCodeAgentRuntimeClient, RuntimeSessionRequest
    from app.services.session_store import SessionStore

    workspace = tmp_path / 'workspace'
    workspace.mkdir(parents=True, exist_ok=True)
    artifact_path = workspace / 'outputs' / 'map.png'
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_bytes(b'png')
    settings = Settings(state_dir=tmp_path / '.state', app_support_dir=tmp_path / 'support', database_path=tmp_path / 'support' / 'metadata.db', workspace_root=tmp_path / 'support' / 'workspace', glm_api_key='test-key')
    SessionStore(settings=settings).save_geospatial_session_context(
        GeospatialSessionContext(id='context-1', session_id='session-1', prompt='对北京出租车轨迹做 KDE 热点分析', workspace_path=str(workspace))
    )
    context_payload = get_session_context_payload(session_context_id='context-1', settings=settings)
    evidence_payload = record_run_evidence_payload(
        session_context_id='context-1',
        record_type='artifact',
        title='KDE 热点图',
        path=str(artifact_path),
        format='png',
        artifact_stage='final',
        display_hint='image',
        category='map',
        settings=settings,
    )

    runtime = OpenCodeAgentRuntimeClient(settings)
    runtime._client = FakeRuntimeHttpClient(
        statuses=[{'ses-1': {'type': 'busy'}}, {'ses-1': {'type': 'idle'}}],
        message_snapshots=[
            [
                {
                    'info': {'id': 'msg-assistant-1', 'role': 'assistant', 'agent': 'geo', 'time': {'created': 1710000000000}},
                    'parts': [
                        {
                            'id': 'tool-context',
                            'type': 'tool',
                            'tool': 'geospatial_get_session_context',
                            'state': {
                                'input': {'session_context_id': 'context-1'},
                                'output': format_get_session_context_output(context_payload),
                            },
                        },
                        {
                            'id': 'tool-evidence',
                            'type': 'tool',
                            'tool': 'geospatial_record_run_evidence',
                            'state': {
                                'input': {'record_type': 'artifact'},
                                'output': format_record_run_evidence_output(evidence_payload),
                            },
                        },
                        {'type': 'text', 'text': evidence_payload['summary']},
                    ],
                }
            ],
            [
                {
                    'info': {'id': 'msg-assistant-1', 'role': 'assistant', 'agent': 'geo', 'time': {'created': 1710000000000}},
                    'parts': [
                        {
                            'id': 'tool-context',
                            'type': 'tool',
                            'tool': 'geospatial_get_session_context',
                            'state': {
                                'input': {'session_context_id': 'context-1'},
                                'output': format_get_session_context_output(context_payload),
                            },
                        },
                        {
                            'id': 'tool-evidence',
                            'type': 'tool',
                            'tool': 'geospatial_record_run_evidence',
                            'state': {
                                'input': {'record_type': 'artifact'},
                                'output': format_record_run_evidence_output(evidence_payload),
                            },
                        },
                        {'type': 'text', 'text': evidence_payload['summary']},
                    ],
                }
            ],
        ],
    )

    emitted: list[tuple[str, object]] = []
    await runtime._poll_session(
        runtime_session_id='ses-1',
        request=RuntimeSessionRequest(session_id='session-1', prompt='对北京出租车轨迹做 KDE 热点分析，使用默认北京市区县边界', workspace_path=workspace, geospatial_context_id='context-1'),
        emit=lambda envelope: _collect_event(emitted, envelope.type, envelope.payload),
    )

    event_types = [event_type for event_type, _ in emitted]
    assert 'session.message_delta' in event_types
    assert 'session.plan' not in event_types
    assert 'session.plan_group' not in event_types
    assert 'session.artifact' in event_types
    assert ('session.status', {'status': 'completed'}) in emitted


@pytest.mark.asyncio
async def test_opencode_runtime_poll_session_waits_after_tool_call_turn(tmp_path: Path) -> None:
    from app.services.agent_runtime import OpenCodeAgentRuntimeClient, RuntimeSessionRequest

    workspace = tmp_path / 'workspace'
    workspace.mkdir(parents=True, exist_ok=True)
    intermediate_message = {
        'info': {
            'id': 'msg-assistant-tool-turn',
            'role': 'assistant',
            'agent': 'geo',
            'time': {'created': 1710000000000, 'completed': 1710000001000},
            'finish': 'tool-calls',
        },
        'parts': [
            {
                'id': 'tool-todos',
                'type': 'tool',
                'tool': 'geospatial_update_todos',
                'state': {
                    'status': 'completed',
                    'input': {'entries': [{'content': '核验数据', 'status': 'in_progress'}]},
                    'output': '<todos status="updated"></todos>',
                },
            }
        ],
    }
    final_message = {
        'info': {
            'id': 'msg-assistant-final',
            'role': 'assistant',
            'agent': 'geo',
            'time': {'created': 1710000002000, 'completed': 1710000003000},
            'finish': 'stop',
        },
        'parts': [{'id': 'part-final-text', 'type': 'text', 'text': '完成。'}],
    }
    runtime = OpenCodeAgentRuntimeClient(Settings(state_dir=tmp_path / '.state', glm_api_key='test-key'))
    runtime._client = FakeRuntimeHttpClient(
        statuses=[{'ses-1': {'type': 'idle'}}, {'ses-1': {'type': 'idle'}}],
        message_snapshots=[[intermediate_message], [intermediate_message, final_message]],
    )

    emitted: list[tuple[str, object]] = []
    await runtime._poll_session(
        runtime_session_id='ses-1',
        request=RuntimeSessionRequest(session_id='session-1', prompt='继续执行', workspace_path=workspace),
        emit=lambda envelope: _collect_event(emitted, envelope.type, envelope.payload),
    )

    message_deltas = [payload for event_type, payload in emitted if event_type == 'session.message_delta']
    statuses = [payload for event_type, payload in emitted if event_type == 'session.status']
    assert any(isinstance(message, dict) and message.get('id') == 'msg-assistant-final' for message in message_deltas)
    assert statuses == [{'status': 'completed'}]


@pytest.mark.asyncio
async def test_opencode_runtime_does_not_emit_plan_group_from_unknown_tool_payload(tmp_path: Path) -> None:
    from app.services.agent_runtime import OpenCodeAgentRuntimeClient

    runtime = OpenCodeAgentRuntimeClient(Settings(state_dir=tmp_path / '.state', glm_api_key='test-key'))
    emitted: list[tuple[str, object]] = []

    await runtime._emit_message_side_effects(
        message={
            'info': {
                'id': 'msg-spatial-prep',
                'role': 'assistant',
                'agent': 'spatial-prep',
                'time': {'created': 1710000000000},
            },
            'parts': [
                {
                    'id': 'tool-plan',
                    'type': 'tool',
                    'tool': 'legacy_plan_writer',
                    'state': {
                        'input': {'agent': 'fake-owner'},
                        'output': json.dumps(
                            {
                                'status': 'completed',
                                'tool': {'name': 'legacy_plan_writer', 'family': 'planning'},
                                'title': '空间整备计划',
                                'agent': 'fake-owner',
                                'entries': [
                                    {'content': '核验 CRS 与研究区边界', 'status': 'in_progress'},
                                    {'content': '等待用户补充轨迹目录', 'status': 'blocked'},
                                ],
                            },
                            ensure_ascii=False,
                        ),
                    },
                }
            ],
        },
        attached_dirs=[],
        seen_tool_part_ids=set(),
        emit=lambda envelope: _collect_event(emitted, envelope.type, envelope.payload),
    )

    assert [event_type for event_type, _ in emitted].count('session.plan_group') == 0


@pytest.mark.asyncio
async def test_opencode_runtime_emits_plan_group_from_update_todos_tool(tmp_path: Path) -> None:
    from app.services.agent_runtime import OpenCodeAgentRuntimeClient
    from app.services.geospatial_mcp_server import format_update_todos_output, update_todos_payload

    runtime = OpenCodeAgentRuntimeClient(Settings(state_dir=tmp_path / '.state', glm_api_key='test-key'))
    emitted: list[tuple[str, object]] = []

    todo_entries = [
        {'content': '核验 CRS 与研究区边界', 'status': 'in_progress'},
        {'content': '等待用户补充轨迹目录', 'status': 'blocked'},
    ]
    payload = update_todos_payload(entries=todo_entries, settings=runtime.settings)
    await runtime._emit_message_side_effects(
        message={
            'info': {
                'id': 'msg-spatial-prep',
                'role': 'assistant',
                'agent': 'spatial-prep',
                'time': {'created': 1710000000000},
            },
            'parts': [
                {
                    'id': 'tool-todos',
                    'type': 'tool',
                    'tool': 'geospatial_update_todos',
                    'state': {
                        'input': {'entries': todo_entries},
                        'output': format_update_todos_output(payload),
                    },
                }
            ],
        },
        attached_dirs=[],
        seen_tool_part_ids=set(),
        emit=lambda envelope: _collect_event(emitted, envelope.type, envelope.payload),
    )

    plan_groups = [payload for event_type, payload in emitted if event_type == 'session.plan_group']
    assert len(plan_groups) == 1
    assert plan_groups[0]['agent'] == 'spatial-prep'
    assert [entry['label'] for entry in plan_groups[0]['entries']] == ['核验 CRS 与研究区边界', '等待用户补充轨迹目录']
    assert [entry['status'] for entry in plan_groups[0]['entries']] == ['in_progress', 'blocked']


@pytest.mark.asyncio
async def test_opencode_runtime_skips_previous_tool_side_effects_on_resume(tmp_path: Path) -> None:
    from app.services.agent_runtime import OpenCodeAgentRuntimeClient, RuntimeSessionRequest
    from app.services.geospatial_mcp_server import format_update_todos_output, update_todos_payload

    workspace = tmp_path / 'workspace'
    workspace.mkdir(parents=True, exist_ok=True)
    todo_entries = [{'content': '继续生成热力图', 'status': 'in_progress'}]
    runtime = OpenCodeAgentRuntimeClient(Settings(state_dir=tmp_path / '.state', glm_api_key='test-key'))
    payload = update_todos_payload(entries=todo_entries, settings=runtime.settings)
    messages = [
        {
            'info': {'id': 'msg-old', 'role': 'assistant', 'agent': 'geo', 'time': {'created': 1710000000000}},
            'parts': [
                {
                    'id': 'old-failed-todos',
                    'type': 'tool',
                    'tool': 'geospatial_update_todos',
                    'state': {
                        'status': 'completed',
                        'input': {'entries': [{'task': '旧的错误待办', 'status': 'in_progress'}]},
                        'output': '<error tool="update_todos" reason="invalid_todo_entries"><message>旧错误</message></error>',
                    },
                }
            ],
        },
        {
            'info': {'id': 'msg-new', 'role': 'assistant', 'agent': 'geo', 'time': {'created': 1710000001000}},
            'parts': [
                {
                    'id': 'new-todos',
                    'type': 'tool',
                    'tool': 'geospatial_update_todos',
                    'state': {
                        'status': 'completed',
                        'input': {'entries': todo_entries},
                        'output': format_update_todos_output(payload),
                    },
                }
            ],
        },
    ]
    runtime._client = FakeRuntimeHttpClient(
        statuses=[{'ses-1': {'type': 'busy'}}, {'ses-1': {'type': 'idle'}}],
        message_snapshots=[messages, messages],
    )

    emitted: list[tuple[str, object]] = []
    await runtime._poll_session(
        runtime_session_id='ses-1',
        request=RuntimeSessionRequest(
            session_id='session-1',
            prompt='继续',
            workspace_path=workspace,
            runtime_session_id='ses-1',
            processed_tool_part_ids={'old-failed-todos'},
        ),
        emit=lambda envelope: _collect_event(emitted, envelope.type, envelope.payload),
    )

    assert [event_type for event_type, _ in emitted].count('session.issue') == 0
    plan_groups = [payload for event_type, payload in emitted if event_type == 'session.plan_group']
    assert len(plan_groups) == 1
    assert [entry['label'] for entry in plan_groups[0]['entries']] == ['继续生成热力图']


@pytest.mark.asyncio
async def test_opencode_runtime_waits_for_completed_update_todos_before_plan_group(tmp_path: Path) -> None:
    from app.services.agent_runtime import OpenCodeAgentRuntimeClient
    from app.services.geospatial_mcp_server import format_update_todos_output, update_todos_payload

    runtime = OpenCodeAgentRuntimeClient(Settings(state_dir=tmp_path / '.state', glm_api_key='test-key'))
    emitted: list[tuple[str, object]] = []
    seen_tool_part_ids: set[str] = set()
    pending_message = {
        'info': {
            'id': 'msg-geo',
            'role': 'assistant',
            'agent': 'geo',
            'time': {'created': 1710000000000},
        },
        'parts': [
            {
                'id': 'tool-todos',
                'type': 'tool',
                'tool': 'geospatial_update_todos',
                'state': {
                    'status': 'running',
                    'input': {'entries': [{'task': '错误字段', 'status': 'in_progress'}]},
                },
            }
        ],
    }
    todo_entries = [{'content': '核验 CRS 与研究区边界', 'status': 'in_progress'}]
    completed_payload = update_todos_payload(entries=todo_entries, settings=runtime.settings)
    completed_message = {
        **pending_message,
        'parts': [
            {
                'id': 'tool-todos',
                'type': 'tool',
                'tool': 'geospatial_update_todos',
                'state': {
                    'status': 'completed',
                    'input': {'entries': todo_entries},
                    'output': format_update_todos_output(completed_payload),
                },
            }
        ],
    }

    await runtime._emit_message_side_effects(
        message=pending_message,
        attached_dirs=[],
        seen_tool_part_ids=seen_tool_part_ids,
        emit=lambda envelope: _collect_event(emitted, envelope.type, envelope.payload),
    )
    await runtime._emit_message_side_effects(
        message=completed_message,
        attached_dirs=[],
        seen_tool_part_ids=seen_tool_part_ids,
        emit=lambda envelope: _collect_event(emitted, envelope.type, envelope.payload),
    )

    plan_groups = [payload for event_type, payload in emitted if event_type == 'session.plan_group']
    assert len(plan_groups) == 1
    assert [entry['label'] for entry in plan_groups[0]['entries']] == ['核验 CRS 与研究区边界']


@pytest.mark.asyncio
async def test_opencode_runtime_poll_session_keeps_failed_evidence_visible(tmp_path: Path) -> None:
    from app.services.agent_runtime import OpenCodeAgentRuntimeClient, RuntimeSessionRequest
    from app.services.geospatial_mcp_server import format_record_run_evidence_output

    workspace = tmp_path / 'workspace'
    workspace.mkdir(parents=True, exist_ok=True)
    failed_evidence_payload = {
        'status': 'failed',
        'summary': '证据记录失败。',
        'tool': {'name': 'record_run_evidence', 'family': 'evidence'},
        'reason': 'artifact_path_outside_workspace',
    }

    runtime = OpenCodeAgentRuntimeClient(Settings(state_dir=tmp_path / '.state', glm_api_key='test-key'))
    runtime._client = FakeRuntimeHttpClient(
        statuses=[{'ses-1': {'type': 'busy'}}, {'ses-1': {'type': 'idle'}}],
        message_snapshots=[[
            {
                'info': {'id': 'msg-assistant-1', 'role': 'assistant', 'agent': 'geo', 'time': {'created': 1710000000000}},
                'parts': [
                    {
                        'id': 'tool-evidence',
                        'type': 'tool',
                            'tool': 'geospatial_record_run_evidence',
                            'state': {
                                'input': {'record_type': 'artifact'},
                                'output': format_record_run_evidence_output(failed_evidence_payload),
                            },
                        }
                ],
            }
        ], [
            {
                'info': {'id': 'msg-assistant-1', 'role': 'assistant', 'agent': 'geo', 'time': {'created': 1710000000000}},
                'parts': [
                    {
                        'id': 'tool-evidence',
                        'type': 'tool',
                            'tool': 'geospatial_record_run_evidence',
                            'state': {
                                'input': {'record_type': 'artifact'},
                                'output': format_record_run_evidence_output(failed_evidence_payload),
                            },
                        }
                ],
            }
        ]],
    )

    emitted: list[tuple[str, object]] = []
    await runtime._poll_session(
        runtime_session_id='ses-1',
        request=RuntimeSessionRequest(session_id='session-1', prompt='失败案例', workspace_path=workspace),
        emit=lambda envelope: _collect_event(emitted, envelope.type, envelope.payload),
    )

    timeline_entries = [payload for event_type, payload in emitted if event_type == 'session.timeline_entry']
    issue_entries = [payload for event_type, payload in emitted if event_type == 'session.issue']
    assert any(isinstance(entry, dict) and entry.get('text') == '证据记录失败。' for entry in timeline_entries)
    assert any(isinstance(entry, dict) and entry.get('type') == 'tool_failure' and entry.get('title') == '证据记录失败' for entry in issue_entries)


async def _collect_event(events: list[tuple[str, object]], event_type: str, payload: object) -> None:
    events.append((event_type, payload))


async def _discard_event(_envelope) -> None:
    return None


def test_opencode_runtime_writes_managed_assets_into_app_config_dir(tmp_path: Path) -> None:
    from app.services.agent_runtime import OpenCodeAgentRuntimeClient

    runtime = OpenCodeAgentRuntimeClient(Settings(app_support_dir=tmp_path / 'geo-agent', glm_api_key='test-key'))
    config_path = runtime._global_config_path()
    runtime._write_global_config_file(port=43111)
    config = json.loads(config_path.read_text(encoding='utf-8'))

    assert config_path == tmp_path / 'geo-agent' / '.config' / 'opencode' / 'opencode.json'
    assert config_path.exists()
    config_root = tmp_path / 'geo-agent' / '.config' / 'opencode'
    skills_root = tmp_path / 'geo-agent' / '.config' / 'opencode' / 'skills'
    assert (skills_root / 'geospatial-kde-runbook' / 'SKILL.md').exists()
    assert (skills_root / 'geospatial-crs-projection-safety' / 'SKILL.md').exists()
    assert (config_root / 'manifest.json').exists()
    assert not (tmp_path / 'geo-agent' / 'runtime-config').exists()
    assert config['tools']['codesearch'] is False
    assert config['tools']['lsp'] is False
    assert config['agent']['general']['disable'] is True
    assert config['agent']['explore']['disable'] is True


def test_opencode_runtime_builds_deepseek_config_with_custom_provider(tmp_path: Path) -> None:
    from app.services.agent_runtime import OpenCodeAgentRuntimeClient

    runtime = OpenCodeAgentRuntimeClient(
        Settings(
            state_dir=tmp_path / '.state',
            model_provider='deepseek',
            deepseek_api_key='deepseek-key',
            deepseek_model='deepseek-v4-pro',
        )
    )

    config = runtime._build_runtime_config(port=43111, cors_origin='http://127.0.0.1:5173')

    assert config['enabled_providers'] == ['deepseek']
    assert config['model'] == 'deepseek/deepseek-v4-pro'
    assert config['small_model'] == 'deepseek/deepseek-v4-pro'
    assert config['provider']['deepseek']['npm'] == '@ai-sdk/openai-compatible'
    assert config['provider']['deepseek']['name'] == 'DeepSeek'
    assert config['provider']['deepseek']['options']['baseURL'] == 'https://api.deepseek.com'
    assert config['provider']['deepseek']['options']['apiKey'] == 'deepseek-key'
    assert config['provider']['deepseek']['models'] == {
        'deepseek-v4-pro': {'name': 'deepseek-v4-pro'}
    }


def test_opencode_runtime_writes_selected_deepseek_auth(tmp_path: Path) -> None:
    from app.services.agent_runtime import OpenCodeAgentRuntimeClient

    support_root = tmp_path / 'geo-agent'
    runtime = OpenCodeAgentRuntimeClient(
        Settings(
            app_support_dir=support_root,
            model_provider='deepseek',
            deepseek_api_key='deepseek-key',
        )
    )

    runtime._build_server_env(port=43111)
    auth_path = support_root / '.local' / 'share' / 'opencode' / 'auth.json'
    auth = json.loads(auth_path.read_text(encoding='utf-8'))

    assert auth == {'deepseek': {'type': 'api', 'key': 'deepseek-key'}}


def test_opencode_runtime_removes_legacy_workspace_config_file(tmp_path: Path) -> None:
    from app.services.agent_runtime import OpenCodeAgentRuntimeClient

    runtime = OpenCodeAgentRuntimeClient(Settings(app_support_dir=tmp_path / 'geo-agent', glm_api_key='test-key'))
    legacy = tmp_path / 'geo-agent' / 'workspace' / 'config.json'
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text('{}', encoding='utf-8')

    runtime._build_server_env(port=43111)

    assert not legacy.exists()
    env = runtime._build_server_env(port=43111)
    assert 'OPENCODE_DISABLE_EXTERNAL_SKILLS' not in env


def test_default_workspace_root_uses_shared_workspace_directory(tmp_path: Path) -> None:
    settings = Settings(app_support_dir=tmp_path / 'geo-agent')

    assert settings.resolved_workspace_root() == tmp_path / 'geo-agent' / 'workspace'
