from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.models import Artifact, ChatMessage, ChatMessagePart, EventEnvelope, GeospatialPreprocessing, GeospatialSessionContext, GeospatialTask, OperatorMetadata, RuntimeProfile, Question, RuntimeStatus, VerificationEntry
from app.main import app as exported_app, create_app, serialize_sse_event
from app.services.runtime import RuntimeManager
from app.services.sessions import SessionService


class StubRuntimeClient:
    def __init__(self, scripted_runs: list[list[EventEnvelope]] | None = None) -> None:
        self.scripted_runs = scripted_runs or []
        self.started = False
        self.stopped = False
        self.start_calls = 0
        self.stop_calls = 0
        self.requests: list[dict[str, object]] = []

    @property
    def is_ready(self) -> bool:
        return True

    async def start(self) -> None:
        self.started = True
        self.start_calls += 1

    async def stop(self) -> None:
        self.stopped = True
        self.stop_calls += 1

    def status(self) -> RuntimeStatus:
        return RuntimeStatus(status='ready', label='opencode-runtime', detail='server ready')

    async def run_session(self, request, emit):
        self.requests.append({
            'session_id': request.session_id,
            'prompt': request.prompt,
            'attached_data_directories': request.attached_data_directories or [],
        })
        for envelope in self.scripted_runs.pop(0):
            await asyncio.sleep(0)
            await emit(envelope)
        return {'runtime_session_id': 'runtime-session-1', 'trace_path': 'runtime/trace.jsonl'}


class BlockingRuntimeClient(StubRuntimeClient):
    def __init__(self) -> None:
        super().__init__([])
        self.run_started = asyncio.Event()
        self.run_cancelled = asyncio.Event()
        self.aborted_runtime_sessions: list[str] = []

    async def run_session(self, request, emit):
        await emit(EventEnvelope(type='session.runtime_session', payload={'runtime_session_id': 'runtime-session-1'}))
        self.run_started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            self.run_cancelled.set()
            raise

    async def abort_session(self, runtime_session_id: str) -> None:
        self.aborted_runtime_sessions.append(runtime_session_id)


class SlowStartingRuntimeClient(StubRuntimeClient):
    def __init__(self) -> None:
        super().__init__([])
        self.started = False

    @property
    def is_ready(self) -> bool:
        return False

    async def start(self) -> None:
        self.started = True
        await asyncio.Future()

    def status(self) -> RuntimeStatus:
        return RuntimeStatus(status='starting', label='opencode-runtime', detail='OpenCode runtime is starting.')


class LifecycleRuntimeManager:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True


class LifecycleSessionService:
    def __init__(self, *, shutdown_error: Exception | None = None) -> None:
        self.shutdown_error = shutdown_error
        self.shutdown_called = False

    async def shutdown(self) -> None:
        self.shutdown_called = True
        if self.shutdown_error is not None:
            raise self.shutdown_error


def make_runtime_task(prompt: str, stage: str = 'completed') -> GeospatialTask:
    return GeospatialTask(
        id='task-runtime-fixture',
        prompt=prompt,
        analysis_type='kde',
        stage=stage,
        runtime=RuntimeProfile(
            bundle_id='app-geospatial-agent-knowledge',
            label='Runtime geospatial agent bundle',
            tools=['get_session_context', 'update_todos', 'record_run_evidence'],
        ),
        preprocessing=GeospatialPreprocessing(target_crs='EPSG:32650'),
        operator=OperatorMetadata(name='kde', stage=stage),
    )


def test_create_app_uses_injected_settings_for_isolated_storage(isolated_settings: Settings) -> None:
    isolated_app = create_app(isolated_settings)

    assert isolated_app.state.settings == isolated_settings
    assert isolated_app.state.session_service.settings.database_path == isolated_settings.database_path
    assert isolated_app.state.session_service.settings.workspace_root == isolated_settings.workspace_root
    assert isolated_app.state.runtime_manager.settings.state_dir == isolated_settings.state_dir
    assert isolated_app.state.runtime_manager.runtime_client is isolated_app.state.session_service.runtime_client


@pytest.mark.asyncio
async def test_lifespan_uses_one_shared_runtime_client(isolated_settings: Settings) -> None:
    isolated_app = create_app(isolated_settings)
    runtime_client = StubRuntimeClient()
    isolated_app.state.runtime_manager = RuntimeManager(settings=isolated_settings, state_dir=None, runtime_client=runtime_client)
    isolated_app.state.session_service = SessionService(settings=isolated_settings, runtime_client=runtime_client)

    async with isolated_app.router.lifespan_context(isolated_app):
        assert runtime_client.start_calls == 1
        assert isolated_app.state.runtime_manager.runtime_client is isolated_app.state.session_service.runtime_client

    assert runtime_client.stop_calls == 1


