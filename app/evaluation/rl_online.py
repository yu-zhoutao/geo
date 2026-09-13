from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
import asyncio
import json
import os
from pathlib import Path
from typing import Any, Literal, Sequence

from app.evaluation.benchmarks import (
    BenchmarkScenario,
    BenchmarkValidationError,
    default_benchmark_root,
    load_benchmark_scenarios,
    load_simple_yaml,
    repo_root,
)
from app.evaluation.judge_rubrics import GEOSPATIAL_AGENT_RUBRIC
from app.evaluation.llm_judge import GLMJudgeProvider, JUDGE_SCORE_FILENAME, JudgeConfig
from app.evaluation.rl_rewards import RewardConfig, write_reward_record
from app.evaluation.rl_task import SELECT_STRATEGY_TOOL_NAME, StrategyRolloutBridge, require_trl_dependencies
from app.evaluation.run_bundles import ARTIFACT_MANIFEST_FILENAME, RUN_MANIFEST_FILENAME, RUN_STATUS_FILENAME
from app.evaluation.runner import ExecutionBackend, execute_campaign_run
from app.evaluation.scoring_pipeline import score_campaign_run
from app.evaluation.strategy_profiles import StrategySelection


OnlineRLAlgorithm = Literal['rloo', 'grpo']
ONLINE_RL_EXPERIMENT_SCHEMA = 'geo-agent.evaluation.trl-online-experiment.v1'
ONLINE_RL_RUN_SCHEMA = 'geo-agent.evaluation.trl-online-run.v1'
ONLINE_RL_SUMMARY_FILENAME = 'online-rl-summary.json'
ONLINE_RL_MANIFEST_FILENAME = 'online-rl-manifest.json'
ONLINE_RL_ROLLOUTS_FILENAME = 'online-rollouts.jsonl'
ONLINE_RL_METRICS_FILENAME = 'training-metrics.json'
FROZEN_POLICY_EVAL_FILENAME = 'frozen-policy-evaluation.json'
DEFAULT_ONLINE_RL_MANIFEST = repo_root() / 'app' / 'evaluation_assets' / 'rl' / 'minimal-online-trl-v1.yaml'
DEFAULT_REMOTE_OUTPUT_ROOT = '/raid/$USER/geo-agent/experiments/rl-online'
DEFAULT_DOWNSTREAM_PROVIDER = 'deepseek'
DEFAULT_DOWNSTREAM_MODEL = 'deepseek-v4-flash'
DEFAULT_PYTHON_INDEX_URL = 'https://pypi.tuna.tsinghua.edu.cn/simple'
VALID_ALGORITHMS: set[str] = {'rloo', 'grpo'}
POLICY_GENERATION_MAX_PROMPT_LENGTH = 2048
ONLINE_ROLLOUT_ERROR_REWARD = 0.0


@dataclass(frozen=True, slots=True)
class LoRASettings:
    rank: int = 8
    alpha: int = 16
    dropout: float = 0.05
    target_modules: tuple[str, ...] = ()

    def as_json(self) -> dict[str, object]:
        return {
            'rank': self.rank,
            'alpha': self.alpha,
            'dropout': self.dropout,
            'target_modules': list(self.target_modules),
        }


@dataclass(frozen=True, slots=True)
class OnlineRLExperimentManifest:
    id: str
    path: Path
    benchmark_root: Path
    campaign_path: Path
    variant_root: Path
    variant_id: str
    scenario_selector: str
    strategy_set: tuple[str, ...]
    episode_cap: int
    parallel_rollout_cap: int
    wall_clock_budget_seconds: int
    rollout_wall_clock_budget_seconds: int
    rollout_retry_count: int
    algorithm: OnlineRLAlgorithm
    group_completions_per_prompt: int
    reward_formula_id: str
    policy_model_id: str
    max_completion_length: int
    learning_rate: float
    logging_steps: int
    save_steps: int
    lora: LoRASettings
    checkpoint_root: Path
    downstream_model_provider: str
    downstream_model: str
    judge_model: str
    judge_temperature: float
    output_root: Path
    python_index_url: str

    def as_json(self) -> dict[str, object]:
        return {
            'schema': ONLINE_RL_EXPERIMENT_SCHEMA,
            'id': self.id,
            'manifest_path': str(self.path),
            'benchmark_root': str(self.benchmark_root),
            'campaign_path': str(self.campaign_path),
            'variant_root': str(self.variant_root),
            'variant_id': self.variant_id,
            'scenario_selector': self.scenario_selector,
            'strategy_set': list(self.strategy_set),
            'episode_cap': self.episode_cap,
            'parallel_rollout_cap': self.parallel_rollout_cap,
            'wall_clock_budget_seconds': self.wall_clock_budget_seconds,
            'rollout_wall_clock_budget_seconds': self.rollout_wall_clock_budget_seconds,
            'rollout_retry_count': self.rollout_retry_count,
            'algorithm': self.algorithm,
            'group_completions_per_prompt': self.group_completions_per_prompt,
            'reward_formula_id': self.reward_formula_id,
            'policy_model_id': self.policy_model_id,
            'max_completion_length': self.max_completion_length,
            'learning_rate': self.learning_rate,
            'logging_steps': self.logging_steps,
            'save_steps': self.save_steps,
            'lora': self.lora.as_json(),
            'checkpoint_root': str(self.checkpoint_root),
            'downstream_model_provider': self.downstream_model_provider,
            'downstream_model': self.downstream_model,
            'judge_model': self.judge_model,
            'judge_temperature': self.judge_temperature,
            'output_root': str(self.output_root),
            'python_index_url': self.python_index_url,
        }


@dataclass(frozen=True, slots=True)
class OnlineTrainingRun:
    run_id: str
    root: Path
    manifest_path: Path
    rollout_path: Path
    metrics_path: Path
    checkpoint_root: Path
    summary_path: Path

    def as_json(self) -> dict[str, object]:
        return {
            'run_id': self.run_id,
            'root': str(self.root),
            'manifest_path': str(self.manifest_path),
            'rollout_path': str(self.rollout_path),
            'metrics_path': str(self.metrics_path),
            'checkpoint_root': str(self.checkpoint_root),
            'summary_path': str(self.summary_path),
        }


