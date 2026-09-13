from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
from pathlib import Path
import threading
from typing import Any

import pytest

from app.evaluation.app_client import EvaluationAppClient
from app.evaluation.benchmarks import BenchmarkScenario, load_benchmark_scenario, repo_root
from app.evaluation.run_bundles import (
    ARTIFACT_MANIFEST_FILENAME,
    RUN_MANIFEST_FILENAME,
    RUN_STATUS_FILENAME,
    RunBundleCaptureError,
    capture_run_bundle,
)
from app.evaluation.scenario_execution import ScenarioAttemptResult
from app.evaluation.session_traces import SESSION_JSON_FILENAME, SESSION_TRACE_FILENAME, TRANSCRIPT_FILENAME
from app.evaluation.strategy_profiles import StrategySelection
from app.services.session_archives import SESSION_ARCHIVE_SCHEMA


class BundleServerState:
    def __init__(self, *, archive: dict[str, object], artifact_status: int = 200) -> None:
        self.archive = archive
        self.artifact_status = artifact_status
        self.artifact_requests: list[str] = []


@contextmanager
def _bundle_server(state: BundleServerState) -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == '/api/sessions/session-1/archive':
                self._write_json(state.archive)
                return
            if self.path == '/api/sessions/session-1/artifacts/artifact-1/content':
                state.artifact_requests.append(self.path)
                if state.artifact_status != 200:
                    self._write_json({'detail': 'missing artifact'}, status=state.artifact_status)
                    return
                self._write_bytes(b'evaluation artifact')
                return
            self._write_json({'detail': 'not found'}, status=404)

        def log_message(self, format: str, *args: object) -> None:
            return

        def _write_json(self, payload: dict[str, object], *, status: int = 200) -> None:
            body = json.dumps(payload).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _write_bytes(self, payload: bytes, *, status: int = 200) -> None:
            self.send_response(status)
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f'http://{host}:{port}'
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def _scenario() -> BenchmarkScenario:
    return load_benchmark_scenario(
        repo_root() / 'app' / 'agent_assets' / 'benchmarks' / 'core' / 'p01-clear-local-kde.yaml'
    )


def _result() -> ScenarioAttemptResult:
    started_at = datetime(2026, 4, 29, 1, 2, 3, tzinfo=UTC)
    finished_at = datetime(2026, 4, 29, 1, 2, 8, tzinfo=UTC)
    return ScenarioAttemptResult(
        session_id='session-1',
        status='completed',
        terminal_reason='completed',
        timed_out=False,
        session={'id': 'session-1', 'status': 'completed'},
        started_at=started_at,
        finished_at=finished_at,
        continuation_count=1,
    )


def _archive(workspace: Path | None, *, include_artifact: bool = True) -> dict[str, object]:
    artifacts: list[dict[str, object]] = []
    if include_artifact:
        artifacts.append(
            {
                'id': 'artifact-1',
                'title': 'KDE 运行清单',
                'path': 'outputs/run.txt',
                'kind': 'text',
            }
        )
    return {
        'schema': SESSION_ARCHIVE_SCHEMA,
        'exported_at': '2026-04-29T00:00:00+00:00',
        'source': {'session_id': 'session-1'},
        'session': {
            'id': 'session-1',
            'status': 'completed',
            'workspace_path': str(workspace) if workspace is not None else None,
            'runtime_trace_path': 'runtime/trace.jsonl' if workspace is not None else None,
            'messages': [
                {
                    'id': 'message-1',
                    'role': 'user',
                    'parts': [{'type': 'text', 'text': 'Run unchanged prompt'}],
                }
            ],
            'artifacts': artifacts,
        },
        'evidence_records': [{'id': 'evidence-1', 'record_type': 'artifact'}],
        'runtime_trace': {'trace_path': 'runtime/trace.jsonl'} if workspace is not None else {},
    }


