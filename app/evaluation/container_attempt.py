from __future__ import annotations

from argparse import ArgumentParser, Namespace
import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import tempfile
from typing import Sequence

from app.evaluation.app_client import EvaluationAppClient
from app.evaluation.app_lifecycle import start_evaluation_app
from app.evaluation.benchmarks import (
    BenchmarkScenario,
    BenchmarkValidationError,
    default_benchmark_root,
    validate_benchmark_suite,
)
from app.evaluation.judge_rubrics import get_judge_rubric
from app.evaluation.llm_judge import GLMJudgeProvider, JudgeConfig, write_judge_score
from app.evaluation.manifests import (
    ScoringMode,
    VariantManifest,
    default_variant_root,
    load_variant_manifest,
)
from app.evaluation.run_bundles import (
    ARTIFACT_MANIFEST_FILENAME,
    ARTIFACTS_DIRNAME,
    RUN_MANIFEST_FILENAME,
    RUN_STATUS_FILENAME,
    capture_run_bundle,
    write_failed_run_bundle,
)
from app.evaluation.runner import (
    CampaignDirectories,
    VARIANT_RUNTIME_ASSETS_FILENAME,
    _write_json,
)
from app.evaluation.runtime_assets import prepare_variant_agent_assets
from app.evaluation.scenario_execution import (
    execute_scenario_attempt,
    prepare_scenario_data_attachments,
)
from app.evaluation.strategy_profiles import (
    StrategyProfile,
    StrategySelection,
    StrategySource,
    default_strategy_profile_root,
    load_selected_strategy_profiles,
)


DEFAULT_DATA_ROOT = Path('/data')
DEFAULT_RUN_BUNDLE_PATH = Path('/evaluation-run')
CONTAINER_APP_SUPPORT_DIR = '/opt/geo-agent/app-support'
CONTAINER_FAILURE_FILENAME = 'container-entrypoint-error.json'


@dataclass(frozen=True, slots=True)
class ContainerAttemptConfig:
    run_id: str
    variant_id: str
    scenario_id: str
    repeat_index: int
    attempt_number: int
    run_bundle_path: Path
    data_root: Path
    wall_clock_budget_seconds: float
    readiness_timeout_seconds: float
    scoring_mode: ScoringMode
    judge_model: str
    judge_temperature: float
    fairness_model: str
    strategy_id: str | None = None
    strategy_source: StrategySource | None = None
    strategy_profile_hash: str | None = None
    policy_run_id: str | None = None
    policy_checkpoint_id: str | None = None
    trl_run_id: str | None = None
    training_step: int | None = None
    strategy_action_rationale: str | None = None