def load_online_rl_manifest(path: Path) -> OnlineRLExperimentManifest:
    payload: dict[str, Any] = load_simple_yaml(path)
    _require_fields(
        path,
        payload,
        (
            'id',
            'scenario_selector',
            'strategy_set',
            'episode_cap',
            'parallel_rollout_cap',
            'wall_clock_budget_seconds',
            'policy_model_id',
            'checkpoint_root',
            'output_root',
        ),
    )
    algorithm = _optional_literal(payload, 'algorithm', 'rloo', VALID_ALGORITHMS, path)
    group_completions = _optional_int(payload, 'group_completions_per_prompt', 2)
    if algorithm == 'grpo' and group_completions <= 1:
        raise BenchmarkValidationError(
            f'{path} algorithm grpo requires group_completions_per_prompt greater than 1'
        )
    manifest = OnlineRLExperimentManifest(
        id=_as_str(payload, 'id'),
        path=path,
        benchmark_root=_resolve_path(_optional_str(payload, 'benchmark_root', str(default_benchmark_root()))),
        campaign_path=_resolve_path(
            _optional_str(payload, 'campaign_path', 'app/evaluation_assets/campaigns/thesis-balanced-v1.yaml')
        ),
        variant_root=_resolve_path(_optional_str(payload, 'variant_root', 'app/evaluation_assets/variants')),
        variant_id=_optional_str(payload, 'variant_id', 'full-system'),
        scenario_selector=_as_str(payload, 'scenario_selector'),
        strategy_set=_as_tuple(payload, 'strategy_set'),
        episode_cap=_as_positive_int(payload, 'episode_cap'),
        parallel_rollout_cap=_as_positive_int(payload, 'parallel_rollout_cap'),
        wall_clock_budget_seconds=_as_positive_int(payload, 'wall_clock_budget_seconds'),
        rollout_wall_clock_budget_seconds=_optional_positive_int(payload, 'rollout_wall_clock_budget_seconds', 900),
        rollout_retry_count=_optional_int(payload, 'rollout_retry_count', 1),
        algorithm=algorithm,  # type: ignore[arg-type]
        group_completions_per_prompt=group_completions,
        reward_formula_id=_optional_str(payload, 'reward_formula_id', 'geospatial-strategy-reward-v1'),
        policy_model_id=_as_model_ref(payload, 'policy_model_id'),
        max_completion_length=_optional_positive_int(payload, 'max_completion_length', 96),
        learning_rate=_optional_float(payload, 'learning_rate', 1e-6),
        logging_steps=_optional_positive_int(payload, 'logging_steps', 1),
        save_steps=_optional_positive_int(payload, 'save_steps', 10),
        lora=LoRASettings(
            rank=_optional_int(payload, 'lora_rank', 8),
            alpha=_optional_int(payload, 'lora_alpha', 16),
            dropout=_optional_float(payload, 'lora_dropout', 0.05),
            target_modules=_optional_tuple(payload, 'lora_target_modules', ()),
        ),
        checkpoint_root=Path(_as_str(payload, 'checkpoint_root')),
        downstream_model_provider=_optional_str(payload, 'downstream_model_provider', DEFAULT_DOWNSTREAM_PROVIDER),
        downstream_model=_optional_str(payload, 'downstream_model', DEFAULT_DOWNSTREAM_MODEL),
        judge_model=_optional_str(payload, 'judge_model', 'glm-5.1'),
        judge_temperature=_optional_float(payload, 'judge_temperature', 0.0),
        output_root=_resolve_path(_as_str(payload, 'output_root')),
        python_index_url=_optional_str(payload, 'python_index_url', DEFAULT_PYTHON_INDEX_URL),
    )
    _validate_online_manifest(manifest)
    return manifest


def selected_training_scenarios(manifest: OnlineRLExperimentManifest) -> tuple[BenchmarkScenario, ...]:
    scenarios = load_benchmark_scenarios(manifest.benchmark_root)
    selected = tuple(scenario for scenario in scenarios if manifest.scenario_selector in scenario.subset_tags)
    if not selected:
        raise BenchmarkValidationError(
            f'{manifest.path} scenario_selector {manifest.scenario_selector} does not match any scenarios'
        )
    return selected


def create_online_training_run(
    manifest: OnlineRLExperimentManifest,
    *,
    timestamp: datetime | None = None,
) -> OnlineTrainingRun:
    created_at = timestamp or datetime.now(UTC)
    root = _unique_run_root(manifest.output_root, timestamp=created_at, experiment_id=manifest.id)
    checkpoint_root = manifest.checkpoint_root
    if not checkpoint_root.is_absolute():
        checkpoint_root = root / checkpoint_root
    run = OnlineTrainingRun(
        run_id=root.name,
        root=root,
        manifest_path=root / ONLINE_RL_MANIFEST_FILENAME,
        rollout_path=root / ONLINE_RL_ROLLOUTS_FILENAME,
        metrics_path=root / ONLINE_RL_METRICS_FILENAME,
        checkpoint_root=checkpoint_root,
        summary_path=root / ONLINE_RL_SUMMARY_FILENAME,
    )
    run.root.mkdir(parents=True, exist_ok=False)
    run.checkpoint_root.mkdir(parents=True, exist_ok=True)
    _write_json(run.manifest_path, manifest.as_json())
    return run


