from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from app.services.session_archives import SESSION_ARCHIVE_SCHEMA


SESSION_TRACE_FILENAME = 'session-trace.json'
SESSION_JSON_FILENAME = 'session.json'
TRANSCRIPT_FILENAME = 'transcript.json'
EVIDENCE_RECORDS_FILENAME = 'evidence-records.json'
RUNTIME_TRACE_REF_FILENAME = 'runtime-trace-ref.json'
TRACE_CAPTURE_MANIFEST_FILENAME = 'trace-capture-manifest.json'


class SessionTraceCaptureError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SessionTraceCapture:
    session_id: str
    session_status: str
    runtime_session_id: str | None
    runtime_trace_path: str | None
    message_count: int
    evidence_record_count: int
    artifact_count: int
    session_trace_path: Path
    manifest_path: Path


def write_session_trace_bundle(archive: dict[str, Any], bundle_root: Path) -> SessionTraceCapture:
    session = _session_payload(archive)
    evidence_records = _evidence_records(archive)
    runtime_trace = _object_payload(archive, 'runtime_trace')
    messages = _list_payload(session, 'messages')
    artifacts = _list_payload(session, 'artifacts')

    output_paths: dict[str, Path] = {
        'session_trace': bundle_root / SESSION_TRACE_FILENAME,
        'session_json': bundle_root / SESSION_JSON_FILENAME,
        'transcript': bundle_root / TRANSCRIPT_FILENAME,
        'evidence_records': bundle_root / EVIDENCE_RECORDS_FILENAME,
        'runtime_trace_ref': bundle_root / RUNTIME_TRACE_REF_FILENAME,
        'manifest': bundle_root / TRACE_CAPTURE_MANIFEST_FILENAME,
    }
    existing: list[Path] = [path for path in output_paths.values() if path.exists()]
    if existing:
        joined = ', '.join(str(path) for path in existing)
        raise SessionTraceCaptureError(f'Session trace bundle would overwrite existing files: {joined}')

    bundle_root.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        'schema': 'geo-agent.evaluation.session-trace-capture.v1',
        'source_schema': archive.get('schema'),
        'session_id': _string_field(session, 'id'),
        'session_status': _string_field(session, 'status'),
        'runtime_session_id': runtime_trace.get('runtime_session_id') or session.get('runtime_session_id'),
        'runtime_trace_path': runtime_trace.get('trace_path') or session.get('runtime_trace_path'),
        'message_count': len(messages),
        'evidence_record_count': len(evidence_records),
        'artifact_count': len(artifacts),
        'files': {key: path.name for key, path in output_paths.items()},
    }

    _write_json(output_paths['session_trace'], archive)
    _write_json(output_paths['session_json'], session)
    _write_json(output_paths['transcript'], {'messages': messages, 'message_count': len(messages)})
    _write_json(output_paths['evidence_records'], {'items': evidence_records, 'record_count': len(evidence_records)})
    _write_json(output_paths['runtime_trace_ref'], runtime_trace)
    _write_json(output_paths['manifest'], manifest)

    return SessionTraceCapture(
        session_id=str(manifest['session_id']),
        session_status=str(manifest['session_status']),
        runtime_session_id=_optional_string(manifest.get('runtime_session_id')),
        runtime_trace_path=_optional_string(manifest.get('runtime_trace_path')),
        message_count=len(messages),
        evidence_record_count=len(evidence_records),
        artifact_count=len(artifacts),
        session_trace_path=output_paths['session_trace'],
        manifest_path=output_paths['manifest'],
    )


def _session_payload(archive: dict[str, Any]) -> dict[str, Any]:
    if archive.get('schema') != SESSION_ARCHIVE_SCHEMA:
        raise SessionTraceCaptureError('Unsupported session archive schema')
    session = archive.get('session')
    if not isinstance(session, dict):
        raise SessionTraceCaptureError('Session archive requires a session object')
    _string_field(session, 'id')
    _string_field(session, 'status')
    return session


def _evidence_records(archive: dict[str, Any]) -> list[dict[str, Any]]:
    records = archive.get('evidence_records')
    if records is None:
        return []
    if not isinstance(records, list) or not all(isinstance(record, dict) for record in records):
        raise SessionTraceCaptureError('Session archive evidence_records must be a list of objects')
    return records


def _object_payload(payload: dict[str, Any], field: str) -> dict[str, Any]:
    value = payload.get(field)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise SessionTraceCaptureError(f'Session archive {field} must be an object')
    return value


def _list_payload(payload: dict[str, Any], field: str) -> list[dict[str, Any]]:
    value = payload.get(field)
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise SessionTraceCaptureError(f'Session {field} must be a list of objects')
    return value


def _string_field(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise SessionTraceCaptureError(f'Session archive requires string field: {field}')
    return value


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
