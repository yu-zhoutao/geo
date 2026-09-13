from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from app.models import GeospatialSessionContext, Session


SESSION_ARCHIVE_SCHEMA = 'geo-agent.session-archive.v1'


class SessionArchiveError(ValueError):
    pass


def build_session_archive(
    *,
    session: Session,
    geospatial_context: GeospatialSessionContext | None,
    evidence_records: list[dict[str, object]],
) -> dict[str, Any]:
    source: dict[str, object] = {
        'session_id': session.id,
        'title': session.title,
        'runtime_session_id': session.runtime_session_id,
        'runtime_trace_path': session.runtime_trace_path,
        'workspace_path': session.workspace_path,
    }
    runtime_trace: dict[str, object] = {
        'runtime_session_id': session.runtime_session_id,
        'trace_path': session.runtime_trace_path,
    }
    return {
        'schema': SESSION_ARCHIVE_SCHEMA,
        'exported_at': datetime.now(UTC).isoformat(),
        'source': source,
        'session': session.model_dump(mode='json'),
        'geospatial_context': geospatial_context.model_dump(mode='json') if geospatial_context is not None else None,
        'evidence_records': evidence_records,
        'runtime_trace': runtime_trace,
    }


def session_archive_filename(session: Session) -> str:
    safe_session_id = ''.join(character if character.isalnum() or character in {'-', '_'} else '-' for character in session.id)
    return f'geo-agent-session-{safe_session_id}.json'


def imported_session_from_archive(archive: dict[str, Any]) -> tuple[Session, GeospatialSessionContext | None, list[dict[str, object]]]:
    if archive.get('schema') != SESSION_ARCHIVE_SCHEMA:
        raise SessionArchiveError('Unsupported session archive schema')
    session_payload = archive.get('session')
    if not isinstance(session_payload, dict):
        raise SessionArchiveError('Session archive requires a session payload')
    try:
        source_session = Session.model_validate(session_payload)
    except ValidationError as exc:
        raise SessionArchiveError('Session archive contains malformed session data') from exc

    imported_at = datetime.now(UTC)
    imported_session_id = f'imported-session-{uuid4().hex[:8]}'
    source = archive.get('source') if isinstance(archive.get('source'), dict) else {}
    runtime_trace = archive.get('runtime_trace') if isinstance(archive.get('runtime_trace'), dict) else {}
    context_payload = archive.get('geospatial_context')
    imported_context_id = f'imported-context-{uuid4().hex[:8]}' if isinstance(context_payload, dict) else None
    archive_metadata: dict[str, object] = {
        'schema': SESSION_ARCHIVE_SCHEMA,
        'imported_at': imported_at.isoformat(),
        'exported_at': archive.get('exported_at'),
        'source': source,
        'runtime_trace': runtime_trace,
    }
    imported_session = source_session.model_copy(
        update={
            'id': imported_session_id,
            'updated_at': imported_at,
            'workspace_path': None,
            'geospatial_context_id': imported_context_id,
            'runtime_session_id': None,
            'runtime_trace_path': None,
            'read_only': True,
            'archive_metadata': archive_metadata,
        }
    )

    imported_context: GeospatialSessionContext | None = None
    if isinstance(context_payload, dict):
        try:
            source_context = GeospatialSessionContext.model_validate(context_payload)
        except ValidationError as exc:
            raise SessionArchiveError('Session archive contains malformed geospatial context data') from exc
        imported_context = source_context.model_copy(
            update={
                'id': imported_context_id,
                'session_id': imported_session_id,
                'runtime_session_id': None,
                'mcp_session_id': None,
                'workspace_path': '',
                'updated_at': imported_at,
            }
        )

    records_payload = archive.get('evidence_records')
    if records_payload is None:
        evidence_records: list[dict[str, object]] = []
    elif isinstance(records_payload, list):
        evidence_records = [dict(record) for record in records_payload if isinstance(record, dict)]
    else:
        raise SessionArchiveError('Session archive evidence_records must be a list')
    if imported_context_id is not None:
        evidence_records = [
            {
                **record,
                'session_context_id': imported_context_id,
            }
            for record in evidence_records
        ]
    return imported_session, imported_context, evidence_records