@pytest.mark.asyncio
async def test_create_app_exposes_backend_routes_for_isolated_instances(isolated_settings: Settings) -> None:
    isolated_app = create_app(isolated_settings)
    transport = ASGITransport(app=isolated_app)

    async with AsyncClient(transport=transport, base_url='http://testserver') as async_client:
        response = await async_client.get('/')

    assert response.status_code == 204


@pytest.mark.asyncio
async def test_exported_app_registers_backend_routes_for_uvicorn_entrypoint() -> None:
    transport = ASGITransport(app=exported_app)

    async with AsyncClient(transport=transport, base_url='http://testserver') as async_client:
        response = await async_client.get('/api/health')

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_lifespan_stops_runtime_when_app_context_raises(isolated_settings: Settings) -> None:
    isolated_app = create_app(isolated_settings)
    runtime_manager = LifecycleRuntimeManager()
    session_service = LifecycleSessionService()
    isolated_app.state.runtime_manager = runtime_manager
    isolated_app.state.session_service = session_service

    with pytest.raises(RuntimeError, match='lifespan boom'):
        async with isolated_app.router.lifespan_context(isolated_app):
            assert runtime_manager.started is True
            raise RuntimeError('lifespan boom')

    assert session_service.shutdown_called is True
    assert runtime_manager.stopped is True


@pytest.mark.asyncio
async def test_lifespan_stops_runtime_when_session_shutdown_fails(isolated_settings: Settings) -> None:
    isolated_app = create_app(isolated_settings)
    runtime_manager = LifecycleRuntimeManager()
    session_service = LifecycleSessionService(shutdown_error=RuntimeError('shutdown boom'))
    isolated_app.state.runtime_manager = runtime_manager
    isolated_app.state.session_service = session_service

    with pytest.raises(RuntimeError, match='shutdown boom'):
        async with isolated_app.router.lifespan_context(isolated_app):
            assert runtime_manager.started is True

    assert session_service.shutdown_called is True
    assert runtime_manager.stopped is True


@pytest.mark.asyncio
async def test_health_reports_runtime_state(client: AsyncClient, runtime_manager: RuntimeManager) -> None:
    runtime_manager.runtime_client = StubRuntimeClient()
    response = await client.get('/api/health')

    assert response.status_code == 200
    payload = response.json()
    assert payload['app'] == 'ready'
    assert payload['runtime']['status'] == 'ready'
    assert payload['storage']['status'] == 'ready'
    assert payload['workspace']['status'] == 'ready'
    assert payload['provider']['status'] in {'ready', 'not_configured'}
    assert 'mcp' in payload


@pytest.mark.asyncio
async def test_health_reports_selected_deepseek_runtime_without_secret(isolated_settings: Settings) -> None:
    settings = isolated_settings.model_copy(
        update={
            'model_provider': 'deepseek',
            'deepseek_api_key': 'deepseek-secret',
            'deepseek_model': 'deepseek-v4-pro',
        }
    )
    isolated_app = create_app(settings)
    transport = ASGITransport(app=isolated_app)

    async with AsyncClient(transport=transport, base_url='http://testserver') as client:
        response = await client.get('/api/health')

    assert response.status_code == 200
    provider = response.json()['provider']
    assert provider['status'] == 'ready'
    assert provider['provider'] == 'deepseek'
    assert provider['model'] == 'deepseek-v4-pro'
    assert provider['opencode_model'] == 'deepseek/deepseek-v4-pro'
    assert provider['title_status'] == 'not_configured'
    assert 'api_key' not in provider
    assert 'deepseek-secret' not in {str(value) for value in provider.values()}


@pytest.mark.asyncio
async def test_health_does_not_block_on_runtime_start(isolated_settings: Settings) -> None:
    isolated_app = create_app(isolated_settings)
    runtime_client = SlowStartingRuntimeClient()
    isolated_app.state.runtime_manager.runtime_client = runtime_client
    transport = ASGITransport(app=isolated_app)

    async with AsyncClient(transport=transport, base_url='http://testserver') as async_client:
        response = await asyncio.wait_for(async_client.get('/api/health'), timeout=0.2)

    assert response.status_code == 200
    assert response.json()['runtime']['status'] == 'starting'
    assert runtime_client.started is False


