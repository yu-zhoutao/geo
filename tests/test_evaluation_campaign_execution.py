from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import sys

import pytest

from app.evaluation.app_lifecycle import APP_LIFECYCLE_LOG
from app.evaluation.benchmarks import BenchmarkValidationError
from app.evaluation.judge_rubrics import GEOSPATIAL_AGENT_RUBRIC
from app.evaluation.llm_judge import JudgeConfig
from app.evaluation.run_bundles import (
    ARTIFACT_MANIFEST_FILENAME,
    RUN_MANIFEST_FILENAME,
    RUN_STATUS_FILENAME,
)
from app.evaluation.runner import CAMPAIGN_EXECUTION_SCHEMA, execute_campaign_run
from app.evaluation.scoring_pipeline import score_campaign_run
from app.evaluation.session_traces import SESSION_JSON_FILENAME, TRANSCRIPT_FILENAME


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _campaign_path() -> Path:
    return _repo_root() / 'app' / 'evaluation_assets' / 'campaigns' / 'thesis-balanced-v1.yaml'


def _variant_root() -> Path:
    return _repo_root() / 'app' / 'evaluation_assets' / 'variants'


def _failing_app_command() -> list[str]:
    return [sys.executable, '-c', 'raise SystemExit("app should not start")']


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def _write_smoke_app(path: Path) -> None:
    path.write_text(
        '''
from __future__ import annotations

import json
import os
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


sessions: dict[str, dict[str, object]] = {}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == '/api/health':
            self._write_json({'app': 'ready', 'geospatial_environment': {'status': 'ready'}})
            return
        if self.path == '/api/sessions/session-1':
            session = sessions['session-1']
            polls = int(session.get('polls') or 0) + 1
            session['polls'] = polls
            if polls >= 2:
                session['status'] = 'completed'
            self._write_json(_session_payload(session))
            return
        if self.path == '/api/sessions/session-1/archive':
            self._write_json(_archive_payload(sessions['session-1']))
            return
        if self.path == '/api/sessions/session-1/artifacts/artifact-1/content':
            self._write_bytes(b'evaluation artifact')
            return
        self._write_json({'detail': 'not found'}, status=404)

    def do_POST(self) -> None:
        if self.path == '/api/sessions':
            workspace = Path(os.environ['GEO_AGENT_WORKSPACE_ROOT']) / 'session-1'
            trace_path = workspace / 'runtime' / 'trace.jsonl'
            trace_path.parent.mkdir(parents=True, exist_ok=True)
            trace_path.write_text('{"event":"smoke"}\\n', encoding='utf-8')
            sessions['session-1'] = {
                'id': 'session-1',
                'status': 'idle',
                'workspace_path': str(workspace),
                'runtime_trace_path': 'runtime/trace.jsonl',
                'prompt': '',
                'polls': 0,
                'attached_data_directories': [],
            }
            self._write_json(_session_payload(sessions['session-1']))
            return
        if self.path == '/api/sessions/session-1/messages':
            payload = self._read_json()
            session = sessions['session-1']
            session['prompt'] = str(payload.get('text') or '')
            session['status'] = 'running'
            self._write_json({'accepted': True}, status=202)
            return
        if self.path == '/api/sessions/session-1/interrupt':
            sessions['session-1']['status'] = 'failed'
            self._write_json({}, status=204)
            return
        self._write_json({'detail': 'not found'}, status=404)

    def do_PUT(self) -> None:
        if self.path == '/api/sessions/session-1/data-directories':
            payload = self._read_json()
            sessions['session-1']['attached_data_directories'] = payload.get('items') or []
            self._write_json(_session_payload(sessions['session-1']))
            return
        self._write_json({'detail': 'not found'}, status=404)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _read_json(self) -> dict[str, object]:
        length = int(self.headers.get('Content-Length') or '0')
        body = self.rfile.read(length).decode('utf-8') if length else '{}'
        payload = json.loads(body)
        return payload if isinstance(payload, dict) else {}

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


def _session_payload(session: dict[str, object]) -> dict[str, object]:
    return {
        'id': session['id'],
        'status': session['status'],
        'workspace_path': session['workspace_path'],
        'runtime_trace_path': session['runtime_trace_path'],
        'attached_data_directories': session['attached_data_directories'],
        'messages': [
            {
                'id': 'message-1',
                'role': 'user',
                'created_at': '2026-04-29T00:00:00+00:00',
                'parts': [{'type': 'text', 'text': session['prompt']}],
            }
        ],
        'artifacts': [
            {
                'id': 'artifact-1',
                'title': 'Smoke artifact',
                'path': 'outputs/run.txt',
                'kind': 'text',
            }
        ],
    }


def _archive_payload(session: dict[str, object]) -> dict[str, object]:
    return {
        'schema': 'geo-agent.session-archive.v1',
        'exported_at': '2026-04-29T00:00:00+00:00',
        'source': {'session_id': session['id']},
        'session': _session_payload(session),
        'geospatial_context': None,
        'evidence_records': [{'id': 'evidence-1', 'record_type': 'artifact'}],
        'runtime_trace': {'trace_path': session['runtime_trace_path']},
    }


port = int(os.environ['GEO_AGENT_EVALUATION_PORT'])
ThreadingHTTPServer(('127.0.0.1', port), Handler).serve_forever()
'''.lstrip(),
        encoding='utf-8',
    )


