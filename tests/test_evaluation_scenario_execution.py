from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import struct
import threading
from typing import Any

import pytest

from app.evaluation import app_client as app_client_module
from app.evaluation.app_client import EvaluationAppClient
from app.evaluation.benchmarks import BenchmarkScenario, load_benchmark_scenario, repo_root
from app.evaluation.scenario_execution import (
    execute_scenario_attempt,
    prepare_scenario_data_attachments,
    scenario_data_attachments,
)


class ScenarioServerState:
    def __init__(
        self,
        *,
        complete_after_polls: int | None,
        idle_after_polls: int | None = None,
        question_after_polls: int | None = None,
        complete_after_continuation: bool = False,
    ) -> None:
        self.complete_after_polls = complete_after_polls
        self.idle_after_polls = idle_after_polls
        self.question_after_polls = question_after_polls
        self.complete_after_continuation = complete_after_continuation
        self.poll_count = 0
        self.created = False
        self.attached_items: list[dict[str, object]] = []
        self.prompt: str | None = None
        self.prompts: list[str] = []
        self.interrupted = False
        self.answer_payloads: list[dict[str, Any]] = []
        self.question: dict[str, object] | None = None
        self.status = 'idle'


@contextmanager
def _scenario_server(state: ScenarioServerState) -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            if self.path == '/api/sessions':
                state.created = True
                state.status = 'idle'
                self._write_json({'id': 'session-1', 'status': state.status})
                return
            if self.path == '/api/sessions/session-1/messages':
                payload = self._read_json()
                state.prompt = str(payload.get('text') or '')
                state.prompts.append(state.prompt)
                state.status = 'running'
                if state.complete_after_continuation and len(state.prompts) > 1:
                    state.idle_after_polls = None
                    state.complete_after_polls = state.poll_count + 1
                self._write_json({'accepted': True}, status=202)
                return
            if self.path == '/api/sessions/session-1/interrupt':
                state.interrupted = True
                state.status = 'idle'
                self._write_json({}, status=204)
                return
            if self.path == '/api/sessions/session-1/questions/question-1/answers':
                state.answer_payloads.append(self._read_json())
                state.question = None
                state.status = 'running'
                state.complete_after_polls = state.poll_count + 1
                self._write_json({'accepted': True}, status=202)
                return
            self._write_json({'detail': 'not found'}, status=404)

        def do_PUT(self) -> None:
            if self.path == '/api/sessions/session-1/data-directories':
                payload = self._read_json()
                items = payload.get('items')
                state.attached_items = items if isinstance(items, list) else []
                self._write_json({'id': 'session-1', 'status': state.status})
                return
            self._write_json({'detail': 'not found'}, status=404)

        def do_GET(self) -> None:
            if self.path == '/api/sessions/session-1':
                state.poll_count += 1
                if (
                    state.question_after_polls is not None
                    and state.poll_count >= state.question_after_polls
                    and not state.answer_payloads
                ):
                    state.status = 'waiting_for_input'
                    state.question = {
                        'id': 'question-1',
                        'prompt': '请选择研究区范围',
                        'source': 'runtime',
                        'questions': [],
                    }
                if state.complete_after_polls is not None and state.poll_count >= state.complete_after_polls:
                    state.status = 'completed'
                    state.question = None
                if state.idle_after_polls is not None and state.poll_count >= state.idle_after_polls:
                    state.status = 'idle'
                    state.question = None
                payload: dict[str, object] = {'id': 'session-1', 'status': state.status}
                if state.question is not None:
                    payload['question'] = state.question
                self._write_json(payload)
                return
            self._write_json({'detail': 'not found'}, status=404)

        def log_message(self, format: str, *args: object) -> None:
            return

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get('Content-Length') or '0')
            body = self.rfile.read(length).decode('utf-8') if length else '{}'
            payload = json.loads(body)
            return payload if isinstance(payload, dict) else {}

        def _write_json(self, payload: dict[str, Any], *, status: int = 200) -> None:
            body = b'' if status == 204 else json.dumps(payload).encode('utf-8')
            self.send_response(status)
            if status != 204:
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            if body:
                self.wfile.write(body)

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


