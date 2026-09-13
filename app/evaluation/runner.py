from __future__ import annotations

from argparse import ArgumentParser
import asyncio
from dataclasses import dataclass, replace
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import shutil
from typing import TYPE_CHECKING, Any, Literal, Sequence

from app.evaluation.benchmarks import (
    BenchmarkScenario,
    BenchmarkValidationError,
    repo_root,
    validate_benchmark_suite,
)
from app.evaluation.manifests import (
    CampaignManifest,
    RunnerResumePolicy,
    VariantManifest,
    default_variant_root,
    load_variant_manifest,
    validate_campaign_manifest,
)
from app.evaluation.runtime_assets import prepare_variant_agent_assets
from app.evaluation.strategy_profiles import (
    StrategyProfile,
    StrategySelection,
    StrategySource,
    default_strategy_profile_root,
    load_selected_strategy_profiles,
    strategy_selection_from_profile,
)


if TYPE_CHECKING:
    from app.evaluation.run_bundles import RunBundleCapture


CAMPAIGN_PLAN_FILENAME = 'campaign-plan.json'
CAMPAIGN_INIT_SCHEMA = 'geo-agent.evaluation.campaign-init.v1'
CAMPAIGN_EXECUTION_FILENAME = 'campaign-execution.json'
CAMPAIGN_EXECUTION_SCHEMA = 'geo-agent.evaluation.campaign-execution.v1'
VARIANT_RUNTIME_ASSETS_FILENAME = 'variant-runtime-assets.json'
DEFAULT_EVALUATION_DOCKER_IMAGE = 'geo-agent-eval:latest'
DEFAULT_AGENT_CONCURRENCY = 2
DEFAULT_JUDGE_CONCURRENCY = 1
DEFAULT_INFRASTRUCTURE_MAX_RETRIES = 0
INFRASTRUCTURE_RETRY_TERMINAL_REASONS: set[str] = {
    'container_cancelled',
    'container_start_failed',
    'container_entrypoint_failed',
}
INFRASTRUCTURE_RETRY_TEXT_MARKERS: tuple[str, ...] = (
    '429',
    'rate limit',
    'ratelimit',
    'too many requests',
    'connection reset',
    'connection aborted',
    'temporary failure',
    'network is unreachable',
)
ExecutionBackend = Literal['local-process', 'docker-per-attempt']


@dataclass(frozen=True, slots=True)
class CampaignDirectories:
    root: Path
    manifests: Path
    runs: Path
    logs: Path
    app_support: Path | None
    workspace: Path
    runtime_config: Path | None
    runtime_assets: Path


@dataclass(frozen=True, slots=True)
class PlannedAttempt:
    id: str
    variant_id: str
    scenario_id: str
    repeat_index: int
    run_bundle_path: Path
    strategy: StrategySelection | None = None

    def as_json(self, campaign_root: Path) -> dict[str, object]:
        return {
            'id': self.id,
            'variant_id': self.variant_id,
            'scenario_id': self.scenario_id,
            'repeat_index': self.repeat_index,
            'run_bundle_path': _relative_or_absolute(self.run_bundle_path, campaign_root),
            'strategy': self.strategy.as_json() if self.strategy is not None else None,
        }


@dataclass(frozen=True, slots=True)
class RunBundleAllocation:
    id: str
    path: Path
    planned_attempt: PlannedAttempt
    attempt_number: int

    def as_json(self, campaign_root: Path) -> dict[str, object]:
        return {
            'id': self.id,
            'path': _relative_or_absolute(self.path, campaign_root),
            'planned_attempt_id': self.planned_attempt.id,
            'attempt_number': self.attempt_number,
        }


@dataclass(frozen=True, slots=True)
class CampaignInitialization:
    campaign: CampaignManifest
    directories: CampaignDirectories
    scenarios: tuple[BenchmarkScenario, ...]
    variants: tuple[VariantManifest, ...]
    strategy_profiles: tuple[StrategyProfile, ...]
    planned_attempts: tuple[PlannedAttempt, ...]
    campaign_snapshot_path: Path
    plan_path: Path

    def summary(self) -> dict[str, object]:
        return {
            'campaign_id': self.campaign.id,
            'campaign_root': str(self.directories.root),
            'campaign_snapshot_path': str(self.campaign_snapshot_path),
            'plan_path': str(self.plan_path),
            'planned_attempt_count': len(self.planned_attempts),
        }


