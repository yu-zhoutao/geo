from __future__ import annotations

import json
from pathlib import Path

from app.evaluation.costs import RUN_COST_SCHEMA, extract_run_costs
from app.evaluation.run_bundles import ARTIFACT_MANIFEST_FILENAME, RUN_MANIFEST_FILENAME, RUN_STATUS_FILENAME
from app.evaluation.session_traces import SESSION_JSON_FILENAME


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def test_extract_run_costs_uses_available_runtime_and_session_metadata(tmp_path: Path) -> None:
    bundle = tmp_path / 'bundle'
    _write_json(
        bundle / RUN_STATUS_FILENAME,
        {
            'duration_seconds': 12.5,
            'session_status': 'completed',
            'timed_out': False,
            'retry_count': 2,
        },
    )
    _write_json(bundle / RUN_MANIFEST_FILENAME, {'error_count': 0})
    _write_json(bundle / ARTIFACT_MANIFEST_FILENAME, {'artifact_count': 3})
    _write_json(
        bundle / SESSION_JSON_FILENAME,
        {
            'messages': [
                {
                    'usage': {'input_tokens': 100, 'output_tokens': 25},
                    'parts': [
                        {'type': 'text', 'text': 'done'},
                        {'type': 'tool', 'tool': 'record_run_evidence', 'state': {'status': 'completed'}},
                    ],
                },
                {
                    'usage': {'input_tokens': 10, 'output_tokens': 5},
                    'parts': [
                        {'type': 'tool', 'tool': 'runtime_tool', 'state': {'status': 'failed'}},
                    ],
                },
            ]
        },
    )

    costs = extract_run_costs(bundle).as_json()

    assert costs['schema'] == RUN_COST_SCHEMA
    assert costs['wall_clock_seconds'] == 12.5
    assert costs['token_counts'] == {'input_tokens': 110, 'output_tokens': 30, 'total_tokens': 140}
    assert costs['tool_call_count'] == 2
    assert costs['failed_tool_call_count'] == 1
    assert costs['artifact_count'] == 3
    assert costs['retry_count'] == 2
    assert costs['failed_attempt'] is False
    assert costs['unavailable'] == []


def test_extract_run_costs_marks_failed_attempt_from_terminal_status(tmp_path: Path) -> None:
    bundle = tmp_path / 'bundle'
    _write_json(bundle / RUN_STATUS_FILENAME, {'duration_seconds': 12.5, 'session_status': 'failed', 'timed_out': False})
    _write_json(bundle / RUN_MANIFEST_FILENAME, {'error_count': 0})
    _write_json(bundle / ARTIFACT_MANIFEST_FILENAME, {'artifact_count': 0})
    _write_json(bundle / SESSION_JSON_FILENAME, {'messages': []})

    costs = extract_run_costs(bundle).as_json()

    assert costs['failed_attempt'] is True


def test_extract_run_costs_marks_unavailable_fields_without_failing(tmp_path: Path) -> None:
    bundle = tmp_path / 'bundle'
    _write_json(bundle / RUN_STATUS_FILENAME, {'session_status': 'completed', 'timed_out': False})
    _write_json(bundle / RUN_MANIFEST_FILENAME, {'error_count': 0})
    _write_json(bundle / ARTIFACT_MANIFEST_FILENAME, {'items': [{'id': 'artifact-1'}]})
    _write_json(bundle / SESSION_JSON_FILENAME, {'messages': []})

    costs = extract_run_costs(bundle).as_json()

    assert costs['wall_clock_seconds'] is None
    assert costs['token_counts'] == {}
    assert costs['artifact_count'] == 1
    assert costs['failed_attempt'] is False
    assert costs['unavailable'] == ['wall_clock_seconds', 'token_counts']
