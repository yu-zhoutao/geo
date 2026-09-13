from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from app.evaluation.aggregation import (
    CAMPAIGN_SUMMARY_FILENAME,
    EXPORT_DIRNAME,
    RUN_SCORES_FILENAME,
    SCENARIO_DIMENSION_SCORES_FILENAME,
    THESIS_SUMMARY_FILENAME,
    VARIANT_DIMENSION_SCORES_FILENAME,
    VARIANT_SCENARIO_SCORES_FILENAME,
    aggregate_campaign,
    load_run_records,
)
from app.evaluation.judge_rubrics import GEOSPATIAL_AGENT_RUBRIC
from app.evaluation.llm_judge import JUDGE_SCORE_FILENAME
from app.evaluation.rl_online import (
    TRLOnlineRewardFunction,
    _resume_completion_offset,
    load_online_rl_manifest,
    run_mock_online_training,
)
from app.evaluation.rl_experiment import write_policy_stub_evaluation
from app.evaluation.rl_rewards import REWARD_RECORD_FILENAME, build_reward_record, write_reward_table
from app.evaluation.rl_task import SELECT_STRATEGY_TOOL_NAME, StrategyRolloutBridge
from app.evaluation.run_bundles import RUN_MANIFEST_FILENAME, RUN_STATUS_FILENAME


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _dimension_payload(score: int) -> dict[str, dict[str, object]]:
    return {
        dimension.id: {'score': score, 'reason': f'{dimension.id} reason'}
        for dimension in GEOSPATIAL_AGENT_RUBRIC.dimensions
    }