def initialize_campaign_run(
    campaign_path: Path,
    *,
    variant_root: Path | None = None,
    output_root: Path | None = None,
    timestamp: datetime | None = None,
    strategy_profile_ids: Sequence[str] | None = None,
    strategy_profile_root: Path | None = None,
    strategy_source: StrategySource = 'offline-sweep',
    strategy_policy_run_id: str | None = None,
    strategy_policy_checkpoint_id: str | None = None,
    strategy_trl_run_id: str | None = None,
    strategy_training_step: int | None = None,
    strategy_action_rationale: str | None = None,
) -> CampaignInitialization:
    resolved_variant_root: Path = variant_root or default_variant_root()
    campaign: CampaignManifest = validate_campaign_manifest(campaign_path, resolved_variant_root)
    scenarios: list[BenchmarkScenario] = validate_benchmark_suite(_resolve_repo_path(campaign.benchmark_root))
    variants: list[VariantManifest] = [
        load_variant_manifest(resolved_variant_root / f'{variant_id}.yaml')
        for variant_id in campaign.variants
    ]
    strategy_profiles: tuple[StrategyProfile, ...] = load_selected_strategy_profiles(
        tuple(strategy_profile_ids or ()),
        root=strategy_profile_root or default_strategy_profile_root(),
    )
    created_at: datetime = timestamp or datetime.now(UTC)
    directories: CampaignDirectories = _create_campaign_directories(
        campaign=campaign,
        output_root=output_root,
        timestamp=created_at,
    )
    campaign_snapshot_path: Path = _write_snapshots(
        directories=directories,
        campaign=campaign,
        variants=variants,
        scenarios=scenarios,
    )
    planned_attempts: tuple[PlannedAttempt, ...] = tuple(
        _planned_attempts(
            campaign=campaign,
            variants=variants,
            scenarios=scenarios,
            directories=directories,
            strategy_profiles=strategy_profiles,
            strategy_source=strategy_source,
            strategy_policy_run_id=strategy_policy_run_id,
            strategy_policy_checkpoint_id=strategy_policy_checkpoint_id,
            strategy_trl_run_id=strategy_trl_run_id,
            strategy_training_step=strategy_training_step,
            strategy_action_rationale=strategy_action_rationale,
        )
    )
    plan_path: Path = directories.root / CAMPAIGN_PLAN_FILENAME
    _write_json(
        plan_path,
        _campaign_plan(
            campaign=campaign,
            directories=directories,
            variants=variants,
            strategy_profiles=list(strategy_profiles),
            scenarios=scenarios,
            attempts=planned_attempts,
            created_at=created_at,
        ),
    )
    return CampaignInitialization(
        campaign=campaign,
        directories=directories,
        scenarios=tuple(scenarios),
        variants=tuple(variants),
        strategy_profiles=strategy_profiles,
        planned_attempts=planned_attempts,
        campaign_snapshot_path=campaign_snapshot_path,
        plan_path=plan_path,
    )


@dataclass(frozen=True, slots=True)
class CampaignExecution:
    initialization: CampaignInitialization
    run_captures: tuple['RunBundleCapture', ...]
    summary_path: Path


def allocate_run_bundle(
    planned_attempt: PlannedAttempt,
    *,
    resume_policy: RunnerResumePolicy = 'append-attempts',
) -> RunBundleAllocation:
    if resume_policy not in {'append-attempts', 'fail-if-existing'}:
        raise BenchmarkValidationError(f'Unsupported runner resume policy: {resume_policy}')
    if resume_policy == 'fail-if-existing' and planned_attempt.run_bundle_path.exists():
        raise BenchmarkValidationError(f'Run bundle already exists: {planned_attempt.run_bundle_path}')

    for attempt_number in range(1, 1000):
        path: Path = _run_bundle_candidate(planned_attempt.run_bundle_path, attempt_number)
        if path.exists():
            continue
        path.mkdir(parents=True, exist_ok=False)
        return RunBundleAllocation(
            id=_run_bundle_attempt_id(planned_attempt.id, attempt_number),
            path=path,
            planned_attempt=planned_attempt,
            attempt_number=attempt_number,
        )
    raise BenchmarkValidationError(f'Could not allocate a unique run bundle for: {planned_attempt.id}')


