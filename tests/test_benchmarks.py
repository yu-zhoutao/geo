from __future__ import annotations

from pathlib import Path

import pytest

from app.evaluation.benchmarks import (
    BenchmarkValidationError,
    load_simple_yaml,
    validate_benchmark_scenario,
    validate_benchmark_suite,
)

THESIS_REAL_CORE_IDS: set[str] = {'C06', 'C09', 'P01', 'P07', 'P08', 'R04', 'R07', 'X01'}
THESIS_REAL_ABLATION_IDS: set[str] = {'C09', 'P01', 'R07', 'X01'}


def _benchmark_root() -> Path:
    return Path(__file__).resolve().parents[1] / 'app' / 'agent_assets' / 'benchmarks'


def test_benchmark_assets_include_schema_scorecards_and_baselines() -> None:
    root: Path = _benchmark_root()

    assert (root / 'scenario-schema.yaml').exists()
    assert (root / 'scorecards.md').exists()
    assert (root / 'baselines.md').exists()


def test_core_and_stress_benchmark_counts_match_change_targets() -> None:
    root: Path = _benchmark_root()

    core_cases: list[Path] = sorted((root / 'core').glob('*.yaml'))
    stress_cases: list[Path] = sorted((root / 'stress').glob('*.yaml'))

    assert len(core_cases) == 36
    assert len(stress_cases) == 8


def test_legacy_kde_core_suite_keeps_balanced_gold_control_states() -> None:
    root: Path = _benchmark_root()
    counts: dict[str, int] = {'proceed': 0, 'clarify': 0, 'repair': 0, 'stop': 0}
    legacy_ids: set[str] = {
        *(f'P{index:02d}' for index in range(1, 7)),
        *(f'C{index:02d}' for index in range(1, 7)),
        *(f'R{index:02d}' for index in range(1, 7)),
        *(f'S{index:02d}' for index in range(1, 7)),
    }

    for path in (root / 'core').glob('*.yaml'):
        payload: dict[str, object] = load_simple_yaml(path)
        if str(payload['id']) in legacy_ids:
            counts[str(payload['gold_control_state'])] += 1

    assert counts == {'proceed': 6, 'clarify': 6, 'repair': 6, 'stop': 6}


def test_new_task_families_cover_gold_control_states() -> None:
    scenarios = validate_benchmark_suite(_benchmark_root())
    expected_states: set[str] = {'proceed', 'clarify', 'repair', 'stop'}

    for family in ('spatial_interpolation', 'spatial_hotspot'):
        states: set[str] = {
            scenario.gold_control_state
            for scenario in scenarios
            if scenario.task_family == family
        }
        assert states == expected_states


def test_benchmark_schema_allows_current_task_families() -> None:
    schema: str = (_benchmark_root() / 'scenario-schema.yaml').read_text(encoding='utf-8')

    assert 'spatial_interpolation' in schema
    assert 'spatial_hotspot' in schema


def test_benchmark_suite_contains_required_guardrail_cases() -> None:
    scenarios = validate_benchmark_suite(_benchmark_root())
    case_ids: set[str] = {scenario.id for scenario in scenarios}

    assert {'S01', 'S02', 'S03', 'R01', 'R05', 'P09', 'P10', 'C09', 'S09', 'X01', 'X07'}.issubset(case_ids)


def test_new_family_fixtures_assert_evidence_and_forbidden_conflation() -> None:
    root: Path = _benchmark_root()

    for path in (root / 'core').glob('*.yaml'):
        payload: dict[str, object] = load_simple_yaml(path)
        family: object = payload.get('task_family')
        required_artifacts: set[str] = set(payload.get('required_artifacts', ()))
        forbidden_moves: set[str] = set(payload.get('forbidden_moves', ()))
        if family == 'spatial_interpolation':
            assert {'study_design.json', 'data_audit.json', 'claim_trace.json'}.issubset(required_artifacts)
            assert forbidden_moves & {'route-idw-to-kde', 'claim-significance-from-idw', 'run-idw-without-value-field'}
        if family == 'spatial_hotspot':
            assert {'study_design.json', 'data_audit.json', 'claim_trace.json'}.issubset(required_artifacts)
            assert forbidden_moves & {'route-gistar-to-kde', 'run-gistar-on-raw-points', 'label-high-values-as-significant'}


def test_benchmark_suite_has_complete_extended_metadata() -> None:
    scenarios = validate_benchmark_suite(_benchmark_root())

    assert len(scenarios) == 44
    assert all(scenario.dataset_pack for scenario in scenarios)
    assert all(scenario.oracle_id.startswith('ORACLE-') for scenario in scenarios)
    assert all(scenario.judge_rubric == 'geospatial-task-quality-v2' for scenario in scenarios)
    assert all('full-suite' in scenario.subset_tags for scenario in scenarios)
    assert all(scenario.scoring_weight == 1.0 for scenario in scenarios)


