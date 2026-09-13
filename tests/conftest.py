from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app
from app.services.runtime import RuntimeManager
from app.services.sessions import SessionService


@pytest.fixture
def isolated_settings(tmp_path: Path) -> Settings:
    app_data_dir = tmp_path / 'app-data'
    return Settings(
        state_dir=app_data_dir / '.state',
        app_support_dir=app_data_dir / 'support',
        database_path=app_data_dir / 'support' / 'metadata.db',
        workspace_root=app_data_dir / 'support' / 'workspace',
    )


@pytest.fixture
def api_app(isolated_settings: Settings) -> FastAPI:
    return create_app(isolated_settings)


@pytest.fixture
def runtime_manager(api_app: FastAPI) -> RuntimeManager:
    return api_app.state.runtime_manager


@pytest.fixture
def session_service(api_app: FastAPI) -> SessionService:
    return api_app.state.session_service


@pytest.fixture
async def client(api_app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url='http://testserver') as async_client:
        yield async_client