def parse_args(argv: Sequence[str] | None = None) -> ContainerAttemptConfig:
    parser = ArgumentParser(description='Run one geospatial evaluation attempt inside a container.')
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--variant-id', required=True)
    parser.add_argument('--scenario-id', required=True)
    parser.add_argument('--repeat-index', type=int, required=True)
    parser.add_argument('--attempt-number', type=int, default=1)
    parser.add_argument('--run-bundle-path', type=Path, default=DEFAULT_RUN_BUNDLE_PATH)
    parser.add_argument('--data-root', type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument('--wall-clock-budget-seconds', type=float, default=0.0)
    parser.add_argument('--readiness-timeout-seconds', type=float, default=120.0)
    parser.add_argument(
        '--scoring-mode',
        choices=('none', 'llm-judge'),
        default='none',
    )
    parser.add_argument('--judge-model', default='glm-5.1')
    parser.add_argument('--judge-temperature', type=float, default=0.0)
    parser.add_argument('--fairness-model', default='inherit')
    parser.add_argument('--strategy-id', default=None)
    parser.add_argument(
        '--strategy-source',
        choices=('manual-baseline', 'offline-sweep', 'trained-policy', 'policy-stub'),
        default=None,
    )
    parser.add_argument('--strategy-profile-hash', default=None)
    parser.add_argument('--policy-run-id', default=None)
    parser.add_argument('--policy-checkpoint-id', default=None)
    parser.add_argument('--trl-run-id', default=None)
    parser.add_argument('--training-step', type=int, default=None)
    parser.add_argument('--strategy-action-rationale', default=None)
    args: Namespace = parser.parse_args(argv)
    if args.repeat_index <= 0:
        raise BenchmarkValidationError('repeat-index must be positive')
    if args.attempt_number <= 0:
        raise BenchmarkValidationError('attempt-number must be positive')
    if args.wall_clock_budget_seconds < 0:
        raise BenchmarkValidationError('wall-clock-budget-seconds must be non-negative')
    if args.readiness_timeout_seconds <= 0:
        raise BenchmarkValidationError('readiness-timeout-seconds must be positive')
    if bool(args.strategy_id) != bool(args.strategy_profile_hash):
        raise BenchmarkValidationError('strategy-id and strategy-profile-hash must be provided together')
    if args.strategy_source and not args.strategy_id:
        raise BenchmarkValidationError('strategy-source requires strategy-id')
    return ContainerAttemptConfig(
        run_id=str(args.run_id),
        variant_id=str(args.variant_id),
        scenario_id=str(args.scenario_id),
        repeat_index=int(args.repeat_index),
        attempt_number=int(args.attempt_number),
        run_bundle_path=args.run_bundle_path,
        data_root=args.data_root,
        wall_clock_budget_seconds=float(args.wall_clock_budget_seconds),
        readiness_timeout_seconds=float(args.readiness_timeout_seconds),
        scoring_mode=args.scoring_mode,
        judge_model=str(args.judge_model),
        judge_temperature=float(args.judge_temperature),
        fairness_model=str(args.fairness_model),
        strategy_id=str(args.strategy_id) if args.strategy_id else None,
        strategy_source=args.strategy_source,
        strategy_profile_hash=str(args.strategy_profile_hash) if args.strategy_profile_hash else None,
        policy_run_id=str(args.policy_run_id) if args.policy_run_id else None,
        policy_checkpoint_id=str(args.policy_checkpoint_id) if args.policy_checkpoint_id else None,
        trl_run_id=str(args.trl_run_id) if args.trl_run_id else None,
        training_step=int(args.training_step) if args.training_step is not None else None,
        strategy_action_rationale=str(args.strategy_action_rationale) if args.strategy_action_rationale else None,
    )


async def execute_container_attempt(config: ContainerAttemptConfig) -> None:
    scenario: BenchmarkScenario = _load_scenario(config.scenario_id)
    variant: VariantManifest = load_variant_manifest(default_variant_root() / f'{config.variant_id}.yaml')
    get_judge_rubric(scenario.judge_rubric)
    run_bundle_path: Path = config.run_bundle_path.resolve()
    run_bundle_path.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix='geo-agent-container-attempt-') as temp_dir:
        temp_root = Path(temp_dir)
        runtime_assets_root: Path = temp_root / 'runtime-assets'
        strategy_profile: StrategyProfile | None = _container_strategy_profile(config)
        prepared_assets = prepare_variant_agent_assets(variant, runtime_assets_root, strategy_profile=strategy_profile)
        _write_json(run_bundle_path / VARIANT_RUNTIME_ASSETS_FILENAME, prepared_assets.manifest)

        directories = CampaignDirectories(
            root=temp_root / 'app-state',
            manifests=temp_root / 'manifests',
            runs=temp_root / 'runs',
            logs=run_bundle_path / 'logs',
            app_support=temp_root / 'app-support',
            workspace=run_bundle_path / 'workspace',
            runtime_config=temp_root / 'runtime-config',
            runtime_assets=runtime_assets_root,
        )
        directories.workspace.mkdir(parents=True, exist_ok=True)
        handle = await start_evaluation_app(
            directories,
            readiness_timeout_seconds=config.readiness_timeout_seconds,
            require_geospatial_environment=True,
            extra_env=_variant_runtime_env(config, variant, prepared_assets.agent_asset_root),
        )
        try:
            client = EvaluationAppClient(handle.base_url)
            result = await execute_scenario_attempt(
                client,
                scenario,
                data_attachments=container_scenario_data_attachments(
                    scenario,
                    data_root=config.data_root,
                    run_bundle_path=run_bundle_path,
                ),
                wall_clock_budget_seconds=_container_attempt_budget(config, variant),
            )
            await capture_run_bundle(
                client,
                result,
                scenario,
                run_bundle_path,
                run_id=config.run_id,
                variant=variant,
                strategy=_config_strategy_selection(config),
                log_paths=(handle.stdout_log_path, handle.stderr_log_path, handle.lifecycle_log_path),
            )
        finally:
            await handle.shutdown()

    await _write_attempt_scores(config, scenario, run_bundle_path)