class _FakeJsonResponse:
    status = 200

    def __enter__(self) -> '_FakeJsonResponse':
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        return False

    def read(self) -> bytes:
        return b'{"id": "session-1", "status": "completed"}'


@pytest.mark.asyncio
async def test_evaluation_app_client_retries_transient_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def flaky_urlopen(request: Any, *, timeout: float) -> _FakeJsonResponse:
        calls.append(request.full_url)
        if len(calls) == 1:
            raise TimeoutError('timed out')
        return _FakeJsonResponse()

    monkeypatch.setattr(app_client_module.urllib.request, 'urlopen', flaky_urlopen)
    client = EvaluationAppClient(
        'http://127.0.0.1:1',
        timeout_seconds=0.01,
        max_attempts=2,
        retry_backoff_seconds=0,
    )

    payload = await client.get_session('session-1')

    assert payload == {'id': 'session-1', 'status': 'completed'}
    assert calls == [
        'http://127.0.0.1:1/api/sessions/session-1',
        'http://127.0.0.1:1/api/sessions/session-1',
    ]


def test_prepare_scenario_data_attachments_materializes_synthetic_pack(tmp_path: Path) -> None:
    scenario = replace(
        _scenario(),
        dataset_root='app/agent_assets/benchmarks/datasets',
        dataset_pack_mode='synthetic',
        dataset_pack=('fcd_points_sample.csv', 'beijing_boundary.geojson'),
    )

    attachments = prepare_scenario_data_attachments(scenario, tmp_path)

    assert attachments == [
        {
            'id': 'scenario-p01-dataset-root',
            'path': str(tmp_path.resolve()),
            'enabled': True,
            'label': 'P01 dataset root',
        }
    ]
    assert (tmp_path / 'fcd_points_sample.csv').read_text(encoding='utf-8').startswith('taxi_id,longitude,latitude')
    assert (tmp_path / 'beijing_boundary.geojson').exists()


def test_prepare_scenario_data_attachments_materializes_valid_synthetic_shapefile(tmp_path: Path) -> None:
    scenario = replace(
        _scenario(),
        id='T07',
        dataset_root='app/agent_assets/benchmarks/datasets',
        dataset_pack_mode='synthetic',
        dataset_pack=('pm25_stations.geojson', 'beijing_boundary.shp'),
    )

    prepare_scenario_data_attachments(scenario, tmp_path)

    shp_path: Path = tmp_path / 'beijing_boundary.shp'
    sidecar_names: set[str] = {path.name for path in tmp_path.glob('beijing_boundary.*')}
    station_payload = json.loads((tmp_path / 'pm25_stations.geojson').read_text(encoding='utf-8'))
    station_properties = station_payload['features'][0]['properties']
    assert {'beijing_boundary.shp', 'beijing_boundary.shx', 'beijing_boundary.dbf', 'beijing_boundary.prj'} <= sidecar_names
    assert struct.unpack('>i', shp_path.read_bytes()[:4])[0] == 9994
    assert 'pm25' in station_properties
    assert 'value' not in station_properties
    assert str(station_properties['station_id']).startswith('station_')


@pytest.mark.asyncio
async def test_execute_scenario_attempt_posts_prompt_and_polls_until_completed() -> None:
    scenario = _scenario()
    state = ScenarioServerState(complete_after_polls=2)

    with _scenario_server(state) as base_url:
        result = await execute_scenario_attempt(
            EvaluationAppClient(base_url),
            scenario,
            wall_clock_budget_seconds=5,
            poll_interval_seconds=0.01,
        )

    assert result.session_id == 'session-1'
    assert result.status == 'completed'
    assert result.terminal_reason == 'completed'
    assert result.timed_out is False
    assert state.created is True
    assert state.prompt == scenario.user_prompt
    assert state.attached_items == scenario_data_attachments(scenario)
    assert state.poll_count == 2
    assert state.interrupted is False


