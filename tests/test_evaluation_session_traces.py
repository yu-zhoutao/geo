from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.evaluation.session_traces import (
    EVIDENCE_RECORDS_FILENAME,
    RUNTIME_TRACE_REF_FILENAME,
    SESSION_JSON_FILENAME,
    SESSION_TRACE_FILENAME,
    TRACE_CAPTURE_MANIFEST_FILENAME,
    TRANSCRIPT_FILENAME,
    SessionTraceCaptureError,
    write_session_trace_bundle,
)
from app.services.session_archives import SESSION_ARCHIVE_SCHEMA


def _archive() -> dict[str, object]:
    return {
        'schema': SESSION_ARCHIVE_SCHEMA,
        'exported_at': '2026-04-29T00:00:00+00:00',
        'source': {
            'session_id': 'session-1',
            'runtime_session_id': 'runtime-1',
            'runtime_trace_path': 'runtime/trace.jsonl',
        },
        'session': {
            'id': 'session-1',
            'title': 'Evaluation run',
            'status': 'completed',
            'created_at': '2026-04-29T00:00:00+00:00',
            'updated_at': '2026-04-29T00:01:00+00:00',
            'workspace_path': '/tmp/workspace',
            'runtime_session_id': 'runtime-1',
            'runtime_trace_path': 'runtime/trace.jsonl',
            'attached_data_directories': [],
            'messages': [
                {
                    'id': 'msg-user-1',
                    'role': 'user',
                    'agent': 'geo',
                    'created_at': '2026-04-29T00:00:00+00:00',
                    'parts': [{'type': 'text', 'text': 'Run unchanged prompt'}],
                },
            ],
            'timeline': [],
            'plan': [],
            'plan_groups': [],
            'issues': [],
            'question': None,
            'artifacts': [
                {
                    'id': 'artifact-1',
                    'title': 'KDE 运行清单',
                    'path': 'outputs/run-manifest.json',
                    'kind': 'manifest',
                },
            ],
            'geospatial_task': None,
            'verification': [],
        },
        'geospatial_context': None,
        'evidence_records': [
            {
                'id': 'evidence-1',
                'session_context_id': 'context-1',
                'record_type': 'claim_trace',
                'title': '声明追踪',
            },
        ],
        'runtime_trace': {'runtime_session_id': 'runtime-1', 'trace_path': 'runtime/trace.jsonl'},
    }


def test_write_session_trace_bundle_splits_archive_into_runner_inputs(tmp_path: Path) -> None:
    bundle_root: Path = tmp_path / 'run-bundle'

    capture = write_session_trace_bundle(_archive(), bundle_root)

    assert capture.session_id == 'session-1'
    assert capture.session_status == 'completed'
    assert capture.runtime_session_id == 'runtime-1'
    assert capture.runtime_trace_path == 'runtime/trace.jsonl'
    assert capture.message_count == 1
    assert capture.evidence_record_count == 1
    assert capture.artifact_count == 1
    assert capture.session_trace_path == bundle_root / SESSION_TRACE_FILENAME
    assert capture.manifest_path == bundle_root / TRACE_CAPTURE_MANIFEST_FILENAME

    manifest = json.loads((bundle_root / TRACE_CAPTURE_MANIFEST_FILENAME).read_text(encoding='utf-8'))
    transcript = json.loads((bundle_root / TRANSCRIPT_FILENAME).read_text(encoding='utf-8'))
    evidence = json.loads((bundle_root / EVIDENCE_RECORDS_FILENAME).read_text(encoding='utf-8'))
    runtime_trace = json.loads((bundle_root / RUNTIME_TRACE_REF_FILENAME).read_text(encoding='utf-8'))
    session = json.loads((bundle_root / SESSION_JSON_FILENAME).read_text(encoding='utf-8'))
    trace = json.loads((bundle_root / SESSION_TRACE_FILENAME).read_text(encoding='utf-8'))

    assert manifest['source_schema'] == SESSION_ARCHIVE_SCHEMA
    assert manifest['files']['session_trace'] == SESSION_TRACE_FILENAME
    assert transcript['messages'][0]['parts'][0]['text'] == 'Run unchanged prompt'
    assert evidence['items'][0]['id'] == 'evidence-1'
    assert runtime_trace['trace_path'] == 'runtime/trace.jsonl'
    assert session['artifacts'][0]['id'] == 'artifact-1'
    assert trace['schema'] == SESSION_ARCHIVE_SCHEMA


def test_write_session_trace_bundle_rejects_overwrite(tmp_path: Path) -> None:
    bundle_root: Path = tmp_path / 'run-bundle'
    write_session_trace_bundle(_archive(), bundle_root)

    with pytest.raises(SessionTraceCaptureError, match='overwrite existing files'):
        write_session_trace_bundle(_archive(), bundle_root)


def test_write_session_trace_bundle_rejects_invalid_archive_schema(tmp_path: Path) -> None:
    archive = _archive()
    archive['schema'] = 'geo-agent.session-archive.v999'

    with pytest.raises(SessionTraceCaptureError, match='Unsupported session archive schema'):
        write_session_trace_bundle(archive, tmp_path / 'run-bundle')
