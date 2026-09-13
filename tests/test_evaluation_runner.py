from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

from app.evaluation.benchmarks import BenchmarkValidationError
from app.evaluation.runner import (
    CAMPAIGN_INIT_SCHEMA,
    PlannedAttempt,
    _variant_runtime_env,
    allocate_run_bundle,
    initialize_campaign_run,
)

THESIS_REAL_CORE_IDS: set[str] = {'C06', 'C09', 'P01', 'P07', 'P08', 'R04', 'R07', 'X01'}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _campaign_path() -> Path:
    return _repo_root() / 'app' / 'evaluation_assets' / 'campaigns' / 'thesis-balanced-v1.yaml'


def _variant_root() -> Path:
    return _repo_root() / 'app' / 'evaluation_assets' / 'variants'


def _planned_attempt(root: Path) -> PlannedAttempt:
    return PlannedAttempt(
        id='full-system__P01__r001',
        variant_id='full-system',
        scenario_id='P01',
        repeat_index=1,
        run_bundle_path=root / 'runs' / 'full-system' / 'P01' / 'repeat-001',
    )


def test_initialize_campaign_run_creates_timestamped_root_and_manifest_snapshots(tmp_path: Path) -> None:
    timestamp = datetime(2026, 4, 29, 1, 2, 3, tzinfo=UTC)

    initialized = initialize_campaign_run(
        _campaign_path(),
        variant_root=_variant_root(),
        output_root=tmp_path,
        timestamp=timestamp,
    )

    assert initialized.directories.root == tmp_path / '20260429T010203Z-thesis-balanced-v1'
    assert initialized.campaign_snapshot_path == initialized.directories.manifests / 'campaign.yaml'
    assert initialized.plan_path == initialized.directories.root / 'campaign-plan.json'
    assert initialized.planned_attempts
    assert initialized.campaign_snapshot_path.read_text(encoding='utf-8').startswith('id: thesis-balanced-v1')
    assert (initialized.directories.manifests / 'variants' / 'full-system.yaml').exists()
    assert (initialized.directories.manifests / 'scenarios' / 'P01-p01-clear-local-kde.yaml').exists()
    assert initialized.directories.root.parent == tmp_path
    assert not initialized.directories.runs.exists()
    assert not initialized.directories.logs.exists()
    assert initialized.directories.app_support is None
    assert not initialized.directories.workspace.exists()
    assert initialized.directories.runtime_config is None
    assert not initialized.directories.runtime_assets.exists()
    assert not (initialized.directories.root / 'app-support').exists()
    assert not (initialized.directories.root / 'runtime-config').exists()
    assert not (initialized.directories.root / 'workspace').exists()

    plan = json.loads(initialized.plan_path.read_text(encoding='utf-8'))
    assert plan['schema'] == CAMPAIGN_INIT_SCHEMA
    assert plan['campaign']['id'] == 'thesis-balanced-v1'
    assert plan['campaign']['snapshot_path'] == 'manifests/campaign.yaml'
    assert plan['directories']['runs'] == 'runs'
    assert 'app_support' not in plan['directories']
    assert 'runtime_config' not in plan['directories']
    assert 'workspace' not in plan['directories']
    assert plan['runner']['resume_policy'] == 'append-attempts'
    assert plan['attempt_count'] == len(initialized.planned_attempts)
    assert all(str(attempt['run_bundle_path']).startswith('runs/') for attempt in plan['attempts'])
    full_system = next(variant for variant in plan['variants'] if variant['id'] == 'full-system')
    assert not any(variant['id'] == 'deterministic-gis-reference' for variant in plan['variants'])
    assert plan['attempt_count'] == 60
    assert {scenario['id'] for scenario in plan['scenarios']} == THESIS_REAL_CORE_IDS
    assert full_system['scenario_selector'] == 'thesis-core-real-v1'
    assert full_system['repeat_count'] == 3


def test_initialize_campaign_run_expands_strategy_profile_attempts(tmp_path: Path) -> None:
    initialized = initialize_campaign_run(
        _campaign_path(),
        variant_root=_variant_root(),
        output_root=tmp_path,
        timestamp=datetime(2026, 4, 29, 1, 2, 3, tzinfo=UTC),
        strategy_profile_ids=('balanced', 'crs_first'),
    )

    plan = json.loads(initialized.plan_path.read_text(encoding='utf-8'))
    strategy_attempts = [attempt for attempt in initialized.planned_attempts if attempt.strategy is not None]
    deterministic_attempts = [
        attempt for attempt in initialized.planned_attempts if attempt.variant_id == 'deterministic-gis-reference'
    ]

    assert {profile.id for profile in initialized.strategy_profiles} == {'balanced', 'crs_first'}
    assert strategy_attempts
    assert all(attempt.strategy is None for attempt in deterministic_attempts)
    assert 'full-system__balanced__P01__r001' in {attempt.id for attempt in initialized.planned_attempts}
    assert 'full-system__crs_first__P01__r001' in {attempt.id for attempt in initialized.planned_attempts}
    assert plan['strategy_profiles'][0]['profile_hash']
    first_strategy = next(attempt for attempt in plan['attempts'] if attempt['strategy'] is not None)
    assert first_strategy['strategy']['source'] == 'offline-sweep'
    assert first_strategy['run_bundle_path'].startswith('runs/full-system/')


