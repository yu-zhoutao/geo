from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.config import Settings
from app.models import AnalysisType, Artifact, ChatMessage, ChatMessagePart, EventEnvelope, GeospatialPreprocessing, GeospatialSessionContext, GeospatialTask, OperatorMetadata, PlanEntry, Question, QuestionItem, QuestionOption, RuntimeProfile, RuntimeStatus, TaskStage, VerificationEntry
from app.services.sessions import SessionService


class StubTitleProvider:
    def __init__(self, title: str | None = None, *, fail: bool = False) -> None:
        self.title = title
        self.fail = fail

    @property
    def is_configured(self) -> bool:
        return True

    async def generate_session_title(self, prompt: str) -> str:
        if self.fail:
            raise RuntimeError('title generation failed')
        return self.title or f'Title for {prompt}'


class StubAgentRuntimeClient:
    def __init__(self, scripted_runs: list[list[EventEnvelope]], *, ready: bool = True, detail: str = 'sdk ready') -> None:
        self.scripted_runs = scripted_runs
        self.ready = ready
        self.detail = detail
        self.requests: list[dict[str, object]] = []

    @property
    def is_ready(self) -> bool:
        return self.ready

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    def status(self) -> RuntimeStatus:
        return RuntimeStatus(
            status='ready' if self.ready else 'stopped',
            label='openhands-runtime',
            detail=self.detail,
        )

    async def run_session(self, request, emit):
        self.requests.append({
            'session_id': request.session_id,
            'prompt': request.prompt,
            'answer': request.answer,
            'question_request_id': getattr(request, 'question_request_id', None),
            'question_answers': getattr(request, 'question_answers', None),
            'geospatial_context_id': request.geospatial_context_id,
            'runtime_session_id': request.runtime_session_id,
            'attached_data_directories': request.attached_data_directories,
        })
        for envelope in self.scripted_runs.pop(0):
            await asyncio.sleep(0)
            await emit(envelope)
        return {'runtime_session_id': 'runtime-session-1', 'trace_path': 'runtime/trace.jsonl'}


class MessageRecoveryRuntimeClient(StubAgentRuntimeClient):
    def __init__(self, messages_by_session: dict[str, list[dict[str, object]]]) -> None:
        super().__init__([])
        self.messages_by_session = messages_by_session
        self.fetches: list[str] = []

    async def fetch_session_messages(self, runtime_session_id: str) -> list[dict[str, object]]:
        self.fetches.append(runtime_session_id)
        return self.messages_by_session.get(runtime_session_id, [])


class StartFailingRuntimeClient(StubAgentRuntimeClient):
    def __init__(self) -> None:
        super().__init__([])

    async def start(self) -> None:
        raise RuntimeError('OpenCode server exited before becoming healthy')

    def status(self) -> RuntimeStatus:
        return RuntimeStatus(status='stopped', label='opencode-runtime', detail='OpenCode runtime is stopped.')


class FailingRunRuntimeClient(StubAgentRuntimeClient):
    def __init__(self, *, stopped: bool = False) -> None:
        super().__init__([])
        self.stopped = stopped

    def status(self) -> RuntimeStatus:
        return RuntimeStatus(
            status='stopped' if self.stopped else 'ready',
            label='opencode-runtime',
            detail='OpenCode runtime is stopped.' if self.stopped else 'OpenCode runtime is ready.',
        )

    async def run_session(self, request, emit):
        await emit(EventEnvelope(type='session.runtime_session', payload={'runtime_session_id': 'runtime-session-1'}))
        raise RuntimeError('runtime exploded')


class BlockingRuntimeClient(StubAgentRuntimeClient):
    def __init__(self) -> None:
        super().__init__([])
        self.run_started = asyncio.Event()
        self.run_cancelled = asyncio.Event()
        self.aborted_runtime_sessions: list[str] = []

    async def run_session(self, request, emit):
        self.requests.append({
            'session_id': request.session_id,
            'prompt': request.prompt,
            'answer': request.answer,
            'question_request_id': getattr(request, 'question_request_id', None),
            'question_answers': getattr(request, 'question_answers', None),
            'geospatial_context_id': request.geospatial_context_id,
            'runtime_session_id': request.runtime_session_id,
            'attached_data_directories': request.attached_data_directories,
        })
        await emit(EventEnvelope(type='session.runtime_session', payload={'runtime_session_id': 'runtime-session-1'}))
        self.run_started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            self.run_cancelled.set()
            raise

    async def abort_session(self, runtime_session_id: str) -> None:
        self.aborted_runtime_sessions.append(runtime_session_id)


class FinishingAbortRuntimeClient(StubAgentRuntimeClient):
    def __init__(self) -> None:
        super().__init__([])
        self.run_started = asyncio.Event()
        self.finish_run = asyncio.Event()
        self.run_finished = asyncio.Event()
        self.aborted_runtime_sessions: list[str] = []

    async def run_session(self, request, emit):
        await emit(EventEnvelope(type='session.runtime_session', payload={'runtime_session_id': 'runtime-session-1'}))
        self.run_started.set()
        await self.finish_run.wait()
        self.run_finished.set()
        return {'runtime_session_id': 'runtime-session-1', 'trace_path': 'runtime/trace.jsonl'}

    async def abort_session(self, runtime_session_id: str) -> None:
        self.aborted_runtime_sessions.append(runtime_session_id)
        self.finish_run.set()
        await asyncio.wait_for(self.run_finished.wait(), timeout=1)


class RequestTrackingRuntimeClient(StubAgentRuntimeClient):
    def __init__(self) -> None:
        super().__init__([])
        self.run_started = asyncio.Event()
        self.run_cancelled = asyncio.Event()
        self.aborted_runtime_sessions: list[str] = []

    async def run_session(self, request, emit):
        request.runtime_session_id = 'runtime-session-1'
        self.run_started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            self.run_cancelled.set()
            raise

    async def abort_session(self, runtime_session_id: str) -> None:
        self.aborted_runtime_sessions.append(runtime_session_id)


class FailingAbortRuntimeClient(RequestTrackingRuntimeClient):
    async def abort_session(self, runtime_session_id: str) -> None:
        self.aborted_runtime_sessions.append(runtime_session_id)
        raise RuntimeError('abort failed')


class ReplacementRuntimeClient(StubAgentRuntimeClient):
    def __init__(self) -> None:
        super().__init__([])
        self.run_started = asyncio.Event()
        self.first_run_cancelled = asyncio.Event()
        self.run_count = 0
        self.aborted_runtime_sessions: list[str] = []

    async def run_session(self, request, emit):
        self.run_count += 1
        runtime_session_id = f'runtime-session-{self.run_count}'
        request.runtime_session_id = runtime_session_id
        await emit(EventEnvelope(type='session.runtime_session', payload={'runtime_session_id': runtime_session_id}))
        if self.run_count == 1:
            self.run_started.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                self.first_run_cancelled.set()
                raise
        await emit(EventEnvelope(type='session.status', payload={'status': 'completed'}))
        return {'runtime_session_id': runtime_session_id, 'trace_path': f'runtime/{runtime_session_id}.jsonl'}

    async def abort_session(self, runtime_session_id: str) -> None:
        self.aborted_runtime_sessions.append(runtime_session_id)


class CompletingAbortRuntimeClient(StubAgentRuntimeClient):
    def __init__(self) -> None:
        super().__init__([])
        self.run_started = asyncio.Event()
        self.finish_run = asyncio.Event()
        self.run_finished = asyncio.Event()
        self.aborted_runtime_sessions: list[str] = []

    async def run_session(self, request, emit):
        await emit(EventEnvelope(type='session.runtime_session', payload={'runtime_session_id': 'runtime-session-1'}))
        self.run_started.set()
        await self.finish_run.wait()
        await emit(EventEnvelope(type='session.status', payload={'status': 'completed'}))
        self.run_finished.set()
        return {'runtime_session_id': 'runtime-session-1', 'trace_path': 'runtime/trace.jsonl'}

    async def abort_session(self, runtime_session_id: str) -> None:
        self.aborted_runtime_sessions.append(runtime_session_id)
        self.finish_run.set()
        await asyncio.wait_for(self.run_finished.wait(), timeout=1)


class FakeRuntimeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self.payload


class FakeRuntimeHttpClient:
    def __init__(self, *, statuses: list[object], message_snapshots: list[list[dict[str, object]]], session_details: list[dict[str, object]] | None = None) -> None:
        self._statuses = list(statuses)
        self._message_snapshots = list(message_snapshots)
        self._session_details = list(session_details or [])

    async def get(self, path: str) -> FakeRuntimeResponse:
        if path == '/session/status':
            return FakeRuntimeResponse(self._statuses.pop(0))
        if path.startswith('/session/') and path.endswith('/message'):
            return FakeRuntimeResponse(self._message_snapshots.pop(0))
        if path.startswith('/session/') and not path.endswith('/message'):
            return FakeRuntimeResponse(self._session_details.pop(0))
        raise AssertionError(f'unexpected path: {path}')


class GeoCliRuntimeClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.requests: list[dict[str, object]] = []

    @property
    def is_ready(self) -> bool:
        return True

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    def status(self) -> RuntimeStatus:
        return RuntimeStatus(status='ready', label='opencode-runtime', detail='deterministic test runtime ready')

    async def run_session(self, request, emit):
        from app.services.geospatial_mcp_server import get_session_context_payload, record_run_evidence_payload

        self.requests.append({
            'session_id': request.session_id,
            'prompt': request.prompt,
            'answer': request.answer,
            'geospatial_context_id': request.geospatial_context_id,
            'runtime_session_id': request.runtime_session_id,
            'attached_data_directories': request.attached_data_directories,
        })

        context_payload = get_session_context_payload(
            session_context_id=request.geospatial_context_id,
            settings=self.settings,
        )
        artifact_dir = Path(context_payload['workspace']['root']) / 'outputs'
        artifact_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = artifact_dir / 'run-manifest.json'
        claim_trace_path = artifact_dir / 'claim-trace.json'
        manifest_path.write_text(json.dumps({'prompt': request.prompt, 'source': 'agent-authored-script'}, ensure_ascii=False), encoding='utf-8')
        claim_trace_path.write_text(json.dumps({'claims': [], 'source': 'agent-authored-script'}, ensure_ascii=False), encoding='utf-8')

        manifest_payload = record_run_evidence_payload(
            session_context_id=request.geospatial_context_id,
            record_type='artifact',
            title='KDE 运行清单',
            path=str(manifest_path),
            format='json',
            artifact_stage='final',
            display_hint='json',
            category='manifest',
            provenance={'command': 'uv run python scripts/kde_validation.py'},
            settings=self.settings,
        )
        claim_trace_payload = record_run_evidence_payload(
            session_context_id=request.geospatial_context_id,
            record_type='artifact',
            title='Claim Trace',
            path=str(claim_trace_path),
            format='json',
            artifact_stage='final',
            display_hint='json',
            category='metadata',
            provenance={'command': 'uv run python scripts/kde_validation.py'},
            settings=self.settings,
        )
        await emit(EventEnvelope(type='session.artifact', payload=manifest_payload['artifact']))
        await emit(EventEnvelope(type='session.artifact', payload=claim_trace_payload['artifact']))
        await emit(
            EventEnvelope(
                type='session.verification',
                payload=[
                    VerificationEntry(
                        id='verification-kde-outputs-ready',
                        code='kde_outputs_ready',
                        title='KDE 输出已登记',
                        status='passed',
                        detail='最终产物已由运行时脚本生成并登记为证据。',
                    ).model_dump(mode='json')
                ],
            )
        )
        await emit(EventEnvelope(type='session.status', payload={'status': 'completed'}))
        return {'runtime_session_id': 'runtime-session-cli', 'trace_path': str(self.settings.resolved_app_support_dir() / 'runtime-traces' / 'runtime-session-cli')}


def make_settings(tmp_path: Path) -> Settings:
    support_dir = tmp_path / 'support'
    return Settings(
        state_dir=tmp_path / '.state',
        app_support_dir=support_dir,
        database_path=support_dir / 'geo-agent.db',
        workspace_root=support_dir / 'workspace',
    )


def make_runtime_task(prompt: str, stage: TaskStage = 'planned', analysis_type: AnalysisType = 'kde') -> GeospatialTask:
    return GeospatialTask(
        id='task-runtime-fixture',
        prompt=prompt,
        analysis_type=analysis_type,
        stage=stage,
        runtime=RuntimeProfile(
            bundle_id='app-geospatial-agent-knowledge',
            label='Runtime geospatial agent bundle',
            tools=['get_session_context', 'update_todos', 'record_run_evidence'],
        ),
        preprocessing=GeospatialPreprocessing(target_crs='EPSG:32650'),
        operator=OperatorMetadata(name=analysis_type, stage=stage),
    )