@pytest.mark.asyncio
async def test_message_submission_is_rejected_while_geospatial_environment_provisions(isolated_settings: Settings) -> None:
    settings = isolated_settings.model_copy(update={'geospatial_python_auto_provision': True})
    isolated_app = create_app(settings)
    isolated_app.state.runtime_manager.runtime_client = StubRuntimeClient()
    isolated_app.state.runtime_manager._geospatial_environment_status = {
        'status': 'provisioning',
        'progress': 0.25,
        'logs': ['Resolving geospatial packages'],
    }
    transport = ASGITransport(app=isolated_app)

    async with AsyncClient(transport=transport, base_url='http://testserver') as async_client:
        create_response = await async_client.post('/api/sessions')
        session = create_response.json()
        response = await async_client.post(f"/api/sessions/{session['id']}/messages", json={'text': 'Run KDE now'})

    assert response.status_code == 409
    assert response.json()['detail']['reason'] == 'geospatial_environment_not_ready'
    assert response.json()['detail']['status'] == 'provisioning'


@pytest.mark.asyncio
async def test_session_rename_and_delete_endpoints(client: AsyncClient) -> None:
    create_response = await client.post('/api/sessions')
    session = create_response.json()

    rename_response = await client.patch(
        f"/api/sessions/{session['id']}",
        json={'title': '北京 FCD KDE 会话'},
    )
    list_response = await client.get('/api/sessions')
    delete_response = await client.delete(f"/api/sessions/{session['id']}")
    list_after_delete = await client.get('/api/sessions')

    assert rename_response.status_code == 200
    assert rename_response.json()['title'] == '北京 FCD KDE 会话'
    assert list_response.json()[0]['title'] == '北京 FCD KDE 会话'
    assert delete_response.status_code == 204
    assert all(item['id'] != session['id'] for item in list_after_delete.json())


@pytest.mark.asyncio
async def test_session_data_directory_endpoint_updates_session_metadata(client: AsyncClient) -> None:
    create_response = await client.post('/api/sessions')
    session = create_response.json()

    update_response = await client.put(
        f"/api/sessions/{session['id']}/data-directories",
        json={
            'items': [
                {'id': 'dir-1', 'path': '/data/beijing-fcd', 'enabled': True},
                {'id': 'dir-2', 'path': '/data/backup', 'enabled': False},
            ]
        },
    )

    assert update_response.status_code == 200
    payload = update_response.json()
    assert payload['attached_data_directories'][0]['path'] == '/data/beijing-fcd'


@pytest.mark.asyncio
async def test_headless_evaluation_api_flow_exports_run_state(
    client: AsyncClient,
    session_service: SessionService,
    tmp_path: Path,
) -> None:
    data_dir: Path = tmp_path / 'scenario-data'
    data_dir.mkdir()
    runtime_client = StubRuntimeClient([
        [
            EventEnvelope(type='session.plan_group', payload={
                'id': 'geo',
                'agent': 'geo',
                'label': 'Geo',
                'entries': [{'id': 'plan-1', 'label': 'Run unchanged prompt', 'status': 'completed'}],
                'updated_at': '2026-03-25T00:00:00+00:00',
            }),
            EventEnvelope(type='session.verification', payload=[
                VerificationEntry(
                    id='verification-1',
                    code='artifact_registered',
                    title='Artifact registered',
                    status='passed',
                    detail='The output artifact was registered.',
                ).model_dump()
            ]),
            EventEnvelope(type='session.artifact', payload=Artifact(
                id='artifact-1',
                title='Run artifact',
                path='outputs/run.txt',
                kind='text',
                format='txt',
            ).model_dump(mode='json')),
            EventEnvelope(type='session.status', payload={'status': 'completed'}),
        ]
    ])
    session_service.runtime_client = runtime_client
    create_response = await client.post('/api/sessions')
    session = create_response.json()
    workspace: Path = Path(session['workspace_path'])
    artifact_path: Path = workspace / 'outputs' / 'run.txt'
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text('evaluation artifact', encoding='utf-8')
    prompt = 'Run the benchmark prompt without rewriting it.'

    attach_response = await client.put(
        f"/api/sessions/{session['id']}/data-directories",
        json={'items': [{'id': 'scenario-pack', 'path': str(data_dir), 'enabled': True}]},
    )
    send_response = await client.post(
        f"/api/sessions/{session['id']}/messages",
        json={'text': prompt},
    )
    await session_service.wait_for_run(session['id'])
    session_response = await client.get(f"/api/sessions/{session['id']}")
    archive_response = await client.get(f"/api/sessions/{session['id']}/archive")
    artifact_response = await client.get(f"/api/sessions/{session['id']}/artifacts/artifact-1/content")

    resumed = session_response.json()
    archive = archive_response.json()
    assert attach_response.status_code == 200
    assert send_response.status_code == 202
    assert session_response.status_code == 200
    assert archive_response.status_code == 200
    assert artifact_response.status_code == 200
    assert artifact_response.text == 'evaluation artifact'
    assert runtime_client.requests[0]['prompt'] == prompt
    attached_dirs = runtime_client.requests[0]['attached_data_directories']
    assert isinstance(attached_dirs, list)
    assert attached_dirs[0]['path'] == str(data_dir.resolve())
    assert resumed['status'] == 'completed'
    assert resumed['runtime_trace_path'] == 'runtime/trace.jsonl'
    assert resumed['plan_groups'][0]['entries'][0]['label'] == 'Run unchanged prompt'
    assert resumed['verification'][0]['code'] == 'artifact_registered'
    assert resumed['artifacts'][0]['id'] == 'artifact-1'
    assert archive['schema'] == 'geo-agent.session-archive.v1'
    assert archive['session']['id'] == session['id']
    assert archive['runtime_trace']['trace_path'] == 'runtime/trace.jsonl'
    assert archive['session']['messages'][0]['parts'][0]['text'] == prompt