@pytest.mark.asyncio
async def test_execute_scenario_attempt_returns_when_session_becomes_idle() -> None:
    scenario = _scenario()
    state = ScenarioServerState(complete_after_polls=None, idle_after_polls=2)

    with _scenario_server(state) as base_url:
        result = await execute_scenario_attempt(
            EvaluationAppClient(base_url),
            scenario,
            wall_clock_budget_seconds=5,
            poll_interval_seconds=0.01,
            max_continuations=0,
        )

    assert result.session_id == 'session-1'
    assert result.status == 'idle'
    assert result.terminal_reason == 'idle'
    assert result.timed_out is False
    assert state.poll_count == 2


@pytest.mark.asyncio
async def test_execute_scenario_attempt_sends_continuation_when_session_becomes_idle() -> None:
    scenario = _scenario()
    state = ScenarioServerState(
        complete_after_polls=None,
        idle_after_polls=1,
        complete_after_continuation=True,
    )

    with _scenario_server(state) as base_url:
        result = await execute_scenario_attempt(
            EvaluationAppClient(base_url),
            scenario,
            wall_clock_budget_seconds=5,
            poll_interval_seconds=0.01,
        )

    assert result.status == 'completed'
    assert result.terminal_reason == 'completed'
    assert result.continuation_count == 1
    assert state.prompts[0] == scenario.user_prompt
    assert len(state.prompts) == 2
    assert '继续' in state.prompts[1]


@pytest.mark.asyncio
async def test_execute_scenario_attempt_limits_continuations_to_two_by_default() -> None:
    scenario = _scenario()
    state = ScenarioServerState(complete_after_polls=None, idle_after_polls=1)

    with _scenario_server(state) as base_url:
        result = await execute_scenario_attempt(
            EvaluationAppClient(base_url),
            scenario,
            wall_clock_budget_seconds=5,
            poll_interval_seconds=0.01,
        )

    assert result.status == 'idle'
    assert result.continuation_count == 2
    assert len(state.prompts) == 3


@pytest.mark.asyncio
async def test_execute_scenario_attempt_interrupts_on_budget_timeout() -> None:
    scenario = _scenario()
    state = ScenarioServerState(complete_after_polls=None)

    with _scenario_server(state) as base_url:
        result = await execute_scenario_attempt(
            EvaluationAppClient(base_url),
            scenario,
            wall_clock_budget_seconds=0.05,
            poll_interval_seconds=0.01,
        )

    assert result.session_id == 'session-1'
    assert result.terminal_reason == 'timeout'
    assert result.timed_out is True
    assert state.interrupted is True
    assert state.poll_count >= 1


@pytest.mark.asyncio
async def test_execute_scenario_attempt_stops_successfully_for_expected_clarification() -> None:
    scenario = replace(_scenario(), gold_control_state='clarify')
    state = ScenarioServerState(complete_after_polls=None, question_after_polls=1)

    with _scenario_server(state) as base_url:
        result = await execute_scenario_attempt(
            EvaluationAppClient(base_url),
            scenario,
            wall_clock_budget_seconds=5,
            poll_interval_seconds=0.01,
        )

    assert result.status == 'waiting_for_input'
    assert result.terminal_reason == 'expected_clarification'
    assert result.clarification_answer_count == 0
    assert state.answer_payloads == []


@pytest.mark.asyncio
async def test_execute_scenario_attempt_answers_scenario_defined_clarification_policy() -> None:
    scenario = replace(
        _scenario(),
        gold_control_state='clarify',
        clarification_answer_policy='answer-once',
        clarification_answers=('使用默认北京市区县边界',),
    )
    state = ScenarioServerState(complete_after_polls=None, question_after_polls=1)

    with _scenario_server(state) as base_url:
        result = await execute_scenario_attempt(
            EvaluationAppClient(base_url),
            scenario,
            wall_clock_budget_seconds=5,
            poll_interval_seconds=0.01,
        )

    assert result.status == 'completed'
    assert result.terminal_reason == 'completed'
    assert result.clarification_answer_count == 1
    assert result.clarification_question_ids == ('question-1',)
    assert state.answer_payloads == [{'answer': None, 'answers': ['使用默认北京市区县边界']}]
