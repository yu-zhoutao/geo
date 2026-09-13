from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3

from app.config import Settings, get_settings
from app.models import Artifact, ChatMessage, DataDirectoryAttachment, GeospatialSessionContext, GeospatialTask, PlanEntry, PlanGroup, Question, Session, SessionIssue, SessionSummary, TimelineEntry, VerificationEntry


class SessionStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.db_path = self.settings.resolved_database_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                '''
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    workspace_path TEXT NOT NULL,
                    geospatial_context_id TEXT,
                    runtime_session_id TEXT,
                    runtime_trace_path TEXT,
                    attached_data_dirs_json TEXT,
                    artifacts_json TEXT,
                    geospatial_task_json TEXT,
                    verification_json TEXT,
                    messages_json TEXT,
                    timeline_json TEXT,
                    plan_json TEXT,
                    plan_groups_json TEXT,
                    issues_json TEXT,
                    question_json TEXT,
                    read_only INTEGER NOT NULL DEFAULT 0,
                    archive_metadata_json TEXT,
                    deleted_at TEXT
                );

                CREATE TABLE IF NOT EXISTS geospatial_session_contexts (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    runtime_session_id TEXT,
                    mcp_session_id TEXT,
                    prompt TEXT NOT NULL,
                    answer TEXT,
                    workspace_path TEXT NOT NULL,
                    request_snapshot_path TEXT,
                    prepared_input_path TEXT,
                    manifest_path TEXT,
                    attached_data_dirs_json TEXT,
                    geospatial_task_json TEXT,
                    verification_json TEXT,
                    artifacts_json TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS geospatial_evidence_records (
                    id TEXT PRIMARY KEY,
                    context_id TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                '''
            )
            columns = {row['name'] for row in connection.execute('PRAGMA table_info(sessions)').fetchall()}
            for column_name in (
                'geospatial_context_id',
                'runtime_session_id',
                'runtime_trace_path',
                'attached_data_dirs_json',
                'artifacts_json',
                'geospatial_task_json',
                'verification_json',
                'messages_json',
                'timeline_json',
                'plan_json',
                'plan_groups_json',
                'issues_json',
                'question_json',
                'read_only',
                'archive_metadata_json',
            ):
                if column_name not in columns:
                    if column_name == 'read_only':
                        connection.execute('ALTER TABLE sessions ADD COLUMN read_only INTEGER NOT NULL DEFAULT 0')
                    else:
                        connection.execute(f'ALTER TABLE sessions ADD COLUMN {column_name} TEXT')

    def save_session(self, session: Session) -> None:
        with self._connect() as connection:
            connection.execute(
                '''
                INSERT INTO sessions (
                    id, title, status, created_at, updated_at, workspace_path,
                    geospatial_context_id,
                    runtime_session_id, runtime_trace_path,
                    attached_data_dirs_json, artifacts_json, geospatial_task_json,
                    verification_json, messages_json, timeline_json, plan_json, plan_groups_json, issues_json, question_json,
                    read_only, archive_metadata_json, deleted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title,
                    status=excluded.status,
                    updated_at=excluded.updated_at,
                    workspace_path=excluded.workspace_path,
                    geospatial_context_id=excluded.geospatial_context_id,
                    runtime_session_id=excluded.runtime_session_id,
                    runtime_trace_path=excluded.runtime_trace_path,
                    attached_data_dirs_json=excluded.attached_data_dirs_json,
                    artifacts_json=excluded.artifacts_json,
                    geospatial_task_json=excluded.geospatial_task_json,
                    verification_json=excluded.verification_json,
                    messages_json=excluded.messages_json,
                    timeline_json=excluded.timeline_json,
                    plan_json=excluded.plan_json,
                    plan_groups_json=excluded.plan_groups_json,
                    issues_json=excluded.issues_json,
                    question_json=excluded.question_json,
                    read_only=excluded.read_only,
                    archive_metadata_json=excluded.archive_metadata_json
                ''',
                (
                    session.id,
                    session.title,
                    session.status,
                    session.created_at.isoformat(),
                    session.updated_at.isoformat(),
                    session.workspace_path or '',
                    session.geospatial_context_id,
                    session.runtime_session_id,
                    session.runtime_trace_path,
                    json.dumps([item.model_dump(mode='json') for item in session.attached_data_directories]),
                    json.dumps([artifact.model_dump(mode='json') for artifact in session.artifacts]),
                    json.dumps(session.geospatial_task.model_dump(mode='json')) if session.geospatial_task is not None else None,
                    json.dumps([entry.model_dump(mode='json') for entry in session.verification]),
                    json.dumps([message.model_dump(mode='json') for message in session.messages]),
                    json.dumps([entry.model_dump(mode='json') for entry in session.timeline]),
                    json.dumps([entry.model_dump(mode='json') for entry in session.plan]),
                    json.dumps([group.model_dump(mode='json') for group in session.plan_groups]),
                    json.dumps([issue.model_dump(mode='json') for issue in session.issues]),
                    json.dumps(session.question.model_dump(mode='json')) if session.question is not None else None,
                    1 if session.read_only else 0,
                    json.dumps(session.archive_metadata, ensure_ascii=False, sort_keys=True),
                ),
            )

    def list_sessions(self) -> list[SessionSummary]:
        with self._connect() as connection:
            rows = connection.execute(
                '''
                SELECT id, title, status, created_at, updated_at, workspace_path
                , geospatial_context_id, runtime_session_id, runtime_trace_path, attached_data_dirs_json
                , read_only, archive_metadata_json
                FROM sessions
                WHERE deleted_at IS NULL
                ORDER BY updated_at DESC
                '''
            ).fetchall()
        return [
            SessionSummary(
                id=row['id'],
                title=row['title'],
                status=row['status'],
                created_at=datetime.fromisoformat(row['created_at']),
                updated_at=datetime.fromisoformat(row['updated_at']),
                workspace_path=None if bool(row['read_only']) and not row['workspace_path'] else row['workspace_path'],
                geospatial_context_id=row['geospatial_context_id'],
                runtime_session_id=row['runtime_session_id'],
                runtime_trace_path=row['runtime_trace_path'],
                attached_data_directories=[DataDirectoryAttachment(**item) for item in json.loads(row['attached_data_dirs_json'] or '[]')],
                read_only=bool(row['read_only']),
                archive_metadata=json.loads(row['archive_metadata_json'] or '{}'),
            )
            for row in rows
        ]

    def load_session(self, session_id: str) -> Session | None:
        with self._connect() as connection:
            row = connection.execute(
                '''
                SELECT *
                FROM sessions
                WHERE id = ? AND deleted_at IS NULL
                ''',
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        attached_dirs_payload = json.loads(row['attached_data_dirs_json'] or '[]')
        artifacts_payload = json.loads(row['artifacts_json'] or '[]')
        geospatial_task_payload = json.loads(row['geospatial_task_json']) if row['geospatial_task_json'] else None
        verification_payload = json.loads(row['verification_json'] or '[]')
        messages_payload = json.loads(row['messages_json'] or '[]')
        timeline_payload = json.loads(row['timeline_json'] or '[]')
        plan_payload = json.loads(row['plan_json'] or '[]')
        plan_groups_payload = json.loads(row['plan_groups_json'] or '[]')
        issues_payload = json.loads(row['issues_json'] or '[]')
        question_payload = json.loads(row['question_json']) if row['question_json'] else None
        return Session(
            id=row['id'],
            title=row['title'],
            status=row['status'],
            created_at=datetime.fromisoformat(row['created_at']),
            updated_at=datetime.fromisoformat(row['updated_at']),
            workspace_path=None if bool(row['read_only']) and not row['workspace_path'] else row['workspace_path'],
            geospatial_context_id=row['geospatial_context_id'],
            runtime_session_id=row['runtime_session_id'],
            runtime_trace_path=row['runtime_trace_path'],
            attached_data_directories=[DataDirectoryAttachment(**item) for item in attached_dirs_payload],
            messages=[ChatMessage(**item) for item in messages_payload],
            timeline=[TimelineEntry(**item) for item in timeline_payload],
            plan=[PlanEntry(**item) for item in plan_payload],
            plan_groups=[PlanGroup(**item) for item in plan_groups_payload],
            issues=[SessionIssue(**item) for item in issues_payload],
            artifacts=[Artifact(**item) for item in artifacts_payload],
            geospatial_task=GeospatialTask(**geospatial_task_payload) if geospatial_task_payload is not None else None,
            verification=[VerificationEntry(**item) for item in verification_payload],
            question=Question(**question_payload) if question_payload is not None else None,
            read_only=bool(row['read_only']),
            archive_metadata=json.loads(row['archive_metadata_json'] or '{}'),
        )

    def rename_session(self, session_id: str, title: str) -> None:
        with self._connect() as connection:
            connection.execute(
                'UPDATE sessions SET title = ?, updated_at = ? WHERE id = ? AND deleted_at IS NULL',
                (title, datetime.now(UTC).isoformat(), session_id),
            )

    def delete_session(self, session_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                'UPDATE sessions SET deleted_at = ?, updated_at = ? WHERE id = ? AND deleted_at IS NULL',
                (datetime.now(UTC).isoformat(), datetime.now(UTC).isoformat(), session_id),
            )

    def status_payload(self) -> dict[str, object]:
        return {
            'status': 'ready',
            'path': str(self.db_path),
        }

    def save_geospatial_session_context(self, context: GeospatialSessionContext) -> None:
        with self._connect() as connection:
            connection.execute(
                '''
                INSERT INTO geospatial_session_contexts (
                    id, session_id, runtime_session_id, mcp_session_id, prompt, answer,
                    workspace_path, request_snapshot_path, prepared_input_path, manifest_path,
                    attached_data_dirs_json, geospatial_task_json, verification_json, artifacts_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    session_id=excluded.session_id,
                    runtime_session_id=excluded.runtime_session_id,
                    mcp_session_id=excluded.mcp_session_id,
                    prompt=excluded.prompt,
                    answer=excluded.answer,
                    workspace_path=excluded.workspace_path,
                    request_snapshot_path=excluded.request_snapshot_path,
                    prepared_input_path=excluded.prepared_input_path,
                    manifest_path=excluded.manifest_path,
                    attached_data_dirs_json=excluded.attached_data_dirs_json,
                    geospatial_task_json=excluded.geospatial_task_json,
                    verification_json=excluded.verification_json,
                    artifacts_json=excluded.artifacts_json,
                    updated_at=excluded.updated_at
                ''',
                (
                    context.id,
                    context.session_id,
                    context.runtime_session_id,
                    context.mcp_session_id,
                    context.prompt,
                    context.answer,
                    context.workspace_path,
                    context.request_snapshot_path,
                    context.prepared_input_path,
                    context.manifest_path,
                    json.dumps([item.model_dump(mode='json') for item in context.attached_data_directories]),
                    json.dumps(context.geospatial_task.model_dump(mode='json')) if context.geospatial_task is not None else None,
                    json.dumps([item.model_dump(mode='json') for item in context.verification]),
                    json.dumps([item.model_dump(mode='json') for item in context.artifacts]),
                    context.updated_at.isoformat(),
                ),
            )

    def load_geospatial_session_context(self, context_id: str | None) -> GeospatialSessionContext | None:
        if context_id is None:
            return None
        with self._connect() as connection:
            row = connection.execute(
                'SELECT * FROM geospatial_session_contexts WHERE id = ?',
                (context_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_geospatial_session_context(row)

    def load_geospatial_session_context_by_mcp_session(self, mcp_session_id: str | None) -> GeospatialSessionContext | None:
        if mcp_session_id is None:
            return None
        with self._connect() as connection:
            row = connection.execute(
                '''
                SELECT * FROM geospatial_session_contexts
                WHERE mcp_session_id = ?
                ORDER BY updated_at DESC
                LIMIT 1
                ''',
                (mcp_session_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_geospatial_session_context(row)

    def load_latest_geospatial_session_context_by_prompt(self, prompt: str, answer: str | None) -> GeospatialSessionContext | None:
        with self._connect() as connection:
            rows = connection.execute(
                '''
                SELECT * FROM geospatial_session_contexts
                WHERE prompt = ? AND (answer IS ? OR answer = ?)
                ORDER BY updated_at DESC
                ''',
                (prompt, answer, answer),
            ).fetchall()
        if len(rows) != 1:
            return None
        return self._row_to_geospatial_session_context(rows[0])

    def load_latest_geospatial_session_context(self) -> GeospatialSessionContext | None:
        with self._connect() as connection:
            row = connection.execute(
                '''
                SELECT * FROM geospatial_session_contexts
                ORDER BY updated_at DESC
                LIMIT 1
                '''
            ).fetchone()
        if row is None:
            return None
        return self._row_to_geospatial_session_context(row)

    def append_geospatial_evidence_record(self, record: dict[str, object]) -> None:
        context_id = str(record.get('session_context_id') or '')
        if not context_id:
            raise ValueError('Geospatial evidence record requires session_context_id')
        record_id = str(record.get('id') or '')
        if not record_id:
            raise ValueError('Geospatial evidence record requires id')
        created_at = str(record.get('created_at') or datetime.now(UTC).isoformat())
        with self._connect() as connection:
            connection.execute(
                '''
                INSERT INTO geospatial_evidence_records (
                    id, context_id, record_json, created_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    context_id=excluded.context_id,
                    record_json=excluded.record_json,
                    created_at=excluded.created_at
                ''',
                (
                    record_id,
                    context_id,
                    json.dumps(record, ensure_ascii=False, sort_keys=True),
                    created_at,
                ),
            )

    def list_geospatial_evidence_records(self, context_id: str) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                '''
                SELECT record_json
                FROM geospatial_evidence_records
                WHERE context_id = ?
                ORDER BY created_at ASC, id ASC
                ''',
                (context_id,),
            ).fetchall()
        records: list[dict[str, object]] = []
        for row in rows:
            payload = json.loads(row['record_json'])
            if isinstance(payload, dict):
                records.append(payload)
        return records

    def _row_to_geospatial_session_context(self, row: sqlite3.Row) -> GeospatialSessionContext:
        attached_dirs_payload = json.loads(row['attached_data_dirs_json'] or '[]')
        geospatial_task_payload = json.loads(row['geospatial_task_json']) if row['geospatial_task_json'] else None
        verification_payload = json.loads(row['verification_json'] or '[]')
        artifacts_payload = json.loads(row['artifacts_json'] or '[]')
        return GeospatialSessionContext(
            id=row['id'],
            session_id=row['session_id'],
            runtime_session_id=row['runtime_session_id'],
            mcp_session_id=row['mcp_session_id'],
            prompt=row['prompt'],
            answer=row['answer'],
            workspace_path=row['workspace_path'],
            request_snapshot_path=row['request_snapshot_path'],
            prepared_input_path=row['prepared_input_path'],
            manifest_path=row['manifest_path'],
            attached_data_directories=[DataDirectoryAttachment(**item) for item in attached_dirs_payload],
            geospatial_task=GeospatialTask(**geospatial_task_payload) if geospatial_task_payload is not None else None,
            verification=[VerificationEntry(**item) for item in verification_payload],
            artifacts=[Artifact(**item) for item in artifacts_payload],
            updated_at=datetime.fromisoformat(row['updated_at']),
        )