@pytest.mark.asyncio
async def test_session_evidence_records_endpoint_exports_raw_records(
    client: AsyncClient,
    session_service: SessionService,
) -> None:
    session_service.runtime_client = StubRuntimeClient([
        [EventEnvelope(type='session.status', payload={'status': 'completed'})]
    ])
    create_response = await client.post('/api/sessions')
    session_id = create_response.json()['id']
    await client.post(
        f'/api/sessions/{session_id}/messages',
        json={'text': 'Record evidence for evaluation export.'},
    )
    await session_service.wait_for_run(session_id)
    session = session_service.get_session(session_id)
    assert session.geospatial_context_id is not None
    session_service.store.append_geospatial_evidence_record({
        'id': 'evidence-1',
        'session_context_id': session.geospatial_context_id,
        'record_type': 'verification_fact',
        'title': 'CRS checked',
        'created_at': '2026-03-25T00:00:00+00:00',
        'data': {'crs': 'EPSG:32650'},
    })

    response = await client.get(f'/api/sessions/{session_id}/evidence-records')

    payload = response.json()
    assert response.status_code == 200
    assert payload['record_count'] == 1
    assert payload['items'][0]['id'] == 'evidence-1'
    assert payload['items'][0]['data']['crs'] == 'EPSG:32650'


@pytest.mark.asyncio
async def test_session_data_directory_endpoint_collapses_overlapping_paths(client: AsyncClient, tmp_path: Path) -> None:
    create_response = await client.post('/api/sessions')
    session = create_response.json()
    parent = tmp_path / 'data-root'
    child = parent / 'nested'
    child.mkdir(parents=True)

    update_response = await client.put(
        f"/api/sessions/{session['id']}/data-directories",
        json={
            'items': [
                {'id': 'dir-child', 'path': str(child), 'enabled': True, 'label': '子目录'},
                {'id': 'dir-parent', 'path': str(parent), 'enabled': True, 'label': '父目录'},
            ]
        },
    )

    assert update_response.status_code == 200
    payload = update_response.json()
    assert [(item['path'], item['label']) for item in payload['attached_data_directories']] == [(str(parent.resolve()), '父目录')]


@pytest.mark.asyncio
async def test_data_directory_browser_lists_child_directories(client: AsyncClient, isolated_settings: Settings) -> None:
    root = isolated_settings.resolved_workspace_root()
    source_dir = root / 'inputs'
    output_dir = root / 'outputs'
    source_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    response = await client.get('/api/data-directories/browser', params={'path': str(root)})

    assert response.status_code == 200
    payload = response.json()
    assert payload['current_path'] == str(root)
    assert payload['home_path']
    assert payload['cwd_path']
    assert [entry['name'] for entry in payload['entries']] == ['inputs', 'outputs']
    assert all(entry['is_dir'] is True for entry in payload['entries'])


@pytest.mark.asyncio
async def test_data_directory_browser_defaults_to_current_working_directory(client: AsyncClient) -> None:
    response = await client.get('/api/data-directories/browser')

    assert response.status_code == 200
    payload = response.json()
    assert payload['current_path'] == str(Path.cwd().resolve())


@pytest.mark.asyncio
async def test_recent_data_directories_are_deduplicated_from_sessions(client: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'data').mkdir()
    first = (await client.post('/api/sessions')).json()
    second = (await client.post('/api/sessions')).json()

    await client.put(
        f"/api/sessions/{first['id']}/data-directories",
        json={'items': [{'id': 'dir-1', 'path': '/data/beijing-fcd', 'enabled': True, 'label': '北京 FCD'}]},
    )
    await client.put(
        f"/api/sessions/{second['id']}/data-directories",
        json={
            'items': [
                {'id': 'dir-2', 'path': '/data/backup', 'enabled': True, 'label': '备用目录'},
                {'id': 'dir-3', 'path': '/data/beijing-fcd', 'enabled': True, 'label': '北京 FCD'},
            ]
        },
    )

    response = await client.get('/api/data-directories/recent')

    assert response.status_code == 200
    payload = response.json()
    assert [item['path'] for item in payload['items']] == [str((tmp_path / 'data').resolve()), '/data/backup', '/data/beijing-fcd']
    assert payload['items'][0]['label'] == '默认数据目录'


