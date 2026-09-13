from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path
import re
import sys
from typing import Final, Literal, cast

from pydantic import BaseModel, ConfigDict, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

GLM_MODEL_NAME_PATTERN: Final[re.Pattern[str]] = re.compile(r'glm-[a-z0-9][a-z0-9.-]*')
DEEPSEEK_MODEL_NAME_PATTERN: Final[re.Pattern[str]] = re.compile(r'deepseek-[a-z0-9][a-z0-9.-]*')
RuntimeModelProvider = Literal['glm', 'deepseek']
VALID_RUNTIME_MODEL_PROVIDERS: Final[set[str]] = {'glm', 'deepseek'}


def _default_app_support_dir(app_name: str) -> Path:
    home = Path.home()
    if sys.platform == 'darwin':
        return home / 'Library' / 'Application Support' / app_name
    if sys.platform.startswith('win'):
        appdata = os.getenv('APPDATA')
        if appdata:
            return Path(appdata) / app_name
        return home / 'AppData' / 'Roaming' / app_name
    return Path('.state') / app_name


def _validate_glm_model(value: str) -> str:
    model = value.strip()
    if not GLM_MODEL_NAME_PATTERN.fullmatch(model):
        raise ValueError('glm_model must be a bare GLM model name such as "glm-5"')
    return model


def _validate_deepseek_model(value: str) -> str:
    model = value.strip()
    if not DEEPSEEK_MODEL_NAME_PATTERN.fullmatch(model):
        raise ValueError('deepseek_model must be a bare DeepSeek model name such as "deepseek-v4-pro"')
    return model


def _validate_runtime_model_provider(value: object) -> RuntimeModelProvider:
    if not isinstance(value, str):
        raise ValueError('model_provider must be "glm" or "deepseek"')
    provider = value.strip().lower()
    if provider not in VALID_RUNTIME_MODEL_PROVIDERS:
        raise ValueError('model_provider must be "glm" or "deepseek"')
    return cast(RuntimeModelProvider, provider)


class _EnvironmentSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix='GEO_AGENT_',
        env_file='.env',
        extra='ignore',
    )

    state_dir: Path = Path('.state')
    app_support_dir: Path | None = None
    database_path: Path | None = None
    workspace_root: Path | None = None
    runtime_config_root: Path | None = None
    agent_asset_root: Path | None = None
    frontend_origin: str = 'http://127.0.0.1:5173'
    model_provider: RuntimeModelProvider = 'glm'
    glm_api_key: str | None = None
    glm_model: str = 'glm-5.1'
    glm_base_url: str = 'https://open.bigmodel.cn/api/paas/v4'
    deepseek_api_key: str | None = None
    deepseek_model: str = 'deepseek-v4-pro'
    deepseek_base_url: str = 'https://api.deepseek.com'
    opencode_binary: str = 'opencode'
    opencode_hostname: str = '127.0.0.1'
    geospatial_python_auto_provision: bool = True
    geospatial_python_project: Path | None = None
    geospatial_python_version: str = '3.12'
    uv_bin: str | None = None

    @field_validator('model_provider', mode='before')
    @classmethod
    def validate_model_provider(cls, value: object) -> RuntimeModelProvider:
        return _validate_runtime_model_provider(value)

    @field_validator('glm_model')
    @classmethod
    def validate_glm_model(cls, value: str) -> str:
        return _validate_glm_model(value)

    @field_validator('deepseek_model')
    @classmethod
    def validate_deepseek_model(cls, value: str) -> str:
        return _validate_deepseek_model(value)


class Settings(BaseModel):
    model_config = ConfigDict(extra='ignore')

    app_name: str = 'geo-agent'
    state_dir: Path = Path('.state')
    app_support_dir: Path | None = None
    database_path: Path | None = None
    workspace_root: Path | None = None
    runtime_config_root: Path | None = None
    agent_asset_root: Path | None = None
    runtime_label: str = 'opencode-runtime'
    frontend_origin: str = 'http://127.0.0.1:5173'
    model_provider: RuntimeModelProvider = 'glm'
    glm_api_key: str | None = None
    glm_model: str = 'glm-5.1'
    glm_base_url: str = 'https://open.bigmodel.cn/api/paas/v4'
    deepseek_api_key: str | None = None
    deepseek_model: str = 'deepseek-v4-pro'
    deepseek_base_url: str = 'https://api.deepseek.com'
    opencode_binary: str = 'opencode'
    opencode_hostname: str = '127.0.0.1'
    geospatial_python_auto_provision: bool = False
    geospatial_python_project: Path | None = None
    geospatial_python_version: str = '3.12'
    uv_bin: str | None = None

    @field_validator('model_provider', mode='before')
    @classmethod
    def validate_model_provider(cls, value: object) -> RuntimeModelProvider:
        return _validate_runtime_model_provider(value)

    @field_validator('glm_model')
    @classmethod
    def validate_glm_model(cls, value: str) -> str:
        return _validate_glm_model(value)

    @field_validator('deepseek_model')
    @classmethod
    def validate_deepseek_model(cls, value: str) -> str:
        return _validate_deepseek_model(value)

    def resolved_app_support_dir(self) -> Path:
        return self.app_support_dir or _default_app_support_dir(self.app_name)

    def resolved_database_path(self) -> Path:
        return self.database_path or self.resolved_app_support_dir() / 'metadata.db'

    def resolved_workspace_root(self) -> Path:
        return self.workspace_root or self.resolved_app_support_dir() / 'workspace'

    def resolved_runtime_config_root(self) -> Path:
        return self.runtime_config_root or self.resolved_app_support_dir()

    def resolved_agent_asset_root(self) -> Path:
        return self.agent_asset_root or Path(__file__).resolve().parent / 'agent_assets'

    def resolved_geospatial_python_project(self) -> Path:
        return self.geospatial_python_project or Path(__file__).resolve().parent / 'runtime_assets' / 'geospatial-python'

    def resolved_geospatial_python_environment(self) -> Path:
        return self.resolved_app_support_dir() / 'runtime' / 'geospatial-python' / '.venv'


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    environment = _EnvironmentSettings()
    return Settings(
        state_dir=environment.state_dir,
        app_support_dir=environment.app_support_dir,
        database_path=environment.database_path,
        workspace_root=environment.workspace_root,
        runtime_config_root=environment.runtime_config_root,
        agent_asset_root=environment.agent_asset_root,
        frontend_origin=environment.frontend_origin,
        model_provider=environment.model_provider,
        glm_api_key=environment.glm_api_key,
        glm_model=environment.glm_model,
        glm_base_url=environment.glm_base_url,
        deepseek_api_key=environment.deepseek_api_key,
        deepseek_model=environment.deepseek_model,
        deepseek_base_url=environment.deepseek_base_url,
        opencode_binary=environment.opencode_binary,
        opencode_hostname=environment.opencode_hostname,
        geospatial_python_auto_provision=environment.geospatial_python_auto_provision,
        geospatial_python_project=environment.geospatial_python_project,
        geospatial_python_version=environment.geospatial_python_version,
        uv_bin=environment.uv_bin,
    )


def evaluation_settings(root: Path, base: Settings | None = None) -> Settings:
    resolved = base or get_settings()
    return resolved.model_copy(
        update={
            'state_dir': root / 'state',
            'database_path': root / 'metadata.db',
            'workspace_root': root / 'workspace',
        }
    )
