from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
import os
from pathlib import Path
import socket
import sys
from typing import Any, TextIO
import urllib.error
import urllib.request

from app.evaluation.runner import CampaignDirectories


APP_STDOUT_LOG = 'app-stdout.log'
APP_STDERR_LOG = 'app-stderr.log'
APP_LIFECYCLE_LOG = 'app-lifecycle.json'
EVALUATION_PORT_ENV = 'GEO_AGENT_EVALUATION_PORT'


class EvaluationAppLifecycleError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class EvaluationAppHandle:
    base_url: str
    process: asyncio.subprocess.Process
    stdout_log_path: Path
    stderr_log_path: Path
    lifecycle_log_path: Path

    async def shutdown(self, *, timeout_seconds: float = 10.0) -> int | None:
        if self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=timeout_seconds)
            except TimeoutError:
                self.process.kill()
                await self.process.wait()
        _write_json(
            self.lifecycle_log_path,
            {
                'base_url': self.base_url,
                'returncode': self.process.returncode,
                'stdout_log': self.stdout_log_path.name,
                'stderr_log': self.stderr_log_path.name,
                'shutdown': 'completed',
            },
        )
        return self.process.returncode


async def start_evaluation_app(
    directories: CampaignDirectories,
    *,
    readiness_timeout_seconds: float,
    require_geospatial_environment: bool = False,
    host: str = '127.0.0.1',
    port: int | None = None,
    command: Sequence[str] | None = None,
    extra_env: Mapping[str, str] | None = None,
) -> EvaluationAppHandle:
    resolved_port: int = port or _allocate_port(host)
    base_url: str = f'http://{host}:{resolved_port}'
    stdout_log_path: Path = directories.logs / APP_STDOUT_LOG
    stderr_log_path: Path = directories.logs / APP_STDERR_LOG
    lifecycle_log_path: Path = directories.logs / APP_LIFECYCLE_LOG
    directories.logs.mkdir(parents=True, exist_ok=True)

    stdout_handle: TextIO
    stderr_handle: TextIO
    stdout_handle = stdout_log_path.open('w', encoding='utf-8')
    stderr_handle = stderr_log_path.open('w', encoding='utf-8')
    process: asyncio.subprocess.Process | None = None
    try:
        process = await asyncio.create_subprocess_exec(
            *(command or _uvicorn_command(host, resolved_port)),
            cwd=repo_root(),
            env=_evaluation_app_env(
                directories,
                port=resolved_port,
                extra_env=extra_env,
            ),
            stdout=stdout_handle,
            stderr=stderr_handle,
        )
    finally:
        stdout_handle.close()
        stderr_handle.close()
    handle = EvaluationAppHandle(
        base_url=base_url,
        process=process,
        stdout_log_path=stdout_log_path,
        stderr_log_path=stderr_log_path,
        lifecycle_log_path=lifecycle_log_path,
    )
    try:
        await wait_for_health(
            handle,
            timeout_seconds=readiness_timeout_seconds,
            require_geospatial_environment=require_geospatial_environment,
        )
    except Exception as exc:
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=3)
            except TimeoutError:
                process.kill()
                await process.wait()
        _write_json(
            lifecycle_log_path,
            {
                'base_url': base_url,
                'returncode': process.returncode,
                'stdout_log': stdout_log_path.name,
                'stderr_log': stderr_log_path.name,
                'startup': 'failed',
                'error': str(exc),
            },
        )
        raise EvaluationAppLifecycleError(f'Evaluation app failed readiness check: {exc}') from exc
    _write_json(
        lifecycle_log_path,
        {
            'base_url': base_url,
            'returncode': process.returncode,
            'stdout_log': stdout_log_path.name,
            'stderr_log': stderr_log_path.name,
            'startup': 'ready',
        },
    )
    return handle


async def wait_for_health(
    handle: EvaluationAppHandle,
    *,
    timeout_seconds: float,
    require_geospatial_environment: bool = False,
) -> dict[str, Any]:
    deadline: float = asyncio.get_running_loop().time() + timeout_seconds
    health_url: str = f'{handle.base_url}/api/health'
    last_error: Exception | None = None
    while asyncio.get_running_loop().time() < deadline:
        if handle.process.returncode is not None:
            raise EvaluationAppLifecycleError(
                f'Evaluation app exited before readiness with code {handle.process.returncode}'
            )
        try:
            payload = await asyncio.to_thread(_fetch_health, health_url)
            if _health_payload_ready(payload, require_geospatial_environment=require_geospatial_environment):
                return payload
            geospatial_environment = payload.get('geospatial_environment')
            if isinstance(geospatial_environment, dict) and geospatial_environment.get('status') == 'failed':
                raise EvaluationAppLifecycleError('Geospatial environment provisioning failed')
        except Exception as exc:
            last_error = exc
        await asyncio.sleep(0.2)
    detail: str = f': {last_error}' if last_error is not None else ''
    raise TimeoutError(f'Timed out waiting for evaluation app health{detail}')


def _evaluation_app_env(
    directories: CampaignDirectories,
    *,
    port: int,
    extra_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    env: dict[str, str] = dict(os.environ)
    env.update(
        {
            'GEO_AGENT_STATE_DIR': str(directories.root / 'state'),
            'GEO_AGENT_DATABASE_PATH': str(directories.root / 'metadata.db'),
            'GEO_AGENT_WORKSPACE_ROOT': str(directories.workspace),
            EVALUATION_PORT_ENV: str(port),
        }
    )
    if directories.app_support is not None:
        env['GEO_AGENT_APP_SUPPORT_DIR'] = str(directories.app_support)
    if directories.runtime_config is not None:
        env['GEO_AGENT_RUNTIME_CONFIG_ROOT'] = str(directories.runtime_config)
    if extra_env is not None:
        env.update(extra_env)
    return env


def _uvicorn_command(host: str, port: int) -> list[str]:
    return [
        sys.executable,
        '-m',
        'uvicorn',
        'app.main:app',
        '--host',
        host,
        '--port',
        str(port),
        '--log-level',
        'info',
    ]


def _fetch_health(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=1) as response:
            if response.status != 200:
                raise EvaluationAppLifecycleError(f'Health endpoint returned status {response.status}')
            payload = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        raise EvaluationAppLifecycleError(f'Health endpoint returned status {exc.code}') from exc
    if not isinstance(payload, dict):
        raise EvaluationAppLifecycleError('Health endpoint returned a non-object payload')
    return payload


def _health_payload_ready(payload: dict[str, Any], *, require_geospatial_environment: bool) -> bool:
    if not require_geospatial_environment:
        return True
    geospatial_environment = payload.get('geospatial_environment')
    if not isinstance(geospatial_environment, dict):
        return False
    return geospatial_environment.get('status') == 'ready'


def _allocate_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