@dataclass(slots=True)
class MockOnlineRolloutExecutor:
    output_root: Path
    reward_config: RewardConfig
    policy_model_id: str
    downstream_model_provider: str
    downstream_model: str
    score: int = 3

    async def __call__(self, scenario: BenchmarkScenario, selection: StrategySelection) -> dict[str, Any]:
        training_step = selection.training_step or 0
        run_id = f'{selection.trl_run_id or "trl-smoke"}__{selection.strategy_id}__{scenario.id}__s{training_step:04d}'
        bundle_path = self.output_root / 'mock-run-bundles' / _safe_slug(run_id)
        bundle_path.mkdir(parents=True, exist_ok=False)
        created_at = datetime.now(UTC).isoformat()
        strategy = selection.as_json()
        _write_json(
            bundle_path / RUN_STATUS_FILENAME,
            {
                'schema': 'geo-agent.evaluation.run-status.v1',
                'session_id': f'mock-session-{run_id}',
                'session_status': 'completed',
                'terminal_reason': 'mock_online_rollout',
                'timed_out': False,
                'started_at': created_at,
                'finished_at': created_at,
                'duration_seconds': 0.0,
                'continuation_count': 0,
                'clarification_answer_count': 0,
                'clarification_question_ids': [],
                'error_count': 0,
                'errors': [],
                'strategy': strategy,
                'mock_online_rollout': True,
            },
        )
        _write_json(
            bundle_path / ARTIFACT_MANIFEST_FILENAME,
            {
                'schema': 'geo-agent.evaluation.artifact-capture.v1',
                'session_id': f'mock-session-{run_id}',
                'artifact_count': 0,
                'items': [],
            },
        )
        _write_json(
            bundle_path / RUN_MANIFEST_FILENAME,
            {
                'schema': 'geo-agent.evaluation.run-bundle.v1',
                'run_id': run_id,
                'session_id': f'mock-session-{run_id}',
                'scenario': _scenario_reference(scenario),
                'variant': {'id': 'mock-online-rollout'},
                'strategy': strategy,
                'status': {
                    'session_status': 'completed',
                    'terminal_reason': 'mock_online_rollout',
                    'timed_out': False,
                },
                'trace_capture': None,
                'runtime_trace': {'status': 'mocked'},
                'logs': [],
                'files': {
                    'run_status': RUN_STATUS_FILENAME,
                    'artifact_manifest': ARTIFACT_MANIFEST_FILENAME,
                    'artifact_root': 'artifacts',
                },
                'error_count': 0,
                'errors': [],
                'mock_online_rollout': True,
                'downstream_model': {
                    'provider': self.downstream_model_provider,
                    'model': self.downstream_model,
                },
            },
        )
        _write_json(
            bundle_path / JUDGE_SCORE_FILENAME,
            {
                'schema': 'geo-agent.evaluation.judge-result.v1',
                'scenario_id': scenario.id,
                'model': 'mock-judge',
                'temperature': 0.0,
                'judged_at': created_at,
                'attempts': [{'index': 1, 'raw_response': '{}', 'parsed_score': _mock_score(self.score), 'error': None}],
                'parsed_score': _mock_score(self.score),
            },
        )
        reward_path = write_reward_record(
            bundle_path,
            config=self.reward_config,
            reward_source='mock-online-trl-training',
        )
        record = json.loads(reward_path.read_text(encoding='utf-8'))
        if not isinstance(record, dict):
            raise BenchmarkValidationError(f'Invalid mock reward record: {reward_path}')
        return {
            'reward': float(record.get('reward') or 0.0),
            'reward_source': 'mock-online-trl-training',
            'run_bundle_path': str(bundle_path),
            'judge_score_path': str(bundle_path / JUDGE_SCORE_FILENAME),
            'reward_record_path': str(reward_path),
            'record': record,
            'downstream_model_provider': self.downstream_model_provider,
            'downstream_model': self.downstream_model,
            'mock_online_rollout': True,
        }


@dataclass(slots=True)
class LiveEvaluationRolloutExecutor:
    manifest: OnlineRLExperimentManifest
    output_root: Path
    app_command: tuple[str, ...] | None = None
    execution_backend: ExecutionBackend = 'local-process'

    async def __call__(self, scenario: BenchmarkScenario, selection: StrategySelection) -> dict[str, Any]:
        attempt_id = '__'.join(
            [
                _safe_slug(self.manifest.variant_id),
                _safe_slug(selection.strategy_id),
                _safe_slug(scenario.id),
                'r001',
            ]
        )
        execution = await execute_campaign_run(
            self.manifest.campaign_path,
            variant_root=self.manifest.variant_root,
            output_root=self.output_root,
            app_command=self.app_command,
            max_attempts=1,
            attempt_ids=(attempt_id,),
            execution_backend=self.execution_backend,
            attempt_wall_clock_budget_seconds=float(self.manifest.rollout_wall_clock_budget_seconds),
            strategy_profile_ids=(selection.strategy_id,),
            strategy_source=selection.source,
            strategy_policy_run_id=selection.policy_run_id,
            strategy_policy_checkpoint_id=selection.policy_checkpoint_id,
            strategy_trl_run_id=selection.trl_run_id,
            strategy_training_step=selection.training_step,
            strategy_action_rationale=selection.action_rationale,
            runtime_env_overrides={
                'GEO_AGENT_MODEL_PROVIDER': self.manifest.downstream_model_provider,
                'GEO_AGENT_DEEPSEEK_MODEL': self.manifest.downstream_model,
            },
        )
        scoring = await score_campaign_run(
            execution.initialization.directories.root,
            judge_provider=GLMJudgeProvider(),
            judge_config=JudgeConfig(model=self.manifest.judge_model, temperature=self.manifest.judge_temperature),
        )
        if not execution.run_captures:
            raise BenchmarkValidationError(f'Online rollout produced no run capture for {attempt_id}')
        bundle_path = execution.run_captures[0].bundle_root
        reward_path = write_reward_record(
            bundle_path,
            config=RewardConfig(formula_id=self.manifest.reward_formula_id),
            reward_source='online-trl-training',
        )
        record = json.loads(reward_path.read_text(encoding='utf-8'))
        if not isinstance(record, dict):
            raise BenchmarkValidationError(f'Invalid online reward record: {reward_path}')
        return {
            'reward': float(record.get('reward') or 0.0),
            'reward_source': 'online-trl-training',
            'run_bundle_path': str(bundle_path),
            'campaign_root': str(execution.initialization.directories.root),
            'judge_score_count': len(scoring.judge_score_paths),
            'reward_record_path': str(reward_path),
            'record': record,
            'downstream_model_provider': self.manifest.downstream_model_provider,
            'downstream_model': self.manifest.downstream_model,
        }


