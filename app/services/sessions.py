from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import HTTPException

from app.config import Settings, get_settings
from app.models import Artifact, ChatMessage, ChatMessagePart, DataDirectoryAttachment, EventEnvelope, GeospatialSessionContext, PlanEntry, PlanGroup, Question, Session, SessionIssue, SessionIssueSeverity, SessionIssueSource, SessionIssueType, SessionSummary, TimelineEntry
from app.services.agent_identity import load_agent_identity_map
from app.services.agent_runtime import AgentRuntimeClient, RuntimeSessionRequest, build_agent_runtime_client
from app.services.artifacts import upsert_artifact_by_path
from app.services.providers import TitleProvider, build_title_provider, selected_model_provider_metadata
from app.services.session_archives import SessionArchiveError, build_session_archive, imported_session_from_archive
from app.services.session_store import SessionStore
from app.services.tool_identity import canonical_tool_name
from app.services.workspace import WorkspaceManager


RunCancellationReason = Literal['replace', 'delete', 'shutdown', 'interrupt']


class SessionService:
    def __init__(
        self,
        settings: Settings | None = None,
        title_provider: TitleProvider | None = None,
        runtime_client: AgentRuntimeClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.sessions: dict[str, Session] = {}
        self.subscribers: dict[str, list[asyncio.Queue[EventEnvelope]]] = {}
        self.active_runs: dict[str, asyncio.Task[None]] = {}
        self.active_runtime_requests: dict[str, RuntimeSessionRequest] = {}
        self.run_cancellation_reasons: dict[str, RunCancellationReason] = {}
        self.workspace_manager = WorkspaceManager(settings=self.settings)
        self.store = SessionStore(settings=self.settings)
        self.title_provider = title_provider or build_title_provider(settings=self.settings)
        self.runtime_client = runtime_client or build_agent_runtime_client(self.settings)

    def list_sessions(self) -> list[SessionSummary]:
        return self.store.list_sessions()

    def get_session(self, session_id: str) -> Session:
        session = self.sessions.get(session_id)
        if session is None:
            session = self.store.load_session(session_id)
            if session is not None:
                self.sessions[session.id] = session
        if session is None:
            raise HTTPException(status_code=404, detail='Session not found')
        return session

    async def get_session_with_runtime_recovery(self, session_id: str) -> Session:
        session = self.get_session(session_id)
        if session.read_only:
            return session
        self._cleanup_session_artifact_state(session)
        await self._recover_runtime_messages(session)
        self._recover_evidence_timeline_from_store(session)
        self._recover_plan_groups_from_messages(session)
        return session

    async def export_session_archive(self, session_id: str) -> dict[str, object]:
        session = await self.get_session_with_runtime_recovery(session_id)
        context = self.store.load_geospatial_session_context(session.geospatial_context_id)
        evidence_records = self.store.list_geospatial_evidence_records(context.id) if context is not None else []
        return build_session_archive(session=session, geospatial_context=context, evidence_records=evidence_records)

    async def import_session_archive(self, archive: dict[str, object]) -> Session:
        try:
            session, context, evidence_records = imported_session_from_archive(archive)
        except SessionArchiveError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if context is not None:
            self.store.save_geospatial_session_context(context)
        for record in evidence_records:
            if context is None:
                continue
            self.store.append_geospatial_evidence_record(record)
        self.sessions[session.id] = session
        self.subscribers.setdefault(session.id, [])
        self.store.save_session(session)
        return session

    def list_evidence_records(self, session_id: str) -> list[dict[str, object]]:
        session = self.get_session(session_id)
        context = self.store.load_geospatial_session_context(session.geospatial_context_id)
        if context is None:
            return []
        return self.store.list_geospatial_evidence_records(context.id)

    async def create_session(self) -> Session:
        now = datetime.now(UTC)
        session_id = f'session-{uuid4().hex[:8]}'
        workspace = self.workspace_manager.create_session_workspace(session_id)
        title = f'新建会话 {len(self.store.list_sessions()) + 1}'
        session = Session(
            id=session_id,
            title=title,
            status='idle',
            created_at=now,
            updated_at=now,
            workspace_path=str(workspace),
            attached_data_directories=self._default_attached_data_directories(),
        )
        self.sessions[session.id] = session
        self.subscribers.setdefault(session.id, [])
        self.store.save_session(session)
        return session

    async def rename_session(self, session_id: str, title: str) -> Session:
        session = self.get_session(session_id)
        self._ensure_session_writable(session)
        session.title = title
        session.updated_at = datetime.now(UTC)
        self.store.rename_session(session_id, title)
        self.store.save_session(session)
        await self._publish(session.id, 'session.title', {'id': session.id, 'title': session.title})
        return session

    async def delete_session(self, session_id: str) -> None:
        self.get_session(session_id)
        await self._abort_runtime_session(session_id)
        await self._cancel_run(session_id, reason='delete')
        self.store.delete_session(session_id)
        self.sessions.pop(session_id, None)
        self.subscribers.pop(session_id, None)

    async def open_workspace(self, session_id: str) -> None:
        session = self.get_session(session_id)
        self._ensure_session_writable(session)
        if session.workspace_path is None:
            raise HTTPException(status_code=404, detail='Workspace not found')
        await self.workspace_manager.open_workspace(session.workspace_path)

    def resolve_artifact_path(self, session_id: str, artifact_id: str) -> Path:
        session = self.get_session(session_id)
        self._ensure_session_writable(session)
        if session.workspace_path is None:
            raise HTTPException(status_code=404, detail='Workspace not found')
        artifact = next((item for item in session.artifacts if item.id == artifact_id), None)
        if artifact is None:
            raise HTTPException(status_code=404, detail='Artifact not found')
        workspace_path = Path(session.workspace_path).expanduser().resolve()
        raw_path = Path(artifact.path).expanduser()
        artifact_path = raw_path if raw_path.is_absolute() else workspace_path / raw_path
        resolved_artifact_path = artifact_path.resolve()
        if not (resolved_artifact_path == workspace_path or resolved_artifact_path.is_relative_to(workspace_path)):
            raise HTTPException(status_code=400, detail='Artifact path is outside the workspace')
        if not resolved_artifact_path.exists():
            raise HTTPException(status_code=404, detail='Artifact file not found')
        return resolved_artifact_path

    async def open_artifact(self, session_id: str, artifact_id: str) -> None:
        artifact_path = self.resolve_artifact_path(session_id, artifact_id)
        await self.workspace_manager.open_workspace(str(artifact_path))

    async def open_data_directory(self, path: str) -> None:
        target = Path(path).expanduser().resolve()
        if not target.exists() or not target.is_dir():
            raise HTTPException(status_code=404, detail='Directory not found')
        await self.workspace_manager.open_workspace(str(target))

    async def submit_message(self, session_id: str, text: str) -> Question | None:
        session = self.get_session(session_id)
        self._ensure_session_writable(session)
        await self._abort_runtime_session(session_id)
        await self._cancel_run(session_id, reason='replace')

        now = datetime.now(UTC)
        session.status = 'running'
        session.updated_at = now
        session.timeline.append(
            TimelineEntry(
                id=f'timeline-{uuid4().hex[:8]}',
                kind='message',
                text=text,
                created_at=now,
            )
        )
        session.messages.append(
            ChatMessage(
                id=f'message-{uuid4().hex[:8]}',
                role='user',
                agent='geo',
                created_at=now,
                parts=[ChatMessagePart(type='text', text=text)],
            )
        )
        session.plan = []
        session.geospatial_task = None
        session.verification = []
        session.question = None
        self._sync_geospatial_context(session, prompt=text, answer=None, reset_runtime_state=True)

        session.timeline.append(
            TimelineEntry(
                id=f'timeline-{uuid4().hex[:8]}',
                kind='status',
                text='请求已发送到真实智能体运行时，等待模型规划下一步。',
                created_at=now,
            )
        )
        self.store.save_session(session)
        await self._publish_standard_updates(session)

        try:
            await self.runtime_client.start()
        except Exception as exc:
            session.status = 'failed'
            session.updated_at = datetime.now(UTC)
            session.timeline.append(
                TimelineEntry(
                    id=f'timeline-{uuid4().hex[:8]}',
                    kind='status',
                    text=f'OpenCode 运行时启动失败：{exc}',
                    created_at=session.updated_at,
                )
            )
            await self._record_session_issue(
                session,
                issue_type='runtime_crash',
                severity='error',
                source='opencode',
                title='OpenCode 运行时启动失败',
                detail=str(exc),
                recoverable=True,
                publish=False,
            )
            self.store.save_session(session)
            await self._publish_standard_updates(session)
            return None
        if not self.runtime_client.is_ready:
            status = self.runtime_client.status()
            session.status = 'failed'
            session.updated_at = datetime.now(UTC)
            session.timeline.append(
                TimelineEntry(
                    id=f'timeline-{uuid4().hex[:8]}',
                    kind='status',
                    text=status.detail or '真实智能体运行时未就绪。',
                    created_at=session.updated_at,
                )
            )
            await self._record_session_issue(
                session,
                issue_type='runtime_error',
                severity='error',
                source='opencode',
                title='OpenCode 运行时未就绪',
                detail=status.detail or '真实智能体运行时未就绪。',
                recoverable=True,
                publish=False,
            )
            self.store.save_session(session)
            await self._publish_standard_updates(session)
            return None

        self._start_run(session_id, prompt=text, answer=None)
        for _ in range(5):
            await asyncio.sleep(0)
            current = self.get_session(session_id)
            if current.status in {'waiting_for_input', 'completed', 'failed'}:
                break
        return self.get_session(session_id).question

    async def answer_question(self, session_id: str, question_id: str, answer: str | None = None, answers: list[str] | None = None) -> None:
        session = self.get_session(session_id)
        self._ensure_session_writable(session)
        if session.question is None or session.question.id != question_id:
            raise HTTPException(status_code=404, detail='Question not found')

        current_question = session.question
        prompt = session.geospatial_task.prompt if session.geospatial_task else ''
        answer_list = [item.strip() for item in (answers or []) if item.strip()]
        if not answer_list and answer is not None and answer.strip():
            answer_list = [answer.strip()]
        display_answer = self._display_answer_for_question(current_question, answer_list)
        session.updated_at = datetime.now(UTC)
        session.status = 'running'
        session.question = None
        session.timeline.append(
            TimelineEntry(
                id=f'timeline-{uuid4().hex[:8]}',
                kind='question',
                text=f'用户回答：{display_answer}',
                created_at=session.updated_at,
            )
        )
        session.messages.append(
            ChatMessage(
                id=f'message-{uuid4().hex[:8]}',
                role='user',
                agent='geo',
                created_at=session.updated_at,
                parts=[ChatMessagePart(type='text', text=display_answer, state={'history_excluded': True, 'question_id': question_id, 'question_answers': answer_list})],
            )
        )
        self.store.save_session(session)
        await self._publish(session.id, 'session.question', None)
        await self._publish_standard_updates(session)
        self._start_run(session_id, prompt=prompt, answer=None, question_id=question_id, question_answers=answer_list)
        await asyncio.sleep(0)

    async def interrupt_session(self, session_id: str) -> None:
        session = self.get_session(session_id)
        self._ensure_session_writable(session)
        had_active_run = session_id in self.active_runs
        abort_failure = await self._abort_runtime_session(session_id)
        await self._cancel_run(session_id, reason='interrupt')
        if session.status == 'running':
            await self._finalize_interrupted_run(session, abort_failure=abort_failure)

    async def subscribe(self, session_id: str) -> asyncio.Queue[EventEnvelope]:
        self.get_session(session_id)
        queue: asyncio.Queue[EventEnvelope] = asyncio.Queue()
        self.subscribers.setdefault(session_id, []).append(queue)
        return queue

    def unsubscribe(self, session_id: str, queue: asyncio.Queue[EventEnvelope]) -> None:
        subscribers = self.subscribers.get(session_id, [])
        if queue in subscribers:
            subscribers.remove(queue)

    async def wait_for_run(self, session_id: str) -> None:
        task = self.active_runs.get(session_id)
        if task is not None:
            await asyncio.shield(task)

    async def shutdown(self) -> None:
        for session_id in list(self.active_runs):
            await self._abort_runtime_session(session_id)
            await self._cancel_run(session_id, reason='shutdown')

    async def update_attached_data_directories(self, session_id: str, items: list[dict[str, object]]) -> Session:
        session = self.get_session(session_id)
        self._ensure_session_writable(session)
        session.attached_data_directories = self._normalize_attached_data_directories(items)
        session.updated_at = datetime.now(UTC)
        self.store.save_session(session)
        await self._publish(session.id, 'session.attached_data_directories', [item.model_dump(mode='json') for item in session.attached_data_directories])
        return session

    async def browse_data_directories(self, path: str | None) -> dict[str, object]:
        current = Path(path).expanduser() if path else Path.cwd().resolve()
        current = current.resolve()
        if not current.exists() or not current.is_dir():
            raise HTTPException(status_code=404, detail='Directory not found')

        entries = [
            {
                'name': child.name,
                'path': str(child),
                'is_dir': True,
            }
            for child in sorted(current.iterdir(), key=lambda item: item.name.lower())
            if child.is_dir()
        ]

        parent_path = None if current.parent == current else str(current.parent)
        return {
            'current_path': str(current),
            'parent_path': parent_path,
            'home_path': str(Path.home()),
            'cwd_path': str(Path.cwd().resolve()),
            'entries': entries,
        }

    def list_recent_data_directories(self) -> dict[str, object]:
        deduplicated: list[dict[str, object]] = []
        seen_paths: set[str] = set()
        for item in self._default_attached_data_directories():
            if item.path in seen_paths:
                continue
            seen_paths.add(item.path)
            deduplicated.append(item.model_dump(mode='json'))
        for session in self.store.list_sessions():
            for item in session.attached_data_directories:
                if item.path in seen_paths:
                    continue
                seen_paths.add(item.path)
                deduplicated.append(item.model_dump(mode='json'))
        return {'items': deduplicated}

    async def _publish(self, session_id: str, event_type: str, payload: object) -> None:
        envelope = EventEnvelope(type=event_type, payload=payload)
        for queue in self.subscribers.get(session_id, []):
            await queue.put(envelope)

    def _ensure_session_writable(self, session: Session) -> None:
        if session.read_only:
            raise HTTPException(status_code=409, detail='Imported session archives are read-only')

    async def _abort_runtime_session(self, session_id: str) -> str | None:
        session = self.get_session(session_id)
        runtime_session_id = session.runtime_session_id
        if runtime_session_id is None:
            active_request = self.active_runtime_requests.get(session_id)
            runtime_session_id = active_request.runtime_session_id if active_request is not None else None
        if runtime_session_id is None:
            return None
        abort_session = getattr(self.runtime_client, 'abort_session', None)
        if not callable(abort_session):
            return None
        try:
            await asyncio.wait_for(abort_session(runtime_session_id), timeout=5)
        except Exception as exc:
            return str(exc)
        return None

    def _start_run(
        self,
        session_id: str,
        *,
        prompt: str,
        answer: str | None,
        question_id: str | None = None,
        question_answers: list[str] | None = None,
    ) -> None:
        task = asyncio.create_task(
            self._execute_run(
                session_id,
                prompt=prompt,
                answer=answer,
                question_id=question_id,
                question_answers=question_answers,
            )
        )
        self.active_runs[session_id] = task

        def _cleanup(_task: asyncio.Task[None]) -> None:
            if self.active_runs.get(session_id) is _task:
                self.active_runs.pop(session_id, None)
            self.run_cancellation_reasons.pop(session_id, None)

        task.add_done_callback(_cleanup)

    async def _cancel_run(self, session_id: str, *, reason: RunCancellationReason) -> None:
        task = self.active_runs.pop(session_id, None)
        if task is None:
            return
        self.run_cancellation_reasons[session_id] = reason
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            return
        finally:
            self.run_cancellation_reasons.pop(session_id, None)

    async def _execute_run(
        self,
        session_id: str,
        *,
        prompt: str,
        answer: str | None,
        question_id: str | None,
        question_answers: list[str] | None,
    ) -> None:
        session = self.get_session(session_id)
        workspace_dir = Path(session.workspace_path) if session.workspace_path else None
        request = RuntimeSessionRequest(
            session_id=session.id,
            prompt=prompt,
            workspace_path=workspace_dir or Path('.'),
            answer=answer,
            question_request_id=question_id,
            question_answers=question_answers,
            geospatial_context_id=session.geospatial_context_id,
            runtime_session_id=session.runtime_session_id,
            attached_data_directories=[item.model_dump(mode='json') for item in session.attached_data_directories],
            processed_tool_part_ids=self._processed_tool_part_keys(session.messages),
        )
        self.active_runtime_requests[session_id] = request

        try:
            session.updated_at = datetime.now(UTC)
            self.store.save_session(session)
            await self._publish_standard_updates(session)

            result = await self.runtime_client.run_session(
                request,
                lambda envelope: self._handle_runtime_event(session, envelope),
            )
            runtime_session_id = getattr(result, 'runtime_session_id', None)
            trace_path = getattr(result, 'trace_path', None)
            if isinstance(result, dict):
                runtime_session_id = result.get('runtime_session_id', runtime_session_id)
                trace_path = result.get('trace_path', trace_path)
            session.runtime_session_id = runtime_session_id or session.runtime_session_id
            session.runtime_trace_path = trace_path or session.runtime_trace_path
            session.updated_at = datetime.now(UTC)
            self._sync_geospatial_context(session, prompt=prompt, answer=answer, reset_runtime_state=False)
            self.store.save_session(session)
        except asyncio.CancelledError:
            self.run_cancellation_reasons.pop(session_id, None)
            raise
        except Exception as exc:
            session.status = 'failed'
            session.updated_at = datetime.now(UTC)
            if session.geospatial_task is not None:
                session.geospatial_task.stage = 'failed'
                session.geospatial_task.operator.stage = 'failed'
            session.verification.append(
                self._verification_entry(
                    code='runtime_execution_failed',
                    title='运行时执行失败',
                    status='failed',
                    detail=str(exc),
                )
            )
            session.timeline.append(
                TimelineEntry(
                    id=f'timeline-{uuid4().hex[:8]}',
                    kind='status',
                    text=f'运行失败：{exc}',
                    created_at=session.updated_at,
                )
            )
            issue_type: SessionIssueType = 'runtime_crash' if self.runtime_client.status().status == 'stopped' else 'runtime_error'
            source: SessionIssueSource = 'opencode' if issue_type == 'runtime_crash' else 'runtime'
            await self._record_session_issue(
                session,
                issue_type=issue_type,
                severity='error',
                source=source,
                title='OpenCode 运行时异常退出' if issue_type == 'runtime_crash' else '运行时执行失败',
                detail=str(exc),
                runtime_session_id=session.runtime_session_id or request.runtime_session_id,
                trace_path=session.runtime_trace_path,
                recoverable=True,
                publish=False,
            )
            self.store.save_session(session)
            await self._publish_standard_updates(session)
        finally:
            self.active_runtime_requests.pop(session_id, None)

    async def _publish_standard_updates(self, session: Session) -> None:
        await self._publish(session.id, 'session.status', {'status': session.status})
        await self._publish(session.id, 'session.messages', [message.model_dump(mode='json') for message in session.messages])
        await self._publish(session.id, 'session.timeline', [item.model_dump(mode='json') for item in session.timeline])
        await self._publish(session.id, 'session.plan', [item.model_dump() for item in session.plan])
        await self._publish(session.id, 'session.plan_groups', [group.model_dump(mode='json') for group in session.plan_groups])
        await self._publish(session.id, 'session.issues', [issue.model_dump(mode='json') for issue in session.issues])
        if session.geospatial_task is not None:
            await self._publish(session.id, 'session.geospatial_task', session.geospatial_task.model_dump())
        await self._publish(session.id, 'session.verification', [item.model_dump() for item in session.verification])
        await self._publish(session.id, 'session.attached_data_directories', [item.model_dump(mode='json') for item in session.attached_data_directories])

    async def _handle_runtime_event(self, session: Session, envelope: EventEnvelope) -> None:
        inline_message: ChatMessage | None = None
        payload_for_publish: object = envelope.payload
        event_type_for_publish = envelope.type
        if envelope.type == 'session.status':
            payload = envelope.payload if isinstance(envelope.payload, dict) else {}
            session.status = payload.get('status', session.status)
        elif envelope.type == 'session.plan':
            session.plan = [PlanEntry.model_validate(item) for item in envelope.payload]
            inline_message = self._append_inline_message(
                session,
                agent='geo',
                part=ChatMessagePart(type='todo', state={'entries': [item.model_dump(mode='json') for item in session.plan]}),
            )
        elif envelope.type == 'session.plan_group':
            plan_group = PlanGroup.model_validate(envelope.payload)
            session.plan_groups = self._upsert_plan_group(session.plan_groups, plan_group)
            session.plan = self._primary_plan_from_groups(session.plan_groups)
            payload_for_publish = [group.model_dump(mode='json') for group in session.plan_groups]
            event_type_for_publish = 'session.plan_groups'
        elif envelope.type == 'session.plan_groups':
            session.plan_groups = [PlanGroup.model_validate(item) for item in envelope.payload]
            session.plan = self._primary_plan_from_groups(session.plan_groups)
            payload_for_publish = [group.model_dump(mode='json') for group in session.plan_groups]
        elif envelope.type == 'session.messages':
            inline_messages = [message for message in session.messages if message.id.startswith('inline-')]
            runtime_messages = [ChatMessage.model_validate(item) for item in envelope.payload]
            session.messages = runtime_messages + inline_messages
        elif envelope.type == 'session.message_delta':
            message = ChatMessage.model_validate(envelope.payload)
            session.messages = self._upsert_message(session.messages, message)
        elif envelope.type == 'session.issue':
            issue = SessionIssue.model_validate(envelope.payload)
            inline_message = self._append_issue(session, issue)
            payload_for_publish = issue.model_dump(mode='json')
        elif envelope.type == 'session.question':
            session.question = Question.model_validate(envelope.payload) if envelope.payload else None
            if session.question is not None:
                inline_message = self._append_inline_message(
                    session,
                    agent='geo',
                    part=ChatMessagePart(
                        type='question',
                        text=session.question.prompt,
                        state=session.question.model_dump(mode='json'),
                    ),
                )
        elif envelope.type == 'session.geospatial_task':
            from app.models import GeospatialTask

            session.geospatial_task = GeospatialTask.model_validate(envelope.payload)
            self._sync_geospatial_context(session, reset_runtime_state=False)
        elif envelope.type == 'session.verification':
            from app.models import VerificationEntry

            session.verification = [VerificationEntry.model_validate(item) for item in envelope.payload]
            self._sync_geospatial_context(session, reset_runtime_state=False)
            if session.verification:
                inline_message = self._append_inline_message(
                    session,
                    agent='skeptical-review',
                    part=ChatMessagePart(
                        type='verification',
                        state={'entries': [item.model_dump(mode='json') for item in session.verification]},
                    ),
                )
        elif envelope.type == 'session.artifact':
            artifact = Artifact.model_validate(envelope.payload)
            session.artifacts = upsert_artifact_by_path(session.artifacts, artifact)
            self._sync_geospatial_context(
                session,
                manifest_path=artifact.path if artifact.kind == 'manifest' else None,
                reset_runtime_state=False,
            )
            session.timeline.append(
                TimelineEntry(
                    id=f'timeline-{uuid4().hex[:8]}',
                    kind='artifact',
                    text=artifact.title,
                    created_at=datetime.now(UTC),
                )
            )
        elif envelope.type == 'session.timeline':
            session.timeline = [TimelineEntry.model_validate(item) for item in envelope.payload]
        elif envelope.type == 'session.timeline_entry':
            timeline_entry = TimelineEntry.model_validate(envelope.payload)
            session.timeline = self._upsert_timeline_entry(session.timeline, timeline_entry)
        elif envelope.type == 'session.title':
            if isinstance(envelope.payload, dict) and 'title' in envelope.payload:
                session.title = str(envelope.payload['title'])
                runtime_session_id = envelope.payload.get('runtime_session_id')
                if isinstance(runtime_session_id, str):
                    session.runtime_session_id = runtime_session_id
                payload_for_publish = {
                    'id': session.id,
                    'title': session.title,
                    'runtime_session_id': session.runtime_session_id,
                }
        elif envelope.type == 'session.runtime_session':
            if isinstance(envelope.payload, dict):
                runtime_session_id = envelope.payload.get('runtime_session_id')
                if isinstance(runtime_session_id, str):
                    session.runtime_session_id = runtime_session_id
                    self._sync_geospatial_context(session, reset_runtime_state=False)

        session.updated_at = datetime.now(UTC)
        self.store.save_session(session)
        if envelope.type == 'session.messages':
            await self._publish(session.id, 'session.messages', [message.model_dump(mode='json') for message in session.messages])
        else:
            await self._publish(session.id, event_type_for_publish, payload_for_publish)
        if inline_message is not None:
            await self._publish(session.id, 'session.message_delta', inline_message.model_dump(mode='json'))

    def _upsert_message(self, messages: list[ChatMessage], message: ChatMessage) -> list[ChatMessage]:
        for index, existing in enumerate(messages):
            if existing.id == message.id:
                updated = list(messages)
                updated[index] = message
                return updated
        return [*messages, message]

    async def _recover_runtime_messages(self, session: Session) -> None:
        if not self._should_recover_runtime_messages(session):
            return
        try:
            runtime_payload = await asyncio.wait_for(
                self.runtime_client.fetch_session_messages(str(session.runtime_session_id)),
                timeout=3,
            )
        except Exception:
            return
        runtime_messages = [ChatMessage.model_validate(item) for item in runtime_payload]
        if not runtime_messages:
            return
        runtime_messages = await self._recover_subtask_messages(runtime_messages)
        inline_messages = [message for message in session.messages if message.id.startswith('inline-')]
        inline_messages = [
            message for message in inline_messages
            if message.id not in {runtime_message.id for runtime_message in runtime_messages}
            and not self._is_legacy_inline_artifact_message(message)
        ]
        current_runtime_messages = [message for message in session.messages if not message.id.startswith('inline-')]
        if [message.model_dump(mode='json') for message in current_runtime_messages] == [message.model_dump(mode='json') for message in runtime_messages]:
            return
        session.messages = runtime_messages + inline_messages
        session.updated_at = datetime.now(UTC)
        self.store.save_session(session)

    def _recover_plan_groups_from_messages(self, session: Session) -> None:
        recovered_groups = self._plan_groups_from_messages(session.messages)
        if not recovered_groups:
            return
        plan_groups = list(session.plan_groups)
        for group in recovered_groups:
            plan_groups = self._upsert_plan_group(plan_groups, group)
        if [group.model_dump(mode='json') for group in plan_groups] == [group.model_dump(mode='json') for group in session.plan_groups]:
            return
        session.plan_groups = plan_groups
        session.plan = self._primary_plan_from_groups(session.plan_groups)
        session.updated_at = datetime.now(UTC)
        self.store.save_session(session)

    def _recover_evidence_timeline_from_store(self, session: Session) -> None:
        context = self.store.load_geospatial_session_context(session.geospatial_context_id)
        if context is None:
            return

        updated = False
        for record in self.store.list_geospatial_evidence_records(context.id):
            timeline_entry = self._timeline_entry_from_evidence_record(record)
            if timeline_entry is None:
                continue
            next_timeline = self._upsert_timeline_entry(session.timeline, timeline_entry)
            if next_timeline != session.timeline:
                session.timeline = next_timeline
                updated = True

        if updated:
            session.updated_at = datetime.now(UTC)
            self.store.save_session(session)

    def _timeline_entry_from_evidence_record(self, record: dict[str, object]) -> TimelineEntry | None:
        record_type = str(record.get('record_type') or '')
        if record_type == 'artifact' or not record_type:
            return None
        record_id = str(record.get('id') or uuid4().hex[:8])
        title = str(record.get('title') or '运行证据')
        description = record.get('description')
        category = record.get('category')
        data = record.get('data')
        provenance = record.get('provenance')
        created_at = record.get('created_at') or datetime.now(UTC).isoformat()
        return TimelineEntry.model_validate({
            'id': f'evidence-{record_id}',
            'kind': 'evidence',
            'text': title,
            'title': title,
            'detail': str(description) if description is not None else None,
            'record_type': record_type,
            'category': str(category) if category is not None else None,
            'evidence_record_id': record_id,
            'created_at': created_at,
            'data': data if isinstance(data, dict) else {},
            'provenance': provenance if isinstance(provenance, dict) else {},
        })

    def _plan_groups_from_messages(self, messages: list[ChatMessage]) -> list[PlanGroup]:
        identities = load_agent_identity_map()
        groups: list[PlanGroup] = []
        for message in messages:
            for part in message.parts:
                if part.type != 'tool' or canonical_tool_name(part.tool) != 'update_todos':
                    continue
                if self._todo_tool_output_is_error(part):
                    continue
                entries = self._plan_entries_from_todo_part(part)
                if not entries:
                    continue
                agent = message.agent or 'geo'
                identity = identities.get(agent)
                groups = self._upsert_plan_group(
                    groups,
                    PlanGroup(
                        id=agent,
                        agent=agent,
                        label=identity.label if identity is not None else agent,
                        entries=entries,
                        updated_at=message.created_at,
                    ),
                )
        return groups

    def _todo_tool_output_is_error(self, part: ChatMessagePart) -> bool:
        output = (part.state or {}).get('output')
        if not isinstance(output, str):
            return False
        return output.lstrip().startswith('<error')

    def _plan_entries_from_todo_part(self, part: ChatMessagePart) -> list[PlanEntry]:
        state = part.state or {}
        input_payload = state.get('input')
        if not isinstance(input_payload, dict):
            return []
        raw_entries = input_payload.get('entries')
        if not isinstance(raw_entries, list):
            raw_entries = input_payload.get('todos')
        if not isinstance(raw_entries, list):
            return []
        allowed_statuses = {'pending', 'in_progress', 'completed', 'blocked'}
        entries: list[PlanEntry] = []
        for index, entry in enumerate(raw_entries, start=1):
            if not isinstance(entry, dict):
                continue
            raw_label = entry.get('content') if isinstance(entry.get('content'), str) else entry.get('label')
            if not isinstance(raw_label, str) or not raw_label.strip():
                continue
            raw_status = entry.get('status')
            status = raw_status if raw_status in allowed_statuses else 'pending'
            raw_id = entry.get('id')
            entry_id = raw_id.strip() if isinstance(raw_id, str) and raw_id.strip() else f'plan-{index}'
            entries.append(PlanEntry(id=entry_id, label=raw_label.strip(), status=status))
        return entries

    def _should_recover_runtime_messages(self, session: Session) -> bool:
        if session.runtime_session_id is None or session.status == 'running':
            return False
        if any(
            message.role == 'assistant' and not message.parts and not message.id.startswith('inline-')
            for message in session.messages
        ):
            return True
        task_session_ids = {
            task_session_id
            for message in session.messages
            for part in message.parts
            if (task_session_id := self._task_session_id_from_part(part)) is not None
        }
        return any(
            not any(message.id == f'inline-subtask-{task_session_id}' for message in session.messages)
            for task_session_id in task_session_ids
        )

    async def _recover_subtask_messages(self, runtime_messages: list[ChatMessage]) -> list[ChatMessage]:
        recovered: list[ChatMessage] = []
        seen_task_session_ids: set[str] = set()
        for message in runtime_messages:
            recovered.append(message)
            for part in message.parts:
                task_session_id = self._task_session_id_from_part(part)
                if task_session_id is None or task_session_id in seen_task_session_ids:
                    continue
                seen_task_session_ids.add(task_session_id)
                child_messages = await self._fetch_child_runtime_messages(task_session_id)
                if not child_messages:
                    continue
                recovered.append(self._subtask_inline_message(parent_message=message, part=part, task_session_id=task_session_id, child_messages=child_messages))
                recovered.extend(
                    child_message.model_copy(update={'id': f'inline-{child_message.id}-{task_session_id}'})
                    for child_message in child_messages
                    if child_message.role != 'user'
                )
        return recovered

    async def _fetch_child_runtime_messages(self, task_session_id: str) -> list[ChatMessage]:
        try:
            payload = await asyncio.wait_for(self.runtime_client.fetch_session_messages(task_session_id), timeout=3)
        except Exception:
            return []
        return [ChatMessage.model_validate(item) for item in payload]

    def _subtask_inline_message(
        self,
        *,
        parent_message: ChatMessage,
        part: ChatMessagePart,
        task_session_id: str,
        child_messages: list[ChatMessage],
    ) -> ChatMessage:
        input_payload = part.state.get('input') if isinstance(part.state, dict) else None
        input_state = input_payload if isinstance(input_payload, dict) else {}
        first_child_user = next((message for message in child_messages if message.role == 'user'), None)
        first_child_assistant = next((message for message in child_messages if message.role == 'assistant'), None)
        prompt = input_state.get('prompt')
        if not isinstance(prompt, str) or not prompt.strip():
            prompt = self._first_text_part(first_child_user)
        description = input_state.get('description')
        child_agent = input_state.get('subagent_type')
        if not isinstance(child_agent, str) or not child_agent.strip():
            child_agent = (first_child_assistant or first_child_user or parent_message).agent
        created_at = (first_child_user or first_child_assistant or parent_message).created_at
        return ChatMessage(
            id=f'inline-subtask-{task_session_id}',
            role='system',
            agent=None,
            created_at=created_at,
            parts=[
                ChatMessagePart(
                    type='subtask',
                    state={
                        'task_session_id': task_session_id,
                        'parent_agent': parent_message.agent,
                        'child_agent': child_agent,
                        'description': description if isinstance(description, str) else None,
                        'prompt': prompt,
                    },
                )
            ],
        )

    def _cleanup_session_artifact_state(self, session: Session) -> None:
        updated = False
        deduplicated_artifacts: list[Artifact] = []
        for artifact in session.artifacts:
            deduplicated_artifacts = upsert_artifact_by_path(deduplicated_artifacts, artifact)
        if [artifact.model_dump(mode='json') for artifact in deduplicated_artifacts] != [artifact.model_dump(mode='json') for artifact in session.artifacts]:
            session.artifacts = deduplicated_artifacts
            updated = True

        filtered_messages = [
            message for message in session.messages
            if not self._is_legacy_inline_artifact_message(message)
        ]
        if [message.model_dump(mode='json') for message in filtered_messages] != [message.model_dump(mode='json') for message in session.messages]:
            session.messages = filtered_messages
            updated = True

        if updated:
            session.updated_at = datetime.now(UTC)
            self.store.save_session(session)

    def _is_legacy_inline_artifact_message(self, message: ChatMessage) -> bool:
        return message.id.startswith('inline-') and any(part.type == 'artifact' for part in message.parts)

    def _task_session_id_from_part(self, part: ChatMessagePart) -> str | None:
        if part.tool != 'task' or not isinstance(part.state, dict):
            return None
        output_session_id = self._task_session_id_from_output(part.state.get('output'))
        if output_session_id:
            return output_session_id
        metadata = part.state.get('metadata')
        if isinstance(metadata, dict):
            metadata_session_id = self._first_task_session_id(metadata)
            if metadata_session_id:
                return metadata_session_id
        return self._first_task_session_id(part.state)

    def _task_session_id_from_output(self, output: object) -> str | None:
        if isinstance(output, dict):
            return self._first_task_session_id(output)
        if not isinstance(output, str):
            return None
        for line in output.splitlines():
            stripped = line.strip()
            if not stripped.startswith('task_id:'):
                continue
            session_id = stripped.removeprefix('task_id:').strip().split(' ', maxsplit=1)[0]
            return session_id or None
        return None

    def _first_task_session_id(self, payload: dict[str, object]) -> str | None:
        for key in ('task_id', 'taskId', 'session_id', 'sessionId', 'sessionID'):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _first_text_part(self, message: ChatMessage | None) -> str | None:
        if message is None:
            return None
        return next((part.text for part in message.parts if part.type == 'text' and part.text), None)

    def _upsert_issue(self, issues: list[SessionIssue], issue: SessionIssue) -> list[SessionIssue]:
        for index, existing in enumerate(issues):
            if existing.id == issue.id:
                updated = list(issues)
                updated[index] = issue
                return updated
        return [*issues, issue]

    def _upsert_timeline_entry(self, entries: list[TimelineEntry], entry: TimelineEntry) -> list[TimelineEntry]:
        for index, existing in enumerate(entries):
            if existing.id == entry.id:
                updated = list(entries)
                updated[index] = entry
                return updated
        return [*entries, entry]

    def _processed_tool_part_keys(self, messages: list[ChatMessage]) -> set[str]:
        return {
            self._tool_part_signature(message=message, part=part)
            for message in messages
            for part in message.parts
            if part.type == 'tool'
        }

    def _tool_part_signature(self, *, message: ChatMessage, part: ChatMessagePart) -> str:
        state = part.state or {}
        signature = {
            'message_id': message.id,
            'tool': part.tool or '',
            'input': state.get('input'),
            'output': state.get('output'),
        }
        return f'signature:{json.dumps(signature, ensure_ascii=False, sort_keys=True, default=str)}'

    def _upsert_plan_group(self, groups: list[PlanGroup], group: PlanGroup) -> list[PlanGroup]:
        for index, existing in enumerate(groups):
            if existing.agent == group.agent:
                updated = list(groups)
                updated[index] = group
                return updated
        return [*groups, group]

    def _primary_plan_from_groups(self, groups: list[PlanGroup]) -> list[PlanEntry]:
        if not groups:
            return []
        geo_group = next((group for group in groups if group.agent == 'geo'), None)
        return list((geo_group or groups[0]).entries)

    def _verification_entry(self, *, code: str, title: str, status: str, detail: str):
        from app.models import VerificationEntry

        return VerificationEntry(
            id=f'verification-{uuid4().hex[:8]}',
            code=code,
            title=title,
            status=status,
            detail=detail,
        )

    async def _finalize_interrupted_run(self, session: Session, *, abort_failure: str | None = None) -> None:
        session.status = 'idle'
        session.updated_at = datetime.now(UTC)
        detail = '用户已中断当前任务，保留已有过程记录。'
        if abort_failure:
            detail = f'{detail} OpenCode abort 调用未确认成功：{abort_failure}'
        session.timeline.append(
            TimelineEntry(
                id=f'timeline-{uuid4().hex[:8]}',
                kind='status',
                text=detail,
                created_at=session.updated_at,
            )
        )
        await self._record_session_issue(
            session,
            issue_type='user_interrupt',
            severity='warning' if abort_failure else 'info',
            source='backend',
            title='用户已中断当前任务',
            detail=detail,
            runtime_session_id=session.runtime_session_id,
            trace_path=session.runtime_trace_path,
            recoverable=True,
            publish=False,
        )
        self.store.save_session(session)
        await self._publish_standard_updates(session)

    async def _record_session_issue(
        self,
        session: Session,
        *,
        issue_type: SessionIssueType,
        severity: SessionIssueSeverity,
        source: SessionIssueSource,
        title: str,
        detail: str,
        runtime_session_id: str | None = None,
        trace_path: str | None = None,
        recoverable: bool | None = None,
        publish: bool,
    ) -> SessionIssue:
        issue = SessionIssue(
            id=f'issue-{uuid4().hex[:8]}',
            type=issue_type,
            severity=severity,
            source=source,
            title=title,
            detail=detail,
            created_at=datetime.now(UTC),
            runtime_session_id=runtime_session_id,
            trace_path=trace_path,
            recoverable=recoverable,
        )
        inline_message = self._append_issue(session, issue)
        if publish:
            self.store.save_session(session)
            await self._publish(session.id, 'session.issue', issue.model_dump(mode='json'))
            await self._publish(session.id, 'session.issues', [item.model_dump(mode='json') for item in session.issues])
            if inline_message is not None:
                await self._publish(session.id, 'session.message_delta', inline_message.model_dump(mode='json'))
        return issue

    def _append_issue(self, session: Session, issue: SessionIssue) -> ChatMessage | None:
        session.issues = self._upsert_issue(session.issues, issue)
        message_id = f'inline-issue-{issue.id}'
        if any(message.id == message_id for message in session.messages):
            return None
        message = ChatMessage(
            id=message_id,
            role='system',
            agent=None,
            created_at=issue.created_at,
            parts=[
                ChatMessagePart(
                    type='issue',
                    text=issue.title,
                    state=issue.model_dump(mode='json'),
                )
            ],
        )
        session.messages.append(message)
        return message

    def _append_inline_message(self, session: Session, *, agent: str, part: ChatMessagePart) -> ChatMessage:
        created_at = datetime.now(UTC)
        message = ChatMessage(
            id=f'inline-{uuid4().hex[:8]}',
            role='system',
            agent=agent,
            created_at=created_at,
            parts=[part],
        )
        session.messages.append(message)
        return message

    def _sync_geospatial_context(
        self,
        session: Session,
        *,
        prompt: str | None = None,
        answer: str | None = None,
        request_snapshot_path: str | None = None,
        manifest_path: str | None = None,
        reset_runtime_state: bool,
    ) -> GeospatialSessionContext:
        existing = self.store.load_geospatial_session_context(session.geospatial_context_id)
        if session.geospatial_context_id is None:
            session.geospatial_context_id = f'context-{uuid4().hex[:8]}'
        context = GeospatialSessionContext(
            id=session.geospatial_context_id,
            session_id=session.id,
            runtime_session_id=session.runtime_session_id,
            mcp_session_id=None if reset_runtime_state else (existing.mcp_session_id if existing is not None else None),
            prompt=prompt if prompt is not None else (existing.prompt if existing is not None else (session.geospatial_task.prompt if session.geospatial_task is not None else '')),
            answer=answer if answer is not None else (existing.answer if existing is not None else None),
            workspace_path=session.workspace_path or (existing.workspace_path if existing is not None else ''),
            request_snapshot_path=request_snapshot_path if request_snapshot_path is not None else (existing.request_snapshot_path if existing is not None else None),
            prepared_input_path=None if reset_runtime_state else (existing.prepared_input_path if existing is not None else None),
            manifest_path=None if reset_runtime_state else (manifest_path if manifest_path is not None else (existing.manifest_path if existing is not None else None)),
            attached_data_directories=list(session.attached_data_directories),
            geospatial_task=None if reset_runtime_state else (session.geospatial_task if session.geospatial_task is not None else (existing.geospatial_task if existing is not None else None)),
            verification=[] if reset_runtime_state else (list(session.verification) if session.verification else (list(existing.verification) if existing is not None else [])),
            artifacts=list(session.artifacts) if session.artifacts else (list(existing.artifacts) if existing is not None else []),
            updated_at=datetime.now(UTC),
        )
        self.store.save_geospatial_session_context(context)
        return context

    def _normalize_attached_data_directories(self, items: list[dict[str, object]]) -> list[DataDirectoryAttachment]:
        normalized: list[DataDirectoryAttachment] = []
        for item in items:
            attachment = DataDirectoryAttachment.model_validate(item)
            candidate = attachment.model_copy(update={'path': str(Path(attachment.path).expanduser().resolve())})
            candidate_path = Path(candidate.path)
            next_items: list[DataDirectoryAttachment] = []
            skip_candidate = False
            for existing in normalized:
                existing_path = Path(existing.path)
                if existing_path == candidate_path or self._path_contains(existing_path, candidate_path):
                    next_items.append(existing)
                    skip_candidate = True
                    continue
                if self._path_contains(candidate_path, existing_path):
                    continue
                next_items.append(existing)
            if not skip_candidate:
                next_items.append(candidate)
            normalized = next_items
        return normalized

    def _path_contains(self, parent: Path, child: Path) -> bool:
        try:
            child.relative_to(parent)
        except ValueError:
            return False
        return True

    def _display_answer_for_question(self, question: Question, answers: list[str]) -> str:
        if not answers:
            return ''
        if len(answers) == 1 or not question.questions:
            return answers[0]
        lines: list[str] = []
        for index, value in enumerate(answers):
            item = question.questions[index] if index < len(question.questions) else None
            header = item.header if item is not None else f'问题 {index + 1}'
            lines.append(f'{header}：{value}')
        return '\n'.join(lines)

    def health_payload(self) -> dict[str, object]:
        provider_metadata: dict[str, object] = selected_model_provider_metadata(self.settings)
        provider_metadata['title_status'] = 'ready' if self.title_provider.is_configured else 'not_configured'
        return {
            'storage': self.store.status_payload(),
            'workspace': self.workspace_manager.status_payload(),
            'provider': provider_metadata,
            'default_data_directories': [item.model_dump(mode='json') for item in self._default_attached_data_directories()],
        }

    def _default_attached_data_directories(self) -> list[DataDirectoryAttachment]:
        data_root = Path('data').resolve()
        if data_root.exists():
            return [
                DataDirectoryAttachment(
                    id='attached-data-root',
                    path=str(data_root),
                    enabled=True,
                    label='默认数据目录',
                )
            ]
        return []