def test_thesis_real_core_subset_uses_existing_china_repo_datasets() -> None:
    scenarios = validate_benchmark_suite(_benchmark_root())
    thesis_core = [
        scenario for scenario in scenarios
        if 'thesis-core-real-v1' in scenario.subset_tags
    ]

    assert {scenario.id for scenario in thesis_core} == THESIS_REAL_CORE_IDS
    assert all(scenario.dataset_root == 'data' for scenario in thesis_core)
    assert all(scenario.dataset_pack_mode == 'repo-files' for scenario in thesis_core)
    assert {scenario.gold_control_state for scenario in thesis_core} == {'proceed', 'clarify', 'repair', 'stop'}
    assert {scenario.task_family for scenario in thesis_core} == {
        'kde',
        'spatial_interpolation',
        'spatial_hotspot',
        'unsupported-future-family',
    }
    assert not any(
        any(fallback in item for fallback in ('纽约', '芝加哥', 'EPA加州'))
        for scenario in thesis_core
        for item in scenario.dataset_pack
    )


def test_thesis_real_ablation_subset_is_minimal_and_balanced() -> None:
    scenarios = validate_benchmark_suite(_benchmark_root())
    ablation = [
        scenario for scenario in scenarios
        if 'thesis-ablation-real-v1' in scenario.subset_tags
    ]

    assert {scenario.id for scenario in ablation} == THESIS_REAL_ABLATION_IDS
    assert {scenario.gold_control_state for scenario in ablation} == {'proceed', 'clarify', 'repair', 'stop'}
    assert any(scenario.split == 'stress' for scenario in ablation)
    assert any(scenario.task_family == 'kde' for scenario in ablation)
    assert any(scenario.task_family == 'spatial_interpolation' for scenario in ablation)
    assert any(scenario.task_family == 'spatial_hotspot' for scenario in ablation)


def test_representative_ablation_subset_covers_thesis_categories() -> None:
    scenarios = validate_benchmark_suite(_benchmark_root())
    ablation = [
        scenario for scenario in scenarios
        if 'ablation-representative' in scenario.subset_tags
    ]

    assert {scenario.gold_control_state for scenario in ablation} == {'proceed', 'clarify', 'repair', 'stop'}
    assert any(scenario.split == 'stress' for scenario in ablation)
    assert any(scenario.task_family == 'reporting-review' for scenario in ablation)
    assert any(scenario.task_family == 'spatial_interpolation' for scenario in ablation)
    assert any(scenario.task_family == 'spatial_hotspot' for scenario in ablation)
    assert any('crs' in category for scenario in ablation for category in scenario.hazard_categories)
    assert any('study-area' in category for scenario in ablation for category in scenario.hazard_categories)
    assert any('unsupported' in category for scenario in ablation for category in scenario.hazard_categories)


def test_benchmark_suite_has_no_deterministic_reference_tags() -> None:
    scenarios = validate_benchmark_suite(_benchmark_root())

    assert not any(
        tag in {'deterministic-reference', 'thesis-reference-real-v1'}
        for scenario in scenarios
        for tag in scenario.subset_tags
    )


def test_repo_file_dataset_pack_requires_existing_files(tmp_path: Path) -> None:
    scenario_path: Path = tmp_path / 'scenario.yaml'
    scenario_path.write_text(
        '\n'.join(
            [
                'id: T01',
                'split: dev',
                'difficulty: L1',
                'task_family: kde',
                'gold_control_state: proceed',
                'user_prompt: |',
                '  Run a small benchmark.',
                'dataset_root: app/agent_assets/benchmarks/datasets',
                'dataset_pack_mode: repo-files',
                'dataset_pack: [missing.geojson]',
                'required_artifacts: [study_design.json]',
                'forbidden_moves: [claim-significance-from-kde]',
                'oracle_id: ORACLE-T01',
                'deterministic_checks: [control-state, forbidden-moves, claim-constraints]',
                'judge_rubric: geospatial-task-quality-v2',
                'scoring_weight: 1.0',
                'subset_tags: [full-suite]',
                'hazard_categories: [happy-path-kde]',
            ]
        )
        + '\n',
        encoding='utf-8',
    )

    from app.evaluation.benchmarks import load_benchmark_scenario

    scenario = load_benchmark_scenario(scenario_path)
    with pytest.raises(BenchmarkValidationError, match='missing dataset pack file'):
        validate_benchmark_scenario(scenario)


def test_scenario_validation_does_not_require_framework_artifact_hints(tmp_path: Path) -> None:
    scenario_path: Path = tmp_path / 'scenario.yaml'
    scenario_path.write_text(
        '\n'.join(
            [
                'id: T02',
                'split: dev',
                'difficulty: L1',
                'task_family: kde',
                'gold_control_state: proceed',
                'user_prompt: |',
                '  Run a small benchmark.',
                'dataset_root: app/agent_assets/benchmarks/datasets',
                'dataset_pack_mode: synthetic',
                'dataset_pack: [points.geojson]',
                'forbidden_moves: [claim-significance-from-kde]',
                'oracle_id: ORACLE-T02',
                'judge_rubric: geospatial-task-quality-v2',
                'scoring_weight: 1.0',
                'subset_tags: [full-suite]',
                'hazard_categories: [happy-path-kde]',
            ]
        )
        + '\n',
        encoding='utf-8',
    )

    from app.evaluation.benchmarks import load_benchmark_scenario

    scenario = load_benchmark_scenario(scenario_path)
    validate_benchmark_scenario(scenario)

    assert scenario.required_artifacts == ()
    assert scenario.deterministic_checks == ()