class FakeJudgeProvider:
    async def complete(self, *, messages: list[dict[str, str]], model: str, temperature: float) -> str:
        return json.dumps(
            {
                'dimensions': {
                    dimension.id: {'score': 4, 'reason': 'smoke'}
                    for dimension in GEOSPATIAL_AGENT_RUBRIC.dimensions
                },
                'summary': 'smoke judge result',
            }
        )


@pytest.mark.asyncio
async def test_execute_campaign_run_smoke_path_with_fake_app(tmp_path: Path) -> None:
    script_path = tmp_path / 'smoke_app.py'
    _write_smoke_app(script_path)

    execution = await execute_campaign_run(
        _campaign_path(),
        variant_root=_variant_root(),
        output_root=tmp_path,
        timestamp=datetime(2026, 4, 29, 1, 2, 3, tzinfo=UTC),
        app_command=[sys.executable, str(script_path)],
        max_attempts=1,
    )

    assert execution.summary_path.exists()
    assert len(execution.run_captures) == 1

    summary = json.loads(execution.summary_path.read_text(encoding='utf-8'))
    lifecycle = json.loads(
        (execution.run_captures[0].bundle_root / 'logs' / APP_LIFECYCLE_LOG).read_text(encoding='utf-8')
    )
    transcript = json.loads(
        (execution.run_captures[0].bundle_root / TRANSCRIPT_FILENAME).read_text(encoding='utf-8')
    )
    session = json.loads(
        (execution.run_captures[0].bundle_root / SESSION_JSON_FILENAME).read_text(encoding='utf-8')
    )

    assert summary['schema'] == CAMPAIGN_EXECUTION_SCHEMA
    assert summary['selected_attempt_count'] == 1
    assert summary['executed_attempt_count'] == 1
    assert summary['runs'][0]['error_count'] == 0
    assert lifecycle['shutdown'] == 'completed'
    assert transcript['messages'][0]['parts'][0]['text']
    assert (execution.run_captures[0].bundle_root / 'variant-runtime-assets.json').exists()
    assert session['attached_data_directories'][0]['path'].endswith('/data')
    assert not (execution.run_captures[0].bundle_root / 'dataset-pack').exists()
    assert (execution.run_captures[0].bundle_root / 'workspace').exists()
    assert not (execution.run_captures[0].bundle_root / 'runtime-config').exists()
    assert not (execution.initialization.directories.root / 'app-support').exists()
    assert not (execution.initialization.directories.root / 'runtime-config').exists()
    assert not (execution.initialization.directories.root / 'workspace').exists()
    assert not (execution.initialization.directories.root / 'logs').exists()


@pytest.mark.asyncio
async def test_smoke_campaign_scores_judges_and_aggregates_outputs(tmp_path: Path) -> None:
    script_path = tmp_path / 'smoke_app.py'
    _write_smoke_app(script_path)
    execution = await execute_campaign_run(
        _campaign_path(),
        variant_root=_variant_root(),
        output_root=tmp_path,
        timestamp=datetime(2026, 4, 29, 1, 2, 3, tzinfo=UTC),
        app_command=[sys.executable, str(script_path)],
        max_attempts=1,
    )

    scoring = await score_campaign_run(
        execution.initialization.directories.root,
        judge_provider=FakeJudgeProvider(),
        judge_config=JudgeConfig(model='glm-5.1', temperature=0.0),
    )

    assert len(scoring.judge_score_paths) == 1
    assert not hasattr(scoring, 'deterministic_score_paths')
    assert scoring.aggregate_summary['run_count'] == 1
    assert scoring.aggregate_summary['scored_run_count'] == 1
    assert (execution.initialization.directories.root / 'exports' / 'campaign-summary.json').exists()
    assert not (execution.run_captures[0].bundle_root / 'deterministic-score.json').exists()

    rescoring = await score_campaign_run(
        execution.initialization.directories.root,
        judge_provider=FakeJudgeProvider(),
        judge_config=JudgeConfig(model='glm-5.1', temperature=0.0),
        overwrite_scores=True,
    )

    assert len(rescoring.judge_score_paths) == 1
    assert not hasattr(rescoring, 'deterministic_score_paths')


