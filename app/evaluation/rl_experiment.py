from __future__ import annotations

from argparse import ArgumentParser
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Sequence

from app.evaluation.benchmarks import load_benchmark_scenario
from app.evaluation.rl_online import (
    DEFAULT_ONLINE_RL_MANIFEST,
    run_frozen_policy_online_evaluation,
    run_mock_online_training,
    run_trl_online_training,
    write_frozen_policy_smoke_evaluation,
)
from app.evaluation.rl_rewards import REWARD_TABLE_FILENAME, RewardConfig, write_reward_record, write_reward_table
from app.evaluation.rl_task import StrategyRolloutBridge
from app.evaluation.run_bundles import RUN_MANIFEST_FILENAME


POLICY_STUB_SCHEMA = 'geo-agent.evaluation.rl-policy-stub.v1'


def write_campaign_reward_table(
    campaign_root: Path,
    *,
    output_path: Path | None = None,
    reward_source: str = 'offline-sweep',
) -> dict[str, object]:
    run_bundle_paths: list[Path] = sorted(path.parent for path in (campaign_root / 'runs').glob('**/' + RUN_MANIFEST_FILENAME))
    for run_bundle_path in run_bundle_paths:
        write_reward_record(run_bundle_path, config=RewardConfig(), reward_source=reward_source)
    resolved_output_path: Path = output_path or campaign_root / 'exports' / REWARD_TABLE_FILENAME
    return write_reward_table(run_bundle_paths, resolved_output_path, config=RewardConfig(), reward_source=reward_source)


