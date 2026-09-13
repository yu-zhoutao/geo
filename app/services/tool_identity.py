from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ToolIdentity:
    name: str
    label: str
    family: str
    summary: str
    icon: str
    known: bool = True


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _identity_source_path() -> Path:
    return _repo_root() / 'frontend' / 'src' / 'shared' / 'toolIdentity.json'


@lru_cache(maxsize=1)
def load_tool_identity_map() -> dict[str, ToolIdentity]:
    raw = json.loads(_identity_source_path().read_text(encoding='utf-8'))
    return {
        runtime_name: ToolIdentity(
            name=runtime_name,
            label=str(payload['label']),
            family=str(payload['family']),
            summary=str(payload['summary']),
            icon=str(payload['icon']),
        )
        for runtime_name, payload in raw.items()
    }


def canonical_tool_name(tool_name: str | None) -> str:
    normalized = str(tool_name or '').strip()
    if normalized.startswith('mcp__geospatial__'):
        normalized = normalized.removeprefix('mcp__geospatial__')

    while normalized.startswith('geospatial_geospatial_'):
        normalized = normalized.removeprefix('geospatial_')

    identities = load_tool_identity_map()
    if normalized in identities:
        return normalized

    if normalized.startswith('geospatial_'):
        stripped = normalized.removeprefix('geospatial_')
        if stripped in identities:
            return stripped

    return normalized


def resolve_tool_identity(tool_name: str | None) -> ToolIdentity:
    canonical_name = canonical_tool_name(tool_name)
    identity = load_tool_identity_map().get(canonical_name)
    if identity is not None:
        return identity
    return ToolIdentity(
        name=canonical_name,
        label='运行时工具',
        family='tool',
        summary='未在当前应用工具映射中注册的运行时工具。',
        icon='wrench',
        known=False,
    )