@pytest.mark.asyncio
async def test_score_campaign_run_resolves_container_fixture_paths_and_skips_existing_scores(
    tmp_path: Path,
) -> None:
    campaign_root = tmp_path / 'campaign'
    bundle = campaign_root / 'runs' / 'full-system' / 'P01' / 'repeat-001'
    _write_json(
        bundle / RUN_MANIFEST_FILENAME,
        {
            'schema': 'geo-agent.evaluation.run-bundle.v1',
            'run_id': 'full-system__P01__r001',
            'session_id': 'session-1',
            'scenario': {
                'id': 'P01',
                'fixture_path': '/app/app/agent_assets/benchmarks/core/p01-clear-local-kde.yaml',
                'split': 'dev',
                'difficulty': 'easy',
                'task_family': 'kde',
                'gold_control_state': 'proceed',
            },
            'variant': {'id': 'full-system'},
            'error_count': 0,
            'errors': [],
        },
    )
    _write_json(
        bundle / RUN_STATUS_FILENAME,
        {
            'session_status': 'completed',
            'terminal_reason': 'completed',
            'timed_out': False,
            'duration_seconds': 1.0,
            'continuation_count': 0,
            'error_count': 0,
            'errors': [],
        },
    )
    _write_json(
        bundle / 'session.json',
        {
            'messages': [{'id': 'message-1', 'role': 'assistant', 'parts': [{'type': 'text', 'text': 'done'}]}],
            'artifacts': [],
        },
    )
    _write_json(bundle / 'transcript.json', {'messages': [{'id': 'message-1', 'role': 'assistant'}]})
    _write_json(bundle / ARTIFACT_MANIFEST_FILENAME, {'items': []})

    first = await score_campaign_run(
        campaign_root,
        judge_provider=FakeJudgeProvider(),
        judge_config=JudgeConfig(model='glm-5.1', temperature=0.0),
    )
    second = await score_campaign_run(
        campaign_root,
        judge_provider=FakeJudgeProvider(),
        judge_config=JudgeConfig(model='glm-5.1', temperature=0.0),
    )

    assert len(first.judge_score_paths) == 1
    assert len(second.judge_score_paths) == 0
    assert second.aggregate_summary['run_count'] == 1
    assert second.aggregate_summary['scored_run_count'] == 1


@pytest.mark.asyncio
async def test_execute_campaign_run_filters_explicit_attempt_ids(tmp_path: Path) -> None:
    script_path = tmp_path / 'smoke_app.py'
    _write_smoke_app(script_path)

    execution = await execute_campaign_run(
        _campaign_path(),
        variant_root=_variant_root(),
        output_root=tmp_path,
        timestamp=datetime(2026, 4, 29, 1, 2, 3, tzinfo=UTC),
        app_command=[sys.executable, str(script_path)],
        attempt_ids=('full-system__P01__r001', 'single-agent__P01__r001'),
    )

    assert [capture.run_id for capture in execution.run_captures] == [
        'full-system__P01__r001',
        'single-agent__P01__r001',
    ]
    assert (execution.run_captures[1].bundle_root / 'variant-runtime-assets.json').exists()


@pytest.mark.asyncio
async def test_execute_campaign_run_rejects_removed_deterministic_reference_attempt(tmp_path: Path) -> None:
    with pytest.raises(BenchmarkValidationError, match='Unknown planned attempt id'):
        await execute_campaign_run(
            _campaign_path(),
            variant_root=_variant_root(),
            output_root=tmp_path,
            timestamp=datetime(2026, 4, 29, 1, 2, 3, tzinfo=UTC),
            app_command=_failing_app_command(),
            attempt_ids=('deterministic-gis-reference__P01__r001',),
        )


@pytest.mark.asyncio
async def test_strategy_controlled_attempt_preserves_prompt_and_records_profile(tmp_path: Path) -> None:
    script_path = tmp_path / 'smoke_app.py'
    _write_smoke_app(script_path)

    execution = await execute_campaign_run(
        _campaign_path(),
        variant_root=_variant_root(),
        output_root=tmp_path,
        timestamp=datetime(2026, 4, 29, 1, 2, 3, tzinfo=UTC),
        app_command=[sys.executable, str(script_path)],
        attempt_ids=('full-system__crs_first__P01__r001',),
        strategy_profile_ids=('crs_first',),
        strategy_policy_run_id='policy-1',
        strategy_policy_checkpoint_id='checkpoint-0001',
        strategy_trl_run_id='trl-run-1',
        strategy_training_step=7,
        strategy_action_rationale='CRS risk',
    )

    bundle = execution.run_captures[0].bundle_root
    run_manifest = json.loads((bundle / 'run-manifest.json').read_text(encoding='utf-8'))
    run_status = json.loads((bundle / 'run-status.json').read_text(encoding='utf-8'))
    transcript = json.loads((bundle / TRANSCRIPT_FILENAME).read_text(encoding='utf-8'))
    runtime_assets = json.loads((bundle / 'variant-runtime-assets.json').read_text(encoding='utf-8'))

    assert 'FCD数据/sample_200_taxis.jsonl' in transcript['messages'][0]['parts'][0]['text']
    assert '解释为统计显著热点' in transcript['messages'][0]['parts'][0]['text']
    assert run_manifest['strategy']['strategy_id'] == 'crs_first'
    assert run_manifest['strategy']['policy_checkpoint_id'] == 'checkpoint-0001'
    assert run_manifest['strategy']['trl_run_id'] == 'trl-run-1'
    assert run_manifest['strategy']['training_step'] == 7
    assert run_status['strategy']['source'] == 'offline-sweep'
    assert run_status['strategy']['action_rationale'] == 'CRS risk'
    assert runtime_assets['strategy_profile']['id'] == 'crs_first'
    assert runtime_assets['generated'] is True
