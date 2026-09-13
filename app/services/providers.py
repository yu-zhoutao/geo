from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Protocol

from app.config import RuntimeModelProvider, Settings, get_settings


class TitleProvider(Protocol):
    @property
    def is_configured(self) -> bool: ...

    async def generate_session_title(self, prompt: str) -> str: ...


@dataclass(slots=True)
class ModelProviderConfig:
    provider: RuntimeModelProvider
    opencode_provider: str
    model: str
    opencode_model: str
    small_model: str
    api_key: str
    opencode_provider_config: dict[str, Any] | None = None

    def public_metadata(self, *, status: str = 'ready') -> dict[str, object]:
        return {
            'status': status,
            'provider': self.provider,
            'opencode_provider': self.opencode_provider,
            'model': self.model,
            'opencode_model': self.opencode_model,
        }


def resolve_model_provider_config(settings: Settings | None = None) -> ModelProviderConfig | None:
    resolved = settings or get_settings()
    if resolved.model_provider == 'deepseek':
        if not resolved.deepseek_api_key:
            return None
        return ModelProviderConfig(
            provider='deepseek',
            opencode_provider='deepseek',
            model=resolved.deepseek_model,
            opencode_model=f'deepseek/{resolved.deepseek_model}',
            small_model=f'deepseek/{resolved.deepseek_model}',
            api_key=resolved.deepseek_api_key,
            opencode_provider_config=_openai_compatible_provider_config(
                name='DeepSeek',
                base_url=resolved.deepseek_base_url,
                api_key=resolved.deepseek_api_key,
                model_ids=(resolved.deepseek_model,),
            ),
        )
    if not resolved.glm_api_key:
        return None
    return ModelProviderConfig(
        provider='glm',
        opencode_provider='zhipuai',
        model=resolved.glm_model,
        opencode_model=f'zhipuai/{resolved.glm_model}',
        small_model='zhipuai/glm-4.7-flash',
        api_key=resolved.glm_api_key,
        opencode_provider_config=_openai_compatible_provider_config(
            name='Zhipu AI',
            base_url=resolved.glm_base_url,
            api_key=resolved.glm_api_key,
            model_ids=(resolved.glm_model, 'glm-4.7-flash'),
        ),
    )


def selected_model_provider_metadata(settings: Settings | None = None) -> dict[str, object]:
    resolved = settings or get_settings()
    config = resolve_model_provider_config(resolved)
    if config is not None:
        return config.public_metadata()
    if resolved.model_provider == 'deepseek':
        return {
            'status': 'not_configured',
            'provider': 'deepseek',
            'opencode_provider': 'deepseek',
            'model': resolved.deepseek_model,
            'opencode_model': f'deepseek/{resolved.deepseek_model}',
        }
    return {
        'status': 'not_configured',
        'provider': 'glm',
        'opencode_provider': 'zhipuai',
        'model': resolved.glm_model,
        'opencode_model': f'zhipuai/{resolved.glm_model}',
    }


class NullTitleProvider:
    @property
    def is_configured(self) -> bool:
        return False

    async def generate_session_title(self, prompt: str) -> str:
        raise RuntimeError(f'No title provider configured for prompt: {prompt}')


class GLMTitleProvider:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def is_configured(self) -> bool:
        return bool(self.settings.glm_api_key)

    async def generate_session_title(self, prompt: str) -> str:
        if not self.is_configured:
            raise RuntimeError('GLM provider is not configured')
        return await asyncio.to_thread(self._generate_sync, prompt)

    def _generate_sync(self, prompt: str) -> str:
        from zai import ZhipuAiClient

        client_kwargs: dict[str, str] = {'api_key': self.settings.glm_api_key or ''}

        client = ZhipuAiClient(**client_kwargs)
        response = client.chat.completions.create(
            model=self.settings.glm_model,
            messages=[
                {
                    'role': 'system',
                    'content': 'You generate short Chinese session titles for geospatial analysis tasks. Return only the title.',
                },
                {
                    'role': 'user',
                    'content': prompt,
                },
            ],
        )
        message = response.choices[0].message.content
        return str(message).strip()


def build_title_provider(settings: Settings | None = None) -> TitleProvider:
    resolved = settings or get_settings()
    provider = GLMTitleProvider(settings=resolved)
    if provider.is_configured:
        return provider
    return NullTitleProvider()


def _openai_compatible_provider_config(
    *,
    name: str,
    base_url: str,
    api_key: str,
    model_ids: tuple[str, ...],
) -> dict[str, Any]:
    models: dict[str, dict[str, str]] = {
        model_id: {'name': model_id}
        for model_id in dict.fromkeys(model_ids)
    }
    return {
        'npm': '@ai-sdk/openai-compatible',
        'name': name,
        'options': {
            'baseURL': base_url,
            'apiKey': api_key,
        },
        'models': models,
    }
