from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from app.evaluation.benchmarks import (
    BenchmarkScenario,
    BenchmarkValidationError,
    load_simple_yaml,
    repo_root,
    validate_benchmark_suite,
)


VariantKind = Literal['internal-agent-runtime', 'external-adapter']
AgentAssetMode = Literal['default', 'generated-single-agent', 'disable-skills', 'disable-role']
SkillMode = Literal['enabled', 'disabled', 'partial']
ScoringMode = Literal['none', 'llm-judge']
RunnerIsolationMode = Literal['per-campaign', 'per-run']
RunnerResumePolicy = Literal['append-attempts', 'fail-if-existing']
OutputDirectoryPolicy = Literal['timestamped-campaign-dir', 'explicit-empty-directory']

VALID_VARIANT_KINDS: set[str] = {'internal-agent-runtime', 'external-adapter'}
VALID_AGENT_ASSET_MODES: set[str] = {'default', 'generated-single-agent', 'disable-skills', 'disable-role'}
VALID_SKILL_MODES: set[str] = {'enabled', 'disabled', 'partial'}
VALID_SCORING_MODES: set[str] = {'none', 'llm-judge'}
VALID_SCORING_ELIGIBILITY: set[str] = {'llm-judge'}
VALID_FAIRNESS_DATASET_POLICIES: set[str] = {'scenario-dataset-pack'}
VALID_FAIRNESS_TOOL_POLICIES: set[str] = {'shared-tool-catalog', 'variant-defined-tool-catalog'}
VALID_FAIRNESS_RUNTIME_POLICIES: set[str] = {'shared-budget', 'variant-specific'}
VALID_RUNNER_ISOLATION_MODES: set[str] = {'per-campaign', 'per-run'}
VALID_RUNNER_RESUME_POLICIES: set[str] = {'append-attempts', 'fail-if-existing'}
VALID_OUTPUT_DIRECTORY_POLICIES: set[str] = {'timestamped-campaign-dir', 'explicit-empty-directory'}

REQUIRED_CAMPAIGN_FIELDS: tuple[str, ...] = (
    'id',
    'benchmark_version',
    'benchmark_root',
    'scenario_selector',
    'variants',
    'full_system_selector',
    'full_system_repeats',
    'comparison_selector',
    'comparison_repeats',
    'wall_clock_budget_seconds',
    'max_turns',
    'fairness_model',
    'fairness_temperature',
    'fairness_dataset_policy',
    'fairness_tool_policy',
    'fairness_runtime_policy',
    'runner_isolation_mode',
    'runner_resume_policy',
    'runner_readiness_timeout_seconds',
    'scoring_mode',
    'judge_model',
    'judge_temperature',
    'output_root',
    'output_directory_policy',
)
REQUIRED_VARIANT_FIELDS: tuple[str, ...] = (
    'id',
    'label',
    'kind',
    'agent_asset_mode',
    'agent_asset_root',
    'agent_asset_overlay_root',
    'enabled_roles',
    'disabled_roles',
    'skill_mode',
    'enabled_skills',
    'disabled_skills',
    'model',
    'temperature',
    'runtime_wall_clock_budget_seconds',
    'max_turns',
    'scenario_selector',
    'scoring_eligibility',
)
EMPTY_VARIANT_FIELDS: set[str] = {
    'enabled_roles',
    'disabled_roles',
    'enabled_skills',
    'disabled_skills',
    'scoring_eligibility',
}


@dataclass(frozen=True, slots=True)
class CampaignManifest:
    id: str
    path: Path
    benchmark_version: str
    benchmark_root: str
    scenario_selector: str
    variants: tuple[str, ...]
    full_system_selector: str
    full_system_repeats: int
    comparison_selector: str
    comparison_repeats: int
    wall_clock_budget_seconds: int
    max_turns: int
    fairness_model: str
    fairness_temperature: float
    fairness_dataset_policy: str
    fairness_tool_policy: str
    fairness_runtime_policy: str
    runner_isolation_mode: RunnerIsolationMode
    runner_resume_policy: RunnerResumePolicy
    runner_readiness_timeout_seconds: int
    scoring_mode: ScoringMode
    judge_model: str
    judge_temperature: float
    output_root: str
    output_directory_policy: OutputDirectoryPolicy


@dataclass(frozen=True, slots=True)
class VariantManifest:
    id: str
    path: Path
    label: str
    kind: VariantKind
    agent_asset_mode: AgentAssetMode
    agent_asset_root: str
    agent_asset_overlay_root: str
    enabled_roles: tuple[str, ...]
    disabled_roles: tuple[str, ...]
    skill_mode: SkillMode
    enabled_skills: tuple[str, ...]
    disabled_skills: tuple[str, ...]
    model: str
    temperature: float
    runtime_wall_clock_budget_seconds: int
    max_turns: int
    scenario_selector: str
    scoring_eligibility: tuple[str, ...]