def _write_run(
    campaign_root: Path,
    *,
    variant_id: str,
    scenario_id: str,
    score: int | None,
    session_status: str = 'completed',
    terminal_reason: str = 'completed',
    continuation_count: int = 0,
    error_count: int = 0,
    errors: tuple[str, ...] = (),
    strategy_id: str | None = None,
    reward: float | None = None,
    policy_checkpoint_id: str | None = None,
    trl_run_id: str | None = None,
    training_step: int | None = None,
) -> Path:
    bundle = campaign_root / 'runs' / variant_id / scenario_id / 'repeat-001'
    _write_json(
        bundle / RUN_MANIFEST_FILENAME,
        {
            'run_id': f'{variant_id}__{scenario_id}__r001',
            'variant': {'id': variant_id},
            'strategy': {
                'strategy_id': strategy_id,
                'source': 'offline-sweep',
                'profile_hash': 'profile-hash',
                'policy_run_id': 'policy-1',
                'policy_checkpoint_id': policy_checkpoint_id,
                'trl_run_id': trl_run_id,
                'training_step': training_step,
                'action_valid': True,
                'action_rationale': 'test',
            } if strategy_id is not None else None,
            'scenario': {
                'id': scenario_id,
                'fixture_hash': f'{scenario_id}-fixture-hash',
                'split': 'dev',
                'difficulty': 'L1',
                'task_family': 'kde',
                'gold_control_state': 'proceed',
                'hazard_categories': ['crs-projection'],
            },
        },
    )
    _write_json(
        bundle / RUN_STATUS_FILENAME,
        {
            'schema': 'geo-agent.evaluation.run-status.v1',
            'session_status': session_status,
            'terminal_reason': terminal_reason,
            'timed_out': False,
            'duration_seconds': 12.5,
            'continuation_count': continuation_count,
            'error_count': error_count,
            'errors': list(errors),
            'strategy': {
                'strategy_id': strategy_id,
                'source': 'offline-sweep',
                'profile_hash': 'profile-hash',
                'policy_run_id': 'policy-1',
                'policy_checkpoint_id': policy_checkpoint_id,
                'trl_run_id': trl_run_id,
                'training_step': training_step,
                'action_valid': True,
                'action_rationale': 'test',
            } if strategy_id is not None else None,
        },
    )
    if reward is not None:
        _write_json(
            bundle / REWARD_RECORD_FILENAME,
            {
                'schema': 'geo-agent.evaluation.rl-reward.v1',
                'run_id': f'{variant_id}__{scenario_id}__r001',
                'scenario_id': scenario_id,
                'strategy_id': strategy_id,
                'reward': reward,
                'reward_source': 'offline-sweep',
                'components': {'dimension.overall_task_success': reward},
            },
        )
    if score is not None:
        parsed_score: dict[str, object] = {
            'dimensions': _dimension_payload(score),
            'summary': f'{score}-point run',
        }
        _write_json(
            bundle / JUDGE_SCORE_FILENAME,
            {
                'schema': 'geo-agent.evaluation.judge-result.v1',
                'scenario_id': scenario_id,
                'model': 'glm-5.1',
                'temperature': 0.0,
                'judged_at': '2026-05-01T00:00:00+00:00',
                'attempts': [{'index': 1, 'raw_response': '{}', 'parsed_score': parsed_score, 'error': None}],
                'parsed_score': parsed_score,
            },
        )
    return bundle


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open('r', encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def _scenario_stub(scenario_id: str = 'P01') -> object:
    return type(
        'Scenario',
        (),
        {
            'id': scenario_id,
            'split': 'dev',
            'difficulty': 'L1',
            'task_family': 'kde',
            'user_prompt': 'Run KDE',
            'dataset_pack_mode': 'repo-files',
            'dataset_pack': ('points.geojson',),
            'hazard_categories': ('crs-projection',),
            'forbidden_moves': ('claim-significance-from-kde',),
        },
    )()


def test_aggregate_campaign_exports_dimension_scores_and_runtime_status(tmp_path: Path) -> None:
    campaign_root = tmp_path / 'campaign'
    _write_run(campaign_root, variant_id='full-system', scenario_id='P01', score=5, continuation_count=1)
    _write_run(campaign_root, variant_id='full-system', scenario_id='C06', score=3)
    _write_run(campaign_root, variant_id='no-skills', scenario_id='P01', score=2)
    _write_run(
        campaign_root,
        variant_id='single-agent',
        scenario_id='C09',
        score=None,
        session_status='failed',
        terminal_reason='runtime_error',
        error_count=1,
        errors=('RuntimeError: opencode crashed',),
    )

    summary = aggregate_campaign(campaign_root)
    records = load_run_records(campaign_root)
    export_root = campaign_root / EXPORT_DIRNAME

    assert summary['schema'] == 'geo-agent.evaluation.dimension-score-summary.v1'
    assert summary['run_count'] == 4
    assert summary['scored_run_count'] == 3
    assert len(records) == 4
    assert summary['dimension_ids'] == [dimension.id for dimension in GEOSPATIAL_AGENT_RUBRIC.dimensions]
    assert (export_root / CAMPAIGN_SUMMARY_FILENAME).exists()
    assert (export_root / RUN_SCORES_FILENAME).exists()
    assert (export_root / VARIANT_DIMENSION_SCORES_FILENAME).exists()
    assert (export_root / SCENARIO_DIMENSION_SCORES_FILENAME).exists()
    assert (export_root / VARIANT_SCENARIO_SCORES_FILENAME).exists()
    assert (export_root / THESIS_SUMMARY_FILENAME).exists()
    assert not (export_root / 'full-system-reliability.csv').exists()
    assert not (export_root / 'ablation-comparison.csv').exists()
    assert not (export_root / 'structural-baseline.csv').exists()
    assert not (export_root / 'guardrail-failures.csv').exists()

    run_rows = _csv_rows(export_root / RUN_SCORES_FILENAME)
    variant_rows = _csv_rows(export_root / VARIANT_DIMENSION_SCORES_FILENAME)
    failed_row = next(row for row in run_rows if row['run_id'] == 'single-agent__C09__r001')
    full_system_row = next(row for row in variant_rows if row['variant_id'] == 'full-system')

    assert failed_row['judge_status'] == 'missing'
    assert failed_row['session_status'] == 'failed'
    assert failed_row['terminal_reason'] == 'runtime_error'
    assert failed_row['error_count'] == '1'
    assert failed_row['errors'] == 'RuntimeError: opencode crashed'
    assert full_system_row['average_score'] == '4.0'
    assert full_system_row['method_selection_average'] == '4.0'
    assert summary['per_risk_category'][0]['risk_category'] == 'crs-projection'  # type: ignore[index]

    per_run = summary['per_run'][0]
    per_variant = summary['per_variant'][0]
    per_variant_scenario = summary['per_variant_scenario'][0]
    assert 'dimension_scores' in per_run
    assert 'dimension_reasons' in per_run
    assert 'session_status' in per_run
    assert 'continuation_count' in per_run
    assert 'task_quality_passed' not in per_run
    assert 'professional_acceptability' not in per_run
    assert 'deterministic_pass_rate' not in per_variant
    assert 'judgeability_rate' not in per_variant
    assert 'traceability_rate' not in per_variant
    assert 'task_success_rate' not in per_variant
    assert {'variant_id', 'scenario_id', 'average_score'}.issubset(per_variant_scenario)


def test_aggregate_campaign_exports_rl_strategy_summary_and_cautious_packet(tmp_path: Path) -> None:
    campaign_root = tmp_path / 'campaign'
    _write_run(
        campaign_root,
        variant_id='full-system',
        scenario_id='P01',
        score=4,
        strategy_id='crs_first',
        reward=0.72,
        policy_checkpoint_id='checkpoint-0001',
        trl_run_id='trl-run-1',
        training_step=1,
    )
    _write_run(
        campaign_root,
        variant_id='full-system',
        scenario_id='R07',
        score=2,
        strategy_id='balanced',
        reward=-0.1,
        error_count=1,
        errors=('RuntimeError: smoke',),
    )

    summary = aggregate_campaign(campaign_root)
    export_root = campaign_root / EXPORT_DIRNAME
    rl_summary = json.loads((export_root / 'rl-strategy-summary.json').read_text(encoding='utf-8'))
    rl_packet = (export_root / 'rl-thesis-evidence.md').read_text(encoding='utf-8')

    assert summary['rl_strategy_experiment']['run_count'] == 2  # type: ignore[index]
    assert rl_summary['rewarded_run_count'] == 2
    assert {row['strategy_id'] for row in rl_summary['per_strategy']} == {'balanced', 'crs_first'}
    assert rl_summary['online_training']['episode_count'] == 1
    assert rl_summary['online_training']['checkpoint_ids'] == ['checkpoint-0001']
    assert rl_summary['failure_cases']
    assert 'does not claim end-to-end training' in rl_packet
    assert 'strategy-selection layer' in rl_packet
    assert 'Online TRL/RLOO rows' in rl_packet


def test_reward_record_uses_dimension_scores_and_penalties(tmp_path: Path) -> None:
    campaign_root = tmp_path / 'campaign'
    bundle = _write_run(
        campaign_root,
        variant_id='full-system',
        scenario_id='P01',
        score=5,
        strategy_id='crs_first',
        error_count=2,
        errors=('first', 'second'),
    )

    record = build_reward_record(bundle)

    assert record.strategy_id == 'crs_first'
    assert record.run_bundle_path == bundle
    assert record.scenario_fixture_hash == 'P01-fixture-hash'
    assert record.strategy_profile_hash == 'profile-hash'
    assert record.runtime_status['error_count'] == 2
    assert record.components['dimension.crs_and_units'] == 0.18
    assert record.components['penalty.errors'] == -0.1
    assert record.reward < 1.0


@pytest.mark.asyncio
async def test_geo_strategy_task_validates_actions_and_uses_reward_lookup(tmp_path: Path) -> None:
    campaign_root = tmp_path / 'campaign'
    bundle = _write_run(
        campaign_root,
        variant_id='full-system',
        scenario_id='P01',
        score=4,
        strategy_id='crs_first',
        reward=0.64,
    )
    reward_table_path = tmp_path / 'reward-table.json'
    table_payload = write_reward_table([bundle], reward_table_path)
    scenario = _scenario_stub()
    task = StrategyRolloutBridge(reward_table_path=reward_table_path, policy_run_id='policy-1')

    action = task.validate_action({'strategy_id': 'crs_first', 'rationale': 'CRS risk'})
    reward = await task.reward_for_action(scenario, action)  # type: ignore[arg-type]
    invalid = task.validate_action({'strategy_id': 'missing'})
    policy_stub_path = tmp_path / 'policy-stub.json'
    policy_stub = await write_policy_stub_evaluation(
        scenario_path=_repo_root()
        / 'app'
        / 'agent_assets'
        / 'benchmarks'
        / 'core'
        / 'p01-clear-local-kde.yaml',
        reward_table_path=reward_table_path,
        strategy_id='crs_first',
        output_path=policy_stub_path,
        policy_model_id='stub-policy-model',
        checkpoint_id='stub-checkpoint',
        scenario_selector='unit-smoke',
    )

    assert table_payload['records'][0]['run_bundle_path'] == str(bundle)  # type: ignore[index]
    assert table_payload['records'][0]['scenario_fixture_hash'] == 'P01-fixture-hash'  # type: ignore[index]
    assert table_payload['records'][0]['strategy_profile_hash'] == 'profile-hash'  # type: ignore[index]
    assert action.valid is True
    assert reward['reward_source'] == 'offline-lookup'
    assert reward['reward'] == 0.8
    assert invalid.valid is False
    assert invalid.selection is not None
    assert invalid.selection.action_valid is False
    assert policy_stub['policy_model_id'] == 'stub-policy-model'
    assert policy_stub['checkpoint_id'] == 'stub-checkpoint'
    assert policy_stub['scenario_selector'] == 'unit-smoke'
    assert policy_stub['reward_config']


@pytest.mark.asyncio
async def test_strategy_rollout_bridge_parses_trl_completion_and_rejects_unsafe_payload(tmp_path: Path) -> None:
    scenario = _scenario_stub()

    async def online_executor(_scenario: object, selection: object) -> dict[str, object]:
        return {
            'reward': 0.42,
            'reward_source': 'online-trl-training',
            'selection': selection.as_json(),  # type: ignore[attr-defined]
        }

    bridge = StrategyRolloutBridge(
        policy_run_id='policy-1',
        policy_checkpoint_id='checkpoint-0001',
        trl_run_id='trl-run-1',
        training_step=3,
        online_executor=online_executor,  # type: ignore[arg-type]
    )
    completion = json.dumps(
        {
            'name': SELECT_STRATEGY_TOOL_NAME,
            'arguments': {'strategy_id': 'crs_first', 'rationale': 'CRS risk'},
        }
    )

    reward = await bridge.reward_for_completion(scenario, completion, require_function_call=True)  # type: ignore[arg-type]
    unsafe = bridge.validate_completion(
        json.dumps(
            {
                'name': SELECT_STRATEGY_TOOL_NAME,
                'arguments': {'strategy_id': 'crs_first', 'extra': 'not allowed'},
            }
        ),
        require_function_call=True,
    )
    wrapped_direct_action = bridge.validate_completion(
        '<think>\nshort private scratchpad\n</think>\n'
        '{"strategy_id": "claim_conservative", "rationale": "Avoid overclaiming KDE significance."}\n'
        'ignored trailing text',
        require_function_call=False,
    )
    missing_call = bridge.validate_completion({'strategy_id': 'crs_first'}, require_function_call=True)

    assert reward['reward'] == 0.42
    assert reward['reward_source'] == 'online-trl-training'
    assert reward['action']['selection']['policy_checkpoint_id'] == 'checkpoint-0001'  # type: ignore[index]
    assert reward['action']['selection']['trl_run_id'] == 'trl-run-1'  # type: ignore[index]
    assert reward['action']['selection']['training_step'] == 3  # type: ignore[index]
    assert unsafe.valid is False
    assert unsafe.error == 'strategy action contains unsupported keys: extra'
    assert wrapped_direct_action.valid is True
    assert wrapped_direct_action.selection is not None
    assert wrapped_direct_action.selection.strategy_id == 'claim_conservative'
    assert missing_call.error == 'completion is missing select_geospatial_strategy function call'


def test_trl_reward_function_records_rollout_error_without_crashing(tmp_path: Path) -> None:
    scenario = _scenario_stub()
    attempt_count = 0

    async def failing_executor(_scenario: object, _selection: object) -> dict[str, object]:
        nonlocal attempt_count
        attempt_count += 1
        raise TimeoutError('session poll timed out')

    bridge = StrategyRolloutBridge(online_executor=failing_executor)  # type: ignore[arg-type]
    reward_func = TRLOnlineRewardFunction(
        bridge=bridge,
        scenarios=(scenario,),  # type: ignore[arg-type]
        require_function_call=False,
        max_reward_attempts=2,
        rollout_record_path=tmp_path / 'online-rollouts.jsonl',
    )

    rewards = reward_func(
        (json.dumps({'strategy_id': 'crs_first', 'rationale': 'CRS risk'}),),
        scenario_id=('P01',),
    )
    records = [
        json.loads(line)
        for line in (tmp_path / 'online-rollouts.jsonl').read_text(encoding='utf-8').splitlines()
    ]

    assert rewards == [0.0]
    assert attempt_count == 2
    assert reward_func.records[0]['reward']['reward_source'] == 'online-rollout-error'  # type: ignore[index]
    assert records[0]['reward']['attempt_count'] == 2
    assert records[0]['reward']['action']['valid'] is True


def test_resume_completion_offset_reads_trainer_state(tmp_path: Path) -> None:
    checkpoint = tmp_path / 'checkpoint-8'
    checkpoint.mkdir()
    _write_json(checkpoint / 'trainer_state.json', {'global_step': 8})

    assert _resume_completion_offset(checkpoint, group_completions_per_prompt=2) == 16


@pytest.mark.asyncio
async def test_mock_online_training_writes_trl_smoke_evidence(tmp_path: Path) -> None:
    manifest_path = tmp_path / 'online-rl.yaml'
    manifest_path.write_text(
        '\n'.join(
            [
                'id: unit-online-trl',
                f'benchmark_root: {_repo_root() / "app" / "agent_assets" / "benchmarks"}',
                f'campaign_path: {_repo_root() / "app" / "evaluation_assets" / "campaigns" / "thesis-balanced-v1.yaml"}',
                f'variant_root: {_repo_root() / "app" / "evaluation_assets" / "variants"}',
                'scenario_selector: thesis-core-real-v1',
                'strategy_set:',
                '  - balanced',
                '  - crs_first',
                'episode_cap: 2',
                'parallel_rollout_cap: 1',
                'wall_clock_budget_seconds: 120',
                'policy_model_id: Qwen/Qwen2.5-0.5B-Instruct',
                'checkpoint_root: checkpoints',
                f'output_root: {tmp_path / "online-runs"}',
                'downstream_model_provider: deepseek',
                'downstream_model: deepseek-v4-flash',
            ]
        )
        + '\n',
        encoding='utf-8',
    )

    manifest = load_online_rl_manifest(manifest_path)
    summary = await run_mock_online_training(manifest_path)
    run_root = Path(summary['run']['root'])  # type: ignore[index]
    rollouts = [
        json.loads(line)
        for line in Path(summary['run']['rollout_path']).read_text(encoding='utf-8').splitlines()  # type: ignore[index]
    ]

    assert manifest.algorithm == 'rloo'
    assert manifest.downstream_model == 'deepseek-v4-flash'
    assert summary['metrics']['episode_count'] == 2  # type: ignore[index]
    assert summary['metrics']['invalid_action_rate'] == 0.0  # type: ignore[index]
    assert len(rollouts) == 2
    assert (run_root / 'checkpoints' / 'checkpoint-0001' / 'adapter_config.json').exists()
    assert (run_root / 'mock-run-bundles').exists()