@pytest.mark.asyncio
async def test_capture_run_bundle_writes_trace_artifacts_runtime_trace_and_status(tmp_path: Path) -> None:
    workspace = tmp_path / 'workspace'
    runtime_trace = workspace / 'runtime' / 'trace.jsonl'
    runtime_trace.parent.mkdir(parents=True)
    runtime_trace.write_text('{"event": "tool"}\n', encoding='utf-8')
    log_path = tmp_path / 'app.log'
    log_path.write_text('app log\n', encoding='utf-8')
    state = BundleServerState(archive=_archive(workspace))

    with _bundle_server(state) as base_url:
        capture = await capture_run_bundle(
            EvaluationAppClient(base_url),
            _result(),
            _scenario(),
            tmp_path / 'bundle',
            run_id='run-1',
            strategy=StrategySelection(
                strategy_id='crs_first',
                source='offline-sweep',
                profile_hash='hash-1',
                policy_run_id='policy-1',
                action_rationale='CRS risk',
            ),
            log_paths=[log_path],
        )

    bundle = tmp_path / 'bundle'
    run_manifest = json.loads((bundle / RUN_MANIFEST_FILENAME).read_text(encoding='utf-8'))
    status = json.loads((bundle / RUN_STATUS_FILENAME).read_text(encoding='utf-8'))
    artifact_manifest = json.loads((bundle / ARTIFACT_MANIFEST_FILENAME).read_text(encoding='utf-8'))

    assert capture.run_id == 'run-1'
    assert capture.artifact_count == 1
    assert capture.error_count == 0
    assert (bundle / SESSION_TRACE_FILENAME).exists()
    assert (bundle / SESSION_JSON_FILENAME).exists()
    assert (bundle / TRANSCRIPT_FILENAME).exists()
    assert run_manifest['schema'] == 'geo-agent.evaluation.run-bundle.v1'
    assert run_manifest['scenario']['id'] == 'P01'
    assert run_manifest['strategy']['strategy_id'] == 'crs_first'
    assert run_manifest['strategy']['policy_run_id'] == 'policy-1'
    assert status['strategy']['action_rationale'] == 'CRS risk'
    assert run_manifest['runtime_trace']['status'] == 'copied'
    assert run_manifest['logs'][0]['status'] == 'copied'
    assert status['duration_seconds'] == 5.0
    assert status['continuation_count'] == 1
    assert artifact_manifest['items'][0]['copied_path'] == 'artifacts/artifact-1.txt'
    assert artifact_manifest['items'][0]['sha256'] == hashlib.sha256(b'evaluation artifact').hexdigest()
    assert state.artifact_requests == ['/api/sessions/session-1/artifacts/artifact-1/content']


@pytest.mark.asyncio
async def test_capture_run_bundle_records_artifact_errors_without_failing(tmp_path: Path) -> None:
    state = BundleServerState(archive=_archive(None), artifact_status=404)

    with _bundle_server(state) as base_url:
        capture = await capture_run_bundle(
            EvaluationAppClient(base_url),
            _result(),
            _scenario(),
            tmp_path / 'bundle',
        )

    artifact_manifest = json.loads((tmp_path / 'bundle' / ARTIFACT_MANIFEST_FILENAME).read_text(encoding='utf-8'))
    status = json.loads((tmp_path / 'bundle' / RUN_STATUS_FILENAME).read_text(encoding='utf-8'))

    assert capture.artifact_count == 1
    assert capture.error_count == 1
    assert artifact_manifest['items'][0]['copied_path'] is None
    assert 'artifact capture failed' in artifact_manifest['items'][0]['error']
    assert status['error_count'] == 1


@pytest.mark.asyncio
async def test_capture_run_bundle_rejects_existing_capture_files(tmp_path: Path) -> None:
    state = BundleServerState(archive=_archive(None, include_artifact=False))
    bundle = tmp_path / 'bundle'

    with _bundle_server(state) as base_url:
        await capture_run_bundle(EvaluationAppClient(base_url), _result(), _scenario(), bundle)
        with pytest.raises(RunBundleCaptureError, match='overwrite existing files'):
            await capture_run_bundle(EvaluationAppClient(base_url), _result(), _scenario(), bundle)
