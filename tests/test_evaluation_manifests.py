from __future__ import annotations

from pathlib import Path

import pytest

from app.evaluation.benchmarks import BenchmarkValidationError
from app.evaluation.manifests import validate_campaign_manifest, validate_variant_manifest
from app.evaluation.strategy_profiles import load_strategy_profiles, validate_strategy_profile


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _list_field(name: str, values: tuple[str, ...]) -> str:
    if not values:
        return f'{name}: []'
    lines: list[str] = [f'{name}:']
    lines.extend(f'  - {value}' for value in values)
    return '\n'.join(lines)


def _write_variant(
    variant_root: Path,
    variant_id: str = 'full-system',
    *,
    kind: str = 'internal-agent-runtime',
    agent_asset_mode: str = 'default',
    enabled_roles: tuple[str, ...] = ('geo-orchestrator',),
    disabled_roles: tuple[str, ...] = (),
    skill_mode: str = 'enabled',
    enabled_skills: tuple[str, ...] = ('all',),
    disabled_skills: tuple[str, ...] = (),
    model: str = 'inherit',
    temperature: str = '0.0',
    wall_clock_budget_seconds: str = '120',
    max_turns: str = '12',
    scenario_selector: str = 'full-suite',
    scoring_eligibility: tuple[str, ...] = ('llm-judge',),
) -> Path:
    variant_root.mkdir(parents=True, exist_ok=True)
    path: Path = variant_root / f'{variant_id}.yaml'
    path.write_text(
        '\n'.join(
            [
                f'id: {variant_id}',
                f'label: {variant_id}',
                f'kind: {kind}',
                f'agent_asset_mode: {agent_asset_mode}',
                'agent_asset_root: app/agent_assets',
                'agent_asset_overlay_root: none',
                _list_field('enabled_roles', enabled_roles),
                _list_field('disabled_roles', disabled_roles),
                f'skill_mode: {skill_mode}',
                _list_field('enabled_skills', enabled_skills),
                _list_field('disabled_skills', disabled_skills),
                f'model: {model}',
                f'temperature: {temperature}',
                f'runtime_wall_clock_budget_seconds: {wall_clock_budget_seconds}',
                f'max_turns: {max_turns}',
                f'scenario_selector: {scenario_selector}',
                _list_field('scoring_eligibility', scoring_eligibility),
            ]
        )
        + '\n',
        encoding='utf-8',
    )
    return path


def _write_campaign(
    tmp_path: Path,
    *,
    variants: tuple[str, ...] = ('full-system',),
    scenario_selector: str = 'full-suite',
    full_system_selector: str = 'full-suite',
    comparison_selector: str = 'ablation-representative',
    fairness_model: str = 'inherit',
    fairness_temperature: str = '0.0',
    wall_clock_budget_seconds: str = '120',
    max_turns: str = '12',
) -> Path:
    path: Path = tmp_path / 'campaign.yaml'
    path.write_text(
        '\n'.join(
            [
                'id: test-campaign',
                'benchmark_version: benchmarks-v1',
                f'benchmark_root: {_repo_root() / "app" / "agent_assets" / "benchmarks"}',
                f'scenario_selector: {scenario_selector}',
                _list_field('variants', variants),
                f'full_system_selector: {full_system_selector}',
                'full_system_repeats: 1',
                f'comparison_selector: {comparison_selector}',
                'comparison_repeats: 1',
                f'wall_clock_budget_seconds: {wall_clock_budget_seconds}',
                f'max_turns: {max_turns}',
                f'fairness_model: {fairness_model}',
                f'fairness_temperature: {fairness_temperature}',
                'fairness_dataset_policy: scenario-dataset-pack',
                'fairness_tool_policy: shared-tool-catalog',
                'fairness_runtime_policy: shared-budget',
                'runner_isolation_mode: per-campaign',
                'runner_resume_policy: append-attempts',
                'runner_readiness_timeout_seconds: 30',
                'scoring_mode: llm-judge',
                'judge_model: configured-evaluation-judge',
                'judge_temperature: 0.0',
                'output_root: evaluation-runs',
                'output_directory_policy: timestamped-campaign-dir',
            ]
        )
        + '\n',
        encoding='utf-8',
    )
    return path


def test_evaluation_assets_include_manifest_schemas() -> None:
    root: Path = _repo_root() / 'app' / 'evaluation_assets'

    assert (root / 'campaign-schema.yaml').exists()
    assert (root / 'variant-schema.yaml').exists()
    assert (root / 'strategy-profile-schema.yaml').exists()


def test_strategy_profile_assets_validate_and_hash() -> None:
    root: Path = _repo_root() / 'app' / 'evaluation_assets' / 'strategy_profiles'

    profiles = load_strategy_profiles(root)

    assert {profile.id for profile in profiles} >= {
        'balanced',
        'crs_first',
        'claim_conservative',
        'repair_stop_first',
        'sensitivity_first',
    }
    assert all(profile.profile_hash for profile in profiles)