class TRLOnlineRewardFunction:
    def __init__(
        self,
        *,
        bridge: StrategyRolloutBridge,
        scenarios: Sequence[BenchmarkScenario],
        require_function_call: bool = True,
        require_rationale: bool = False,
        max_reward_attempts: int = 1,
        rollout_record_path: Path | None = None,
        completion_step_offset: int = 0,
    ) -> None:
        if max_reward_attempts <= 0:
            raise BenchmarkValidationError('max_reward_attempts must be positive')
        if completion_step_offset < 0:
            raise BenchmarkValidationError('completion_step_offset must be non-negative')
        self.bridge = bridge
        self.scenario_by_id: dict[str, BenchmarkScenario] = {scenario.id: scenario for scenario in scenarios}
        self.require_function_call = require_function_call
        self.require_rationale = require_rationale
        self.max_reward_attempts = max_reward_attempts
        self.rollout_record_path = rollout_record_path
        self.completion_step_offset = completion_step_offset
        self.records: list[dict[str, object]] = []
        self.__name__ = 'geospatial_online_reward'

    def __call__(self, completions: Sequence[object], **kwargs: object) -> list[float]:
        return asyncio.run(self._score(completions, **kwargs))

    async def _score(self, completions: Sequence[object], **kwargs: object) -> list[float]:
        scenario_ids = _string_sequence(kwargs.get('scenario_id'))
        if len(scenario_ids) != len(completions):
            raise BenchmarkValidationError('TRL reward function requires one scenario_id per completion')
        rewards: list[float] = []
        for completion, scenario_id in zip(completions, scenario_ids, strict=True):
            scenario = self.scenario_by_id.get(scenario_id)
            if scenario is None:
                raise BenchmarkValidationError(f'Unknown TRL reward scenario_id: {scenario_id}')
            training_step = self.completion_step_offset + len(self.records) + 1
            previous_training_step = self.bridge.training_step
            self.bridge.training_step = training_step
            try:
                reward = await self._reward_with_retries(
                    scenario,
                    completion,
                )
            finally:
                self.bridge.training_step = previous_training_step
            rewards.append(float(reward['reward']))
            record: dict[str, object] = {
                'training_step': training_step,
                'scenario_id': scenario_id,
                'completion': completion,
                'reward': reward,
            }
            self.records.append(record)
            if self.rollout_record_path is not None:
                _append_jsonl(self.rollout_record_path, record)
        log_extra = kwargs.get('log_extra')
        if callable(log_extra):
            log_extra('scenario_id', list(scenario_ids))
            log_extra('geo_reward', rewards)
        return rewards

    async def _reward_with_retries(
        self,
        scenario: BenchmarkScenario,
        completion: object,
    ) -> dict[str, object]:
        errors: list[dict[str, object]] = []
        for attempt_index in range(1, self.max_reward_attempts + 1):
            try:
                reward = await self.bridge.reward_for_completion(
                    scenario,
                    completion,
                    require_function_call=self.require_function_call,
                    require_rationale=self.require_rationale,
                )
            except Exception as exc:
                errors.append(
                    {
                        'attempt_index': attempt_index,
                        'error_type': type(exc).__name__,
                        'error': _error_text(exc),
                    }
                )
                if attempt_index < self.max_reward_attempts:
                    continue
                return self._rollout_error_reward(scenario, completion, errors)
            return reward
        return self._rollout_error_reward(scenario, completion, errors)

    def _rollout_error_reward(
        self,
        scenario: BenchmarkScenario,
        completion: object,
        errors: Sequence[dict[str, object]],
    ) -> dict[str, object]:
        action = self.bridge.validate_completion(
            completion,
            require_function_call=self.require_function_call,
            require_rationale=self.require_rationale,
        )
        return {
            'reward': ONLINE_ROLLOUT_ERROR_REWARD,
            'reward_source': 'online-rollout-error',
            'scenario_id': scenario.id,
            'action': action.as_json(),
            'attempt_count': len(errors),
            'errors': list(errors),
        }


async def run_mock_online_training(
    manifest_path: Path,
    *,
    output_root: Path | None = None,
    timestamp: datetime | None = None,
) -> dict[str, object]:
    manifest = load_online_rl_manifest(manifest_path)
    if output_root is not None:
        manifest = replace(manifest, output_root=output_root.expanduser().resolve())
    scenarios = selected_training_scenarios(manifest)
    run = create_online_training_run(manifest, timestamp=timestamp)
    checkpoint_id = 'checkpoint-0001'
    executor = MockOnlineRolloutExecutor(
        output_root=run.root,
        reward_config=RewardConfig(formula_id=manifest.reward_formula_id),
        policy_model_id=manifest.policy_model_id,
        downstream_model_provider=manifest.downstream_model_provider,
        downstream_model=manifest.downstream_model,
    )
    records: list[dict[str, object]] = []
    rewards: list[float] = []
    invalid_count = 0
    for step in range(1, manifest.episode_cap + 1):
        scenario = scenarios[(step - 1) % len(scenarios)]
        strategy_id = manifest.strategy_set[(step - 1) % len(manifest.strategy_set)]
        bridge = StrategyRolloutBridge(
            policy_run_id=run.run_id,
            policy_checkpoint_id=checkpoint_id,
            trl_run_id=run.run_id,
            training_step=step,
            online_executor=executor,
        )
        completion = json.dumps(
            {
                'name': SELECT_STRATEGY_TOOL_NAME,
                'arguments': {
                    'strategy_id': strategy_id,
                    'rationale': 'Mock online smoke rollout for bounded TRL/RLOO plumbing.',
                },
            },
            ensure_ascii=False,
        )
        reward = await bridge.reward_for_completion(scenario, completion, require_function_call=True)
        reward_value = float(reward['reward'])
        rewards.append(reward_value)
        action = reward.get('action')
        if isinstance(action, dict) and action.get('valid') is False:
            invalid_count += 1
        records.append(
            {
                'step': step,
                'algorithm': manifest.algorithm,
                'policy_model_id': manifest.policy_model_id,
                'policy_checkpoint_id': checkpoint_id,
                'trl_run_id': run.run_id,
                'scenario_id': scenario.id,
                'completion': completion,
                'reward': reward,
            }
        )
    _write_jsonl(run.rollout_path, records)
    _write_mock_checkpoint(run.checkpoint_root / checkpoint_id, manifest, run)
    metrics = {
        'schema': ONLINE_RL_RUN_SCHEMA,
        'run_id': run.run_id,
        'algorithm': manifest.algorithm,
        'mock_online_training': True,
        'episode_count': len(records),
        'invalid_action_count': invalid_count,
        'invalid_action_rate': round(invalid_count / len(records), 6) if records else 0.0,
        'reward_mean': round(sum(rewards) / len(rewards), 6) if rewards else None,
        'reward_trajectory': rewards,
    }
    _write_json(run.metrics_path, metrics)
    summary = {
        'schema': ONLINE_RL_RUN_SCHEMA,
        'run': run.as_json(),
        'manifest': manifest.as_json(),
        'metrics': metrics,
        'evidence_boundary': (
            'This is a mocked online smoke run for TRL/RLOO plumbing. It is not thesis evidence for policy quality.'
        ),
    }
    _write_json(run.summary_path, summary)
    return summary


