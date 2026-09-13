from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import json
import mimetypes

from fastapi import APIRouter, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sse_starlette.sse import EventSourceResponse

from app.config import Settings, get_settings
from app.models import AnswerAccepted, AnswerRequest, DataDirectoryBrowserResponse, HealthResponse, MessageAccepted, MessageRequest, OpenDataDirectoryRequest, RecentDataDirectoriesResponse, RenameSessionRequest, Session, SessionArchiveImportRequest, SessionSummary, UpdateAttachedDataDirectoriesRequest
from app.services.session_archives import session_archive_filename
from app.services.agent_runtime import build_agent_runtime_client
from app.services.geospatial_mcp_server import list_geospatial_mcp_capabilities
from app.services.runtime import RuntimeManager
from app.services.sessions import SessionService


def _settings(app: FastAPI) -> Settings:
    return app.state.settings


def _runtime_manager(app: FastAPI) -> RuntimeManager:
    return app.state.runtime_manager


def _session_service(app: FastAPI) -> SessionService:
    return app.state.session_service


def serialize_sse_event(event_type: str, payload: object) -> dict[str, str]:
    return {
        'event': event_type,
        'data': json.dumps({'type': event_type, 'payload': payload}),
    }


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    runtime_manager = _runtime_manager(app)
    session_service = _session_service(app)
    await runtime_manager.start()
    lifespan_error: BaseException | None = None
    try:
        yield
    except BaseException as exc:
        lifespan_error = exc
        raise
    finally:
        cleanup_error: BaseException | None = None
        try:
            await session_service.shutdown()
        except BaseException as exc:
            cleanup_error = exc
        try:
            await runtime_manager.stop()
        except BaseException as exc:
            if cleanup_error is None:
                cleanup_error = exc
            else:
                cleanup_error.add_note(f'Runtime cleanup also failed: {exc}')
        if cleanup_error is not None:
            if lifespan_error is not None:
                lifespan_error.add_note(f'Application cleanup failed: {cleanup_error}')
            else:
                raise cleanup_error


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    runtime_client = build_agent_runtime_client(resolved_settings)
    app = FastAPI(title='Geo Agent Backend', lifespan=lifespan)
    app.state.settings = resolved_settings
    app.state.runtime_manager = RuntimeManager(settings=resolved_settings, runtime_client=runtime_client)
    app.state.session_service = SessionService(settings=resolved_settings, runtime_client=runtime_client)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[resolved_settings.frontend_origin],
        allow_methods=['*'],
        allow_headers=['*'],
    )
    app.include_router(router)
    return app


router = APIRouter()


@router.get('/api/health', response_model=HealthResponse)
async def get_health(request: Request) -> HealthResponse:
    runtime_manager = _runtime_manager(request.app)
    session_service = _session_service(request.app)
    runtime = runtime_manager.status()
    metadata = session_service.health_payload()
    return HealthResponse(
        runtime=runtime,
        storage=metadata['storage'],
        workspace=metadata['workspace'],
        provider=metadata['provider'],
        mcp={
            'status': 'ready',
            'capabilities': list_geospatial_mcp_capabilities(),
        },
        geospatial_environment=runtime_manager.geospatial_environment_status(),
        default_data_directories=metadata['default_data_directories'],
    )


@router.get('/api/mcp/capabilities')
async def list_mcp_capabilities() -> dict[str, object]:
    return {
        'source': 'application-managed',
        'capabilities': list_geospatial_mcp_capabilities(),
    }


@router.get('/api/sessions')
async def list_sessions(request: Request) -> list[dict[str, object]]:
    session_service = _session_service(request.app)
    return [session.model_dump(mode='json') for session in session_service.list_sessions()]


@router.post('/api/sessions', response_model=Session, status_code=status.HTTP_201_CREATED)
async def create_session(request: Request) -> Session:
    session_service = _session_service(request.app)
    return await session_service.create_session()


@router.patch('/api/sessions/{session_id}', response_model=SessionSummary)
async def rename_session(session_id: str, request: RenameSessionRequest, http_request: Request) -> SessionSummary:
    session_service = _session_service(http_request.app)
    session = await session_service.rename_session(session_id, request.title)
    return SessionSummary(**session.model_dump())