def default_evaluation_assets_root() -> Path:
    return repo_root() / 'app' / 'evaluation_assets'


def default_variant_root() -> Path:
    return default_evaluation_assets_root() / 'variants'


def load_campaign_manifest(path: Path) -> CampaignManifest:
    payload: dict[str, Any] = load_simple_yaml(path)
    _require_fields(path=path, payload=payload, fields=REQUIRED_CAMPAIGN_FIELDS)
    return CampaignManifest(
        id=_as_str(payload, 'id'),
        path=path,
        benchmark_version=_as_str(payload, 'benchmark_version'),
        benchmark_root=_as_str(payload, 'benchmark_root'),
        scenario_selector=_as_str(payload, 'scenario_selector'),
        variants=_as_tuple(payload, 'variants'),
        full_system_selector=_as_str(payload, 'full_system_selector'),
        full_system_repeats=_as_int(payload, 'full_system_repeats'),
        comparison_selector=_as_str(payload, 'comparison_selector'),
        comparison_repeats=_as_int(payload, 'comparison_repeats'),
        wall_clock_budget_seconds=_as_int(payload, 'wall_clock_budget_seconds'),
        max_turns=_as_int(payload, 'max_turns'),
        fairness_model=_as_str(payload, 'fairness_model'),
        fairness_temperature=_as_float(payload, 'fairness_temperature'),
        fairness_dataset_policy=_as_literal(
            _as_str(payload, 'fairness_dataset_policy'),
            VALID_FAIRNESS_DATASET_POLICIES,
            'fairness_dataset_policy',
            path,
        ),
        fairness_tool_policy=_as_literal(
            _as_str(payload, 'fairness_tool_policy'),
            VALID_FAIRNESS_TOOL_POLICIES,
            'fairness_tool_policy',
            path,
        ),
        fairness_runtime_policy=_as_literal(
            _as_str(payload, 'fairness_runtime_policy'),
            VALID_FAIRNESS_RUNTIME_POLICIES,
            'fairness_runtime_policy',
            path,
        ),
        runner_isolation_mode=_as_literal(
            _as_str(payload, 'runner_isolation_mode'),
            VALID_RUNNER_ISOLATION_MODES,
            'runner_isolation_mode',
            path,
        ),  # type: ignore[arg-type]
        runner_resume_policy=_as_literal(
            _as_str(payload, 'runner_resume_policy'),
            VALID_RUNNER_RESUME_POLICIES,
            'runner_resume_policy',
            path,
        ),  # type: ignore[arg-type]
        runner_readiness_timeout_seconds=_as_int(payload, 'runner_readiness_timeout_seconds'),
        scoring_mode=_as_literal(_as_str(payload, 'scoring_mode'), VALID_SCORING_MODES, 'scoring_mode', path),  # type: ignore[arg-type]
        judge_model=_as_str(payload, 'judge_model'),
        judge_temperature=_as_float(payload, 'judge_temperature'),
        output_root=_as_str(payload, 'output_root'),
        output_directory_policy=_as_literal(
            _as_str(payload, 'output_directory_policy'),
            VALID_OUTPUT_DIRECTORY_POLICIES,
            'output_directory_policy',
            path,
        ),  # type: ignore[arg-type]
    )


def load_variant_manifest(path: Path) -> VariantManifest:
    payload: dict[str, Any] = load_simple_yaml(path)
    _require_fields(
        path=path,
        payload=payload,
        fields=REQUIRED_VARIANT_FIELDS,
        allow_empty=EMPTY_VARIANT_FIELDS,
    )
    return VariantManifest(
        id=_as_str(payload, 'id'),
        path=path,
        label=_as_str(payload, 'label'),
        kind=_as_literal(_as_str(payload, 'kind'), VALID_VARIANT_KINDS, 'kind', path),  # type: ignore[arg-type]
        agent_asset_mode=_as_literal(_as_str(payload, 'agent_asset_mode'), VALID_AGENT_ASSET_MODES, 'agent_asset_mode', path),  # type: ignore[arg-type]
        agent_asset_root=_as_str(payload, 'agent_asset_root'),
        agent_asset_overlay_root=_as_str(payload, 'agent_asset_overlay_root'),
        enabled_roles=_as_tuple(payload, 'enabled_roles'),
        disabled_roles=_as_tuple(payload, 'disabled_roles'),
        skill_mode=_as_literal(_as_str(payload, 'skill_mode'), VALID_SKILL_MODES, 'skill_mode', path),  # type: ignore[arg-type]
        enabled_skills=_as_tuple(payload, 'enabled_skills'),
        disabled_skills=_as_tuple(payload, 'disabled_skills'),
        model=_as_str(payload, 'model'),
        temperature=_as_float(payload, 'temperature'),
        runtime_wall_clock_budget_seconds=_as_int(payload, 'runtime_wall_clock_budget_seconds'),
        max_turns=_as_int(payload, 'max_turns'),
        scenario_selector=_as_str(payload, 'scenario_selector'),
        scoring_eligibility=_as_tuple(payload, 'scoring_eligibility'),
    )


