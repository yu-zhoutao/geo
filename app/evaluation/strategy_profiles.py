from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any, Literal

from app.evaluation.benchmarks import BenchmarkValidationError, load_simple_yaml, repo_root


STRATEGY_PROFILE_SCHEMA = 'geo-agent.evaluation.strategy-profile.v1'
STRATEGY_SELECTION_SCHEMA = 'geo-agent.evaluation.strategy-selection.v1'
StrategySource = Literal['manual-baseline', 'offline-sweep', 'trained-policy', 'policy-stub']

VALID_STRATEGY_SOURCES: set[str] = {'manual-baseline', 'offline-sweep', 'trained-policy', 'policy-stub'}
REQUIRED_STRATEGY_PROFILE_FIELDS: tuple[str, ...] = (
    'id',
    'label',
    'source',
    'guidance',
    'focus_dimensions',
)
NO_OVERLAY_VALUES: set[str] = {'', 'none'}


@dataclass(frozen=True, slots=True)
class StrategyProfile:
    id: str
    path: Path
    label: str
    source: str
    guidance: str
    focus_dimensions: tuple[str, ...]
    agent_asset_overlay_root: str = 'none'

    @property
    def profile_hash(self) -> str:
        return _sha256_file(self.path)

    def as_json(self) -> dict[str, object]:
        return {
            'schema': STRATEGY_PROFILE_SCHEMA,
            'id': self.id,
            'label': self.label,
            'source': self.source,
            'guidance': self.guidance,
            'focus_dimensions': list(self.focus_dimensions),
            'agent_asset_overlay_root': self.agent_asset_overlay_root,
            'manifest_path': str(self.path),
            'profile_hash': self.profile_hash,
        }


@dataclass(frozen=True, slots=True)
class StrategySelection:
    strategy_id: str
    source: StrategySource
    profile_hash: str
    policy_run_id: str | None = None
    policy_checkpoint_id: str | None = None
    trl_run_id: str | None = None
    training_step: int | None = None
    action_valid: bool = True
    action_rationale: str | None = None

    def as_json(self) -> dict[str, object]:
        return {
            'schema': STRATEGY_SELECTION_SCHEMA,
            'strategy_id': self.strategy_id,
            'source': self.source,
            'profile_hash': self.profile_hash,
            'policy_run_id': self.policy_run_id,
            'policy_checkpoint_id': self.policy_checkpoint_id,
            'trl_run_id': self.trl_run_id,
            'training_step': self.training_step,
            'action_valid': self.action_valid,
            'action_rationale': self.action_rationale,
        }


def default_strategy_profile_root() -> Path:
    return repo_root() / 'app' / 'evaluation_assets' / 'strategy_profiles'


def load_strategy_profile(path: Path) -> StrategyProfile:
    payload: dict[str, Any] = load_simple_yaml(path)
    missing_fields: list[str] = [
        field for field in REQUIRED_STRATEGY_PROFILE_FIELDS
        if field not in payload or _is_missing_value(payload[field])
    ]
    if missing_fields:
        missing: str = ', '.join(missing_fields)
        raise BenchmarkValidationError(f'{path} is missing required fields: {missing}')
    return StrategyProfile(
        id=_as_strategy_id(payload, 'id', path),
        path=path,
        label=_as_str(payload, 'label'),
        source=_as_str(payload, 'source'),
        guidance=_as_str(payload, 'guidance'),
        focus_dimensions=_as_tuple(payload, 'focus_dimensions'),
        agent_asset_overlay_root=_optional_str(payload, 'agent_asset_overlay_root', 'none'),
    )


def validate_strategy_profile(path: Path) -> StrategyProfile:
    profile: StrategyProfile = load_strategy_profile(path)
    if not profile.label.strip():
        raise BenchmarkValidationError(f'{path} must include a label')
    if not profile.guidance.strip():
        raise BenchmarkValidationError(f'{path} must include non-empty guidance')
    if not profile.focus_dimensions:
        raise BenchmarkValidationError(f'{path} must include focus dimensions')
    overlay_root: Path | None = resolve_strategy_overlay_root(profile)
    if overlay_root is not None and not overlay_root.exists():
        raise BenchmarkValidationError(f'{path} references missing strategy overlay: {overlay_root}')
    return profile