@pytest.mark.asyncio
async def test_workspace_open_endpoint_returns_no_content(client: AsyncClient, session_service: SessionService) -> None:
    async def noop(_workspace_path: str) -> None:
        return None

    session_service.workspace_manager.open_workspace = noop
    session = (await client.post('/api/sessions')).json()

    response = await client.post(f"/api/sessions/{session['id']}/workspace/open")

    assert response.status_code == 204


@pytest.mark.asyncio
async def test_artifact_open_endpoint_returns_no_content(client: AsyncClient, session_service: SessionService) -> None:
    opened_paths: list[str] = []

    async def record_open(workspace_path: str) -> None:
        opened_paths.append(workspace_path)

    session_service.workspace_manager.open_workspace = record_open
    session = await session_service.create_session()
    workspace = Path(session.workspace_path or '')
    artifact_path = workspace / 'outputs' / 'map.png'
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_bytes(b'png')
    session.artifacts = [
        Artifact(id='artifact-1', title='KDE 热点图', path='outputs/map.png', artifact_stage='final', display_hint='image')
    ]
    session_service.store.save_session(session)

    response = await client.post(f'/api/sessions/{session.id}/artifacts/artifact-1/open')

    assert response.status_code == 204
    assert opened_paths == [str(artifact_path.resolve())]


@pytest.mark.asyncio
async def test_session_archive_export_includes_evidence_without_artifact_contents(client: AsyncClient, session_service: SessionService) -> None:
    session = await session_service.create_session()
    workspace = Path(session.workspace_path or '')
    artifact_path = workspace / 'outputs' / 'run-manifest.json'
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text('SECRET_ARTIFACT_BYTES', encoding='utf-8')
    session.runtime_session_id = 'runtime-session-source'
    session.runtime_trace_path = '/tmp/runtime-trace.json'
    session.messages = [
        ChatMessage(
            id='msg-user-1',
            role='user',
            agent='geo',
            created_at=session.created_at,
            parts=[ChatMessagePart(type='text', text='Need a KDE run')],
        )
    ]
    session.artifacts = [
        Artifact(
            id='artifact-1',
            title='KDE 运行清单',
            path='outputs/run-manifest.json',
            kind='manifest',
            artifact_stage='final',
            display_hint='json',
            evidence_record_id='evidence-1',
        )
    ]
    session.geospatial_context_id = 'context-source'
    context = GeospatialSessionContext(
        id='context-source',
        session_id=session.id,
        runtime_session_id=session.runtime_session_id,
        prompt='Need a KDE run',
        workspace_path=str(workspace),
        artifacts=session.artifacts,
        updated_at=session.updated_at,
    )
    session_service.store.save_session(session)
    session_service.store.save_geospatial_session_context(context)
    session_service.store.append_geospatial_evidence_record({
        'id': 'evidence-1',
        'session_context_id': context.id,
        'record_type': 'parameter_snapshot',
        'title': 'KDE 参数',
        'data': {'bandwidth': 1200},
        'created_at': session.created_at.isoformat(),
    })

    response = await client.get(f'/api/sessions/{session.id}/archive')

    assert response.status_code == 200
    assert response.headers['content-disposition'].startswith('attachment;')
    archive = response.json()
    serialized = response.text
    assert archive['schema'] == 'geo-agent.session-archive.v1'
    assert archive['source']['session_id'] == session.id
    assert archive['source']['runtime_session_id'] == 'runtime-session-source'
    assert archive['session']['messages'][0]['parts'][0]['text'] == 'Need a KDE run'
    assert archive['session']['artifacts'][0]['path'] == 'outputs/run-manifest.json'
    assert archive['evidence_records'][0]['title'] == 'KDE 参数'
    assert 'SECRET_ARTIFACT_BYTES' not in serialized
    assert 'campaign_id' not in archive
    assert 'evaluation' not in archive