def run_trl_online_training(
    manifest_path: Path,
    *,
    app_command: Sequence[str] | None = None,
    execution_backend: ExecutionBackend = 'local-process',
    output_root: Path | None = None,
    resume_from_checkpoint: Path | None = None,
    timestamp: datetime | None = None,
) -> dict[str, object]:
    manifest = load_online_rl_manifest(manifest_path)
    if output_root is not None:
        manifest = replace(manifest, output_root=output_root.expanduser().resolve())
    scenarios = selected_training_scenarios(manifest)
    run = create_online_training_run(manifest, timestamp=timestamp)
    executor = LiveEvaluationRolloutExecutor(
        manifest=manifest,
        output_root=run.root / 'live-rollouts',
        app_command=tuple(app_command) if app_command is not None else None,
        execution_backend=execution_backend,
    )
    bridge = StrategyRolloutBridge(
        policy_run_id=run.run_id,
        policy_checkpoint_id=(
            f'resumed-from:{resume_from_checkpoint.name}'
            if resume_from_checkpoint is not None
            else 'online-training-current'
        ),
        trl_run_id=run.run_id,
        online_executor=executor,
    )
    deps = require_trl_dependencies()
    from transformers import AutoTokenizer

    processing_class = AutoTokenizer.from_pretrained(manifest.policy_model_id, trust_remote_code=True)
    if processing_class.pad_token_id is None:
        processing_class.pad_token = processing_class.eos_token
    reward_func = TRLOnlineRewardFunction(
        bridge=bridge,
        scenarios=scenarios,
        require_function_call=False,
        max_reward_attempts=manifest.rollout_retry_count + 1,
        rollout_record_path=run.rollout_path,
        completion_step_offset=_resume_completion_offset(
            resume_from_checkpoint,
            group_completions_per_prompt=manifest.group_completions_per_prompt,
        ),
    )
    dataset_rows = [
        {
            'prompt': _policy_prompt_text(processing_class, bridge.build_policy_prompt(scenario)),
            'scenario_id': scenario.id,
        }
        for scenario in scenarios
    ]
    dataset = deps.dataset.from_list(dataset_rows)
    config_class = deps.rloo_config if manifest.algorithm == 'rloo' else deps.grpo_config
    trainer_class = deps.rloo_trainer if manifest.algorithm == 'rloo' else deps.grpo_trainer
    training_args = config_class(
        output_dir=str(run.checkpoint_root),
        max_steps=manifest.episode_cap,
        per_device_train_batch_size=manifest.group_completions_per_prompt,
        num_generations=manifest.group_completions_per_prompt,
        max_completion_length=manifest.max_completion_length,
        learning_rate=manifest.learning_rate,
        logging_steps=manifest.logging_steps,
        save_steps=manifest.save_steps,
        save_total_limit=3,
        bf16=True,
        model_init_kwargs={
            'trust_remote_code': True,
            'dtype': 'bfloat16',
        },
        generation_kwargs={
            'do_sample': True,
            'temperature': 0.7,
            'top_p': 0.9,
        },
        report_to=[],
    )
    peft_kwargs: dict[str, object] = {}
    if manifest.lora.target_modules:
        peft_kwargs['target_modules'] = (
            manifest.lora.target_modules[0]
            if len(manifest.lora.target_modules) == 1
            else list(manifest.lora.target_modules)
        )
    peft_config = deps.lora_config(
        r=manifest.lora.rank,
        lora_alpha=manifest.lora.alpha,
        lora_dropout=manifest.lora.dropout,
        task_type='CAUSAL_LM',
        **peft_kwargs,
    )
    trainer = trainer_class(
        model=manifest.policy_model_id,
        args=training_args,
        reward_funcs=reward_func,
        train_dataset=dataset,
        processing_class=processing_class,
        peft_config=peft_config,
    )
    train_error: dict[str, object] | None = None
    try:
        trainer.train(
            resume_from_checkpoint=str(resume_from_checkpoint)
            if resume_from_checkpoint is not None
            else None
        )
    except Exception as exc:
        train_error = {
            'error_type': type(exc).__name__,
            'error': _error_text(exc),
        }
    _write_jsonl(run.rollout_path, reward_func.records)
    reward_values = [
        value
        for value in (_reward_value(record.get('reward')) for record in reward_func.records)
        if value is not None
    ]
    invalid_action_count = sum(
        1
        for record in reward_func.records
        if _reward_action_valid(record.get('reward')) is False
    )
    metrics = {
        'schema': ONLINE_RL_RUN_SCHEMA,
        'run_id': run.run_id,
        'algorithm': manifest.algorithm,
        'mock_online_training': False,
        'completed': train_error is None,
        'episode_count': len(reward_func.records),
        'invalid_action_count': invalid_action_count,
        'invalid_action_rate': (
            round(invalid_action_count / len(reward_func.records), 6)
            if reward_func.records
            else 0.0
        ),
        'reward_mean': round(sum(reward_values) / len(reward_values), 6) if reward_values else None,
        'reward_sources': _reward_source_counts(reward_func.records),
        'reward_trajectory': [
            _reward_value(record.get('reward'))
            for record in reward_func.records
        ],
    }
    if train_error is not None:
        metrics['error'] = train_error
    _write_json(run.metrics_path, metrics)
    summary = {
        'schema': ONLINE_RL_RUN_SCHEMA,
        'run': run.as_json(),
        'manifest': manifest.as_json(),
        'resume_from_checkpoint': str(resume_from_checkpoint) if resume_from_checkpoint is not None else None,
        'metrics': metrics,
    }
    _write_json(run.summary_path, summary)
    if train_error is not None:
        raise BenchmarkValidationError(f'TRL online training failed: {train_error["error"]}')
    return summary