def validate_campaign_manifest(path: Path, variant_root: Path | None = None) -> CampaignManifest:
    manifest: CampaignManifest = load_campaign_manifest(path)
    _validate_positive_int(path, 'full_system_repeats', manifest.full_system_repeats)
    _validate_positive_int(path, 'comparison_repeats', manifest.comparison_repeats)
    _validate_nonnegative_budget(path, 'wall_clock_budget_seconds', manifest.wall_clock_budget_seconds)
    _validate_nonnegative_budget(path, 'max_turns', manifest.max_turns)
    _validate_positive_int(path, 'runner_readiness_timeout_seconds', manifest.runner_readiness_timeout_seconds)
    _validate_unit_interval(path, 'fairness_temperature', manifest.fairness_temperature)
    _validate_unit_interval(path, 'judge_temperature', manifest.judge_temperature)

    if not manifest.variants:
        raise BenchmarkValidationError(f'{path} must include at least one variant')

    scenarios: list[BenchmarkScenario] = validate_benchmark_suite(_resolve_path(manifest.benchmark_root))
    selectors: tuple[str, ...] = (
        manifest.scenario_selector,
        manifest.full_system_selector,
        manifest.comparison_selector,
    )
    for selector in selectors:
        _select_scenarios(selector, scenarios, path)

    variants: list[VariantManifest] = _load_referenced_variants(manifest, variant_root or default_variant_root())
    for variant in variants:
        validate_variant_manifest(variant.path)
        _select_scenarios(variant.scenario_selector, scenarios, variant.path)
        _validate_variant_fairness(manifest, variant)

    return manifest


def validate_variant_manifest(path: Path) -> VariantManifest:
    manifest: VariantManifest = load_variant_manifest(path)
    if not manifest.label:
        raise BenchmarkValidationError(f'{path} must include a label')
    _validate_unit_interval(path, 'temperature', manifest.temperature)
    _validate_nonnegative_budget(path, 'runtime_wall_clock_budget_seconds', manifest.runtime_wall_clock_budget_seconds)
    _validate_nonnegative_budget(path, 'max_turns', manifest.max_turns)

    invalid_scoring: set[str] = set(manifest.scoring_eligibility) - VALID_SCORING_ELIGIBILITY
    if invalid_scoring:
        invalid: str = ', '.join(sorted(invalid_scoring))
        raise BenchmarkValidationError(f'{path} has invalid scoring eligibility: {invalid}')
    if not manifest.scoring_eligibility:
        raise BenchmarkValidationError(f'{path} must include at least one scoring eligibility')

    if manifest.kind == 'internal-agent-runtime':
        if not manifest.enabled_roles:
            raise BenchmarkValidationError(f'{path} internal runtime variants must include enabled roles')
    if manifest.agent_asset_mode == 'generated-single-agent' and len(manifest.enabled_roles) != 1:
        raise BenchmarkValidationError(f'{path} generated-single-agent variants must define exactly one enabled role')
    if manifest.agent_asset_mode == 'disable-role' and not manifest.disabled_roles:
        raise BenchmarkValidationError(f'{path} disable-role variants must define disabled roles')
    if manifest.agent_asset_mode == 'disable-skills' and manifest.skill_mode != 'disabled':
        raise BenchmarkValidationError(f'{path} disable-skills variants must set skill_mode to disabled')
    if manifest.skill_mode == 'disabled' and manifest.enabled_skills:
        raise BenchmarkValidationError(f'{path} disabled skill variants cannot list enabled skills')

    return manifest