@pytest.mark.asyncio
async def test_session_archive_import_creates_read_only_session_and_rejects_invalid(client: AsyncClient) -> None:
    archive = {
        'schema': 'geo-agent.session-archive.v1',
        'exported_at': '2026-04-29T00:00:00+00:00',
        'source': {
            'session_id': 'session-source',
            'title': '北京 FCD KDE 会话',
            'runtime_session_id': 'runtime-source',
            'runtime_trace_path': '/tmp/source-trace.json',
        },
        'session': {
            'id': 'session-source',
            'title': '北京 FCD KDE 会话',
            'status': 'completed',
            'created_at': '2026-04-29T00:00:00+00:00',
            'updated_at': '2026-04-29T00:01:00+00:00',
            'workspace_path': '/tmp/source-workspace',
            'runtime_session_id': 'runtime-source',
            'runtime_trace_path': '/tmp/source-trace.json',
            'attached_data_directories': [],
            'messages': [
                {'id': 'msg-user-1', 'role': 'user', 'agent': 'geo', 'created_at': '2026-04-29T00:00:00+00:00', 'parts': [{'type': 'text', 'text': 'Need a KDE run'}]},
            ],
            'timeline': [],
            'plan': [],
            'plan_groups': [],
            'issues': [],
            'question': None,
            'artifacts': [
                {'id': 'artifact-1', 'title': 'KDE 运行清单', 'path': 'outputs/run-manifest.json', 'kind': 'manifest'},
            ],
            'geospatial_task': None,
            'verification': [],
        },
        'geospatial_context': {
            'id': 'context-source',
            'session_id': 'session-source',
            'runtime_session_id': 'runtime-source',
            'prompt': 'Need a KDE run',
            'workspace_path': '/tmp/source-workspace',
            'attached_data_directories': [],
            'verification': [],
            'artifacts': [],
            'updated_at': '2026-04-29T00:01:00+00:00',
        },
        'evidence_records': [
            {'id': 'evidence-1', 'session_context_id': 'context-source', 'record_type': 'claim_trace', 'title': '声明追踪', 'created_at': '2026-04-29T00:01:00+00:00'},
        ],
        'runtime_trace': {'runtime_session_id': 'runtime-source', 'trace_path': '/tmp/source-trace.json'},
        'ignored_future_field': {'ok': True},
    }

    response = await client.post('/api/session-archives/import', json={'archive': archive})
    list_response = await client.get('/api/sessions')
    invalid_response = await client.post('/api/session-archives/import', json={'archive': {'schema': 'geo-agent.session-archive.v999'}})

    assert response.status_code == 201
    imported = response.json()
    assert imported['id'] != 'session-source'
    assert imported['title'] == '北京 FCD KDE 会话'
    assert imported['read_only'] is True
    assert imported['workspace_path'] is None
    assert imported['runtime_session_id'] is None
    assert imported['runtime_trace_path'] is None
    assert imported['archive_metadata']['source']['session_id'] == 'session-source'
    assert imported['archive_metadata']['source']['runtime_session_id'] == 'runtime-source'
    assert imported['messages'][0]['parts'][0]['text'] == 'Need a KDE run'
    assert imported['artifacts'][0]['path'] == 'outputs/run-manifest.json'
    assert list_response.status_code == 200
    assert any(item['id'] == imported['id'] and item['read_only'] is True for item in list_response.json())
    assert invalid_response.status_code == 422


@pytest.mark.asyncio
async def test_imported_session_rejects_mutations_but_allows_delete(client: AsyncClient) -> None:
    archive = {
        'schema': 'geo-agent.session-archive.v1',
        'exported_at': '2026-04-29T00:00:00+00:00',
        'source': {'session_id': 'session-source', 'title': '归档会话'},
        'session': {
            'id': 'session-source',
            'title': '归档会话',
            'status': 'completed',
            'created_at': '2026-04-29T00:00:00+00:00',
            'updated_at': '2026-04-29T00:00:00+00:00',
            'workspace_path': '/tmp/source-workspace',
            'attached_data_directories': [],
            'messages': [],
            'timeline': [],
            'plan': [],
            'plan_groups': [],
            'issues': [],
            'question': None,
            'artifacts': [{'id': 'artifact-1', 'title': '地图', 'path': 'outputs/map.png', 'kind': 'map'}],
            'geospatial_task': None,
            'verification': [],
        },
        'geospatial_context': None,
        'evidence_records': [],
        'runtime_trace': {},
    }
    imported = (await client.post('/api/session-archives/import', json={'archive': archive})).json()
    session_id = imported['id']

    rename_response = await client.patch(f'/api/sessions/{session_id}', json={'title': '新标题'})
    message_response = await client.post(f'/api/sessions/{session_id}/messages', json={'text': 'continue'})
    data_response = await client.put(f'/api/sessions/{session_id}/data-directories', json={'items': []})
    workspace_response = await client.post(f'/api/sessions/{session_id}/workspace/open')
    artifact_response = await client.post(f'/api/sessions/{session_id}/artifacts/artifact-1/open')
    interrupt_response = await client.post(f'/api/sessions/{session_id}/interrupt')
    delete_response = await client.delete(f'/api/sessions/{session_id}')
    list_response = await client.get('/api/sessions')

    assert rename_response.status_code == 409
    assert message_response.status_code == 409
    assert data_response.status_code == 409
    assert workspace_response.status_code == 409
    assert artifact_response.status_code == 409
    assert interrupt_response.status_code == 409
    assert delete_response.status_code == 204
    assert all(item['id'] != session_id for item in list_response.json())