def write_frozen_policy_smoke_evaluation(
    manifest_path: Path,
    *,
    checkpoint_id: str,
    strategy_id: str,
    output_path: Path,
) -> dict[str, object]:
    manifest = load_online_rl_manifest(manifest_path)
    scenarios = selected_training_scenarios(manifest)
    rows = [
        {
            'source': 'base-policy',
            'policy_model_id': manifest.policy_model_id,
            'checkpoint_id': 'base',
            'scenario_id': scenario.id,
            'strategy_id': strategy_id,
            'reward_source': 'frozen-policy-online-evaluation-required',
        }
        for scenario in scenarios
    ]
    rows.extend(
        {
            'source': 'trained-checkpoint',
            'policy_model_id': manifest.policy_model_id,
            'checkpoint_id': checkpoint_id,
            'scenario_id': scenario.id,
            'strategy_id': strategy_id,
            'reward_source': 'frozen-policy-online-evaluation-required',
        }
        for scenario in scenarios
    )
    rows.extend(
        {
            'source': f'fixed-strategy:{fixed_strategy_id}',
            'policy_model_id': 'fixed-strategy-baseline',
            'checkpoint_id': 'none',
            'scenario_id': scenario.id,
            'strategy_id': fixed_strategy_id,
            'reward_source': 'fixed-strategy-online-baseline-required',
        }
        for scenario in scenarios
        for fixed_strategy_id in manifest.strategy_set
    )
    payload: dict[str, object] = {
        'schema': 'geo-agent.evaluation.frozen-policy-evaluation-plan.v1',
        'manifest': manifest.as_json(),
        'checkpoint_id': checkpoint_id,
        'rows': rows,
        'evidence_boundary': (
            'This plan separates base policy, trained checkpoint, fixed-strategy baseline, and offline policy-stub '
            'rows. Fresh online attempts must fill the reward fields before thesis interpretation.'
        ),
    }
    _write_json(output_path, payload)
    return payload


async def run_frozen_policy_online_evaluation(
    manifest_path: Path,
    *,
    checkpoint_id: str,
    strategy_id: str,
    output_root: Path | None = None,
    smoke: bool = True,
    app_command: Sequence[str] | None = None,
    execution_backend: ExecutionBackend = 'local-process',
    timestamp: datetime | None = None,
) -> dict[str, object]:
    manifest = load_online_rl_manifest(manifest_path)
    if output_root is not None:
        manifest = replace(manifest, output_root=output_root.expanduser().resolve())
    scenarios = selected_training_scenarios(manifest)
    run = create_online_training_run(manifest, timestamp=timestamp)
    reward_config = RewardConfig(formula_id=manifest.reward_formula_id)
    executor: MockOnlineRolloutExecutor | LiveEvaluationRolloutExecutor
    if smoke:
        executor = MockOnlineRolloutExecutor(
            output_root=run.root,
            reward_config=reward_config,
            policy_model_id=manifest.policy_model_id,
            downstream_model_provider=manifest.downstream_model_provider,
            downstream_model=manifest.downstream_model,
        )
    else:
        executor = LiveEvaluationRolloutExecutor(
            manifest=manifest,
            output_root=run.root / 'live-frozen-policy-rollouts',
            app_command=tuple(app_command) if app_command is not None else None,
            execution_backend=execution_backend,
        )
    row_specs: list[tuple[str, str, str, str]] = [
        ('base-policy', 'base', strategy_id, 'trained-policy'),
        ('trained-checkpoint', checkpoint_id, strategy_id, 'trained-policy'),
    ]
    generated_completions: dict[tuple[str, str], str] = {}
    if not smoke:
        generated_completions.update(
            _generate_policy_completions(
                manifest=manifest,
                scenarios=scenarios,
                source='base-policy',
                checkpoint_id='base',
                adapter_path=None,
            )
        )
        generated_completions.update(
            _generate_policy_completions(
                manifest=manifest,
                scenarios=scenarios,
                source='trained-checkpoint',
                checkpoint_id=checkpoint_id,
                adapter_path=_policy_checkpoint_path(checkpoint_id),
            )
        )
    row_specs.extend(
        (f'fixed-strategy:{fixed_strategy_id}', 'none', fixed_strategy_id, 'manual-baseline')
        for fixed_strategy_id in manifest.strategy_set
    )
    rows: list[dict[str, object]] = []
    for row_index, (source, row_checkpoint_id, row_strategy_id, strategy_source) in enumerate(row_specs, start=1):
        for scenario_index, scenario in enumerate(scenarios, start=1):
            bridge = StrategyRolloutBridge(
                policy_run_id=f'{run.run_id}-{source}',
                policy_checkpoint_id=row_checkpoint_id,
                trl_run_id=run.run_id,
                training_step=row_index * 1000 + scenario_index,
                strategy_source=strategy_source,  # type: ignore[arg-type]
                online_executor=executor,
            )
            completion = generated_completions.get(
                (source, scenario.id),
                json.dumps(
                    {
                        'name': SELECT_STRATEGY_TOOL_NAME,
                        'arguments': {
                            'strategy_id': row_strategy_id,
                            'rationale': f'Frozen-policy evaluation row: {source}.',
                        },
                    },
                    ensure_ascii=False,
                ),
            )
            reward = await bridge.reward_for_completion(scenario, completion, require_function_call=False)
            rows.append(
                {
                    'source': source,
                    'policy_model_id': (
                        'fixed-strategy-baseline' if source.startswith('fixed-strategy:') else manifest.policy_model_id
                    ),
                    'checkpoint_id': row_checkpoint_id,
                    'scenario_id': scenario.id,
                    'strategy_id': _reward_strategy_id(reward) or row_strategy_id,
                    'completion': completion,
                    'reward_source': reward.get('reward_source'),
                    'reward': reward.get('reward'),
                    'action': reward.get('action'),
                    'record': reward.get('record'),
                }
            )
    payload: dict[str, object] = {
        'schema': 'geo-agent.evaluation.frozen-policy-online-evaluation.v1',
        'run': run.as_json(),
        'manifest': manifest.as_json(),
        'smoke': smoke,
        'rows': rows,
        'reward_source_boundary': (
            'Rows keep base policy, trained checkpoint, fixed-strategy baselines, and offline policy-stub evidence '
            'separate; aggregate interpretation must not mix lookup-derived and fresh online rewards.'
        ),
    }
    output_path = run.root / FROZEN_POLICY_EVAL_FILENAME
    _write_json(output_path, payload)
    return payload


