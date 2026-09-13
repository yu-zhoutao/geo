from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.services.providers import build_title_provider, resolve_model_provider_config, selected_model_provider_metadata


def test_settings_default_glm_model_is_latest_default() -> None:
    assert Settings().model_provider == 'glm'
    assert Settings().glm_model == 'glm-5.1'
    assert Settings().deepseek_model == 'deepseek-v4-pro'


def test_get_settings_loads_glm_and_storage_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv('GEO_AGENT_GLM_API_KEY', 'test-key')
    monkeypatch.setenv('GEO_AGENT_GLM_MODEL', 'glm-5')
    monkeypatch.setenv('GEO_AGENT_MODEL_PROVIDER', 'deepseek')
    monkeypatch.setenv('GEO_AGENT_DEEPSEEK_API_KEY', 'deepseek-key')
    monkeypatch.setenv('GEO_AGENT_DEEPSEEK_MODEL', 'deepseek-v4-flash')
    monkeypatch.setenv('GEO_AGENT_STATE_DIR', str(tmp_path / 'evaluation-state'))
    get_settings.cache_clear()

    try:
        settings = get_settings()
    finally:
        get_settings.cache_clear()

    assert settings.model_provider == 'deepseek'
    assert settings.glm_api_key == 'test-key'
    assert settings.glm_model == 'glm-5'
    assert settings.deepseek_api_key == 'deepseek-key'
    assert settings.deepseek_model == 'deepseek-v4-flash'
    assert settings.state_dir == tmp_path / 'evaluation-state'


def test_settings_rejects_unknown_model_provider() -> None:
    with pytest.raises(ValidationError):
        Settings(model_provider='openai')


def test_settings_rejects_provider_qualified_glm_model() -> None:
    with pytest.raises(ValidationError):
        Settings(glm_model='zai/glm-5')

    with pytest.raises(ValidationError):
        Settings(glm_model='zhipuai/glm-5')


def test_resolve_model_provider_config_keeps_bare_glm_model() -> None:
    config = resolve_model_provider_config(
        Settings(
            glm_api_key='test-key',
            glm_model='glm-5',
        )
    )

    assert config is not None
    assert config.provider == 'glm'
    assert config.opencode_provider == 'zhipuai'
    assert config.model == 'glm-5'
    assert config.opencode_model == 'zhipuai/glm-5'
    assert config.api_key == 'test-key'


def test_resolve_model_provider_config_supports_deepseek_runtime() -> None:
    config = resolve_model_provider_config(
        Settings(
            model_provider='deepseek',
            deepseek_api_key='deepseek-key',
            deepseek_model='deepseek-v4-pro',
        )
    )

    assert config is not None
    assert config.provider == 'deepseek'
    assert config.opencode_provider == 'deepseek'
    assert config.model == 'deepseek-v4-pro'
    assert config.opencode_model == 'deepseek/deepseek-v4-pro'
    assert config.api_key == 'deepseek-key'


def test_resolve_model_provider_config_requires_selected_provider_key() -> None:
    assert resolve_model_provider_config(Settings(glm_api_key=None)) is None
    assert resolve_model_provider_config(Settings(model_provider='deepseek', deepseek_api_key=None)) is None
    assert resolve_model_provider_config(Settings(deepseek_api_key='deepseek-key', glm_api_key=None)) is None


def test_selected_model_provider_metadata_excludes_secrets() -> None:
    metadata = selected_model_provider_metadata(
        Settings(
            model_provider='deepseek',
            deepseek_api_key='deepseek-key',
            deepseek_model='deepseek-v4-pro',
        )
    )

    assert metadata['status'] == 'ready'
    assert metadata['provider'] == 'deepseek'
    assert metadata['model'] == 'deepseek-v4-pro'
    assert 'api_key' not in metadata
    assert 'deepseek-key' not in {str(value) for value in metadata.values()}


def test_deepseek_runtime_does_not_require_glm_title_provider() -> None:
    from app.services.agent_runtime import OpenCodeAgentRuntimeClient, build_agent_runtime_client

    settings = Settings(model_provider='deepseek', deepseek_api_key='deepseek-key', glm_api_key=None)

    assert not build_title_provider(settings).is_configured
    assert isinstance(build_agent_runtime_client(settings), OpenCodeAgentRuntimeClient)
