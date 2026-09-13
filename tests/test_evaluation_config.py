from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings, evaluation_settings, get_settings


def test_evaluation_settings_isolates_result_state_but_keeps_shared_runtime_roots(tmp_path: Path) -> None:
    from app.services.session_store import SessionStore
    from app.services.workspace import WorkspaceManager

    base = Settings(
        app_support_dir=tmp_path / 'interactive-support',
        database_path=tmp_path / 'interactive-support' / 'metadata.db',
        workspace_root=tmp_path / 'interactive-support' / 'workspace',
        runtime_config_root=tmp_path / 'interactive-runtime',
        glm_api_key='test-key',
    )
    campaign_root: Path = tmp_path / 'campaign'

    settings = evaluation_settings(campaign_root, base)

    assert settings.resolved_app_support_dir() == tmp_path / 'interactive-support'
    assert settings.resolved_database_path() == campaign_root / 'metadata.db'
    assert settings.resolved_workspace_root() == campaign_root / 'workspace'
    assert settings.resolved_runtime_config_root() == tmp_path / 'interactive-runtime'
    assert settings.glm_api_key == 'test-key'
    assert base.resolved_app_support_dir() == tmp_path / 'interactive-support'
    assert base.resolved_runtime_config_root() == tmp_path / 'interactive-runtime'

    store = SessionStore(settings)
    workspace = WorkspaceManager(settings)

    assert store.db_path == campaign_root / 'metadata.db'
    assert workspace.root == campaign_root / 'workspace'
    assert not (tmp_path / 'interactive-support' / 'metadata.db').exists()
    assert not (tmp_path / 'interactive-support' / 'workspace').exists()


def test_get_settings_reads_isolated_storage_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root: Path = tmp_path / 'env-campaign'
    monkeypatch.setenv('GEO_AGENT_STATE_DIR', str(root / 'state'))
    monkeypatch.setenv('GEO_AGENT_APP_SUPPORT_DIR', str(root / 'app-support'))
    monkeypatch.setenv('GEO_AGENT_DATABASE_PATH', str(root / 'metadata.db'))
    monkeypatch.setenv('GEO_AGENT_WORKSPACE_ROOT', str(root / 'workspace'))
    monkeypatch.setenv('GEO_AGENT_RUNTIME_CONFIG_ROOT', str(root / 'runtime-config'))
    get_settings.cache_clear()

    try:
        settings = get_settings()
    finally:
        get_settings.cache_clear()

    assert settings.state_dir == root / 'state'
    assert settings.resolved_app_support_dir() == root / 'app-support'
    assert settings.resolved_database_path() == root / 'metadata.db'
    assert settings.resolved_workspace_root() == root / 'workspace'
    assert settings.resolved_runtime_config_root() == root / 'runtime-config'


def test_opencode_runtime_uses_separate_runtime_config_root(tmp_path: Path) -> None:
    from app.services.agent_runtime import OpenCodeAgentRuntimeClient

    support_root: Path = tmp_path / 'app-support'
    runtime_config_root: Path = tmp_path / 'runtime-config'
    runtime = OpenCodeAgentRuntimeClient(
        Settings(
            app_support_dir=support_root,
            runtime_config_root=runtime_config_root,
            glm_api_key='test-key',
        )
    )

    config_path = runtime._global_config_path()
    env = runtime._build_server_env(port=43111)

    assert config_path == runtime_config_root / '.config' / 'opencode' / 'opencode.json'
    assert env['XDG_CONFIG_HOME'] == str(runtime_config_root / '.config')
    assert env['XDG_DATA_HOME'] == str(runtime_config_root / '.local' / 'share')
    assert env['XDG_STATE_HOME'] == str(runtime_config_root / '.local' / 'state')
    assert env['XDG_CACHE_HOME'] == str(runtime_config_root / '.cache')
    assert env['OPENCODE_TEST_HOME'] == str(runtime_config_root)
    assert env['UV_PROJECT_ENVIRONMENT'] == str(support_root / 'runtime' / 'geospatial-python' / '.venv')
    assert not (support_root / '.config').exists()