def _generate_policy_completions(
    *,
    manifest: OnlineRLExperimentManifest,
    scenarios: Sequence[BenchmarkScenario],
    source: str,
    checkpoint_id: str,
    adapter_path: Path | None,
) -> dict[tuple[str, str], str]:
    from peft import PeftModel
    import torch
    from transformers import AutoConfig, AutoModelForCausalLM, AutoModelForImageTextToText, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(manifest.policy_model_id, trust_remote_code=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    config = AutoConfig.from_pretrained(manifest.policy_model_id, trust_remote_code=True)
    architectures = tuple(str(architecture) for architecture in (getattr(config, 'architectures', None) or ()))
    has_vision_config = getattr(config, 'vision_config', None) is not None
    model_class = (
        AutoModelForImageTextToText
        if has_vision_config or any(architecture.endswith('ForConditionalGeneration') for architecture in architectures)
        else AutoModelForCausalLM
    )
    model = model_class.from_pretrained(
        manifest.policy_model_id,
        trust_remote_code=True,
        dtype=torch.bfloat16,
        device_map='auto',
    )
    if adapter_path is not None:
        model = PeftModel.from_pretrained(model, adapter_path)
    model.eval()
    bridge = StrategyRolloutBridge(
        policy_run_id=f'{source}-{checkpoint_id}',
        policy_checkpoint_id=checkpoint_id,
        trl_run_id=checkpoint_id,
    )
    completions: dict[tuple[str, str], str] = {}
    for scenario in scenarios:
        prompt = _policy_prompt_text(tokenizer, bridge.build_policy_prompt(scenario))
        inputs = tokenizer(
            prompt,
            return_tensors='pt',
            truncation=True,
            max_length=POLICY_GENERATION_MAX_PROMPT_LENGTH,
        )
        device = next(model.parameters()).device
        inputs = {key: value.to(device) for key, value in inputs.items()}
        with torch.no_grad():
            output_ids = model.generate(
                **inputs,
                max_new_tokens=manifest.max_completion_length,
                do_sample=False,
                pad_token_id=tokenizer.eos_token_id,
            )
        completion_ids = output_ids[0][inputs['input_ids'].shape[-1]:]
        completions[(source, scenario.id)] = tokenizer.decode(completion_ids, skip_special_tokens=True).strip()
    del model
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return completions


def _policy_prompt_text(tokenizer: Any, prompt: str) -> str:
    if not getattr(tokenizer, 'chat_template', None):
        return prompt
    messages = [{'role': 'user', 'content': prompt}]
    try:
        rendered = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )
    except TypeError:
        rendered = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
    return str(rendered)


def _validate_online_manifest(manifest: OnlineRLExperimentManifest) -> None:
    if manifest.algorithm not in VALID_ALGORITHMS:
        allowed = ', '.join(sorted(VALID_ALGORITHMS))
        raise BenchmarkValidationError(f'{manifest.path} algorithm must be one of {allowed}')
    if not manifest.strategy_set:
        raise BenchmarkValidationError(f'{manifest.path} strategy_set must not be empty')
    if manifest.lora.rank <= 0:
        raise BenchmarkValidationError(f'{manifest.path} lora_rank must be positive')
    if manifest.lora.alpha <= 0:
        raise BenchmarkValidationError(f'{manifest.path} lora_alpha must be positive')
    if not 0 <= manifest.lora.dropout < 1:
        raise BenchmarkValidationError(f'{manifest.path} lora_dropout must be in [0, 1)')
    if manifest.rollout_retry_count < 0:
        raise BenchmarkValidationError(f'{manifest.path} rollout_retry_count must be non-negative')
    if manifest.algorithm == 'rloo' and manifest.group_completions_per_prompt <= 1:
        raise BenchmarkValidationError(
            f'{manifest.path} algorithm rloo requires group_completions_per_prompt greater than 1'
        )
    if manifest.downstream_model != DEFAULT_DOWNSTREAM_MODEL:
        raise BenchmarkValidationError(
            f'{manifest.path} downstream_model must default to {DEFAULT_DOWNSTREAM_MODEL} unless a later '
            'experiment explicitly updates this validation boundary'
        )
    if manifest.downstream_model_provider != DEFAULT_DOWNSTREAM_PROVIDER:
        raise BenchmarkValidationError(
            f'{manifest.path} downstream_model_provider must default to {DEFAULT_DOWNSTREAM_PROVIDER}'
        )


def _scenario_reference(scenario: BenchmarkScenario) -> dict[str, object]:
    return {
        'id': scenario.id,
        'fixture_path': str(scenario.path),
        'fixture_hash': _sha256_file(scenario.path),
        'split': scenario.split,
        'difficulty': scenario.difficulty,
        'task_family': scenario.task_family,
        'gold_control_state': scenario.gold_control_state,
        'hazard_categories': list(scenario.hazard_categories),
    }


def _mock_score(score: int) -> dict[str, object]:
    return {
        'dimensions': {
            dimension.id: {'score': score, 'reason': 'mock online rollout score'}
            for dimension in GEOSPATIAL_AGENT_RUBRIC.dimensions
        },
        'summary': 'mock online rollout score',
    }


def _write_mock_checkpoint(path: Path, manifest: OnlineRLExperimentManifest, run: OnlineTrainingRun) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _write_json(
        path / 'adapter_config.json',
        {
            'schema': 'geo-agent.evaluation.mock-lora-adapter.v1',
            'mock_checkpoint': True,
            'base_model_name_or_path': manifest.policy_model_id,
            'lora': manifest.lora.as_json(),
            'trl_run_id': run.run_id,
            'algorithm': manifest.algorithm,
        },
    )


def _reward_value(value: object) -> float | None:
    if isinstance(value, dict):
        reward = value.get('reward')
        if isinstance(reward, int | float) and not isinstance(reward, bool):
            return float(reward)
    return None