def _load_referenced_variants(manifest: CampaignManifest, variant_root: Path) -> list[VariantManifest]:
    seen_ids: set[str] = set()
    variants: list[VariantManifest] = []
    missing_variants: list[str] = []
    for variant_id in manifest.variants:
        if variant_id in seen_ids:
            raise BenchmarkValidationError(f'{manifest.path} references duplicate variant id: {variant_id}')
        seen_ids.add(variant_id)
        variant_path: Path = variant_root / f'{variant_id}.yaml'
        if not variant_path.exists():
            missing_variants.append(variant_id)
            continue
        variant: VariantManifest = load_variant_manifest(variant_path)
        if variant.id != variant_id:
            raise BenchmarkValidationError(
                f'{variant_path} id {variant.id} does not match campaign reference {variant_id}'
            )
        variants.append(variant)
    if missing_variants:
        missing: str = ', '.join(missing_variants)
        raise BenchmarkValidationError(f'{manifest.path} references missing variant manifests: {missing}')
    return variants


def _validate_variant_fairness(campaign: CampaignManifest, variant: VariantManifest) -> None:
    if variant.kind != 'internal-agent-runtime':
        return
    if campaign.fairness_model != 'variant-specific' and variant.model != campaign.fairness_model:
        raise BenchmarkValidationError(
            f'{variant.path} model {variant.model} does not match campaign fairness_model {campaign.fairness_model}'
        )
    if variant.temperature != campaign.fairness_temperature:
        raise BenchmarkValidationError(
            f'{variant.path} temperature {variant.temperature} does not match campaign fairness_temperature '
            f'{campaign.fairness_temperature}'
        )
    if campaign.fairness_runtime_policy == 'shared-budget':
        if variant.runtime_wall_clock_budget_seconds != campaign.wall_clock_budget_seconds:
            raise BenchmarkValidationError(
                f'{variant.path} runtime_wall_clock_budget_seconds does not match campaign wall_clock_budget_seconds'
            )
        if variant.max_turns != campaign.max_turns:
            raise BenchmarkValidationError(f'{variant.path} max_turns does not match campaign max_turns')


def _select_scenarios(selector: str, scenarios: list[BenchmarkScenario], path: Path) -> list[BenchmarkScenario]:
    selected: list[BenchmarkScenario] = [
        scenario for scenario in scenarios
        if selector in scenario.subset_tags
    ]
    if not selected:
        raise BenchmarkValidationError(f'{path} selector {selector} does not match any benchmark scenarios')
    return selected


def _resolve_path(value: str) -> Path:
    path: Path = Path(value)
    if path.is_absolute():
        return path
    return repo_root() / path


def _require_fields(
    *,
    path: Path,
    payload: dict[str, Any],
    fields: tuple[str, ...],
    allow_empty: set[str] | None = None,
) -> None:
    empty_allowed: set[str] = allow_empty or set()
    missing_fields: list[str] = [
        field for field in fields
        if field not in payload or (field not in empty_allowed and _is_missing_value(payload[field]))
    ]
    if missing_fields:
        missing: str = ', '.join(missing_fields)
        raise BenchmarkValidationError(f'{path} is missing required fields: {missing}')


def _as_str(payload: dict[str, Any], field: str) -> str:
    value: Any = payload[field]
    if not isinstance(value, str):
        raise BenchmarkValidationError(f'{field} must be a string')
    return value


def _as_tuple(payload: dict[str, Any], field: str) -> tuple[str, ...]:
    value: Any = payload[field]
    if isinstance(value, tuple) and all(isinstance(item, str) for item in value):
        return value
    if isinstance(value, str):
        return (value,)
    raise BenchmarkValidationError(f'{field} must be a list of strings')


def _as_float(payload: dict[str, Any], field: str) -> float:
    value: Any = payload[field]
    if isinstance(value, float):
        return value
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError as exc:
            raise BenchmarkValidationError(f'{field} must be a number') from exc
    raise BenchmarkValidationError(f'{field} must be a number')


def _as_int(payload: dict[str, Any], field: str) -> int:
    value: float = _as_float(payload, field)
    if not value.is_integer():
        raise BenchmarkValidationError(f'{field} must be an integer')
    return int(value)


def _as_literal(value: str, valid: set[str], field: str, path: Path) -> Any:
    if value not in valid:
        allowed: str = ', '.join(sorted(valid))
        raise BenchmarkValidationError(f'{path} has invalid {field}: {value}; expected one of {allowed}')
    return value


def _validate_positive_int(path: Path, field: str, value: int) -> None:
    if value <= 0:
        raise BenchmarkValidationError(f'{path} {field} must be positive')


def _validate_nonnegative_budget(path: Path, field: str, value: int) -> None:
    if value < 0:
        raise BenchmarkValidationError(f'{path} {field} must be non-negative')


def _validate_unit_interval(path: Path, field: str, value: float) -> None:
    if not 0 <= value <= 1:
        raise BenchmarkValidationError(f'{path} {field} must be between 0 and 1')


def _is_missing_value(value: Any) -> bool:
    return value == '' or value == () or value == []
