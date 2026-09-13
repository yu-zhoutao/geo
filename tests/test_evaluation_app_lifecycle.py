from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

from app.evaluation.app_lifecycle import (
    APP_LIFECYCLE_LOG,
    APP_STDERR_LOG,
    APP_STDOUT_LOG,
    EvaluationAppLifecycleError,
    start_evaluation_app,
    wait_for_health,
)
from app.evaluation.runner import CampaignDirectories


def _directories(root: Path) -> CampaignDirectories:
    directories = CampaignDirectories(
        root=root,
        manifests=root / 'manifests',
        runs=root / 'runs',
        logs=root / 'logs',
        app_support=None,
        workspace=root / 'workspace',
        runtime_config=None,
        runtime_assets=root / 'runtime-assets',
    )
    for directory in (
        directories.workspace,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    return directories


def _write_healthy_app(path: Path) -> None:
    path.write_text(
        '''
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != '/api/health':
            self.send_response(404)
            self.end_headers()
            return
        payload = {
            'app': 'ready',
            'port': os.environ.get('GEO_AGENT_EVALUATION_PORT'),
            'app_support_dir': os.environ.get('GEO_AGENT_APP_SUPPORT_DIR'),
            'workspace_root': os.environ.get('GEO_AGENT_WORKSPACE_ROOT'),
            'runtime_config_root': os.environ.get('GEO_AGENT_RUNTIME_CONFIG_ROOT'),
        }
        body = json.dumps(payload).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


port = int(os.environ['GEO_AGENT_EVALUATION_PORT'])
print('healthy app starting', flush=True)
ThreadingHTTPServer(('127.0.0.1', port), Handler).serve_forever()
'''.lstrip(),
        encoding='utf-8',
    )


def _write_crashing_app(path: Path) -> None:
    path.write_text(
        '''
from __future__ import annotations

import sys

print('startup failed intentionally', file=sys.stderr, flush=True)
raise SystemExit(7)
'''.lstrip(),
        encoding='utf-8',
    )


def _write_provisioning_app(path: Path) -> None:
    path.write_text(
        '''
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


poll_count = 0


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        global poll_count
        if self.path != '/api/health':
            self.send_response(404)
            self.end_headers()
            return
        poll_count += 1
        status = 'ready' if poll_count >= 3 else 'provisioning'
        payload = {'app': 'ready', 'geospatial_environment': {'status': status}}
        body = json.dumps(payload).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


port = int(os.environ['GEO_AGENT_EVALUATION_PORT'])
ThreadingHTTPServer(('127.0.0.1', port), Handler).serve_forever()
'''.lstrip(),
        encoding='utf-8',
    )


@pytest.mark.asyncio
async def test_start_evaluation_app_waits_for_health_and_preserves_logs(tmp_path: Path) -> None:
    directories = _directories(tmp_path / 'campaign')
    script_path = tmp_path / 'healthy_app.py'
    _write_healthy_app(script_path)

    handle = await start_evaluation_app(
        directories,
        readiness_timeout_seconds=5,
        command=[sys.executable, str(script_path)],
    )
    returncode = await handle.shutdown(timeout_seconds=2)

    lifecycle = json.loads((directories.logs / APP_LIFECYCLE_LOG).read_text(encoding='utf-8'))
    stdout = (directories.logs / APP_STDOUT_LOG).read_text(encoding='utf-8')

    assert handle.base_url.startswith('http://127.0.0.1:')
    assert returncode is not None
    assert lifecycle['shutdown'] == 'completed'
    assert lifecycle['stdout_log'] == APP_STDOUT_LOG
    assert lifecycle['stderr_log'] == APP_STDERR_LOG
    assert 'healthy app starting' in stdout


@pytest.mark.asyncio
async def test_start_evaluation_app_captures_startup_crash(tmp_path: Path) -> None:
    directories = _directories(tmp_path / 'campaign')
    script_path = tmp_path / 'crashing_app.py'
    _write_crashing_app(script_path)

    with pytest.raises(EvaluationAppLifecycleError, match='failed readiness'):
        await start_evaluation_app(
            directories,
            readiness_timeout_seconds=2,
            command=[sys.executable, str(script_path)],
        )

    lifecycle = json.loads((directories.logs / APP_LIFECYCLE_LOG).read_text(encoding='utf-8'))
    stderr = (directories.logs / APP_STDERR_LOG).read_text(encoding='utf-8')

    assert lifecycle['startup'] == 'failed'
    assert lifecycle['returncode'] == 7
    assert 'startup failed intentionally' in stderr


@pytest.mark.asyncio
async def test_evaluation_app_environment_keeps_shared_runtime_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directories = _directories(tmp_path / 'campaign')
    shared_app_support = tmp_path / 'shared-app-support'
    shared_runtime_config = tmp_path / 'shared-runtime-config'
    monkeypatch.setenv('GEO_AGENT_APP_SUPPORT_DIR', str(shared_app_support))
    monkeypatch.setenv('GEO_AGENT_RUNTIME_CONFIG_ROOT', str(shared_runtime_config))
    script_path = tmp_path / 'healthy_app.py'
    _write_healthy_app(script_path)

    handle = await start_evaluation_app(
        directories,
        readiness_timeout_seconds=5,
        command=[sys.executable, str(script_path)],
    )
    try:
        health = await wait_for_health(handle, timeout_seconds=1)
    finally:
        await handle.shutdown(timeout_seconds=2)

    assert health['app_support_dir'] == str(shared_app_support)
    assert health['workspace_root'] == str(directories.workspace)
    assert health['runtime_config_root'] == str(shared_runtime_config)
    assert health['port'].isdigit()
    assert not (directories.root / 'app-support').exists()
    assert not (directories.root / 'runtime-config').exists()


@pytest.mark.asyncio
async def test_start_evaluation_app_can_wait_for_geospatial_environment_readiness(tmp_path: Path) -> None:
    directories = _directories(tmp_path / 'campaign')
    script_path = tmp_path / 'provisioning_app.py'
    _write_provisioning_app(script_path)

    handle = await start_evaluation_app(
        directories,
        readiness_timeout_seconds=5,
        require_geospatial_environment=True,
        command=[sys.executable, str(script_path)],
    )
    try:
        health = await wait_for_health(
            handle,
            timeout_seconds=1,
            require_geospatial_environment=True,
        )
    finally:
        await handle.shutdown(timeout_seconds=2)

    assert health['geospatial_environment']['status'] == 'ready'