def _reward_strategy_id(reward: dict[str, object]) -> str | None:
    action = reward.get('action')
    if not isinstance(action, dict):
        return None
    selection = action.get('selection')
    if not isinstance(selection, dict):
        return None
    strategy_id = selection.get('strategy_id')
    return strategy_id if isinstance(strategy_id, str) else None


def _reward_action_valid(value: object) -> bool | None:
    if not isinstance(value, dict):
        return None
    action = value.get('action')
    if not isinstance(action, dict):
        return None
    valid = action.get('valid')
    return valid if isinstance(valid, bool) else None


def _reward_source_counts(records: Sequence[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        reward = record.get('reward')
        if not isinstance(reward, dict):
            continue
        source = reward.get('reward_source')
        if not isinstance(source, str):
            continue
        counts[source] = counts.get(source, 0) + 1
    return counts


def _policy_checkpoint_path(checkpoint_id: str) -> Path:
    return Path(os.path.expandvars(checkpoint_id)).expanduser()


def _resume_completion_offset(
    checkpoint_path: Path | None,
    *,
    group_completions_per_prompt: int,
) -> int:
    if checkpoint_path is None:
        return 0
    state_path = checkpoint_path / 'trainer_state.json'
    try:
        payload = json.loads(state_path.read_text(encoding='utf-8'))
    except FileNotFoundError as exc:
        raise BenchmarkValidationError(f'Resume checkpoint is missing trainer_state.json: {state_path}') from exc
    if not isinstance(payload, dict):
        raise BenchmarkValidationError(f'Resume checkpoint trainer_state.json must be an object: {state_path}')
    global_step = payload.get('global_step')
    if not isinstance(global_step, int) or isinstance(global_step, bool) or global_step < 0:
        raise BenchmarkValidationError(f'Resume checkpoint has invalid global_step: {state_path}')
    return global_step * group_completions_per_prompt


def _require_fields(path: Path, payload: dict[str, Any], fields: tuple[str, ...]) -> None:
    missing_fields = [field for field in fields if field not in payload or payload[field] in ('', (), [])]
    if missing_fields:
        missing = ', '.join(missing_fields)
        raise BenchmarkValidationError(f'{path} is missing required fields: {missing}')


def _as_str(payload: dict[str, Any], field: str) -> str:
    value = payload[field]
    if not isinstance(value, str) or not value:
        raise BenchmarkValidationError(f'{field} must be a non-empty string')
    return value


def _as_model_ref(payload: dict[str, Any], field: str) -> str:
    value = _as_str(payload, field)
    if value.startswith(('/', '~', '$')):
        return str(Path(os.path.expandvars(value)).expanduser())
    return value


def _optional_str(payload: dict[str, Any], field: str, default: str) -> str:
    value = payload.get(field)
    if value in (None, '', (), []):
        return default
    if not isinstance(value, str):
        raise BenchmarkValidationError(f'{field} must be a string')
    return value


def _as_tuple(payload: dict[str, Any], field: str) -> tuple[str, ...]:
    value = payload[field]
    if isinstance(value, tuple) and all(isinstance(item, str) for item in value):
        return value
    if isinstance(value, str):
        return (value,)
    raise BenchmarkValidationError(f'{field} must be a list of strings')


def _optional_tuple(payload: dict[str, Any], field: str, default: tuple[str, ...]) -> tuple[str, ...]:
    if field not in payload or payload[field] in (None, '', (), []):
        return default
    return _as_tuple(payload, field)


def _as_positive_int(payload: dict[str, Any], field: str) -> int:
    value = _as_number(payload, field)
    if not value.is_integer() or value <= 0:
        raise BenchmarkValidationError(f'{field} must be a positive integer')
    return int(value)


def _optional_positive_int(payload: dict[str, Any], field: str, default: int) -> int:
    if field not in payload or payload[field] in ('', (), []):
        return default
    value = _as_positive_int(payload, field)
    return value


def _optional_int(payload: dict[str, Any], field: str, default: int) -> int:
    if field not in payload or payload[field] in ('', (), []):
        return default
    value = _as_number(payload, field)
    if not value.is_integer():
        raise BenchmarkValidationError(f'{field} must be an integer')
    return int(value)


def _optional_float(payload: dict[str, Any], field: str, default: float) -> float:
    if field not in payload or payload[field] in ('', (), []):
        return default
    return _as_number(payload, field)


def _as_number(payload: dict[str, Any], field: str) -> float:
    value = payload[field]
    if isinstance(value, bool):
        raise BenchmarkValidationError(f'{field} must be a number')
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError as exc:
            raise BenchmarkValidationError(f'{field} must be a number') from exc
    raise BenchmarkValidationError(f'{field} must be a number')


def _optional_literal(
    payload: dict[str, Any],
    field: str,
    default: str,
    valid: set[str],
    path: Path,
) -> str:
    value = _optional_str(payload, field, default)
    if value not in valid:
        allowed = ', '.join(sorted(valid))
        raise BenchmarkValidationError(f'{path} has invalid {field}: {value}; expected one of {allowed}')
    return value


def _string_sequence(value: object) -> tuple[str, ...]:
    if isinstance(value, tuple) and all(isinstance(item, str) for item in value):
        return value
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return tuple(value)
    return ()


def _resolve_path(value: str) -> Path:
    expanded = Path(os.path.expandvars(value)).expanduser()
    if expanded.is_absolute():
        return expanded
    return repo_root() / expanded


def _unique_run_root(output_root: Path, *, timestamp: datetime, experiment_id: str) -> Path:
    stem = f'{timestamp.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")}-{_safe_slug(experiment_id)}'
    root = output_root / stem
    if not root.exists():
        return root
    for index in range(2, 1000):
        candidate = output_root / f'{stem}-{index:03d}'
        if not candidate.exists():
            return candidate
    raise BenchmarkValidationError(f'Could not allocate online RL output directory under {output_root}')


def _safe_slug(value: str) -> str:
    return ''.join(character if character.isalnum() or character in {'-', '_'} else '-' for character in value).strip('-_')


def _error_text(exc: Exception) -> str:
    return str(exc)[:2000]


def _sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open('rb') as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def _write_jsonl(path: Path, records: Sequence[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records]
    path.write_text('\n'.join(lines) + ('\n' if lines else ''), encoding='utf-8')


def _append_jsonl(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + '\n')