@pytest.mark.asyncio
async def test_data_directory_open_endpoint_returns_no_content(client: AsyncClient, session_service: SessionService, tmp_path: Path) -> None:
    opened_paths: list[str] = []

    async def record_open(workspace_path: str) -> None:
        opened_paths.append(workspace_path)

    session_service.workspace_manager.open_workspace = record_open
    target = tmp_path / 'open-me'
    target.mkdir()

    response = await client.post('/api/data-directories/open', json={'path': str(target)})

    assert response.status_code == 204
    assert opened_paths == [str(target.resolve())]


@pytest.mark.asyncio
async def test_session_lifecycle_and_metadata(client: AsyncClient, session_service: SessionService) -> None:
    session_service.runtime_client = StubRuntimeClient([
        [
            EventEnvelope(type='session.plan', payload=[
                {'id': 'plan-1', 'label': '规范化地理分析任务', 'status': 'completed'},
                {'id': 'plan-2', 'label': '执行通用预处理', 'status': 'completed'},
            ]),
            EventEnvelope(type='session.geospatial_task', payload=make_runtime_task('对北京出租车轨迹做 KDE 热点分析').model_dump(mode='json')),
            EventEnvelope(type='session.verification', payload=[
                VerificationEntry(id='verification-1', code='crs_mismatch_detected', title='检测到 CRS 不一致', status='warning', detail='detail').model_dump()
            ]),
            EventEnvelope(type='session.artifact', payload=Artifact(id='artifact-1', title='KDE 运行清单', path='run-manifest.json', kind='manifest', analysis_type='kde').model_dump(mode='json')),
            EventEnvelope(type='session.status', payload={'status': 'completed'}),
        ]
    ])
    create_response = await client.post('/api/sessions')
    session = create_response.json()

    send_response = await client.post(
        f"/api/sessions/{session['id']}/messages",
        json={'text': '对北京出租车轨迹做 KDE 热点分析'},
    )
    await session_service.wait_for_run(session['id'])
    list_response = await client.get('/api/sessions')
    resume_response = await client.get(f"/api/sessions/{session['id']}")

    assert create_response.status_code == 201
    assert send_response.status_code == 202
    assert list_response.status_code == 200
    assert resume_response.status_code == 200
    assert list_response.json()[0]['id'] == session['id']
    resumed = resume_response.json()
    assert resumed['question'] is None
    assert resumed['status'] == 'completed'
    assert resumed['geospatial_task']['analysis_type'] == 'kde'
    assert resumed['geospatial_task']['preprocessing']['target_crs'] == 'EPSG:32650'
    assert any(entry['code'] == 'crs_mismatch_detected' for entry in resumed['verification'])
    assert resumed['artifacts'][0]['analysis_type'] == 'kde'
    assert any(artifact['title'] == 'KDE 运行清单' for artifact in resumed['artifacts'])
    assert resumed['timeline'][-1]['kind'] == 'artifact'


@pytest.mark.asyncio
async def test_session_event_stream_emits_normalized_updates(client: AsyncClient, session_service: SessionService) -> None:
    session_service.runtime_client = StubRuntimeClient([
        [
            EventEnvelope(type='session.messages', payload=[
                {'id': 'msg-user-1', 'role': 'user', 'agent': 'geo', 'created_at': '2026-03-25T00:00:00+00:00', 'parts': [{'type': 'text', 'text': 'Need a KDE run'}]},
                {'id': 'msg-assistant-1', 'role': 'assistant', 'agent': 'geo', 'created_at': '2026-03-25T00:00:01+00:00', 'parts': [{'type': 'tool', 'tool': 'geospatial_record_run_evidence', 'state': {'status': 'completed', 'input': {'record_type': 'artifact', 'title': 'KDE 运行清单'}, 'meta': {'tool_family': 'evidence', 'tool_label': '登记运行证据'}, 'output': '{"status":"completed"}'}}]},
            ]),
            EventEnvelope(type='session.plan', payload=[{'id': 'plan-1', 'label': '规范化地理分析任务', 'status': 'completed'}]),
            EventEnvelope(type='session.geospatial_task', payload=make_runtime_task('Need a KDE run').model_dump(mode='json')),
            EventEnvelope(type='session.verification', payload=[VerificationEntry(id='verification-1', code='runtime_bundle_ready', title='内置 KDE 智能体组已装载', status='passed', detail='detail').model_dump()]),
            EventEnvelope(type='session.artifact', payload=Artifact(id='artifact-1', title='KDE 运行清单', path='run-manifest.json', kind='manifest', analysis_type='kde').model_dump(mode='json')),
            EventEnvelope(type='session.status', payload={'status': 'completed'}),
        ]
    ])
    session_response = await client.post('/api/sessions')
    session_id = session_response.json()['id']
    queue = await session_service.subscribe(session_id)

    await client.post(
        f'/api/sessions/{session_id}/messages',
        json={'text': 'Need a KDE run'},
    )
    await session_service.wait_for_run(session_id)

    envelopes: list[object] = []
    while True:
        envelope = await asyncio.wait_for(queue.get(), timeout=1)
        envelopes.append(envelope)
        if envelope.type == 'session.artifact':
            break
    serialized = [serialize_sse_event(envelope.type, envelope.payload) for envelope in envelopes]

    session_service.unsubscribe(session_id, queue)

    assert serialized[0]['event'] == 'session.status'
    assert 'session.status' in serialized[0]['data']
    assert any(item['event'] == 'session.timeline' for item in serialized)
    assert any(item['event'] == 'session.messages' for item in serialized)
    assert any(item['event'] == 'session.plan' for item in serialized)
    assert any(item['event'] == 'session.geospatial_task' for item in serialized)
    assert any(item['event'] == 'session.verification' for item in serialized)
    assert any(item['event'] == 'session.artifact' for item in serialized)


