from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.evaluation.benchmarks import BenchmarkScenario, load_benchmark_scenario, repo_root
from app.evaluation.judge_rubrics import GEOSPATIAL_AGENT_RUBRIC, get_judge_rubric
from app.evaluation.llm_judge import (
    JUDGE_INPUT_FILENAME,
    JUDGE_SCORE_FILENAME,
    JudgeConfig,
    build_judge_packet,
    run_llm_judge,
    validate_judge_output,
    write_judge_score,
)
from app.evaluation.run_bundles import ARTIFACT_MANIFEST_FILENAME, RUN_STATUS_FILENAME
from app.evaluation.session_traces import EVIDENCE_RECORDS_FILENAME, SESSION_JSON_FILENAME, TRANSCRIPT_FILENAME


class FakeJudgeProvider:
    def __init__(self, responses: tuple[str, ...]) -> None:
        self.responses: list[str] = list(responses)
        self.requests: list[dict[str, object]] = []

    async def complete(self, *, messages: list[dict[str, str]], model: str, temperature: float) -> str:
        self.requests.append({'messages': messages, 'model': model, 'temperature': temperature})
        return self.responses.pop(0)


def _scenario() -> BenchmarkScenario:
    return load_benchmark_scenario(
        repo_root() / 'app' / 'agent_assets' / 'benchmarks' / 'core' / 'p01-clear-local-kde.yaml'
    )


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def _valid_judge_response(*, score: int = 5) -> str:
    return json.dumps(
        {
            'dimensions': {
                dimension.id: {'score': score, 'reason': 'reason'}
                for dimension in GEOSPATIAL_AGENT_RUBRIC.dimensions
            },
            'summary': 'dimension-only score',
        }
    )


def _write_bundle(root: Path) -> None:
    _write_json(
        root / RUN_STATUS_FILENAME,
        {
            'session_status': 'completed',
            'terminal_reason': 'completed',
            'timed_out': False,
            'duration_seconds': 12.5,
            'continuation_count': 1,
            'error_count': 0,
            'errors': [],
        },
    )
    _write_json(
        root / SESSION_JSON_FILENAME,
        {
            'messages': [{'id': 'message-1', 'role': 'assistant', 'parts': [{'type': 'text', 'text': 'done'}]}],
            'artifacts': [{'id': 'artifact-1', 'path': 'outputs/report.md'}],
            'verification': [{'id': 'v1', 'decision': 'proceed'}],
        },
    )
    _write_json(root / TRANSCRIPT_FILENAME, {'messages': [{'id': 'message-1', 'role': 'assistant'}]})
    _write_json(root / EVIDENCE_RECORDS_FILENAME, {'items': [{'id': 'record-1', 'path': 'outputs/report.md'}]})
    _write_json(
        root / ARTIFACT_MANIFEST_FILENAME,
        {'items': [{'id': 'artifact-1', 'source_path': 'outputs/report.md'}]},
    )


def test_fixed_judge_rubric_contains_core_geospatial_quality_dimensions() -> None:
    rubric = get_judge_rubric('geospatial-agent-v1')
    dimension_ids = {dimension.id for dimension in rubric.dimensions}

    assert dimension_ids == {
        'method_selection',
        'data_readiness',
        'crs_and_units',
        'parameterization',
        'execution_correctness',
        'uncertainty_and_sensitivity',
        'claim_validity',
    }
    assert all(dimension.as_json()['score_range'] == {'min': 1, 'max': 5} for dimension in rubric.dimensions)


def test_build_judge_packet_includes_oracle_runtime_status_transcript_and_evidence(tmp_path: Path) -> None:
    bundle = tmp_path / 'bundle'
    _write_bundle(bundle)

    packet = build_judge_packet(_scenario(), bundle).as_json()

    assert packet['schema'] == 'geo-agent.evaluation.judge-packet.v1'
    assert packet['scenario']['oracle_id'] == 'ORACLE-P01'
    assert packet['rubric']['id'] == 'geospatial-task-quality-v2'
    assert packet['run_status']['terminal_reason'] == 'completed'
    assert packet['run_status']['continuation_count'] == 1
    assert packet['transcript']['message_count'] == 1
    assert packet['artifacts']['items'][0]['id'] == 'artifact-1'
    assert 'deterministic_score' not in packet
    assert 'required_artifacts' not in packet['scenario']
    assert 'evidence_records' not in packet