def test_strategy_profile_rejects_unknown_overlay(tmp_path: Path) -> None:
    path = tmp_path / 'bad.yaml'
    path.write_text(
        '\n'.join(
            [
                'id: bad_profile',
                'label: Bad profile',
                'source: curated-profile',
                'focus_dimensions: [crs_and_units]',
                'agent_asset_overlay_root: app/evaluation_assets/missing-strategy-overlay',
                'guidance: |',
                '  Be careful.',
            ]
        )
        + '\n',
        encoding='utf-8',
    )

    with pytest.raises(BenchmarkValidationError, match='missing strategy overlay'):
        validate_strategy_profile(path)


def test_thesis_campaign_manifest_validates_against_initial_variants() -> None:
    root: Path = _repo_root() / 'app' / 'evaluation_assets'

    manifest = validate_campaign_manifest(
        root / 'campaigns' / 'thesis-balanced-v1.yaml',
        root / 'variants',
    )

    assert manifest.variants == (
        'full-system',
        'single-agent',
        'no-skills',
        'no-skeptical-review',
    )
    assert manifest.scenario_selector == 'thesis-core-real-v1'
    assert manifest.full_system_selector == 'thesis-core-real-v1'
    assert manifest.full_system_repeats == 3
    assert manifest.comparison_selector == 'thesis-ablation-real-v1'
    assert manifest.comparison_repeats == 3
    assert not hasattr(manifest, 'deterministic_reference_selector')
    assert not hasattr(manifest, 'deterministic_reference_repeats')
    assert manifest.wall_clock_budget_seconds == 3600
    assert manifest.max_turns == 0
    assert manifest.scoring_mode == 'llm-judge'
    assert manifest.judge_model == 'glm-5.1'
    assert manifest.output_root == 'evaluation-runs'
    for variant_id in manifest.variants:
        variant = validate_variant_manifest(root / 'variants' / f'{variant_id}.yaml')

        assert variant.runtime_wall_clock_budget_seconds == manifest.wall_clock_budget_seconds


def test_campaign_manifest_requires_required_fields(tmp_path: Path) -> None:
    path: Path = tmp_path / 'campaign.yaml'
    path.write_text('id: incomplete\n', encoding='utf-8')

    with pytest.raises(BenchmarkValidationError, match='missing required fields'):
        validate_campaign_manifest(path, tmp_path / 'variants')


def test_variant_manifest_rejects_invalid_kind(tmp_path: Path) -> None:
    path: Path = _write_variant(tmp_path, kind='unknown-kind')

    with pytest.raises(BenchmarkValidationError, match='invalid kind'):
        validate_variant_manifest(path)


def test_variant_manifest_rejects_removed_deterministic_reference_kind(tmp_path: Path) -> None:
    path: Path = _write_variant(
        tmp_path,
        kind='deterministic-reference',
        agent_asset_mode='deterministic-reference',
        enabled_roles=(),
        skill_mode='disabled',
        enabled_skills=(),
        disabled_skills=('all',),
    )

    with pytest.raises(BenchmarkValidationError, match='invalid kind'):
        validate_variant_manifest(path)


def test_campaign_manifest_rejects_invalid_scenario_selector(tmp_path: Path) -> None:
    variant_root: Path = tmp_path / 'variants'
    _write_variant(variant_root)
    path: Path = _write_campaign(tmp_path, scenario_selector='not-a-real-selector')

    with pytest.raises(BenchmarkValidationError, match='does not match any benchmark scenarios'):
        validate_campaign_manifest(path, variant_root)


def test_campaign_manifest_rejects_invalid_variant_reference(tmp_path: Path) -> None:
    path: Path = _write_campaign(tmp_path, variants=('missing-variant',))

    with pytest.raises(BenchmarkValidationError, match='missing variant manifests'):
        validate_campaign_manifest(path, tmp_path / 'variants')


def test_campaign_manifest_rejects_fairness_model_mismatch(tmp_path: Path) -> None:
    variant_root: Path = tmp_path / 'variants'
    _write_variant(variant_root, model='other-model')
    path: Path = _write_campaign(tmp_path, fairness_model='inherit')

    with pytest.raises(BenchmarkValidationError, match='does not match campaign fairness_model'):
        validate_campaign_manifest(path, variant_root)


def test_campaign_manifest_accepts_valid_manifest(tmp_path: Path) -> None:
    variant_root: Path = tmp_path / 'variants'
    _write_variant(variant_root)
    path: Path = _write_campaign(tmp_path)

    manifest = validate_campaign_manifest(path, variant_root)

    assert manifest.id == 'test-campaign'
    assert manifest.variants == ('full-system',)