@pytest.mark.asyncio
async def test_session_issue_events_are_streamed_and_restored(client: AsyncClient, session_service: SessionService) -> None:
    issue_payload = {
        'id': 'issue-runtime-1',
        'type': 'runtime_error',
        'severity': 'error',
        'source': 'runtime',
        'title': '运行时执行失败',
        'detail': 'runtime exploded',
        'created_at': '2026-03-25T00:00:02+00:00',
        'runtime_session_id': 'runtime-session-1',
        'trace_path': 'runtime/trace.jsonl',
        'recoverable': True,
    }
    session_service.runtime_client = StubRuntimeClient([
        [
            EventEnvelope(type='session.issue', payload=issue_payload),
            EventEnvelope(type='session.status', payload={'status': 'failed'}),
        ]
    ])
    session_response = await client.post('/api/sessions')
    session_id = session_response.json()['id']
    queue = await session_service.subscribe(session_id)

    await client.post(
        f'/api/sessions/{session_id}/messages',
        json={'text': 'Need a KDE run'},
    )
    await session_service.wait_for_run(session_id)

    envelopes: list[EventEnvelope] = []
    while not queue.empty():
        envelopes.append(await queue.get())
    resume_response = await client.get(f'/api/sessions/{session_id}')

    session_service.unsubscribe(session_id, queue)

    assert any(envelope.type == 'session.issue' for envelope in envelopes)
    assert resume_response.status_code == 200
    resumed = resume_response.json()
    assert resumed['issues'][0]['id'] == 'issue-runtime-1'
    assert any(part['type'] == 'issue' for message in resumed['messages'] for part in message['parts'])


@pytest.mark.asyncio
async def test_session_interrupt_endpoint_cancels_active_run(client: AsyncClient, session_service: SessionService) -> None:
    runtime_client = BlockingRuntimeClient()
    session_service.runtime_client = runtime_client

    create_response = await client.post('/api/sessions')
    session_id = create_response.json()['id']

    send_response = await client.post(
        f'/api/sessions/{session_id}/messages',
        json={'text': '对北京出租车轨迹做 KDE 热点分析'},
    )
    await asyncio.wait_for(runtime_client.run_started.wait(), timeout=1)

    interrupt_response = await client.post(f'/api/sessions/{session_id}/interrupt')

    assert send_response.status_code == 202
    assert interrupt_response.status_code == 204
    assert runtime_client.run_cancelled.is_set() is True
    assert runtime_client.aborted_runtime_sessions == ['runtime-session-1']
    assert session_service.get_session(session_id).status == 'idle'


@pytest.mark.asyncio
async def test_runtime_manager_stops_child_process() -> None:
    from app.services.runtime import RuntimeManager

    runtime_client = StubRuntimeClient()
    runtime = RuntimeManager(state_dir=None, runtime_client=runtime_client)
    await runtime.start()

    assert runtime_client.started is True

    await runtime.stop()

    assert runtime_client.stopped is True


@pytest.mark.asyncio
async def test_isolated_client_stores_metadata_inside_temporary_app_data(
    client: AsyncClient,
    session_service: SessionService,
    isolated_settings: Settings,
) -> None:
    response = await client.post('/api/sessions')

    assert response.status_code == 201
    assert isolated_settings.database_path is not None
    assert isolated_settings.database_path.exists()
    session = response.json()
    assert session['workspace_path'] == str(isolated_settings.workspace_root)
    assert session_service.settings.database_path == isolated_settings.database_path
    assert session_service.settings.state_dir == isolated_settings.state_dir