def test_initialize_campaign_run_allocates_unique_timestamped_root(tmp_path: Path) -> None:
    timestamp = datetime(2026, 4, 29, 1, 2, 3, tzinfo=UTC)

    first = initialize_campaign_run(
        _campaign_path(),
        variant_root=_variant_root(),
        output_root=tmp_path,
        timestamp=timestamp,
    )
    second = initialize_campaign_run(
        _campaign_path(),
        variant_root=_variant_root(),
        output_root=tmp_path,
        timestamp=timestamp,
    )

    assert first.directories.root.name == '20260429T010203Z-thesis-balanced-v1'
    assert second.directories.root.name == '20260429T010203Z-thesis-balanced-v1-002'


def test_initialize_campaign_run_resolves_relative_output_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    timestamp = datetime(2026, 4, 29, 1, 2, 3, tzinfo=UTC)
    monkeypatch.chdir(tmp_path)

    initialized = initialize_campaign_run(
        _campaign_path(),
        variant_root=_variant_root(),
        output_root=Path('relative-output'),
        timestamp=timestamp,
    )

    expected_root = tmp_path / 'relative-output' / '20260429T010203Z-thesis-balanced-v1'
    assert initialized.directories.root == expected_root
    assert initialized.directories.manifests.is_absolute()
    assert initialized.directories.runs.is_absolute()
    assert initialized.directories.logs.is_absolute()
    assert initialized.directories.workspace.is_absolute()
    assert initialized.directories.runtime_assets.is_absolute()
    assert initialized.directories.app_support is None
    assert initialized.directories.runtime_config is None


def test_initialize_campaign_run_rejects_non_empty_explicit_output_directory(tmp_path: Path) -> None:
    campaign_path = tmp_path / 'campaign.yaml'
    campaign_path.write_text(
        _campaign_path().read_text(encoding='utf-8').replace(
            'output_directory_policy: timestamped-campaign-dir',
            'output_directory_policy: explicit-empty-directory',
        ),
        encoding='utf-8',
    )
    output_root = tmp_path / 'already-used'
    output_root.mkdir()
    (output_root / 'existing.txt').write_text('occupied', encoding='utf-8')

    with pytest.raises(BenchmarkValidationError, match='not empty'):
        initialize_campaign_run(
            campaign_path,
            variant_root=_variant_root(),
            output_root=output_root,
            timestamp=datetime(2026, 4, 29, tzinfo=UTC),
        )


def test_allocate_run_bundle_uses_planned_path_when_available(tmp_path: Path) -> None:
    planned_attempt = _planned_attempt(tmp_path)

    allocation = allocate_run_bundle(planned_attempt)

    assert allocation.id == planned_attempt.id
    assert allocation.path == planned_attempt.run_bundle_path
    assert allocation.attempt_number == 1
    assert allocation.path.exists()


def test_allocate_run_bundle_appends_attempt_number_when_existing(tmp_path: Path) -> None:
    planned_attempt = _planned_attempt(tmp_path)
    first = allocate_run_bundle(planned_attempt)

    second = allocate_run_bundle(planned_attempt)

    assert first.path == planned_attempt.run_bundle_path
    assert second.id == 'full-system__P01__r001__a002'
    assert second.path == planned_attempt.run_bundle_path.with_name('repeat-001-attempt-002')
    assert first.path.exists()
    assert second.path.exists()


def test_allocate_run_bundle_rejects_existing_path_when_policy_requires_it(tmp_path: Path) -> None:
    planned_attempt = _planned_attempt(tmp_path)
    allocate_run_bundle(planned_attempt, resume_policy='fail-if-existing')

    with pytest.raises(BenchmarkValidationError, match='already exists'):
        allocate_run_bundle(planned_attempt, resume_policy='fail-if-existing')


def test_inherited_evaluation_variant_does_not_override_selected_provider_model(tmp_path: Path) -> None:
    initialized = initialize_campaign_run(
        _campaign_path(),
        variant_root=_variant_root(),
        output_root=tmp_path,
        timestamp=datetime(2026, 4, 29, tzinfo=UTC),
    )
    full_system = next(variant for variant in initialized.variants if variant.id == 'full-system')

    env = _variant_runtime_env(initialized.campaign, full_system, tmp_path / 'agent-assets')

    assert env == {'GEO_AGENT_AGENT_ASSET_ROOT': str(tmp_path / 'agent-assets')}
    assert 'GEO_AGENT_GLM_MODEL' not in env
    assert 'GEO_AGENT_DEEPSEEK_MODEL' not in env

    overridden = _variant_runtime_env(
        initialized.campaign,
        full_system,
        tmp_path / 'agent-assets',
        overrides={
            'GEO_AGENT_MODEL_PROVIDER': 'deepseek',
            'GEO_AGENT_DEEPSEEK_MODEL': 'deepseek-v4-flash',
        },
    )

    assert overridden['GEO_AGENT_MODEL_PROVIDER'] == 'deepseek'
    assert overridden['GEO_AGENT_DEEPSEEK_MODEL'] == 'deepseek-v4-flash'