@router.delete('/api/sessions/{session_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: str, request: Request) -> Response:
    session_service = _session_service(request.app)
    await session_service.delete_session(session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get('/api/sessions/{session_id}', response_model=Session)
async def get_session(session_id: str, request: Request) -> Session:
    session_service = _session_service(request.app)
    return await session_service.get_session_with_runtime_recovery(session_id)


@router.get('/api/sessions/{session_id}/archive')
async def export_session_archive(session_id: str, request: Request) -> JSONResponse:
    session_service = _session_service(request.app)
    archive = await session_service.export_session_archive(session_id)
    session = session_service.get_session(session_id)
    return JSONResponse(
        content=archive,
        headers={'Content-Disposition': f'attachment; filename="{session_archive_filename(session)}"'},
    )


@router.post('/api/session-archives/import', response_model=Session, status_code=status.HTTP_201_CREATED)
async def import_session_archive(request: SessionArchiveImportRequest, http_request: Request) -> Session:
    session_service = _session_service(http_request.app)
    return await session_service.import_session_archive(request.archive)


@router.get('/api/sessions/{session_id}/evidence-records')
async def list_session_evidence_records(session_id: str, request: Request) -> dict[str, object]:
    session_service = _session_service(request.app)
    records = session_service.list_evidence_records(session_id)
    return {
        'items': records,
        'record_count': len(records),
    }


@router.put('/api/sessions/{session_id}/data-directories', response_model=Session)
async def update_attached_data_directories(session_id: str, request: UpdateAttachedDataDirectoriesRequest, http_request: Request) -> Session:
    session_service = _session_service(http_request.app)
    return await session_service.update_attached_data_directories(session_id, [item.model_dump(mode='json') for item in request.items])


@router.get('/api/data-directories/browser', response_model=DataDirectoryBrowserResponse)
async def browse_data_directories(request: Request, path: str | None = None) -> DataDirectoryBrowserResponse:
    session_service = _session_service(request.app)
    return DataDirectoryBrowserResponse.model_validate(await session_service.browse_data_directories(path))


@router.get('/api/data-directories/recent', response_model=RecentDataDirectoriesResponse)
async def list_recent_data_directories(request: Request) -> RecentDataDirectoriesResponse:
    session_service = _session_service(request.app)
    return RecentDataDirectoriesResponse.model_validate(session_service.list_recent_data_directories())


@router.post('/api/data-directories/open', status_code=status.HTTP_204_NO_CONTENT)
async def open_data_directory(request: OpenDataDirectoryRequest, http_request: Request) -> Response:
    session_service = _session_service(http_request.app)
    await session_service.open_data_directory(request.path)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post('/api/sessions/{session_id}/workspace/open', status_code=status.HTTP_204_NO_CONTENT)
async def open_workspace(session_id: str, request: Request) -> Response:
    session_service = _session_service(request.app)
    await session_service.open_workspace(session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post('/api/sessions/{session_id}/artifacts/{artifact_id}/open', status_code=status.HTTP_204_NO_CONTENT)
async def open_artifact(session_id: str, artifact_id: str, request: Request) -> Response:
    session_service = _session_service(request.app)
    await session_service.open_artifact(session_id, artifact_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get('/api/sessions/{session_id}/artifacts/{artifact_id}/content')
async def get_artifact_content(session_id: str, artifact_id: str, request: Request) -> FileResponse:
    session_service = _session_service(request.app)
    artifact_path = session_service.resolve_artifact_path(session_id, artifact_id)
    media_type = mimetypes.guess_type(str(artifact_path))[0] or 'application/octet-stream'
    return FileResponse(artifact_path, media_type=media_type, filename=artifact_path.name)


@router.post('/api/sessions/{session_id}/messages', response_model=MessageAccepted, status_code=status.HTTP_202_ACCEPTED)
async def submit_message(session_id: str, request: MessageRequest, http_request: Request) -> MessageAccepted:
    runtime_manager = _runtime_manager(http_request.app)
    environment_status = runtime_manager.geospatial_environment_status()
    if runtime_manager.settings.geospatial_python_auto_provision and environment_status.get('status') != 'ready':
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                'reason': 'geospatial_environment_not_ready',
                'status': environment_status.get('status'),
                'logs': environment_status.get('logs', []),
            },
        )
    session_service = _session_service(http_request.app)
    question = await session_service.submit_message(session_id, request.text)
    return MessageAccepted(question=question)


@router.post('/api/sessions/{session_id}/interrupt', status_code=status.HTTP_204_NO_CONTENT)
async def interrupt_session(session_id: str, request: Request) -> Response:
    session_service = _session_service(request.app)
    await session_service.interrupt_session(session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post('/api/sessions/{session_id}/questions/{question_id}/answers', response_model=AnswerAccepted, status_code=status.HTTP_202_ACCEPTED)
async def answer_question(session_id: str, question_id: str, request: AnswerRequest, http_request: Request) -> AnswerAccepted:
    session_service = _session_service(http_request.app)
    await session_service.answer_question(session_id, question_id, request.answer, request.answers)
    return AnswerAccepted()


@router.get('/api/sessions/{session_id}/events')
async def stream_session_events(session_id: str, request: Request) -> EventSourceResponse:
    session_service = _session_service(request.app)
    queue = await session_service.subscribe(session_id)

    async def event_stream() -> AsyncIterator[dict[str, str]]:
        try:
            while True:
                envelope = await queue.get()
                yield serialize_sse_event(envelope.type, envelope.payload)
        finally:
            session_service.unsubscribe(session_id, queue)

    return EventSourceResponse(event_stream())


@router.get('/')
async def root() -> Response:
    return Response(status_code=status.HTTP_204_NO_CONTENT)


app = create_app()