def load_strategy_profiles(root: Path | None = None) -> tuple[StrategyProfile, ...]:
    resolved_root: Path = root or default_strategy_profile_root()
    profiles: list[StrategyProfile] = [
        validate_strategy_profile(path)
        for path in sorted(resolved_root.glob('*.yaml'))
    ]
    seen: set[str] = set()
    for profile in profiles:
        if profile.id in seen:
            raise BenchmarkValidationError(f'Duplicate strategy profile id: {profile.id}')
        seen.add(profile.id)
    return tuple(profiles)


def load_selected_strategy_profiles(
    strategy_ids: tuple[str, ...],
    *,
    root: Path | None = None,
) -> tuple[StrategyProfile, ...]:
    if not strategy_ids:
        return ()
    profiles: tuple[StrategyProfile, ...] = load_strategy_profiles(root)
    profile_by_id: dict[str, StrategyProfile] = {profile.id: profile for profile in profiles}
    selected: list[StrategyProfile] = []
    missing: list[str] = []
    for strategy_id in strategy_ids:
        profile = profile_by_id.get(strategy_id)
        if profile is None:
            missing.append(strategy_id)
            continue
        selected.append(profile)
    if missing:
        joined: str = ', '.join(missing)
        raise BenchmarkValidationError(f'Unknown strategy profile id: {joined}')
    return tuple(selected)


def strategy_selection_from_profile(
    profile: StrategyProfile,
    *,
    source: StrategySource,
    policy_run_id: str | None = None,
    policy_checkpoint_id: str | None = None,
    trl_run_id: str | None = None,
    training_step: int | None = None,
    action_valid: bool = True,
    action_rationale: str | None = None,
) -> StrategySelection:
    if source not in VALID_STRATEGY_SOURCES:
        allowed: str = ', '.join(sorted(VALID_STRATEGY_SOURCES))
        raise BenchmarkValidationError(f'Unsupported strategy source: {source}; expected one of {allowed}')
    return StrategySelection(
        strategy_id=profile.id,
        source=source,
        profile_hash=profile.profile_hash,
        policy_run_id=policy_run_id,
        policy_checkpoint_id=policy_checkpoint_id,
        trl_run_id=trl_run_id,
        training_step=training_step,
        action_valid=action_valid,
        action_rationale=action_rationale,
    )


def resolve_strategy_overlay_root(profile: StrategyProfile) -> Path | None:
    if profile.agent_asset_overlay_root in NO_OVERLAY_VALUES:
        return None
    path: Path = Path(profile.agent_asset_overlay_root)
    if path.is_absolute():
        return path
    return repo_root() / path


def _as_strategy_id(payload: dict[str, Any], field: str, path: Path) -> str:
    value: str = _as_str(payload, field)
    if value != _safe_id(value):
        raise BenchmarkValidationError(f'{path} has invalid strategy id: {value}')
    return value


def _as_str(payload: dict[str, Any], field: str) -> str:
    value: Any = payload[field]
    if not isinstance(value, str):
        raise BenchmarkValidationError(f'{field} must be a string')
    return value


def _optional_str(payload: dict[str, Any], field: str, default: str) -> str:
    if field not in payload or _is_missing_value(payload[field]):
        return default
    return _as_str(payload, field)


def _as_tuple(payload: dict[str, Any], field: str) -> tuple[str, ...]:
    value: Any = payload[field]
    if isinstance(value, tuple) and all(isinstance(item, str) for item in value):
        return value
    if isinstance(value, str):
        return (value,)
    raise BenchmarkValidationError(f'{field} must be a list of strings')


def _safe_id(value: str) -> str:
    return ''.join(character if character.isalnum() or character in {'_'} else '_' for character in value).strip('_')


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _is_missing_value(value: Any) -> bool:
    return value == '' or value == () or value == []
