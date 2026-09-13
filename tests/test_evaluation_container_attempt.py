from __future__ import annotations

import json
from pathlib import Path

from app.evaluation.benchmarks import BenchmarkScenario
from app.evaluation.container_attempt import (
    container_scenario_data_attachments,
    main,
    parse_args,
)
from app.evaluation.scenario_execution import prepare_scenario_data_attachments


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_container_attempt_parse_args_accepts_single_attempt_identity(tmp_path: Path) -> None:
    config = parse_args([
        '--run-id',
        'full-system__P07__r001',
        '--variant-id',
        'full-system',
        '--scenario-id',
        'P07',
        '--repeat-index',
        '1',
        '--attempt-number',
        '2',
        '--run-bundle-path',
        str(tmp_path / 'run'),
        '--data-root',
        str(tmp_path / 'data'),
        '--scoring-mode',
        'llm-judge',
        '--judge-model',
        'glm-5.1',
    ])

    assert config.run_id == 'full-system__P07__r001'
    assert config.variant_id == 'full-system'
    assert config.scenario_id == 'P07'
    assert config.repeat_index == 1
    assert config.attempt_number == 2
    assert config.scoring_mode == 'llm-judge'


def test_container_attempt_missing_scenario_writes_failed_status(tmp_path: Path) -> None:
    run_bundle = tmp_path / 'run'

    exit_code = main([
        '--run-id',
        'full-system__ZZZ__r001',
        '--variant-id',
        'full-system',
        '--scenario-id',
        'ZZZ',
        '--repeat-index',
        '1',
        '--run-bundle-path',
        str(run_bundle),
    ])

    status = json.loads((run_bundle / 'run-status.json').read_text(encoding='utf-8'))
    manifest = json.loads((run_bundle / 'run-manifest.json').read_text(encoding='utf-8'))
    assert exit_code == 1
    assert status['session_status'] == 'failed'
    assert status['terminal_reason'] == 'container_entrypoint_failed'
    assert manifest['scenario']['id'] == 'ZZZ'


def test_container_synthetic_dataset_materializes_under_run_bundle(tmp_path: Path) -> None:
    scenario = _scenario('synthetic', dataset_root='app/agent_assets/benchmarks/datasets')

    attachments = container_scenario_data_attachments(
        scenario,
        data_root=tmp_path / 'data',
        run_bundle_path=tmp_path / 'run',
    )

    expected = prepare_scenario_data_attachments(scenario, tmp_path / 'run' / 'dataset-pack')
    assert attachments == expected
    assert (tmp_path / 'run' / 'dataset-pack' / 'dataset-pack-manifest.json').exists()


def test_container_repo_file_dataset_resolves_under_readonly_data_mount(tmp_path: Path) -> None:
    scenario = _scenario('repo-files', dataset_root='data/北京空气质量')

    attachments = container_scenario_data_attachments(
        scenario,
        data_root=tmp_path / 'data',
        run_bundle_path=tmp_path / 'run',
    )

    assert attachments == [
        {
            'id': 'scenario-p99-dataset-root',
            'path': str((tmp_path / 'data' / '北京空气质量').resolve()),
            'enabled': True,
            'label': 'P99 dataset root',
        }
    ]


def _scenario(dataset_pack_mode: str, *, dataset_root: str) -> BenchmarkScenario:
    return BenchmarkScenario(
        id='P99',
        path=_repo_root() / 'app' / 'agent_assets' / 'benchmarks' / 'core' / 'p01-clear-local-kde.yaml',
        split='dev',
        difficulty='L1',
        task_family='kde',
        gold_control_state='proceed',
        user_prompt='测试任务',
        dataset_root=dataset_root,
        dataset_pack_mode=dataset_pack_mode,  # type: ignore[arg-type]
        dataset_pack=('fcd_points_sample.csv', 'beijing_boundary.geojson'),
        required_artifacts=('study_design.json',),
        forbidden_moves=(),
        oracle_id='oracle',
        deterministic_checks=('control-state', 'forbidden-moves', 'claim-constraints'),
        judge_rubric='geospatial-agent-v1',
        scoring_weight=1.0,
        subset_tags=('full-suite',),
        hazard_categories=('kde',),
    )