async def execute_campaign_run(
    campaign_path: Path,
    *,
    variant_root: Path | None = None,
    output_root: Path | None = None,
    timestamp: datetime | None = None,
    app_command: Sequence[str] | None = None,
    max_attempts: int | None = None,
    attempt_ids: Sequence[str] | None = None,
    execution_backend: ExecutionBackend = 'local-process',
    docker_image: str = DEFAULT_EVALUATION_DOCKER_IMAGE,
    docker_data_dir: Path | None = None,
    docker_container_data_path: str = '/data',
    docker_container_run_bundle_path: str = '/evaluation-run',
    docker_client: Any | None = None,
    agent_concurrency: int = DEFAULT_AGENT_CONCURRENCY,
    judge_concurrency: int = DEFAULT_JUDGE_CONCURRENCY,
    infrastructure_max_retries: int = DEFAULT_INFRASTRUCTURE_MAX_RETRIES,
    score_after_execution: bool = False,
    attempt_wall_clock_budget_seconds: float | None = None,
    strategy_profile_ids: Sequence[str] | None = None,
    strategy_profile_root: Path | None = None,
    strategy_source: StrategySource = 'offline-sweep',
    strategy_policy_run_id: str | None = None,
    strategy_policy_checkpoint_id: str | None = None,
    strategy_trl_run_id: str | None = None,
    strategy_training_step: int | None = None,
    strategy_action_rationale: str | None = None,
    runtime_env_overrides: dict[str, str] | None = None,
) -> CampaignExecution:
    from app.evaluation.app_client import EvaluationAppClient
    from app.evaluation.app_lifecycle import start_evaluation_app
    from app.evaluation.run_bundles import capture_run_bundle
    from app.evaluation.scenario_execution import (
        execute_scenario_attempt,
        prepare_scenario_data_attachments,
    )

    initialized: CampaignInitialization = initialize_campaign_run(
        campaign_path,
        variant_root=variant_root,
        output_root=output_root,
        timestamp=timestamp,
        strategy_profile_ids=strategy_profile_ids,
        strategy_profile_root=strategy_profile_root,
        strategy_source=strategy_source,
        strategy_policy_run_id=strategy_policy_run_id,
        strategy_policy_checkpoint_id=strategy_policy_checkpoint_id,
        strategy_trl_run_id=strategy_trl_run_id,
        strategy_training_step=strategy_training_step,
        strategy_action_rationale=strategy_action_rationale,
    )
    scenario_by_id: dict[str, BenchmarkScenario] = {
        scenario.id: scenario
        for scenario in initialized.scenarios
    }
    variant_by_id: dict[str, VariantManifest] = {
        variant.id: variant
        for variant in initialized.variants
    }
    strategy_profile_by_id: dict[str, StrategyProfile] = {
        profile.id: profile
        for profile in initialized.strategy_profiles
    }
    selected_attempts: tuple[PlannedAttempt, ...] = _select_planned_attempts(
        initialized.planned_attempts,
        attempt_ids=attempt_ids,
    )
    if max_attempts is not None:
        if max_attempts <= 0:
            raise BenchmarkValidationError('max_attempts must be positive when provided')
        selected_attempts = selected_attempts[:max_attempts]
    if execution_backend not in {'local-process', 'docker-per-attempt'}:
        raise BenchmarkValidationError(f'Unsupported execution backend: {execution_backend}')
    if execution_backend == 'docker-per-attempt' and app_command is not None:
        raise BenchmarkValidationError('app_command is only supported by the local-process execution backend')
    if agent_concurrency <= 0:
        raise BenchmarkValidationError('agent_concurrency must be positive')
    if judge_concurrency <= 0:
        raise BenchmarkValidationError('judge_concurrency must be positive')
    if infrastructure_max_retries < 0:
        raise BenchmarkValidationError('infrastructure_max_retries must be non-negative')
    if attempt_wall_clock_budget_seconds is not None and attempt_wall_clock_budget_seconds <= 0:
        raise BenchmarkValidationError('attempt_wall_clock_budget_seconds must be positive when provided')

    run_captures: list[RunBundleCapture] = []
    if execution_backend == 'docker-per-attempt':
        docker_campaign: CampaignManifest = (
            replace(initialized.campaign, scoring_mode='none')
            if score_after_execution and initialized.campaign.scoring_mode == 'llm-judge'
            else initialized.campaign
        )
        run_captures.extend(
            await _execute_docker_campaign_attempts(
                campaign=docker_campaign,
                planned_attempts=selected_attempts,
                scenario_by_id=scenario_by_id,
                variant_by_id=variant_by_id,
                resume_policy=initialized.campaign.runner_resume_policy,
                docker_image=docker_image,
                docker_data_dir=docker_data_dir,
                docker_container_data_path=docker_container_data_path,
                docker_container_run_bundle_path=docker_container_run_bundle_path,
                docker_client=docker_client,
                agent_concurrency=agent_concurrency,
                infrastructure_max_retries=infrastructure_max_retries,
            )
        )
    else:
        for planned_attempt in selected_attempts:
            allocation: RunBundleAllocation = allocate_run_bundle(
                planned_attempt,
                resume_policy=initialized.campaign.runner_resume_policy,
            )
            scenario: BenchmarkScenario = scenario_by_id[planned_attempt.scenario_id]
            variant: VariantManifest = variant_by_id[planned_attempt.variant_id]
            strategy_profile: StrategyProfile | None = _attempt_strategy_profile(planned_attempt, strategy_profile_by_id)
            prepared_assets = prepare_variant_agent_assets(
                variant,
                initialized.directories.runtime_assets,
                strategy_profile=strategy_profile,
            )
            _write_json(
                allocation.path / VARIANT_RUNTIME_ASSETS_FILENAME,
                prepared_assets.manifest,
            )
            attempt_directories: CampaignDirectories = _attempt_app_directories(initialized.directories, allocation.path)
            handle = await start_evaluation_app(
                attempt_directories,
                readiness_timeout_seconds=initialized.campaign.runner_readiness_timeout_seconds,
                require_geospatial_environment=True,
                command=app_command,
                extra_env=_variant_runtime_env(
                    initialized.campaign,
                    variant,
                    prepared_assets.agent_asset_root,
                    overrides=runtime_env_overrides,
                ),
            )
            try:
                client = EvaluationAppClient(handle.base_url)
                result = await execute_scenario_attempt(
                    client,
                    scenario,
                    data_attachments=prepare_scenario_data_attachments(
                        scenario,
                        allocation.path / 'dataset-pack',
                    ),
                    wall_clock_budget_seconds=(
                        attempt_wall_clock_budget_seconds
                        if attempt_wall_clock_budget_seconds is not None
                        else _attempt_budget_seconds(initialized.campaign, variant)
                    ),
                )
                run_captures.append(
                    await capture_run_bundle(
                        client,
                        result,
                        scenario,
                        allocation.path,
                        run_id=allocation.id,
                        variant=variant,
                        strategy=planned_attempt.strategy,
                        log_paths=(handle.stdout_log_path, handle.stderr_log_path, handle.lifecycle_log_path),
                    )
                )
            finally:
                await handle.shutdown()

    if score_after_execution and initialized.campaign.scoring_mode == 'llm-judge':
        await _score_campaign_run_after_execution(initialized, judge_concurrency=judge_concurrency)

    summary_path: Path = initialized.directories.root / CAMPAIGN_EXECUTION_FILENAME
    _write_json(
        summary_path,
        _campaign_execution_summary(
            initialized=initialized,
            run_captures=tuple(run_captures),
            selected_attempt_count=len(selected_attempts),
        ),
    )
    return CampaignExecution(
        initialization=initialized,
        run_captures=tuple(run_captures),
        summary_path=summary_path,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = ArgumentParser(description='Initialize a headless geospatial evaluation campaign run.')
    parser.add_argument('campaign', type=Path, help='Path to the campaign manifest YAML file.')
    parser.add_argument('--variant-root', type=Path, default=None, help='Directory containing variant manifests.')
    parser.add_argument('--output-root', type=Path, default=None, help='Override the campaign output root.')
    parser.add_argument('--execute', action='store_true', help='Run the campaign through the app API after initialization.')
    parser.add_argument('--max-attempts', type=int, default=None, help='Limit execution to the first N planned attempts.')
    parser.add_argument('--attempt-id', action='append', default=None, help='Execute only this planned attempt id. May be repeated.')
    parser.add_argument(
        '--execution-backend',
        choices=('local-process', 'docker-per-attempt'),
        default='local-process',
        help='Execution backend for non-deterministic attempts.',
    )
    parser.add_argument('--docker-image', default=DEFAULT_EVALUATION_DOCKER_IMAGE, help='Docker image for docker-per-attempt execution.')
    parser.add_argument('--docker-data-dir', type=Path, default=None, help='Host data directory mounted read-only into Docker attempts.')
    parser.add_argument('--docker-container-data-path', default='/data', help='Container path for the read-only data mount.')
    parser.add_argument('--docker-container-run-bundle-path', default='/evaluation-run', help='Container path for the writable attempt run bundle mount.')
    parser.add_argument('--agent-concurrency', type=int, default=DEFAULT_AGENT_CONCURRENCY, help='Concurrent agent attempts for docker-per-attempt execution.')
    parser.add_argument('--judge-concurrency', type=int, default=DEFAULT_JUDGE_CONCURRENCY, help='Concurrent judge scoring requests after execution.')
    parser.add_argument('--infrastructure-max-retries', type=int, default=DEFAULT_INFRASTRUCTURE_MAX_RETRIES, help='Maximum infrastructure retries per counted attempt; 0 means unlimited.')
    parser.add_argument('--skip-judge-scoring', action='store_true', help='Skip post-run LLM judge scoring after execution.')
    parser.add_argument('--strategy-profile', action='append', default=None, help='Strategy profile id for reward-sweep attempts. May be repeated.')
    parser.add_argument('--strategy-profile-root', type=Path, default=None, help='Directory containing strategy profile manifests.')
    parser.add_argument('--strategy-policy-run-id', default=None, help='Policy run id to record on strategy attempts.')
    parser.add_argument('--strategy-policy-checkpoint-id', default=None, help='Policy checkpoint id to record on strategy attempts.')
    parser.add_argument('--strategy-trl-run-id', default=None, help='TRL training run id to record on strategy attempts.')
    parser.add_argument('--strategy-training-step', type=int, default=None, help='TRL training step to record on strategy attempts.')
    parser.add_argument('--strategy-action-rationale', default=None, help='Policy rationale to record on strategy attempts.')
    parser.add_argument(
        '--strategy-source',
        choices=('manual-baseline', 'offline-sweep', 'trained-policy', 'policy-stub'),
        default='offline-sweep',
        help='Evidence source recorded for strategy-controlled attempts.',
    )
    args = parser.parse_args(argv)

    if args.execute:
        executed: CampaignExecution = asyncio.run(
            execute_campaign_run(
                args.campaign,
                variant_root=args.variant_root,
                output_root=args.output_root,
                max_attempts=args.max_attempts,
                attempt_ids=args.attempt_id,
                execution_backend=args.execution_backend,
                docker_image=args.docker_image,
                docker_data_dir=args.docker_data_dir,
                docker_container_data_path=args.docker_container_data_path,
                docker_container_run_bundle_path=args.docker_container_run_bundle_path,
                agent_concurrency=args.agent_concurrency,
                judge_concurrency=args.judge_concurrency,
                infrastructure_max_retries=args.infrastructure_max_retries,
                score_after_execution=not args.skip_judge_scoring,
                strategy_profile_ids=args.strategy_profile,
                strategy_profile_root=args.strategy_profile_root,
                strategy_source=args.strategy_source,
                strategy_policy_run_id=args.strategy_policy_run_id,
                strategy_policy_checkpoint_id=args.strategy_policy_checkpoint_id,
                strategy_trl_run_id=args.strategy_trl_run_id,
                strategy_training_step=args.strategy_training_step,
                strategy_action_rationale=args.strategy_action_rationale,
            )
        )
        print(json.dumps(executed.initialization.summary(), ensure_ascii=False, indent=2))
        print(json.dumps({'summary_path': str(executed.summary_path)}, ensure_ascii=False, indent=2))
    else:
        initialized: CampaignInitialization = initialize_campaign_run(
            args.campaign,
            variant_root=args.variant_root,
            output_root=args.output_root,
            strategy_profile_ids=args.strategy_profile,
            strategy_profile_root=args.strategy_profile_root,
            strategy_source=args.strategy_source,
            strategy_policy_run_id=args.strategy_policy_run_id,
            strategy_policy_checkpoint_id=args.strategy_policy_checkpoint_id,
            strategy_trl_run_id=args.strategy_trl_run_id,
            strategy_training_step=args.strategy_training_step,
            strategy_action_rationale=args.strategy_action_rationale,
        )
        print(json.dumps(initialized.summary(), ensure_ascii=False, indent=2))
    return 0


def _create_campaign_directories(
    *,
    campaign: CampaignManifest,
    output_root: Path | None,
    timestamp: datetime,
) -> CampaignDirectories:
    resolved_output_root: Path = output_root.expanduser().resolve() if output_root is not None else _resolve_repo_path(campaign.output_root)
    if campaign.output_directory_policy == 'timestamped-campaign-dir':
        campaign_root: Path = _unique_timestamped_campaign_root(
            resolved_output_root,
            timestamp=timestamp,
            campaign_id=campaign.id,
        )
        campaign_root_exists_ok = False
    else:
        campaign_root = resolved_output_root
        if campaign_root.exists() and any(campaign_root.iterdir()):
            raise BenchmarkValidationError(f'Explicit campaign output directory is not empty: {campaign_root}')
        campaign_root_exists_ok = True

    directories = CampaignDirectories(
        root=campaign_root,
        manifests=campaign_root / 'manifests',
        runs=campaign_root / 'runs',
        logs=campaign_root / 'logs',
        app_support=None,
        workspace=campaign_root / 'workspace',
        runtime_config=None,
        runtime_assets=campaign_root / 'runtime-assets',
    )
    directories.root.mkdir(parents=True, exist_ok=campaign_root_exists_ok)
    return directories


def _write_snapshots(
    *,
    directories: CampaignDirectories,
    campaign: CampaignManifest,
    variants: list[VariantManifest],
    scenarios: list[BenchmarkScenario],
) -> Path:
    campaign_snapshot_path: Path = directories.manifests / 'campaign.yaml'
    variant_snapshot_root: Path = directories.manifests / 'variants'
    scenario_snapshot_root: Path = directories.manifests / 'scenarios'
    variant_snapshot_root.mkdir(parents=True)
    scenario_snapshot_root.mkdir()

    shutil.copy2(campaign.path, campaign_snapshot_path)
    for variant in variants:
        shutil.copy2(variant.path, variant_snapshot_root / variant.path.name)
    for scenario in scenarios:
        shutil.copy2(scenario.path, scenario_snapshot_root / f'{_safe_slug(scenario.id)}-{scenario.path.name}')
    return campaign_snapshot_path


def _planned_attempts(
    *,
    campaign: CampaignManifest,
    variants: list[VariantManifest],
    scenarios: list[BenchmarkScenario],
    directories: CampaignDirectories,
    strategy_profiles: tuple[StrategyProfile, ...],
    strategy_source: StrategySource,
    strategy_policy_run_id: str | None,
    strategy_policy_checkpoint_id: str | None,
    strategy_trl_run_id: str | None,
    strategy_training_step: int | None,
    strategy_action_rationale: str | None,
) -> list[PlannedAttempt]:
    attempts: list[PlannedAttempt] = []
    for variant in variants:
        selected_scenarios: list[BenchmarkScenario] = _select_scenarios(variant.scenario_selector, scenarios)
        repeat_count: int = _repeat_count(campaign, variant)
        profile_options: tuple[StrategyProfile | None, ...] = (None,) if not strategy_profiles else strategy_profiles
        for scenario in selected_scenarios:
            for profile in profile_options:
                strategy: StrategySelection | None = (
                    strategy_selection_from_profile(
                        profile,
                        source=strategy_source,
                        policy_run_id=strategy_policy_run_id,
                        policy_checkpoint_id=strategy_policy_checkpoint_id,
                        trl_run_id=strategy_trl_run_id,
                        training_step=strategy_training_step,
                        action_rationale=strategy_action_rationale,
                    ) if profile is not None else None
                )
                strategy_segment: str | None = _safe_slug(profile.id) if profile is not None else None
                for repeat_index in range(1, repeat_count + 1):
                    attempt_id_parts: list[str] = [_safe_slug(variant.id)]
                    run_path_parts: list[str] = [variant.id]
                    if strategy_segment is not None:
                        attempt_id_parts.append(strategy_segment)
                        run_path_parts.append(strategy_segment)
                    attempt_id_parts.extend([_safe_slug(scenario.id), f'r{repeat_index:03d}'])
                    run_path_parts.extend([scenario.id, f'repeat-{repeat_index:03d}'])
                    attempts.append(
                        PlannedAttempt(
                            id='__'.join(attempt_id_parts),
                            variant_id=variant.id,
                            scenario_id=scenario.id,
                            repeat_index=repeat_index,
                            run_bundle_path=directories.runs.joinpath(*run_path_parts),
                            strategy=strategy,
                        )
                    )
    return attempts


def _campaign_plan(
    *,
    campaign: CampaignManifest,
    directories: CampaignDirectories,
    variants: list[VariantManifest],
    strategy_profiles: list[StrategyProfile],
    scenarios: list[BenchmarkScenario],
    attempts: tuple[PlannedAttempt, ...],
    created_at: datetime,
) -> dict[str, object]:
    selected_scenario_ids: set[str] = {attempt.scenario_id for attempt in attempts}
    return {
        'schema': CAMPAIGN_INIT_SCHEMA,
        'created_at': created_at.astimezone(UTC).isoformat(),
        'campaign': {
            'id': campaign.id,
            'manifest_path': str(campaign.path),
            'manifest_hash': _sha256_file(campaign.path),
            'snapshot_path': _relative_or_absolute(directories.manifests / 'campaign.yaml', directories.root),
        },
        'directories': {
            'root': str(directories.root),
            'manifests': _relative_or_absolute(directories.manifests, directories.root),
            'runs': _relative_or_absolute(directories.runs, directories.root),
            'logs': _relative_or_absolute(directories.logs, directories.root),
            'runtime_assets': _relative_or_absolute(directories.runtime_assets, directories.root),
        },
        'runner': {
            'resume_policy': campaign.runner_resume_policy,
            'isolation_mode': campaign.runner_isolation_mode,
            'wall_clock_budget_seconds': campaign.wall_clock_budget_seconds,
            'max_turns': campaign.max_turns,
        },
        'variants': [
            {
                'id': variant.id,
                'kind': variant.kind,
                'scenario_selector': variant.scenario_selector,
                'repeat_count': _repeat_count(campaign, variant),
                'manifest_path': str(variant.path),
                'manifest_hash': _sha256_file(variant.path),
                'snapshot_path': _relative_or_absolute(
                    directories.manifests / 'variants' / variant.path.name,
                    directories.root,
                ),
            }
            for variant in variants
        ],
        'strategy_profiles': [
            {
                'id': profile.id,
                'label': profile.label,
                'manifest_path': str(profile.path),
                'profile_hash': profile.profile_hash,
            }
            for profile in strategy_profiles
        ],
        'scenarios': [
            {
                'id': scenario.id,
                'split': scenario.split,
                'task_family': scenario.task_family,
                'gold_control_state': scenario.gold_control_state,
                'fixture_path': str(scenario.path),
                'fixture_hash': _sha256_file(scenario.path),
                'snapshot_path': _relative_or_absolute(
                    directories.manifests / 'scenarios' / f'{_safe_slug(scenario.id)}-{scenario.path.name}',
                    directories.root,
                ),
            }
            for scenario in scenarios
            if scenario.id in selected_scenario_ids
        ],
        'attempt_count': len(attempts),
        'attempts': [attempt.as_json(directories.root) for attempt in attempts],
    }


def _attempt_strategy_profile(
    planned_attempt: PlannedAttempt,
    profile_by_id: dict[str, StrategyProfile],
) -> StrategyProfile | None:
    if planned_attempt.strategy is None:
        return None
    profile = profile_by_id.get(planned_attempt.strategy.strategy_id)
    if profile is None:
        raise BenchmarkValidationError(f'Unknown strategy profile for attempt {planned_attempt.id}: {planned_attempt.strategy.strategy_id}')
    return profile


def _repeat_count(campaign: CampaignManifest, variant: VariantManifest) -> int:
    if variant.id == 'full-system':
        return campaign.full_system_repeats
    return campaign.comparison_repeats


def _attempt_budget_seconds(campaign: CampaignManifest, variant: VariantManifest) -> float:
    if variant.runtime_wall_clock_budget_seconds > 0:
        return float(variant.runtime_wall_clock_budget_seconds)
    return float(campaign.wall_clock_budget_seconds)


async def _execute_docker_campaign_attempts(
    *,
    campaign: CampaignManifest,
    planned_attempts: tuple[PlannedAttempt, ...],
    scenario_by_id: dict[str, BenchmarkScenario],
    variant_by_id: dict[str, VariantManifest],
    resume_policy: RunnerResumePolicy,
    docker_image: str,
    docker_data_dir: Path | None,
    docker_container_data_path: str,
    docker_container_run_bundle_path: str,
    docker_client: Any | None,
    agent_concurrency: int,
    infrastructure_max_retries: int,
) -> tuple['RunBundleCapture', ...]:
    queue: asyncio.Queue[tuple[int, PlannedAttempt]] = asyncio.Queue()
    for item in enumerate(planned_attempts):
        queue.put_nowait(item)
    results: list[tuple[int, 'RunBundleCapture']] = []
    lock = asyncio.Lock()

    async def worker() -> None:
        while True:
            try:
                index, planned_attempt = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            capture = await _execute_one_docker_campaign_attempt(
                campaign=campaign,
                planned_attempt=planned_attempt,
                scenario=scenario_by_id[planned_attempt.scenario_id],
                variant=variant_by_id[planned_attempt.variant_id],
                resume_policy=resume_policy,
                docker_image=docker_image,
                docker_data_dir=docker_data_dir,
                docker_container_data_path=docker_container_data_path,
                docker_container_run_bundle_path=docker_container_run_bundle_path,
                docker_client=docker_client,
                infrastructure_max_retries=infrastructure_max_retries,
            )
            async with lock:
                results.append((index, capture))
            queue.task_done()

    await asyncio.gather(*(worker() for _ in range(agent_concurrency)))
    return tuple(capture for _, capture in sorted(results, key=lambda item: item[0]))


async def _execute_one_docker_campaign_attempt(
    *,
    campaign: CampaignManifest,
    planned_attempt: PlannedAttempt,
    scenario: BenchmarkScenario,
    variant: VariantManifest,
    resume_policy: RunnerResumePolicy,
    docker_image: str,
    docker_data_dir: Path | None,
    docker_container_data_path: str,
    docker_container_run_bundle_path: str,
    docker_client: Any | None,
    infrastructure_max_retries: int,
) -> 'RunBundleCapture':
    allocation: RunBundleAllocation = allocate_run_bundle(planned_attempt, resume_policy=resume_policy)
    from app.evaluation.docker_attempts import DockerAttemptOptions, DockerAttemptRequest, run_docker_attempt

    retry_count = 0
    while True:
        capture = await run_docker_attempt(
            DockerAttemptRequest(
                campaign=campaign,
                allocation=allocation,
                scenario=scenario,
                variant=variant,
                options=DockerAttemptOptions(
                    image=docker_image,
                    data_dir=docker_data_dir,
                    container_data_path=docker_container_data_path,
                    container_run_bundle_path=docker_container_run_bundle_path,
                ),
            ),
            docker_client=docker_client,
        )
        if not _is_retryable_infrastructure_failure(capture.bundle_root):
            return capture
        retry_count += 1
        if infrastructure_max_retries and retry_count > infrastructure_max_retries:
            return capture
        shutil.rmtree(allocation.path, ignore_errors=True)
        allocation.path.mkdir(parents=True, exist_ok=False)


async def _score_campaign_run_after_execution(
    initialized: CampaignInitialization,
    *,
    judge_concurrency: int,
) -> None:
    from app.evaluation.llm_judge import GLMJudgeProvider, JudgeConfig
    from app.evaluation.scoring_pipeline import score_campaign_run

    await score_campaign_run(
        initialized.directories.root,
        judge_provider=GLMJudgeProvider(),
        judge_config=JudgeConfig(
            model=initialized.campaign.judge_model,
            temperature=initialized.campaign.judge_temperature,
        ),
        judge_concurrency=judge_concurrency,
    )


def _is_retryable_infrastructure_failure(run_bundle_path: Path) -> bool:
    status: dict[str, Any] = _load_json(run_bundle_path / 'run-status.json', default={})
    reason = status.get('terminal_reason')
    if isinstance(reason, str) and reason in INFRASTRUCTURE_RETRY_TERMINAL_REASONS:
        return True
    if isinstance(reason, str) and reason == 'container_failed':
        return _bundle_contains_retryable_error_text(run_bundle_path)
    return False


def _bundle_contains_retryable_error_text(run_bundle_path: Path) -> bool:
    paths: list[Path] = [
        run_bundle_path / 'run-status.json',
        run_bundle_path / 'run-manifest.json',
        run_bundle_path / 'container-entrypoint-error.json',
        run_bundle_path / 'container-metadata.json',
    ]
    log_root: Path = run_bundle_path / 'logs'
    if log_root.is_dir():
        paths.extend(sorted(log_root.glob('*')))
    for path in paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding='utf-8', errors='replace').lower()
        if any(marker in text for marker in INFRASTRUCTURE_RETRY_TEXT_MARKERS):
            return True
    return False