def container_scenario_data_attachments(
    scenario: BenchmarkScenario,
    *,
    data_root: Path,
    run_bundle_path: Path,
) -> list[dict[str, object]]:
    if scenario.dataset_pack_mode == 'synthetic':
        return prepare_scenario_data_attachments(scenario, run_bundle_path / 'dataset-pack')
    dataset_root: Path = _container_repo_file_dataset_root(scenario, data_root)
    return [
        {
            'id': f'scenario-{scenario.id.lower()}-dataset-root',
            'path': str(dataset_root.resolve()),
            'enabled': True,
            'label': f'{scenario.id} dataset root',
        }
    ]


def write_container_failure(config: ContainerAttemptConfig, exc: BaseException) -> None:
    run_bundle_path: Path = config.run_bundle_path.resolve()
    run_bundle_path.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        'schema': 'geo-agent.evaluation.container-entrypoint-error.v1',
        'run_id': config.run_id,
        'variant_id': config.variant_id,
        'scenario_id': config.scenario_id,
        'error_type': type(exc).__name__,
        'error': str(exc),
        'failed_at': datetime.now(UTC).isoformat(),
    }
    _write_json(run_bundle_path / CONTAINER_FAILURE_FILENAME, payload)

    if (run_bundle_path / RUN_MANIFEST_FILENAME).exists() or (run_bundle_path / RUN_STATUS_FILENAME).exists():
        return

    try:
        scenario = _load_scenario(config.scenario_id)
    except Exception:
        _write_minimal_container_failure_bundle(config, exc)
        return
    try:
        variant: VariantManifest | None = load_variant_manifest(default_variant_root() / f'{config.variant_id}.yaml')
    except Exception:
        variant = None
    write_failed_run_bundle(
        run_bundle_path,
        run_id=config.run_id,
        session_id=f'container-failed-{config.run_id}',
        scenario=scenario,
        variant=variant,
        terminal_reason='container_entrypoint_failed',
        errors=[f'{type(exc).__name__}: {exc}'],
        strategy=_config_strategy_selection(config),
    )


def _write_minimal_container_failure_bundle(config: ContainerAttemptConfig, exc: BaseException) -> None:
    run_bundle_path: Path = config.run_bundle_path.resolve()
    session_id = f'container-failed-{config.run_id}'
    created_at = datetime.now(UTC).isoformat()
    error = f'{type(exc).__name__}: {exc}'
    _write_json(
        run_bundle_path / RUN_STATUS_FILENAME,
        {
            'schema': 'geo-agent.evaluation.run-status.v1',
            'session_id': session_id,
            'session_status': 'failed',
            'terminal_reason': 'container_entrypoint_failed',
            'timed_out': False,
            'started_at': created_at,
            'finished_at': created_at,
            'duration_seconds': 0.0,
            'continuation_count': 0,
            'clarification_answer_count': 0,
            'clarification_question_ids': [],
            'error_count': 1,
            'errors': [error],
        },
    )
    _write_json(
        run_bundle_path / ARTIFACT_MANIFEST_FILENAME,
        {
            'schema': 'geo-agent.evaluation.artifact-capture.v1',
            'session_id': session_id,
            'artifact_count': 0,
            'items': [],
        },
    )
    _write_json(
        run_bundle_path / RUN_MANIFEST_FILENAME,
        {
            'schema': 'geo-agent.evaluation.run-bundle.v1',
            'run_id': config.run_id,
            'session_id': session_id,
            'scenario': {'id': config.scenario_id},
            'variant': {'id': config.variant_id},
            'strategy': _config_strategy_selection(config).as_json() if _config_strategy_selection(config) else None,
            'status': {
                'session_status': 'failed',
                'terminal_reason': 'container_entrypoint_failed',
                'timed_out': False,
            },
            'trace_capture': None,
            'runtime_trace': {'status': 'unavailable'},
            'logs': [],
            'files': {
                'run_status': RUN_STATUS_FILENAME,
                'artifact_manifest': ARTIFACT_MANIFEST_FILENAME,
                'artifact_root': ARTIFACTS_DIRNAME,
            },
            'error_count': 1,
            'errors': [error],
        },
    )