async def write_policy_stub_evaluation(
    *,
    scenario_path: Path,
    reward_table_path: Path,
    strategy_id: str,
    output_path: Path,
    policy_run_id: str = 'policy-stub',
    policy_model_id: str = 'policy-stub',
    checkpoint_id: str = 'policy-stub',
    scenario_selector: str = 'manual-scenario',
) -> dict[str, object]:
    scenario = load_benchmark_scenario(scenario_path)
    bridge = StrategyRolloutBridge(
        reward_table_path=reward_table_path,
        policy_run_id=policy_run_id,
        policy_checkpoint_id=checkpoint_id,
        strategy_source='policy-stub',
    )
    action = bridge.validate_action({'strategy_id': strategy_id, 'rationale': 'Minimal frozen-policy smoke evaluation.'})
    reward = await bridge.reward_for_action(scenario, action)
    payload: dict[str, object] = {
        'schema': POLICY_STUB_SCHEMA,
        'created_at': datetime.now(UTC).isoformat(),
        'policy_run_id': policy_run_id,
        'policy_model_id': policy_model_id,
        'checkpoint_id': checkpoint_id,
        'scenario_selector': scenario_selector,
        'scenario_id': scenario.id,
        'strategy_id': strategy_id,
        'reward_config': _reward_table_config(reward_table_path),
        'run_metadata': {
            'scenario_path': str(scenario_path),
            'reward_table_path': str(reward_table_path),
            'output_path': str(output_path),
        },
        'action': action.as_json(),
        'reward': reward,
        'evidence_boundary': (
            'This is a minimal policy-stub smoke artifact for the strategy-controller harness, not a trained model result.'
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = ArgumentParser(description='Run RL strategy-controller experiment utilities.')
    subparsers = parser.add_subparsers(dest='command', required=True)

    reward_parser = subparsers.add_parser('write-reward-table')
    reward_parser.add_argument('campaign_root', type=Path)
    reward_parser.add_argument('--output', type=Path, default=None)
    reward_parser.add_argument('--reward-source', default='offline-sweep')

    stub_parser = subparsers.add_parser('policy-stub')
    stub_parser.add_argument('scenario_path', type=Path)
    stub_parser.add_argument('reward_table_path', type=Path)
    stub_parser.add_argument('strategy_id')
    stub_parser.add_argument('--output', type=Path, required=True)
    stub_parser.add_argument('--policy-run-id', default='policy-stub')
    stub_parser.add_argument('--policy-model-id', default='policy-stub')
    stub_parser.add_argument('--checkpoint-id', default='policy-stub')
    stub_parser.add_argument('--scenario-selector', default='manual-scenario')
    online_smoke_parser = subparsers.add_parser('online-smoke')
    online_smoke_parser.add_argument('manifest', type=Path, nargs='?', default=DEFAULT_ONLINE_RL_MANIFEST)
    online_smoke_parser.add_argument('--output-root', type=Path, default=None)
    online_train_parser = subparsers.add_parser('train-online')
    online_train_parser.add_argument('manifest', type=Path, nargs='?', default=DEFAULT_ONLINE_RL_MANIFEST)
    online_train_parser.add_argument('--app-command', action='append', default=None)
    online_train_parser.add_argument('--output-root', type=Path, default=None)
    online_train_parser.add_argument('--resume-from-checkpoint', type=Path, default=None)
    online_train_parser.add_argument(
        '--execution-backend',
        choices=('local-process', 'docker-per-attempt'),
        default='local-process',
    )
    frozen_parser = subparsers.add_parser('frozen-policy-plan')
    frozen_parser.add_argument('manifest', type=Path, nargs='?', default=DEFAULT_ONLINE_RL_MANIFEST)
    frozen_parser.add_argument('--checkpoint-id', required=True)
    frozen_parser.add_argument('--strategy-id', required=True)
    frozen_parser.add_argument('--output', type=Path, required=True)
    frozen_eval_parser = subparsers.add_parser('frozen-policy-eval')
    frozen_eval_parser.add_argument('manifest', type=Path, nargs='?', default=DEFAULT_ONLINE_RL_MANIFEST)
    frozen_eval_parser.add_argument('--checkpoint-id', required=True)
    frozen_eval_parser.add_argument('--strategy-id', required=True)
    frozen_eval_parser.add_argument('--output-root', type=Path, default=None)
    frozen_eval_parser.add_argument('--live', action='store_true')
    frozen_eval_parser.add_argument('--app-command', action='append', default=None)
    frozen_eval_parser.add_argument(
        '--execution-backend',
        choices=('local-process', 'docker-per-attempt'),
        default='local-process',
    )
    args = parser.parse_args(argv)

    if args.command == 'write-reward-table':
        payload = write_campaign_reward_table(
            args.campaign_root,
            output_path=args.output,
            reward_source=args.reward_source,
        )
    elif args.command == 'policy-stub':
        import asyncio

        payload = asyncio.run(
            write_policy_stub_evaluation(
                scenario_path=args.scenario_path,
                reward_table_path=args.reward_table_path,
                strategy_id=args.strategy_id,
                output_path=args.output,
                policy_run_id=args.policy_run_id,
                policy_model_id=args.policy_model_id,
                checkpoint_id=args.checkpoint_id,
                scenario_selector=args.scenario_selector,
            )
        )
    elif args.command == 'online-smoke':
        import asyncio

        payload = asyncio.run(run_mock_online_training(args.manifest, output_root=args.output_root))
    elif args.command == 'train-online':
        payload = run_trl_online_training(
            args.manifest,
            app_command=args.app_command,
            execution_backend=args.execution_backend,
            output_root=args.output_root,
            resume_from_checkpoint=args.resume_from_checkpoint,
        )
    elif args.command == 'frozen-policy-plan':
        payload = write_frozen_policy_smoke_evaluation(
            args.manifest,
            checkpoint_id=args.checkpoint_id,
            strategy_id=args.strategy_id,
            output_path=args.output,
        )
    else:
        import asyncio

        payload = asyncio.run(
            run_frozen_policy_online_evaluation(
                args.manifest,
                checkpoint_id=args.checkpoint_id,
                strategy_id=args.strategy_id,
                output_root=args.output_root,
                smoke=not args.live,
                app_command=args.app_command,
                execution_backend=args.execution_backend,
            )
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _reward_table_config(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {}
    if not isinstance(payload, dict):
        return {}
    config = payload.get('reward_config')
    return config if isinstance(config, dict) else {}


if __name__ == '__main__':
    raise SystemExit(main())