def _select_planned_attempts(
    attempts: tuple[PlannedAttempt, ...],
    *,
    attempt_ids: Sequence[str] | None,
) -> tuple[PlannedAttempt, ...]:
    if not attempt_ids:
        return attempts
    requested: tuple[str, ...] = tuple(attempt_ids)
    attempt_by_id: dict[str, PlannedAttempt] = {attempt.id: attempt for attempt in attempts}
    missing: list[str] = [attempt_id for attempt_id in requested if attempt_id not in attempt_by_id]
    if missing:
        joined: str = ', '.join(missing)
        raise BenchmarkValidationError(f'Unknown planned attempt id: {joined}')
    return tuple(attempt_by_id[attempt_id] for attempt_id in requested)


def _attempt_app_directories(campaign_directories: CampaignDirectories, run_bundle_path: Path) -> CampaignDirectories:
    app_state_root: Path = run_bundle_path / 'app-state'
    directories = CampaignDirectories(
        root=app_state_root,
        manifests=campaign_directories.manifests,
        runs=campaign_directories.runs,
        logs=run_bundle_path / 'logs',
        app_support=None,
        workspace=run_bundle_path / 'workspace',
        runtime_config=None,
        runtime_assets=campaign_directories.runtime_assets,
    )
    for directory in (
        directories.root,
        directories.workspace,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    return directories


def _variant_runtime_env(
    campaign: CampaignManifest,
    variant: VariantManifest,
    agent_asset_root: Path,
    *,
    overrides: dict[str, str] | None = None,
) -> dict[str, str]:
    env: dict[str, str] = {'GEO_AGENT_AGENT_ASSET_ROOT': str(agent_asset_root)}
    model: str = variant.model if variant.model != 'inherit' else campaign.fairness_model
    if model != 'inherit':
        env['GEO_AGENT_GLM_MODEL'] = model
    if overrides is not None:
        env.update(overrides)
    return env


def _scenario_reference(scenario: BenchmarkScenario) -> dict[str, object]:
    return {
        'id': scenario.id,
        'fixture_path': str(scenario.path),
        'fixture_hash': _sha256_file(scenario.path),
        'split': scenario.split,
        'difficulty': scenario.difficulty,
        'task_family': scenario.task_family,
        'gold_control_state': scenario.gold_control_state,
        'dataset_root': scenario.dataset_root,
    }


def _variant_reference(variant: VariantManifest) -> dict[str, object]:
    return {
        'id': variant.id,
        'kind': variant.kind,
        'manifest_path': str(variant.path),
        'manifest_hash': _sha256_file(variant.path),
    }


def _campaign_execution_summary(
    *,
    initialized: CampaignInitialization,
    run_captures: tuple['RunBundleCapture', ...],
    selected_attempt_count: int,
) -> dict[str, object]:
    return {
        'schema': CAMPAIGN_EXECUTION_SCHEMA,
        'campaign_id': initialized.campaign.id,
        'campaign_root': str(initialized.directories.root),
        'planned_attempt_count': len(initialized.planned_attempts),
        'selected_attempt_count': selected_attempt_count,
        'executed_attempt_count': len(run_captures),
        'runs': [
            {
                'run_id': capture.run_id,
                'bundle_path': _relative_or_absolute(capture.bundle_root, initialized.directories.root),
                'run_manifest_path': _relative_or_absolute(capture.run_manifest_path, initialized.directories.root),
                'error_count': capture.error_count,
                'artifact_count': capture.artifact_count,
            }
            for capture in run_captures
        ],
    }


def _select_scenarios(selector: str, scenarios: list[BenchmarkScenario]) -> list[BenchmarkScenario]:
    selected: list[BenchmarkScenario] = [
        scenario for scenario in scenarios
        if selector in scenario.subset_tags
    ]
    if not selected:
        raise BenchmarkValidationError(f'Scenario selector does not match any benchmark scenarios: {selector}')
    return selected


def _unique_timestamped_campaign_root(output_root: Path, *, timestamp: datetime, campaign_id: str) -> Path:
    slug: str = f'{timestamp.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")}-{_safe_slug(campaign_id)}'
    candidate: Path = output_root / slug
    if not candidate.exists():
        return candidate
    for index in range(2, 1000):
        candidate = output_root / f'{slug}-{index:03d}'
        if not candidate.exists():
            return candidate
    raise BenchmarkValidationError(f'Could not allocate a unique campaign directory under: {output_root}')


def _run_bundle_candidate(path: Path, attempt_number: int) -> Path:
    if attempt_number == 1:
        return path
    return path.with_name(f'{path.name}-attempt-{attempt_number:03d}')


def _run_bundle_attempt_id(planned_attempt_id: str, attempt_number: int) -> str:
    if attempt_number == 1:
        return planned_attempt_id
    return f'{planned_attempt_id}__a{attempt_number:03d}'


def _resolve_repo_path(value: str) -> Path:
    path: Path = Path(value)
    if path.is_absolute():
        return path
    return repo_root() / path


def _relative_or_absolute(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _safe_slug(value: str) -> str:
    slug: str = ''.join(character if character.isalnum() or character in {'-', '_'} else '-' for character in value)
    return slug.strip('-') or 'unnamed'


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def _load_json(path: Path, *, default: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return default
    if not isinstance(payload, dict):
        return default
    return payload


if __name__ == '__main__':
    raise SystemExit(main())