def _load_scenario(scenario_id: str) -> BenchmarkScenario:
    scenarios = validate_benchmark_suite(default_benchmark_root())
    for scenario in scenarios:
        if scenario.id == scenario_id:
            return scenario
    raise BenchmarkValidationError(f'Unknown benchmark scenario id: {scenario_id}')


def _container_repo_file_dataset_root(scenario: BenchmarkScenario, data_root: Path) -> Path:
    configured = Path(scenario.dataset_root)
    if configured.is_absolute():
        return configured
    if configured.parts and configured.parts[0] == 'data':
        return data_root / Path(*configured.parts[1:])
    return data_root / configured


def _container_attempt_budget(config: ContainerAttemptConfig, variant: VariantManifest) -> float:
    if variant.runtime_wall_clock_budget_seconds > 0:
        return float(variant.runtime_wall_clock_budget_seconds)
    return config.wall_clock_budget_seconds


def _variant_runtime_env(
    config: ContainerAttemptConfig,
    variant: VariantManifest,
    agent_asset_root: Path,
) -> dict[str, str]:
    env: dict[str, str] = {
        'GEO_AGENT_AGENT_ASSET_ROOT': str(agent_asset_root),
        'GEO_AGENT_APP_SUPPORT_DIR': CONTAINER_APP_SUPPORT_DIR,
        'GEO_AGENT_STATE_DIR': '/tmp/geo-agent-eval/state',
        'GEO_AGENT_DATABASE_PATH': '/tmp/geo-agent-eval/metadata.db',
        'GEO_AGENT_RUNTIME_CONFIG_ROOT': '/tmp/geo-agent-eval/runtime-config',
        'GEO_AGENT_OPENCODE_BINARY': 'opencode',
    }
    model: str = variant.model if variant.model != 'inherit' else config.fairness_model
    if model != 'inherit':
        env['GEO_AGENT_GLM_MODEL'] = model
    return env


def _container_strategy_profile(config: ContainerAttemptConfig) -> StrategyProfile | None:
    if config.strategy_id is None:
        return None
    profiles: tuple[StrategyProfile, ...] = load_selected_strategy_profiles(
        (config.strategy_id,),
        root=default_strategy_profile_root(),
    )
    profile = profiles[0]
    if config.strategy_profile_hash is not None and profile.profile_hash != config.strategy_profile_hash:
        raise BenchmarkValidationError(
            f'Strategy profile hash mismatch for {config.strategy_id}: '
            f'{profile.profile_hash} != {config.strategy_profile_hash}'
        )
    return profile


def _config_strategy_selection(config: ContainerAttemptConfig) -> StrategySelection | None:
    if config.strategy_id is None or config.strategy_profile_hash is None:
        return None
    return StrategySelection(
        strategy_id=config.strategy_id,
        source=config.strategy_source or 'offline-sweep',
        profile_hash=config.strategy_profile_hash,
        policy_run_id=config.policy_run_id,
        policy_checkpoint_id=config.policy_checkpoint_id,
        trl_run_id=config.trl_run_id,
        training_step=config.training_step,
        action_valid=True,
        action_rationale=config.strategy_action_rationale,
    )


async def _write_attempt_scores(
    config: ContainerAttemptConfig,
    scenario: BenchmarkScenario,
    run_bundle_path: Path,
) -> None:
    if config.scoring_mode == 'llm-judge':
        await write_judge_score(
            scenario,
            run_bundle_path,
            GLMJudgeProvider(),
            JudgeConfig(model=config.judge_model, temperature=config.judge_temperature),
        )


async def _main_async(argv: Sequence[str] | None) -> int:
    config = parse_args(argv)
    try:
        await execute_container_attempt(config)
    except BaseException as exc:
        write_container_failure(config, exc)
        return 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(_main_async(argv))


if __name__ == '__main__':
    raise SystemExit(main())