def test_build_judge_packet_trims_transcript_tool_outputs_and_reasoning(tmp_path: Path) -> None:
    bundle = tmp_path / 'bundle'
    _write_bundle(bundle)
    _write_json(
        bundle / TRANSCRIPT_FILENAME,
        {
            'messages': [
                {'id': 'user-1', 'role': 'user', 'parts': [{'type': 'text', 'text': 'analyze this'}]},
                {
                    'id': 'assistant-1',
                    'role': 'assistant',
                    'parts': [
                        {'type': 'reasoning', 'text': 'private reasoning should not reach the judge'},
                        {'type': 'step-start', 'text': 'starting'},
                        {'type': 'text', 'text': 'A' * 2500},
                        {
                            'type': 'tool',
                            'tool': 'read',
                            'text': None,
                            'state': {
                                'input': {'filePath': '/app/data/large.geojson'},
                                'output': 'TOOL_OUTPUT' * 500,
                                'status': 'completed',
                                'title': 'Read large GeoJSON',
                                'time': {'start': 1, 'end': 2},
                            },
                        },
                        {
                            'type': 'subtask',
                            'state': {
                                'child_agent': 'analysis',
                                'description': 'inspect data',
                                'prompt': 'SUBTASK_PROMPT' * 500,
                            },
                        },
                    ],
                },
            ],
        },
    )

    packet = build_judge_packet(_scenario(), bundle).as_json()
    transcript_json = json.dumps(packet['transcript'], ensure_ascii=False)
    assistant_parts = packet['transcript']['messages'][1]['parts']

    assert [part['type'] for part in assistant_parts] == ['text', 'tool']
    assert len(assistant_parts[0]['text']) <= 1200
    assert assistant_parts[1] == {
        'type': 'tool',
        'tool': 'read',
        'state': {
            'status': 'completed',
            'title': 'Read large GeoJSON',
        },
    }
    assert 'private reasoning' not in transcript_json
    assert 'TOOL_OUTPUT' not in transcript_json
    assert 'SUBTASK_PROMPT' not in transcript_json


def test_validate_judge_output_rejects_missing_dimensions() -> None:
    rubric = get_judge_rubric('geospatial-agent-v1').as_json()

    with pytest.raises(ValueError, match='missing dimensions'):
        validate_judge_output(
            json.dumps({'dimensions': {}, 'summary': 'bad'}),
            rubric,
        )


def test_validate_judge_output_rejects_zero_scores() -> None:
    rubric = get_judge_rubric('geospatial-agent-v1').as_json()
    response = {
        'dimensions': {
            dimension.id: {'score': 1, 'reason': 'reason'}
            for dimension in GEOSPATIAL_AGENT_RUBRIC.dimensions
        },
        'summary': 'invalid',
    }
    response['dimensions']['method_selection']['score'] = 0

    with pytest.raises(ValueError, match='integer 1-5'):
        validate_judge_output(json.dumps(response), rubric)


def test_validate_judge_output_accepts_fenced_list_dimensions() -> None:
    rubric = get_judge_rubric('geospatial-agent-v1').as_json()
    response = {
        'dimensions': [
            {'id': dimension.id, 'score': 4, 'reason': 'reason'}
            for dimension in GEOSPATIAL_AGENT_RUBRIC.dimensions
        ],
        'professional_acceptability': True,
        'summary': 'acceptable',
    }

    parsed = validate_judge_output(f'```json\n{json.dumps(response)}\n```', rubric)

    assert isinstance(parsed['dimensions'], dict)
    assert 'professional_acceptability' not in parsed
    assert parsed['dimensions']['method_selection']['score'] == 4


@pytest.mark.asyncio
async def test_write_judge_score_retries_invalid_output_and_preserves_raw_responses(tmp_path: Path) -> None:
    bundle = tmp_path / 'bundle'
    _write_bundle(bundle)
    provider = FakeJudgeProvider(('not-json', _valid_judge_response()))

    score_path = await write_judge_score(
        _scenario(),
        bundle,
        provider,
        JudgeConfig(model='glm-5.1', temperature=0.0, max_retries=1),
    )

    score = json.loads(score_path.read_text(encoding='utf-8'))
    judge_input = json.loads((bundle / JUDGE_INPUT_FILENAME).read_text(encoding='utf-8'))

    assert score_path == bundle / JUDGE_SCORE_FILENAME
    assert len(score['attempts']) == 2
    assert score['parsed_score']['dimensions']['method_selection']['score'] == 5
    assert 'passed' not in score
    assert 'professional_acceptability' not in score
    assert 'deterministic_fatal_failures' not in score
    assert (bundle / 'judge-response-001.txt').read_text(encoding='utf-8').strip() == 'not-json'
    response = json.loads((bundle / 'judge-response-002.txt').read_text(encoding='utf-8'))
    assert response['summary'] == 'dimension-only score'
    assert judge_input['config']['model'] == 'glm-5.1'
    assert provider.requests[0]['temperature'] == 0.0


@pytest.mark.asyncio
async def test_llm_judge_keeps_dimension_scores_without_pass_fail_gate(tmp_path: Path) -> None:
    bundle = tmp_path / 'bundle'
    _write_bundle(bundle)
    packet = build_judge_packet(_scenario(), bundle)

    result = await run_llm_judge(
        packet,
        FakeJudgeProvider((_valid_judge_response(score=2),)),
        JudgeConfig(model='glm-5.1', temperature=0.0),
    )

    result_json = result.as_json()

    assert result.parsed_score is not None
    assert result.parsed_score['dimensions']['method_selection']['score'] == 2
    assert 'passed' not in result_json
    assert 'professional_acceptability' not in result_json
    assert 'judgeability_failures' not in result_json