@pytest.mark.asyncio
async def test_create_session_persists_sqlite_metadata_and_workspace(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    service = SessionService(settings=settings, title_provider=StubTitleProvider(), runtime_client=StubAgentRuntimeClient([]))

    session = await service.create_session()
    second = await service.create_session()

    assert session.title.startswith('新建会话')
    assert session.workspace_path is not None
    assert Path(session.workspace_path).exists()
    assert second.workspace_path == session.workspace_path
    assert settings.database_path.exists()

    reloaded = SessionService(settings=settings, title_provider=StubTitleProvider())
    sessions = reloaded.list_sessions()

    assert sessions[0].id == second.id
    assert {item.id for item in sessions[:2]} == {session.id, second.id}
    assert sessions[0].workspace_path == session.workspace_path


@pytest.mark.parametrize(
    ('analysis_type', 'operator_parameters', 'artifact_title'),
    [
        ('spatial_interpolation', {'method': 'idw', 'power': 2}, 'IDW 插值栅格'),
        ('spatial_hotspot', {'method': 'gistar', 'permutations': 999}, 'Gi* 统计表'),
    ],
)
@pytest.mark.asyncio
async def test_session_reload_preserves_new_task_family_metadata(
    tmp_path: Path,
    analysis_type: AnalysisType,
    operator_parameters: dict[str, str | int | float | bool],
    artifact_title: str,
) -> None:
    settings = make_settings(tmp_path)
    task = make_runtime_task(f'执行 {artifact_title}', stage='completed', analysis_type=analysis_type)
    task.operator.parameters = operator_parameters
    runtime_client = StubAgentRuntimeClient([
        [
            EventEnvelope(type='session.geospatial_task', payload=task.model_dump(mode='json')),
            EventEnvelope(
                type='session.artifact',
                payload=Artifact(
                    id='artifact-family-aware',
                    title=artifact_title,
                    path='outputs/family-aware.json',
                    kind='json',
                    analysis_type=analysis_type,
                    provenance={'operator': operator_parameters['method']},
                ).model_dump(mode='json'),
            ),
            EventEnvelope(type='session.status', payload={'status': 'completed'}),
        ],
    ])
    service = SessionService(settings=settings, title_provider=StubTitleProvider(), runtime_client=runtime_client)
    session = await service.create_session()

    await service.submit_message(session.id, f'执行 {artifact_title}')

    restored = SessionService(settings=settings, title_provider=StubTitleProvider(), runtime_client=StubAgentRuntimeClient([])).get_session(session.id)
    assert restored.geospatial_task is not None
    assert restored.geospatial_task.analysis_type == analysis_type
    assert restored.geospatial_task.operator.name == analysis_type
    assert restored.geospatial_task.operator.parameters == operator_parameters
    assert restored.artifacts[0].analysis_type == analysis_type
    assert restored.artifacts[0].provenance['operator'] == operator_parameters['method']


@pytest.mark.asyncio
async def test_session_recovery_restores_hotspot_verification_evidence_metadata(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    service = SessionService(settings=settings, title_provider=StubTitleProvider(), runtime_client=StubAgentRuntimeClient([]))
    session = await service.create_session()
    assert session.workspace_path is not None
    task = make_runtime_task('执行 Gi* 热点分析', stage='completed', analysis_type='spatial_hotspot')
    session.geospatial_context_id = 'context-1'
    session.geospatial_task = task
    session.status = 'completed'
    service.store.save_session(session)
    service.store.save_geospatial_session_context(
        GeospatialSessionContext(
            id='context-1',
            session_id=session.id,
            prompt='执行 Gi* 热点分析',
            workspace_path=session.workspace_path,
            geospatial_task=task,
            verification=[
                VerificationEntry(
                    id='verification-gistar-weights',
                    code='gistar_weights_ready',
                    title='Gi* 权重可解释',
                    status='passed',
                    detail='Queen contiguity weights recorded.',
                ),
            ],
        )
    )
    service.store.append_geospatial_evidence_record({
        'id': 'evidence-gistar-weights',
        'record_type': 'verification_fact',
        'title': 'Gi* 权重和显著性验证',
        'description': 'Queen weights and FDR policy.',
        'category': 'weights',
        'analysis_type': 'spatial_hotspot',
        'session_context_id': 'context-1',
        'created_at': '2026-04-21T10:00:00+00:00',
        'data': {
            'analysis_type': 'spatial_hotspot',
            'weights': {'type': 'Queen contiguity', 'island_weight': 'nan'},
            'significance': {'FDR': 'benjamini_hochberg'},
        },
        'provenance': {'pysal_method': 'esda.G_Local', 'star': True},
    })

    recovered = await SessionService(settings=settings, title_provider=StubTitleProvider(), runtime_client=StubAgentRuntimeClient([])).get_session_with_runtime_recovery(session.id)

    assert recovered.geospatial_task is not None
    assert recovered.geospatial_task.analysis_type == 'spatial_hotspot'
    evidence_entry = next(entry for entry in recovered.timeline if entry.evidence_record_id == 'evidence-gistar-weights')
    assert evidence_entry.record_type == 'verification_fact'
    assert evidence_entry.data['analysis_type'] == 'spatial_hotspot'
    assert evidence_entry.data['weights']['island_weight'] == 'nan'
    assert evidence_entry.provenance['pysal_method'] == 'esda.G_Local'


@pytest.mark.asyncio
async def test_rename_and_delete_session_update_sqlite_metadata(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    service = SessionService(settings=settings, title_provider=StubTitleProvider(), runtime_client=StubAgentRuntimeClient([]))
    session = await service.create_session()

    renamed = await service.rename_session(session.id, '北京 FCD KDE 会话')

    assert renamed.title == '北京 FCD KDE 会话'
    assert service.list_sessions()[0].title == '北京 FCD KDE 会话'

    await service.delete_session(session.id)

    assert service.list_sessions() == []


@pytest.mark.asyncio
async def test_get_session_recovers_truncated_runtime_messages(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    runtime_client = MessageRecoveryRuntimeClient({
        'runtime-session-1': [
            {
                'id': 'msg-assistant-1',
                'role': 'assistant',
                'agent': 'geo',
                'created_at': '2026-04-27T10:42:09+00:00',
                'parts': [
                    {
                        'type': 'tool',
                        'tool': 'geospatial_update_todos',
                        'state': {
                            'status': 'completed',
                            'input': {'entries': [{'content': '检查 CRS', 'status': 'pending'}]},
                            'output': '<todos status="updated"><item status="pending">检查 CRS</item></todos>',
                        },
                    },
                    {
                        'type': 'tool',
                        'tool': 'task',
                        'state': {
                            'input': {
                                'prompt': '请核验数据。',
                                'subagent_type': 'data-audit',
                            },
                            'output': 'task_id: child-session-1\n\n<task_result>done</task_result>',
                        },
                    },
                ],
            },
            {
                'id': 'msg-assistant-2',
                'role': 'assistant',
                'agent': 'geo',
                'created_at': '2026-04-27T10:43:00+00:00',
                'parts': [{'type': 'text', 'text': '继续执行数据核验。'}],
            },
        ],
        'child-session-1': [
            {
                'id': 'msg-child-user',
                'role': 'user',
                'agent': 'data-audit',
                'created_at': '2026-04-27T10:42:10+00:00',
                'parts': [{'type': 'text', 'text': '请核验数据。'}],
            },
            {
                'id': 'msg-child-assistant',
                'role': 'assistant',
                'agent': 'data-audit',
                'created_at': '2026-04-27T10:42:20+00:00',
                'parts': [{'type': 'text', 'text': '数据核验完成。'}],
            },
        ],
    })
    service = SessionService(settings=settings, title_provider=StubTitleProvider(), runtime_client=runtime_client)
    session = await service.create_session()
    session.status = 'completed'
    session.runtime_session_id = 'runtime-session-1'
    session.messages = [
        ChatMessage(id='msg-assistant-1', role='assistant', agent='geo', created_at=session.created_at, parts=[]),
        ChatMessage(
            id='inline-issue-1',
            role='system',
            agent='geo',
            created_at=session.created_at,
            parts=[ChatMessagePart(type='issue', text='保留已有内联问题。')],
        ),
    ]
    service.store.save_session(session)

    recovered = await service.get_session_with_runtime_recovery(session.id)
    restored = service.store.load_session(session.id)

    assert runtime_client.fetches == ['runtime-session-1', 'child-session-1']
    assert [message.id for message in recovered.messages] == [
        'msg-assistant-1',
        'inline-subtask-child-session-1',
        'inline-msg-child-assistant-child-session-1',
        'msg-assistant-2',
        'inline-issue-1',
    ]
    assert recovered.messages[0].parts[0].tool == 'geospatial_update_todos'
    assert recovered.messages[1].parts[0].type == 'subtask'
    assert recovered.messages[2].agent == 'data-audit'
    assert recovered.messages[3].parts[0].text == '继续执行数据核验。'
    assert recovered.plan_groups[0].agent == 'geo'
    assert recovered.plan_groups[0].entries[0].label == '检查 CRS'
    assert recovered.plan[0].label == '检查 CRS'
    assert restored is not None
    assert restored.messages[2].id == 'inline-msg-child-assistant-child-session-1'
    assert restored.plan_groups[0].entries[0].label == '检查 CRS'


@pytest.mark.asyncio
async def test_get_session_recovers_running_task_metadata_child_messages(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    runtime_client = MessageRecoveryRuntimeClient({
        'runtime-session-1': [
            {
                'id': 'msg-assistant-review-task',
                'role': 'assistant',
                'agent': 'geo',
                'created_at': '2026-04-27T15:40:00+00:00',
                'parts': [
                    {
                        'type': 'tool',
                        'tool': 'task',
                        'state': {
                            'status': 'running',
                            'input': {
                                'description': '审查热力图结果合理性',
                                'prompt': '请审查热力图结果是否合理。',
                                'subagent_type': 'skeptical-review',
                            },
                            'metadata': {'sessionId': 'child-review-session'},
                        },
                    },
                ],
            },
        ],
        'child-review-session': [
            {
                'id': 'msg-child-review-user',
                'role': 'user',
                'agent': 'skeptical-review',
                'created_at': '2026-04-27T15:40:01+00:00',
                'parts': [{'type': 'text', 'text': '请审查热力图结果是否合理。'}],
            },
            {
                'id': 'msg-child-review-assistant',
                'role': 'assistant',
                'agent': 'skeptical-review',
                'created_at': '2026-04-27T15:40:10+00:00',
                'parts': [{'type': 'text', 'text': '审查发现热点分布需要进一步说明。'}],
            },
        ],
    })
    service = SessionService(settings=settings, title_provider=StubTitleProvider(), runtime_client=runtime_client)
    session = await service.create_session()
    session.status = 'idle'
    session.runtime_session_id = 'runtime-session-1'
    session.messages = [
        ChatMessage(
            id='msg-assistant-review-task',
            role='assistant',
            agent='geo',
            created_at=session.created_at,
            parts=[
                ChatMessagePart(
                    type='tool',
                    tool='task',
                    state={
                        'status': 'running',
                        'input': {
                            'description': '审查热力图结果合理性',
                            'prompt': '请审查热力图结果是否合理。',
                            'subagent_type': 'skeptical-review',
                        },
                        'metadata': {'sessionId': 'child-review-session'},
                    },
                )
            ],
        )
    ]
    service.store.save_session(session)

    recovered = await service.get_session_with_runtime_recovery(session.id)

    assert runtime_client.fetches == ['runtime-session-1', 'child-review-session']
    assert [message.id for message in recovered.messages] == [
        'msg-assistant-review-task',
        'inline-subtask-child-review-session',
        'inline-msg-child-review-assistant-child-review-session',
    ]
    assert recovered.messages[1].parts[0].state['description'] == '审查热力图结果合理性'
    assert recovered.messages[2].agent == 'skeptical-review'
    assert recovered.messages[2].parts[0].text == '审查发现热点分布需要进一步说明。'


@pytest.mark.asyncio
async def test_session_artifacts_deduplicate_by_path_without_report_inline_message(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    service = SessionService(
        settings=settings,
        title_provider=StubTitleProvider(),
        runtime_client=StubAgentRuntimeClient([
            [
                EventEnvelope(type='session.artifact', payload=Artifact(id='artifact-old', title='旧版热力图', path='outputs/heatmap.png', kind='map').model_dump(mode='json')),
                EventEnvelope(type='session.artifact', payload=Artifact(id='artifact-new', title='新版热力图', path='outputs/heatmap.png', kind='map').model_dump(mode='json')),
                EventEnvelope(type='session.status', payload={'status': 'completed'}),
            ]
        ]),
    )
    session = await service.create_session()

    await service.submit_message(session.id, '生成热力图')
    await service.wait_for_run(session.id)

    completed = service.get_session(session.id)

    assert [artifact.title for artifact in completed.artifacts] == ['新版热力图']
    assert [artifact.id for artifact in completed.artifacts] == ['artifact-new']
    assert not any(message.agent == 'report-synthesizer' for message in completed.messages)
    assert not any(part.type == 'artifact' for message in completed.messages for part in message.parts)


@pytest.mark.asyncio
async def test_intermediate_artifact_updates_artifact_state_without_inline_message(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    service = SessionService(
        settings=settings,
        title_provider=StubTitleProvider(),
        runtime_client=StubAgentRuntimeClient([
            [
                EventEnvelope(type='session.artifact', payload=Artifact(
                    id='artifact-old',
                    title='旧版参数快照',
                    path='outputs/params.json',
                    kind='json',
                    artifact_stage='intermediate',
                    display_hint='json',
                ).model_dump(mode='json')),
                EventEnvelope(type='session.artifact', payload=Artifact(
                    id='artifact-new',
                    title='新版参数快照',
                    path='outputs/params.json',
                    kind='json',
                    artifact_stage='intermediate',
                    display_hint='json',
                ).model_dump(mode='json')),
                EventEnvelope(type='session.status', payload={'status': 'completed'}),
            ]
        ]),
    )
    session = await service.create_session()

    await service.submit_message(session.id, '记录中间产物')
    await service.wait_for_run(session.id)

    completed = service.get_session(session.id)
    artifact_messages = [
        message for message in completed.messages
        if any(part.type == 'artifact' for part in message.parts)
    ]

    assert [artifact.title for artifact in completed.artifacts] == ['新版参数快照']
    assert artifact_messages == []


@pytest.mark.asyncio
async def test_runtime_recovery_keeps_intermediate_artifact_as_artifact_state_only(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    service = SessionService(
        settings=settings,
        title_provider=StubTitleProvider(),
        runtime_client=StubAgentRuntimeClient([]),
    )
    session = await service.create_session()
    artifact = Artifact(
        id='artifact-params',
        title='中间参数快照',
        path='outputs/params.json',
        kind='json',
        artifact_stage='intermediate',
        display_hint='json',
    )
    session.status = 'completed'
    session.artifacts = [artifact]
    session.messages = [
        ChatMessage(
            id='msg-assistant-1',
            role='assistant',
            agent='geo',
            created_at='2026-04-21T10:00:00+00:00',
            parts=[
                ChatMessagePart(
                    type='tool',
                    tool='geospatial_record_run_evidence',
                    state={
                        'input': {'record_type': 'artifact', 'artifact_stage': 'intermediate'},
                        'output': '<evidence status="recorded" type="artifact"></evidence>',
                    },
                ),
            ],
        ),
    ]
    service.store.save_session(session)

    recovered = await service.get_session_with_runtime_recovery(session.id)
    artifact_messages = [
        message for message in recovered.messages
        if any(part.type == 'artifact' for part in message.parts)
    ]

    assert artifact_messages == []
    assert recovered.artifacts == [artifact]
    assert recovered.messages[0].id == 'msg-assistant-1'


@pytest.mark.asyncio
async def test_evidence_timeline_entry_is_persisted_and_restored(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    service = SessionService(
        settings=settings,
        title_provider=StubTitleProvider(),
        runtime_client=StubAgentRuntimeClient([
            [
                EventEnvelope(type='session.timeline_entry', payload={
                    'id': 'evidence-evidence-1',
                    'kind': 'evidence',
                    'text': 'FCD 数据画像',
                    'title': 'FCD 数据画像',
                    'detail': '检查字段和范围。',
                    'record_type': 'dataset_profile',
                    'data': {'feature_count': 60897, 'crs': 'EPSG:32650'},
                    'provenance': {'command': 'uv run python scripts/audit.py'},
                    'evidence_record_id': 'evidence-1',
                    'created_at': '2026-04-21T10:00:00+00:00',
                }),
                EventEnvelope(type='session.status', payload={'status': 'completed'}),
            ]
        ]),
    )
    session = await service.create_session()

    await service.submit_message(session.id, '记录数据画像')
    await service.wait_for_run(session.id)

    completed = service.get_session(session.id)
    assert completed.timeline[-1].kind == 'evidence'
    assert completed.timeline[-1].data == {'feature_count': 60897, 'crs': 'EPSG:32650'}
    assert completed.timeline[-1].provenance == {'command': 'uv run python scripts/audit.py'}
    assert completed.timeline[-1].record_type == 'dataset_profile'

    restarted = SessionService(settings=settings, runtime_client=StubAgentRuntimeClient([]))
    restored = await restarted.get_session_with_runtime_recovery(session.id)

    assert restored.timeline[-1].title == 'FCD 数据画像'
    assert restored.timeline[-1].detail == '检查字段和范围。'


@pytest.mark.asyncio
async def test_session_reload_recovers_evidence_timeline_from_store(tmp_path: Path) -> None:
    from app.services.geospatial_mcp_server import record_run_evidence_payload

    settings = make_settings(tmp_path)
    service = SessionService(
        settings=settings,
        title_provider=StubTitleProvider(),
        runtime_client=StubAgentRuntimeClient([
            [EventEnvelope(type='session.status', payload={'status': 'completed'})],
        ]),
    )
    session = await service.create_session()

    await service.submit_message(session.id, '记录参数快照')
    await service.wait_for_run(session.id)

    completed = service.get_session(session.id)
    assert completed.geospatial_context_id is not None
    record_run_evidence_payload(
        record_type='parameter_snapshot',
        title='KDE 参数快照',
        description='150m 网格，Scott 带宽。',
        session_context_id=completed.geospatial_context_id,
        settings=settings,
    )
    completed.timeline = []
    service.store.save_session(completed)

    restarted = SessionService(settings=settings, runtime_client=StubAgentRuntimeClient([]))
    restored = await restarted.get_session_with_runtime_recovery(session.id)

    assert len(restored.timeline) == 1
    assert restored.timeline[0].kind == 'evidence'
    assert restored.timeline[0].record_type == 'parameter_snapshot'
    assert restored.timeline[0].title == 'KDE 参数快照'
    assert restored.timeline[0].detail == '150m 网格，Scott 带宽。'


@pytest.mark.asyncio
async def test_get_session_prunes_legacy_inline_artifact_messages(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    service = SessionService(settings=settings, title_provider=StubTitleProvider(), runtime_client=MessageRecoveryRuntimeClient({}))
    session = await service.create_session()
    session.runtime_session_id = 'runtime-session-1'
    session.artifacts = [
        Artifact(id='artifact-1', title='KDE 热力图', path='outputs/heatmap.png', kind='map')
    ]
    session.messages = [
        ChatMessage(
            id='inline-legacy-artifact',
            role='system',
            agent='report-synthesizer',
            created_at=session.created_at,
            parts=[ChatMessagePart(type='artifact', state=session.artifacts[0].model_dump(mode='json'))],
        ),
        ChatMessage(
            id='inline-issue-1',
            role='system',
            agent=None,
            created_at=session.created_at,
            parts=[ChatMessagePart(type='issue', text='保留问题记录')],
        ),
    ]
    service.store.save_session(session)

    recovered = await service.get_session_with_runtime_recovery(session.id)

    assert [message.id for message in recovered.messages] == ['inline-issue-1']
    assert recovered.artifacts[0].title == 'KDE 热力图'


@pytest.mark.asyncio
async def test_submit_message_updates_title_and_emits_title_event(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    service = SessionService(
        settings=settings,
        title_provider=StubTitleProvider('Provider generated title'),
        runtime_client=StubAgentRuntimeClient([
            [
                EventEnvelope(type='session.title', payload={'title': 'Runtime generated title'}),
                EventEnvelope(type='session.plan', payload=[{'id': 'plan-1', 'label': '规范化地理分析任务', 'status': 'completed'}]),
                EventEnvelope(type='session.status', payload={'status': 'completed'}),
            ]
        ]),
    )
    session = await service.create_session()
    queue = await service.subscribe(session.id)

    await service.submit_message(session.id, '对北京出租车轨迹做 KDE 热点分析')
    await service.wait_for_run(session.id)
    await asyncio.sleep(0)

    emitted_types: list[str] = []
    while not queue.empty():
        emitted_types.append((await queue.get()).type)

    updated = service.get_session(session.id)

    assert updated.title == 'Runtime generated title'
    assert 'session.title' in emitted_types


@pytest.mark.asyncio
async def test_runtime_title_event_takes_priority_over_provider_generated_title(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    service = SessionService(
        settings=settings,
        title_provider=StubTitleProvider('Provider generated title'),
        runtime_client=StubAgentRuntimeClient([
            [
                EventEnvelope(type='session.title', payload={'title': 'Runtime generated title'}),
                EventEnvelope(type='session.status', payload={'status': 'completed'}),
            ]
        ]),
    )
    session = await service.create_session()

    await service.submit_message(session.id, '对北京出租车轨迹做 KDE 热点分析')
    await service.wait_for_run(session.id)
    await asyncio.sleep(0)

    updated = service.get_session(session.id)

    assert updated.title == 'Runtime generated title'


@pytest.mark.asyncio
async def test_runtime_side_effects_are_added_to_inline_transcript_messages(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    service = SessionService(
        settings=settings,
        title_provider=StubTitleProvider(),
        runtime_client=StubAgentRuntimeClient([
            [
                EventEnvelope(type='session.plan', payload=[{'id': 'plan-1', 'label': '规范化地理分析任务', 'status': 'completed'}]),
                EventEnvelope(type='session.verification', payload=[
                    VerificationEntry(id='verification-1', code='crs_normalized', title='已完成投影归一化', status='passed', detail='detail').model_dump(mode='json'),
                ]),
                EventEnvelope(type='session.artifact', payload=Artifact(id='artifact-1', title='KDE 运行清单', path='run-manifest.json', kind='manifest', analysis_type='kde').model_dump(mode='json')),
                EventEnvelope(type='session.status', payload={'status': 'completed'}),
            ]
        ]),
    )
    session = await service.create_session()

    await service.submit_message(session.id, '对北京出租车轨迹做 KDE 热点分析')
    await service.wait_for_run(session.id)

    updated = service.get_session(session.id)
    part_types = [part.type for message in updated.messages for part in message.parts]

    assert 'todo' in part_types
    assert 'verification' in part_types
    assert 'artifact' not in part_types
    assert updated.artifacts[0].title == 'KDE 运行清单'


@pytest.mark.asyncio
async def test_runtime_inline_transcript_messages_use_canonical_agent_ids(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    service = SessionService(
        settings=settings,
        title_provider=StubTitleProvider(),
        runtime_client=StubAgentRuntimeClient([
            [
                EventEnvelope(type='session.plan', payload=[{'id': 'plan-1', 'label': '规范化地理分析任务', 'status': 'completed'}]),
                EventEnvelope(type='session.question', payload=Question(id='question-1', prompt='请选择研究区范围').model_dump(mode='json')),
                EventEnvelope(type='session.verification', payload=[
                    VerificationEntry(id='verification-1', code='crs_normalized', title='已完成投影归一化', status='passed', detail='detail').model_dump(mode='json'),
                ]),
                EventEnvelope(type='session.artifact', payload=Artifact(id='artifact-1', title='KDE 运行清单', path='run-manifest.json', kind='manifest', analysis_type='kde').model_dump(mode='json')),
                EventEnvelope(type='session.status', payload={'status': 'completed'}),
            ]
        ]),
    )
    session = await service.create_session()

    await service.submit_message(session.id, '对北京出租车轨迹做 KDE 热点分析')
    await service.wait_for_run(session.id)

    updated = service.get_session(session.id)
    inline_agents_by_part = {
        part.type: message.agent
        for message in updated.messages
        if message.id.startswith('inline-')
        for part in message.parts
    }

    assert inline_agents_by_part['todo'] == 'geo'
    assert inline_agents_by_part['question'] == 'geo'
    assert inline_agents_by_part['verification'] == 'skeptical-review'
    assert 'artifact' not in inline_agents_by_part


@pytest.mark.asyncio
async def test_plan_group_events_preserve_per_agent_plans_and_persist(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    service = SessionService(
        settings=settings,
        title_provider=StubTitleProvider(),
        runtime_client=StubAgentRuntimeClient([
            [
                EventEnvelope(type='session.plan_group', payload={
                    'id': 'geo',
                    'agent': 'geo',
                    'label': '空间主理人',
                    'updated_at': '2026-03-25T00:00:01+00:00',
                    'entries': [
                        {'id': 'plan-1', 'label': '判断是否需要分派角色', 'status': 'completed'},
                    ],
                }),
                EventEnvelope(type='session.plan_group', payload={
                    'id': 'spatial-prep',
                    'agent': 'spatial-prep',
                    'label': '空间整备师',
                    'updated_at': '2026-03-25T00:00:02+00:00',
                    'entries': [
                        {'id': 'plan-1', 'label': '核验 CRS 与研究区边界', 'status': 'in_progress'},
                    ],
                }),
                EventEnvelope(type='session.plan_group', payload={
                    'id': 'spatial-prep',
                    'agent': 'spatial-prep',
                    'label': '空间整备师',
                    'updated_at': '2026-03-25T00:00:03+00:00',
                    'entries': [
                        {'id': 'plan-1', 'label': '核验 CRS 与研究区边界', 'status': 'completed'},
                        {'id': 'plan-2', 'label': '等待用户补齐轨迹目录', 'status': 'blocked'},
                    ],
                }),
                EventEnvelope(type='session.status', payload={'status': 'completed'}),
            ]
        ]),
    )
    session = await service.create_session()
    queue = await service.subscribe(session.id)

    await service.submit_message(session.id, '请多 agent 协作并分别维护计划')
    await service.wait_for_run(session.id)
    await asyncio.sleep(0)

    updated = service.get_session(session.id)
    published_types: list[str] = []
    while not queue.empty():
        published_types.append((await queue.get()).type)

    assert 'session.plan_groups' in published_types
    assert [group.agent for group in updated.plan_groups] == ['geo', 'spatial-prep']
    assert updated.plan_groups[0].entries[0].label == '判断是否需要分派角色'
    assert [entry.status for entry in updated.plan_groups[1].entries] == ['completed', 'blocked']
    assert len([group for group in updated.plan_groups if group.agent == 'spatial-prep']) == 1

    restarted = SessionService(settings=settings, title_provider=StubTitleProvider(), runtime_client=StubAgentRuntimeClient([]))
    restored = restarted.get_session(session.id)

    assert [group.agent for group in restored.plan_groups] == ['geo', 'spatial-prep']
    assert restored.plan_groups[1].entries[1].label == '等待用户补齐轨迹目录'


@pytest.mark.asyncio
async def test_session_reload_restores_transcript_evidence_chain(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    service = SessionService(
        settings=settings,
        title_provider=StubTitleProvider(),
        runtime_client=StubAgentRuntimeClient([
            [
                EventEnvelope(type='session.plan', payload=[{'id': 'plan-1', 'label': '规范化地理分析任务', 'status': 'completed'}]),
                EventEnvelope(type='session.verification', payload=[
                    VerificationEntry(id='verification-1', code='crs_normalized', title='已完成投影归一化', status='passed', detail='detail').model_dump(mode='json'),
                ]),
                EventEnvelope(type='session.artifact', payload=Artifact(id='artifact-1', title='KDE 运行清单', path='run-manifest.json', kind='manifest', analysis_type='kde').model_dump(mode='json')),
                EventEnvelope(type='session.status', payload={'status': 'completed'}),
            ]
        ]),
    )
    session = await service.create_session()

    await service.submit_message(session.id, '对北京出租车轨迹做 KDE 热点分析')
    await service.wait_for_run(session.id)

    restarted = SessionService(settings=settings, title_provider=StubTitleProvider(), runtime_client=StubAgentRuntimeClient([]))
    restored = restarted.get_session(session.id)
    part_types = [part.type for message in restored.messages for part in message.parts]

    assert restored.messages
    assert 'todo' in part_types
    assert 'verification' in part_types
    assert 'artifact' not in part_types
    assert restored.artifacts[0].title == 'KDE 运行清单'


@pytest.mark.asyncio
async def test_title_generation_failure_keeps_fallback_title(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    service = SessionService(
        settings=settings,
        title_provider=StubTitleProvider(fail=True),
        runtime_client=StubAgentRuntimeClient([[EventEnvelope(type='session.status', payload={'status': 'completed'})]]),
    )
    session = await service.create_session()

    await service.submit_message(session.id, '对北京出租车轨迹做 KDE 热点分析')
    await service.wait_for_run(session.id)
    await asyncio.sleep(0)

    updated = service.get_session(session.id)

    assert updated.title == session.title


@pytest.mark.asyncio
async def test_answer_question_marks_reply_messages_as_history_excluded(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    service = SessionService(
        settings=settings,
        title_provider=StubTitleProvider(),
        runtime_client=StubAgentRuntimeClient([[]]),
    )
    session = await service.create_session()
    current = service.get_session(session.id)
    current.runtime_session_id = 'runtime-session-1'
    current.question = Question(id='question-1', prompt='是否继续执行？')
    service.store.save_session(current)

    await service.answer_question(session.id, 'question-1', '继续执行')

    updated = service.get_session(session.id)
    latest_message = updated.messages[-1]

    assert latest_message.role == 'user'
    assert latest_message.parts[0].state == {
        'history_excluded': True,
        'question_id': 'question-1',
        'question_answers': ['继续执行'],
    }


@pytest.mark.asyncio
async def test_answer_runtime_question_reuses_runtime_session_and_preserves_visible_context(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    runtime_client = StubAgentRuntimeClient([[EventEnvelope(type='session.status', payload={'status': 'completed'})]])
    service = SessionService(
        settings=settings,
        title_provider=StubTitleProvider(),
        runtime_client=runtime_client,
    )
    session = await service.create_session()
    current = service.get_session(session.id)
    current.runtime_session_id = 'runtime-session-1'
    current.plan = [PlanEntry(id='plan-1', label='等待用户确认研究区', status='in_progress')]
    current.verification = [
        VerificationEntry(
            id='verification-1',
            code='needs_human_decision',
            title='等待人工确认',
            status='warning',
            detail='研究区需要用户确认。',
        )
    ]
    current.artifacts = [
        Artifact(
            id='artifact-1',
            title='临时运行清单',
            path='run-manifest.json',
            kind='manifest',
            analysis_type='kde',
        )
    ]
    current.question = Question(
        id='question-request-1',
        prompt='请选择研究区范围',
        source='runtime',
        questions=[
            QuestionItem(
                header='研究区',
                question='请选择研究区范围',
                options=[
                    QuestionOption(
                        label='使用默认北京市区县边界',
                        description='使用系统默认行政区边界继续执行',
                    )
                ],
            )
        ],
    )
    service.store.save_session(current)

    await service.answer_question(session.id, 'question-request-1', answers=['使用默认北京市区县边界'])
    await service.wait_for_run(session.id)

    updated = service.get_session(session.id)

    assert runtime_client.requests[-1]['runtime_session_id'] == 'runtime-session-1'
    assert runtime_client.requests[-1]['question_request_id'] == 'question-request-1'
    assert runtime_client.requests[-1]['question_answers'] == ['使用默认北京市区县边界']
    assert updated.plan == [PlanEntry(id='plan-1', label='等待用户确认研究区', status='in_progress')]
    assert updated.verification[0].code == 'needs_human_decision'
    assert updated.artifacts[0].title == '临时运行清单'


@pytest.mark.asyncio
async def test_opencode_runtime_poll_emits_runtime_session_title_updates(tmp_path: Path) -> None:
    from app.services.agent_runtime import OpenCodeAgentRuntimeClient, RuntimeSessionRequest

    settings = Settings(state_dir=tmp_path / '.state-runtime-title', glm_api_key='test-key')
    runtime = OpenCodeAgentRuntimeClient(settings)
    runtime._client = FakeRuntimeHttpClient(
        statuses=[{'runtime-session-title': {'type': 'busy'}}, {'runtime-session-title': {'type': 'idle'}}],
        session_details=[
            {'id': 'runtime-session-title', 'title': 'Runtime generated title'},
            {'id': 'runtime-session-title', 'title': 'Runtime generated title'},
        ],
        message_snapshots=[
            [
                {
                    'info': {'id': 'msg-assistant-runtime', 'role': 'assistant', 'agent': 'geo', 'time': {'created': 1710000000000}},
                    'parts': [{'type': 'text', 'text': '正在分析'}],
                }
            ],
            [
                {
                    'info': {'id': 'msg-assistant-runtime', 'role': 'assistant', 'agent': 'geo', 'time': {'created': 1710000000000}},
                    'parts': [{'type': 'text', 'text': '正在分析\n\n已完成'}],
                }
            ],
        ],
    )
    emitted: list[EventEnvelope] = []

    async def emit(envelope: EventEnvelope) -> None:
        emitted.append(envelope)

    await runtime._poll_session(
        runtime_session_id='runtime-session-title',
        request=RuntimeSessionRequest(
            session_id='session-1',
            prompt='对北京出租车轨迹做 KDE 热点分析',
            workspace_path=tmp_path,
        ),
        emit=emit,
    )

    assert any(
        envelope.type == 'session.title'
        and isinstance(envelope.payload, dict)
        and envelope.payload.get('title') == 'Runtime generated title'
        and envelope.payload.get('runtime_session_id') == 'runtime-session-title'
        for envelope in emitted
    )


@pytest.mark.asyncio
async def test_submit_message_runs_async_and_writes_manifest_artifact(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    service = SessionService(
        settings=settings,
        title_provider=StubTitleProvider(),
        runtime_client=StubAgentRuntimeClient([
            [
                EventEnvelope(type='session.messages', payload=[
                    {'id': 'msg-user-1', 'role': 'user', 'agent': 'geo', 'created_at': '2026-03-25T00:00:00+00:00', 'parts': [{'type': 'text', 'text': '对北京出租车轨迹做 KDE 热点分析'}]},
                    {'id': 'msg-assistant-1', 'role': 'assistant', 'agent': 'geo', 'created_at': '2026-03-25T00:00:01+00:00', 'parts': [{'type': 'tool', 'tool': 'geospatial_record_run_evidence', 'state': {'status': 'completed', 'input': {'record_type': 'artifact', 'title': 'KDE 运行清单'}, 'meta': {'tool_family': 'evidence', 'tool_label': '登记运行证据'}, 'output': '{"status":"completed"}'}}]},
                ]),
                EventEnvelope(type='session.plan', payload=[
                    {'id': 'plan-1', 'label': '规范化地理分析任务', 'status': 'completed'},
                    {'id': 'plan-2', 'label': '执行通用预处理', 'status': 'in_progress'},
                ]),
                EventEnvelope(type='session.geospatial_task', payload=make_runtime_task('对北京出租车轨迹做 KDE 热点分析').model_dump(mode='json')),
                EventEnvelope(type='session.verification', payload=[VerificationEntry(id='verification-1', code='runtime_bundle_ready', title='内置 KDE 智能体组已装载', status='passed', detail='detail').model_dump()]),
                EventEnvelope(type='session.artifact', payload=Artifact(id='artifact-1', title='KDE 运行清单', path='run-manifest.json', kind='manifest', analysis_type='kde').model_dump(mode='json')),
                EventEnvelope(type='session.artifact', payload=Artifact(id='artifact-2', title='KDE 热力图 (SVG)', path='outputs/kde-heatmap.svg', kind='map', analysis_type='kde').model_dump(mode='json')),
                EventEnvelope(type='session.status', payload={'status': 'completed'}),
            ]
        ]),
    )
    session = await service.create_session()

    await service.submit_message(session.id, '对北京出租车轨迹做 KDE 热点分析')

    running = service.get_session(session.id)
    assert running.status in {'running', 'waiting_for_input'}
    assert any(entry.status == 'in_progress' for entry in running.plan)

    await service.wait_for_run(session.id)

    completed = service.get_session(session.id)
    assert completed.status == 'completed'
    assert completed.geospatial_task is not None
    assert completed.geospatial_task.runtime.bundle_id == 'app-geospatial-agent-knowledge'
    assert any(artifact.title == 'KDE 运行清单' for artifact in completed.artifacts)
    assert any(artifact.title == 'KDE 热力图 (SVG)' for artifact in completed.artifacts)
    assert completed.runtime_session_id == 'runtime-session-1'
    assert len(completed.messages) >= 4
    assert any(part.type == 'todo' for message in completed.messages for part in message.parts)
    assert any(part.type == 'verification' for message in completed.messages for part in message.parts)
    assert not any(part.type == 'artifact' for message in completed.messages for part in message.parts)
    assert completed.messages[1].parts[0].type == 'tool'


@pytest.mark.asyncio
async def test_submit_message_preserves_existing_artifacts_for_followup_runs(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    service = SessionService(
        settings=settings,
        title_provider=StubTitleProvider(),
        runtime_client=StubAgentRuntimeClient([
            [
                EventEnvelope(type='session.artifact', payload=Artifact(id='artifact-new', title='补充说明', path='outputs/followup.md', kind='report', artifact_stage='final').model_dump(mode='json')),
                EventEnvelope(type='session.status', payload={'status': 'completed'}),
            ]
        ]),
    )
    session = await service.create_session()
    current = service.get_session(session.id)
    current.artifacts = [
        Artifact(id='artifact-report', title='原始报告', path='outputs/report.md', kind='report', artifact_stage='final'),
        Artifact(id='artifact-map', title='原始地图', path='outputs/map.png', kind='map', artifact_stage='final'),
    ]
    service.store.save_session(current)

    await service.submit_message(session.id, '补充说明并输出新产物')
    await service.wait_for_run(session.id)

    updated = service.get_session(session.id)
    context = service.store.load_geospatial_session_context(updated.geospatial_context_id)

    assert [artifact.title for artifact in updated.artifacts] == ['原始报告', '原始地图', '补充说明']
    assert context is not None
    assert [artifact.title for artifact in context.artifacts] == ['原始报告', '原始地图', '补充说明']


@pytest.mark.asyncio
async def test_submit_message_does_not_seed_backend_placeholder_plan_before_runtime_events(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    service = SessionService(
        settings=settings,
        title_provider=StubTitleProvider(),
        runtime_client=StubAgentRuntimeClient([[]]),
    )
    session = await service.create_session()

    await service.submit_message(session.id, '对北京出租车轨迹做 KDE 热点分析')

    running = service.get_session(session.id)
    assert running.plan == []


@pytest.mark.asyncio
async def test_runtime_message_deltas_and_timeline_entries_are_merged_into_session_state(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    service = SessionService(
        settings=settings,
        title_provider=StubTitleProvider(),
        runtime_client=StubAgentRuntimeClient([
            [
                EventEnvelope(type='session.message_delta', payload={
                    'id': 'msg-assistant-1',
                    'role': 'assistant',
                    'agent': 'geo',
                    'created_at': '2026-03-28T00:00:01+00:00',
                    'parts': [{'type': 'text', 'text': '正在规范化请求'}],
                }),
                EventEnvelope(type='session.timeline_entry', payload={
                    'id': 'timeline-1',
                    'kind': 'status',
                    'text': '正在规范化地理任务',
                    'created_at': '2026-03-28T00:00:01+00:00',
                }),
                EventEnvelope(type='session.message_delta', payload={
                    'id': 'msg-assistant-1',
                    'role': 'assistant',
                    'agent': 'geo',
                    'created_at': '2026-03-28T00:00:01+00:00',
                    'parts': [{'type': 'text', 'text': '正在规范化请求\n\n已完成预处理。'}],
                }),
                EventEnvelope(type='session.status', payload={'status': 'completed'}),
            ]
        ]),
    )
    session = await service.create_session()

    await service.submit_message(session.id, '对北京出租车轨迹做 KDE 热点分析')
    await service.wait_for_run(session.id)

    updated = service.get_session(session.id)
    assistant = next(message for message in updated.messages if message.role == 'assistant')
    assert assistant.parts[0].text == '正在规范化请求\n\n已完成预处理。'
    assert any(entry.text == '正在规范化地理任务' for entry in updated.timeline)


@pytest.mark.asyncio
async def test_unknown_study_area_blocks_then_resumes_after_answer(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    service = SessionService(
        settings=settings,
        title_provider=StubTitleProvider(),
        runtime_client=StubAgentRuntimeClient([
            [
                EventEnvelope(type='session.geospatial_task', payload=make_runtime_task('对未知片区做 KDE 热点分析', stage='blocked').model_dump(mode='json')),
                EventEnvelope(type='session.question', payload=Question(id='question-1', prompt='未识别研究区，是否改用默认的北京市区县边界继续执行 KDE 分析？').model_dump()),
                EventEnvelope(type='session.status', payload={'status': 'waiting_for_input'}),
            ],
            [
                EventEnvelope(type='session.geospatial_task', payload=make_runtime_task('对未知片区做 KDE 热点分析', stage='completed').model_dump(mode='json')),
                EventEnvelope(type='session.verification', payload=[VerificationEntry(id='verification-2', code='study_area_repaired_from_answer', title='已根据回答修复研究区设置', status='passed', detail='detail').model_dump()]),
                EventEnvelope(type='session.status', payload={'status': 'completed'}),
            ],
        ]),
    )
    session = await service.create_session()

    question = await service.submit_message(session.id, '对未知片区做 KDE 热点分析')

    waiting = service.get_session(session.id)
    assert waiting.status == 'waiting_for_input'
    assert question is not None
    assert waiting.question is not None
    assert waiting.geospatial_task is not None
    assert waiting.geospatial_task.stage == 'blocked'

    await service.answer_question(session.id, question.id, '使用默认北京市区县边界')
    await service.wait_for_run(session.id)

    resumed = service.get_session(session.id)
    assert resumed.status == 'completed'
    assert resumed.question is None
    assert any(entry.code == 'study_area_repaired_from_answer' for entry in resumed.verification)


@pytest.mark.asyncio
async def test_completed_session_artifacts_are_restored_after_service_restart(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    service = SessionService(
        settings=settings,
        title_provider=StubTitleProvider(),
        runtime_client=StubAgentRuntimeClient([
            [
                EventEnvelope(type='session.geospatial_task', payload=make_runtime_task('对北京出租车轨迹做 KDE 热点分析', stage='completed').model_dump(mode='json')),
                EventEnvelope(type='session.verification', payload=[VerificationEntry(id='verification-1', code='runtime_bundle_ready', title='内置 KDE 智能体组已装载', status='passed', detail='detail').model_dump()]),
                EventEnvelope(type='session.artifact', payload=Artifact(id='artifact-1', title='KDE 运行清单', path='run-manifest.json', kind='manifest', analysis_type='kde').model_dump(mode='json')),
                EventEnvelope(type='session.status', payload={'status': 'completed'}),
            ]
        ]),
    )
    session = await service.create_session()

    await service.submit_message(session.id, '对北京出租车轨迹做 KDE 热点分析')
    await service.wait_for_run(session.id)

    restarted = SessionService(settings=settings, title_provider=StubTitleProvider())
    restored = restarted.get_session(session.id)

    assert restored.status == 'completed'
    assert any(artifact.title == 'KDE 运行清单' for artifact in restored.artifacts)
    assert restored.runtime_session_id == 'runtime-session-1'
    assert restored.geospatial_task is not None
    assert restored.geospatial_task.analysis_type == 'kde'
    assert any(entry.code == 'runtime_bundle_ready' for entry in restored.verification)
    assert restored.messages
    assert not any(part.type == 'artifact' for message in restored.messages for part in message.parts)
    assert restored.plan == []


@pytest.mark.asyncio
async def test_submit_message_fails_explicitly_when_real_runtime_not_ready(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    service = SessionService(
        settings=settings,
        title_provider=StubTitleProvider(),
        runtime_client=StubAgentRuntimeClient([], ready=False, detail='provider not configured'),
    )
    session = await service.create_session()

    await service.submit_message(session.id, '对北京出租车轨迹做 KDE 热点分析')

    failed = service.get_session(session.id)
    assert failed.status == 'failed'
    assert any('provider not configured' in entry.text for entry in failed.timeline if entry.kind == 'status')
    assert any(issue.type == 'runtime_error' and 'provider not configured' in issue.detail for issue in failed.issues)
    assert any(part.type == 'issue' for message in failed.messages for part in message.parts)


@pytest.mark.asyncio
async def test_runtime_start_failure_records_issue(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    service = SessionService(
        settings=settings,
        title_provider=StubTitleProvider(),
        runtime_client=StartFailingRuntimeClient(),
    )
    session = await service.create_session()

    await service.submit_message(session.id, '对北京出租车轨迹做 KDE 热点分析')

    failed = service.get_session(session.id)
    assert failed.status == 'failed'
    assert any(issue.type == 'runtime_crash' and '启动失败' in issue.title for issue in failed.issues)


@pytest.mark.asyncio
async def test_runtime_execution_exception_records_issue_and_restores(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    service = SessionService(
        settings=settings,
        title_provider=StubTitleProvider(),
        runtime_client=FailingRunRuntimeClient(),
    )
    session = await service.create_session()

    await service.submit_message(session.id, '对北京出租车轨迹做 KDE 热点分析')
    await service.wait_for_run(session.id)

    failed = service.get_session(session.id)
    restored = service.store.load_session(session.id)

    assert failed.status == 'failed'
    assert any(issue.type == 'runtime_error' and issue.runtime_session_id == 'runtime-session-1' for issue in failed.issues)
    assert any(part.type == 'issue' for message in failed.messages for part in message.parts)
    assert restored is not None
    assert restored.issues[0].type == 'runtime_error'
    assert any(part.type == 'issue' for message in restored.messages for part in message.parts)


@pytest.mark.asyncio
async def test_opencode_process_exit_records_runtime_crash_issue(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    service = SessionService(
        settings=settings,
        title_provider=StubTitleProvider(),
        runtime_client=FailingRunRuntimeClient(stopped=True),
    )
    session = await service.create_session()

    await service.submit_message(session.id, '对北京出租车轨迹做 KDE 热点分析')
    await service.wait_for_run(session.id)

    failed = service.get_session(session.id)
    assert failed.status == 'failed'
    assert any(issue.type == 'runtime_crash' and issue.source == 'opencode' for issue in failed.issues)


@pytest.mark.asyncio
async def test_interrupt_session_returns_active_run_to_idle_with_timeline_record(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    runtime_client = BlockingRuntimeClient()
    service = SessionService(
        settings=settings,
        title_provider=StubTitleProvider(),
        runtime_client=runtime_client,
    )
    session = await service.create_session()

    await service.submit_message(session.id, '对北京出租车轨迹做 KDE 热点分析')
    await asyncio.wait_for(runtime_client.run_started.wait(), timeout=1)

    await service.interrupt_session(session.id)

    interrupted = service.get_session(session.id)
    assert interrupted.status == 'idle'
    assert runtime_client.run_cancelled.is_set() is True
    assert runtime_client.aborted_runtime_sessions == ['runtime-session-1']
    assert any('用户已中断当前任务' in entry.text for entry in interrupted.timeline if entry.kind == 'status')
    assert any(issue.type == 'user_interrupt' and issue.severity == 'info' for issue in interrupted.issues)
    assert any(part.type == 'issue' for message in interrupted.messages for part in message.parts)
    assert session.id not in service.active_runs


@pytest.mark.asyncio
async def test_interrupt_session_keeps_idle_transition_when_runtime_finishes_before_local_cancel(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    runtime_client = FinishingAbortRuntimeClient()
    service = SessionService(
        settings=settings,
        title_provider=StubTitleProvider(),
        runtime_client=runtime_client,
    )
    session = await service.create_session()

    await service.submit_message(session.id, '对北京出租车轨迹做 KDE 热点分析')
    await asyncio.wait_for(runtime_client.run_started.wait(), timeout=1)

    await service.interrupt_session(session.id)

    interrupted = service.get_session(session.id)
    assert interrupted.status == 'idle'
    assert runtime_client.aborted_runtime_sessions == ['runtime-session-1']
    assert any('用户已中断当前任务' in entry.text for entry in interrupted.timeline if entry.kind == 'status')
    assert any(issue.type == 'user_interrupt' for issue in interrupted.issues)


@pytest.mark.asyncio
async def test_interrupt_session_uses_inflight_runtime_request_when_session_event_has_not_arrived(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    runtime_client = RequestTrackingRuntimeClient()
    service = SessionService(
        settings=settings,
        title_provider=StubTitleProvider(),
        runtime_client=runtime_client,
    )
    session = await service.create_session()

    await service.submit_message(session.id, '对北京出租车轨迹做 KDE 热点分析')
    await asyncio.wait_for(runtime_client.run_started.wait(), timeout=1)

    assert service.get_session(session.id).runtime_session_id is None

    await service.interrupt_session(session.id)

    interrupted = service.get_session(session.id)
    assert interrupted.status == 'idle'
    assert runtime_client.aborted_runtime_sessions == ['runtime-session-1']
    assert runtime_client.run_cancelled.is_set() is True
    assert any(issue.type == 'user_interrupt' for issue in interrupted.issues)


@pytest.mark.asyncio
async def test_interrupt_session_still_unwinds_local_run_when_runtime_abort_fails(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    runtime_client = FailingAbortRuntimeClient()
    service = SessionService(
        settings=settings,
        title_provider=StubTitleProvider(),
        runtime_client=runtime_client,
    )
    session = await service.create_session()

    await service.submit_message(session.id, '对北京出租车轨迹做 KDE 热点分析')
    await asyncio.wait_for(runtime_client.run_started.wait(), timeout=1)

    await service.interrupt_session(session.id)

    interrupted = service.get_session(session.id)
    assert interrupted.status == 'idle'
    assert runtime_client.aborted_runtime_sessions == ['runtime-session-1']
    assert runtime_client.run_cancelled.is_set() is True
    assert any(issue.type == 'user_interrupt' and issue.severity == 'warning' and 'abort failed' in issue.detail for issue in interrupted.issues)


@pytest.mark.asyncio
async def test_interrupt_session_unwinds_orphaned_running_session_after_restart(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    initial_service = SessionService(
        settings=settings,
        title_provider=StubTitleProvider(),
        runtime_client=StubAgentRuntimeClient([]),
    )
    session = await initial_service.create_session()
    session.status = 'running'
    session.runtime_session_id = 'runtime-session-1'
    initial_service.store.save_session(session)

    runtime_client = RequestTrackingRuntimeClient()
    restarted_service = SessionService(
        settings=settings,
        title_provider=StubTitleProvider(),
        runtime_client=runtime_client,
    )

    await restarted_service.interrupt_session(session.id)

    interrupted = restarted_service.get_session(session.id)
    assert interrupted.status == 'idle'
    assert runtime_client.aborted_runtime_sessions == ['runtime-session-1']
    assert any(issue.type == 'user_interrupt' for issue in interrupted.issues)


@pytest.mark.asyncio
async def test_interrupt_session_unwinds_orphaned_running_session_without_runtime_id(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    initial_service = SessionService(
        settings=settings,
        title_provider=StubTitleProvider(),
        runtime_client=StubAgentRuntimeClient([]),
    )
    session = await initial_service.create_session()
    session.status = 'running'
    initial_service.store.save_session(session)

    restarted_service = SessionService(
        settings=settings,
        title_provider=StubTitleProvider(),
        runtime_client=RequestTrackingRuntimeClient(),
    )

    await restarted_service.interrupt_session(session.id)

    interrupted = restarted_service.get_session(session.id)
    assert interrupted.status == 'idle'
    assert any(issue.type == 'user_interrupt' for issue in interrupted.issues)


@pytest.mark.asyncio
async def test_submit_message_aborts_existing_runtime_session_before_starting_replacement_run(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    runtime_client = ReplacementRuntimeClient()
    service = SessionService(
        settings=settings,
        title_provider=StubTitleProvider(),
        runtime_client=runtime_client,
    )
    session = await service.create_session()

    await service.submit_message(session.id, '第一条指令')
    await asyncio.wait_for(runtime_client.run_started.wait(), timeout=1)

    await service.submit_message(session.id, '第二条指令')
    await service.wait_for_run(session.id)

    updated = service.get_session(session.id)
    assert runtime_client.aborted_runtime_sessions == ['runtime-session-1']
    assert runtime_client.first_run_cancelled.is_set() is True
    assert updated.status == 'completed'
    assert updated.runtime_session_id == 'runtime-session-2'
    assert updated.messages[-1].parts[0].text == '第二条指令'


@pytest.mark.asyncio
async def test_interrupt_session_preserves_completed_status_if_run_finishes_during_abort(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    runtime_client = CompletingAbortRuntimeClient()
    service = SessionService(
        settings=settings,
        title_provider=StubTitleProvider(),
        runtime_client=runtime_client,
    )
    session = await service.create_session()

    await service.submit_message(session.id, '对北京出租车轨迹做 KDE 热点分析')
    await asyncio.wait_for(runtime_client.run_started.wait(), timeout=1)

    await service.interrupt_session(session.id)

    updated = service.get_session(session.id)
    assert updated.status == 'completed'
    assert runtime_client.aborted_runtime_sessions == ['runtime-session-1']
    assert not any('用户已中断当前任务' in entry.text for entry in updated.timeline if entry.kind == 'status')
    assert not any(issue.type == 'user_interrupt' for issue in updated.issues)


@pytest.mark.asyncio
async def test_session_persists_attached_data_directories_and_passes_them_to_runtime(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    runtime_client = StubAgentRuntimeClient([[EventEnvelope(type='session.status', payload={'status': 'completed'})]])
    service = SessionService(
        settings=settings,
        title_provider=StubTitleProvider(),
        runtime_client=runtime_client,
    )
    session = await service.create_session()

    await service.update_attached_data_directories(
        session.id,
        [
            {'id': 'dir-1', 'path': '/data/beijing-fcd', 'enabled': True},
            {'id': 'dir-2', 'path': '/data/backup', 'enabled': False},
        ],
    )
    await service.submit_message(session.id, '对北京出租车轨迹做 KDE 热点分析')
    await service.wait_for_run(session.id)

    updated = service.get_session(session.id)
    assert updated.attached_data_directories[0].path == '/data/beijing-fcd'
    assert runtime_client.requests[0]['attached_data_directories'][0]['path'] == '/data/beijing-fcd'

    restarted = SessionService(settings=settings, title_provider=StubTitleProvider(), runtime_client=StubAgentRuntimeClient([]))
    restored = restarted.get_session(session.id)
    assert restored.attached_data_directories[0].path == '/data/beijing-fcd'


@pytest.mark.asyncio
async def test_attached_data_directories_collapse_overlapping_parent_and_child_paths(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    service = SessionService(
        settings=settings,
        title_provider=StubTitleProvider(),
        runtime_client=StubAgentRuntimeClient([]),
    )
    session = await service.create_session()
    parent = tmp_path / 'data-root'
    child = parent / 'nested'
    child.mkdir(parents=True)

    await service.update_attached_data_directories(
        session.id,
        [
            {'id': 'dir-child', 'path': str(child), 'enabled': True, 'label': '子目录'},
            {'id': 'dir-parent', 'path': str(parent), 'enabled': True, 'label': '父目录'},
        ],
    )

    updated = service.get_session(session.id)

    assert [(item.path, item.label) for item in updated.attached_data_directories] == [(str(parent.resolve()), '父目录')]


@pytest.mark.asyncio
async def test_submit_message_creates_and_persists_geospatial_session_context(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    runtime_client = StubAgentRuntimeClient([[EventEnvelope(type='session.status', payload={'status': 'completed'})]])
    service = SessionService(
        settings=settings,
        title_provider=StubTitleProvider(),
        runtime_client=runtime_client,
    )
    session = await service.create_session()

    await service.update_attached_data_directories(
        session.id,
        [{'id': 'dir-1', 'path': '/data/beijing-fcd', 'enabled': True}],
    )
    await service.submit_message(session.id, '对北京出租车轨迹做 KDE 热点分析')
    await service.wait_for_run(session.id)

    updated = service.get_session(session.id)
    context = service.store.load_geospatial_session_context(updated.geospatial_context_id)

    assert updated.geospatial_context_id is not None
    assert context is not None
    assert context.session_id == updated.id
    assert context.prompt == '对北京出租车轨迹做 KDE 热点分析'
    assert context.workspace_path == updated.workspace_path
    assert context.attached_data_directories[0].path == '/data/beijing-fcd'
    assert runtime_client.requests[0]['geospatial_context_id'] == updated.geospatial_context_id

    restarted = SessionService(settings=settings, title_provider=StubTitleProvider(), runtime_client=StubAgentRuntimeClient([]))
    restored = restarted.get_session(session.id)
    restored_context = restarted.store.load_geospatial_session_context(restored.geospatial_context_id)

    assert restored.geospatial_context_id == updated.geospatial_context_id
    assert restored_context is not None
    assert restored_context.session_id == updated.id


@pytest.mark.asyncio
async def test_beijing_fcd_kde_validation_remains_reproducible_after_session_reload(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    runtime_client = GeoCliRuntimeClient(settings)
    service = SessionService(
        settings=settings,
        title_provider=StubTitleProvider(),
        runtime_client=runtime_client,
    )
    session = await service.create_session()

    await service.submit_message(session.id, '对北京出租车轨迹做 KDE 热点分析，使用默认北京市区县边界')
    await service.wait_for_run(session.id)

    completed = service.get_session(session.id)
    manifest = next(artifact for artifact in completed.artifacts if artifact.title == 'KDE 运行清单')
    claim_trace = next(artifact for artifact in completed.artifacts if artifact.title == 'Claim Trace')
    workspace = Path(completed.workspace_path or '')
    assert not Path(manifest.path).is_absolute()
    assert not Path(claim_trace.path).is_absolute()
    assert (workspace / manifest.path).exists()
    assert (workspace / claim_trace.path).exists()

    restarted = SessionService(settings=settings, title_provider=StubTitleProvider(), runtime_client=StubAgentRuntimeClient([]))
    restored = restarted.get_session(session.id)
    restored_manifest = next(artifact for artifact in restored.artifacts if artifact.title == 'KDE 运行清单')
    restored_claim_trace = next(artifact for artifact in restored.artifacts if artifact.title == 'Claim Trace')
    restored_workspace = Path(restored.workspace_path or '')

    assert restored.status == 'completed'
    assert (restored_workspace / restored_manifest.path).exists()
    assert (restored_workspace / restored_claim_trace.path).exists()
    assert any(entry.code == 'kde_outputs_ready' for entry in restored.verification)
