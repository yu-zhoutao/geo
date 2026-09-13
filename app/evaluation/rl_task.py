from __future__ import annotations

from dataclasses import dataclass
import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Awaitable, Callable

from app.evaluation.benchmarks import BenchmarkScenario, BenchmarkValidationError
from app.evaluation.rl_rewards import load_reward_table
from app.evaluation.strategy_profiles import (
    StrategyProfile,
    StrategySelection,
    StrategySource,
    load_strategy_profiles,
)


SELECT_STRATEGY_TOOL_NAME = 'select_geospatial_strategy'
INVALID_ACTION_REWARD = -0.1
SAFE_ACTION_KEYS: set[str] = {'strategy_id', 'rationale'}
OnlineRewardExecutor = Callable[[BenchmarkScenario, StrategySelection], Awaitable[dict[str, Any]]]


@dataclass(frozen=True, slots=True)
class PolicyActionResult:
    selection: StrategySelection | None
    valid: bool
    error: str | None = None
    raw_completion: str | None = None

    def as_json(self) -> dict[str, object]:
        return {
            'valid': self.valid,
            'error': self.error,
            'raw_completion': self.raw_completion,
            'selection': self.selection.as_json() if self.selection is not None else None,
        }


@dataclass(frozen=True, slots=True)
class TRLDependencyBundle:
    rloo_config: Any
    rloo_trainer: Any
    grpo_config: Any
    grpo_trainer: Any
    dataset: Any
    lora_config: Any


class StrategyRolloutBridge:
    def __init__(
        self,
        *,
        strategy_profile_root: Path | None = None,
        reward_table_path: Path | None = None,
        policy_run_id: str | None = None,
        policy_checkpoint_id: str | None = None,
        trl_run_id: str | None = None,
        training_step: int | None = None,
        strategy_source: StrategySource = 'trained-policy',
        online_executor: OnlineRewardExecutor | None = None,
    ) -> None:
        self.profiles: tuple[StrategyProfile, ...] = load_strategy_profiles(strategy_profile_root)
        self.profile_by_id: dict[str, StrategyProfile] = {profile.id: profile for profile in self.profiles}
        self.reward_table: dict[tuple[str, str], dict[str, Any]] = (
            load_reward_table(reward_table_path) if reward_table_path is not None else {}
        )
        self.policy_run_id = policy_run_id
        self.policy_checkpoint_id = policy_checkpoint_id
        self.trl_run_id = trl_run_id
        self.training_step = training_step
        self.strategy_source = strategy_source
        self.online_executor = online_executor

    def tool_schema(self) -> dict[str, object]:
        return {
            'type': 'function',
            'function': {
                'name': SELECT_STRATEGY_TOOL_NAME,
                'description': 'Select one bounded geospatial execution strategy before the real agent attempt starts.',
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'strategy_id': {
                            'type': 'string',
                            'enum': [profile.id for profile in self.profiles],
                        },
                        'rationale': {
                            'type': 'string',
                        },
                    },
                    'required': ['strategy_id'],
                },
            },
        }

    def build_policy_observation(self, scenario: BenchmarkScenario) -> dict[str, object]:
        return {
            'scenario_id': scenario.id,
            'split': scenario.split,
            'difficulty': scenario.difficulty,
            'task_family': scenario.task_family,
            'user_prompt': scenario.user_prompt,
            'dataset_pack_mode': scenario.dataset_pack_mode,
            'dataset_pack_count': len(scenario.dataset_pack),
            'hazard_categories': list(scenario.hazard_categories),
            'forbidden_moves': list(scenario.forbidden_moves),
            'available_strategies': [
                {
                    'id': profile.id,
                    'label': profile.label,
                    'focus_dimensions': list(profile.focus_dimensions),
                }
                for profile in self.profiles
            ],
        }

    def build_policy_prompt(self, scenario: BenchmarkScenario) -> str:
        observation = self.build_policy_observation(scenario)
        action_shape = {
            'strategy_id': '<one available strategy id>',
            'rationale': '<brief reason grounded in scenario risk>',
        }
        return '\n'.join(
            [
                'Select one geospatial execution strategy for the next benchmark attempt.',
                'Return only a compact JSON object with this shape:',
                json.dumps(action_shape, ensure_ascii=False),
                'Do not include markdown, XML tags, chain-of-thought, or any extra text.',
                f'Available strategy ids: {", ".join(sorted(self.profile_by_id))}.',
                'Scenario observation:',
                json.dumps(observation, ensure_ascii=False, sort_keys=True),
            ]
        )

    def validate_completion(
        self,
        completion: object,
        *,
        require_function_call: bool = False,
        require_rationale: bool = False,
    ) -> PolicyActionResult:
        payload, error, raw_completion = self._completion_payload(
            completion,
            require_function_call=require_function_call,
        )
        if payload is None:
            return PolicyActionResult(selection=None, valid=False, error=error, raw_completion=raw_completion)
        result = self.validate_action(payload, require_rationale=require_rationale)
        return PolicyActionResult(
            selection=result.selection,
            valid=result.valid,
            error=result.error,
            raw_completion=raw_completion,
        )

    def validate_action(self, payload: object, *, require_rationale: bool = False) -> PolicyActionResult:
        if not isinstance(payload, dict):
            return PolicyActionResult(selection=None, valid=False, error='strategy action must be a JSON object')
        unexpected_keys = sorted(set(payload) - SAFE_ACTION_KEYS)
        if unexpected_keys:
            return PolicyActionResult(
                selection=None,
                valid=False,
                error=f'strategy action contains unsupported keys: {", ".join(unexpected_keys)}',
            )
        strategy_id = payload.get('strategy_id')
        if not isinstance(strategy_id, str) or not strategy_id:
            return PolicyActionResult(selection=None, valid=False, error='strategy action requires strategy_id')
        rationale = payload.get('rationale')
        if rationale is not None and not isinstance(rationale, str):
            return PolicyActionResult(selection=None, valid=False, error='strategy action rationale must be a string')
        action_rationale = rationale.strip() if isinstance(rationale, str) and rationale.strip() else None
        profile = self.profile_by_id.get(strategy_id)
        if profile is None:
            return PolicyActionResult(
                selection=self._selection(
                    strategy_id=strategy_id,
                    profile_hash='unknown',
                    action_valid=False,
                    action_rationale=action_rationale,
                ),
                valid=False,
                error=f'unknown strategy_id: {strategy_id}',
            )
        if require_rationale and action_rationale is None:
            return PolicyActionResult(
                selection=self._selection(
                    strategy_id=profile.id,
                    profile_hash=profile.profile_hash,
                    action_valid=False,
                    action_rationale=None,
                ),
                valid=False,
                error='strategy action requires a non-empty rationale',
            )
        return PolicyActionResult(
            selection=self._selection(
                strategy_id=profile.id,
                profile_hash=profile.profile_hash,
                action_valid=True,
                action_rationale=action_rationale,
            ),
            valid=True,
            error=None,
        )

    async def reward_for_completion(
        self,
        scenario: BenchmarkScenario,
        completion: object,
        *,
        require_function_call: bool = False,
        require_rationale: bool = False,
    ) -> dict[str, object]:
        action = self.validate_completion(
            completion,
            require_function_call=require_function_call,
            require_rationale=require_rationale,
        )
        return await self.reward_for_action(scenario, action)

    async def reward_for_action(self, scenario: BenchmarkScenario, action: PolicyActionResult) -> dict[str, object]:
        if action.selection is None or not action.valid:
            return {
                'reward': INVALID_ACTION_REWARD,
                'reward_source': 'invalid-action',
                'action': action.as_json(),
            }
        lookup = self.reward_table.get((scenario.id, action.selection.strategy_id))
        if lookup is not None:
            return {
                'reward': float(lookup.get('reward') or 0.0),
                'reward_source': 'offline-lookup',
                'record': lookup,
                'action': action.as_json(),
            }
        if self.online_executor is None:
            raise BenchmarkValidationError(
                f'No reward table entry or online executor for {scenario.id}/{action.selection.strategy_id}'
            )
        reward = await self.online_executor(scenario, action.selection)
        return {
            'reward': float(reward.get('reward') or 0.0),
            'reward_source': str(reward.get('reward_source') or 'online-evaluation'),
            'record': reward,
            'action': action.as_json(),
        }

    def _completion_payload(
        self,
        completion: object,
        *,
        require_function_call: bool,
    ) -> tuple[dict[str, object] | None, str | None, str | None]:
        raw_completion: str | None
        parsed: object
        if isinstance(completion, str):
            raw_completion = completion
            parsed = _parse_json_mapping(completion)
            if parsed is None:
                return None, 'completion must contain a JSON object with a strategy action', raw_completion
        else:
            raw_completion = json.dumps(completion, ensure_ascii=False, sort_keys=True) if completion is not None else None
            parsed = completion
        if not isinstance(parsed, dict):
            return None, 'completion must decode to a JSON object', raw_completion
        return self._payload_from_mapping(parsed, require_function_call=require_function_call, raw_completion=raw_completion)

    def _payload_from_mapping(
        self,
        payload: dict[str, object],
        *,
        require_function_call: bool,
        raw_completion: str | None,
    ) -> tuple[dict[str, object] | None, str | None, str | None]:
        tool_calls = payload.get('tool_calls')
        if isinstance(tool_calls, list) and tool_calls:
            first_call = tool_calls[0]
            if isinstance(first_call, dict):
                function = first_call.get('function')
                if isinstance(function, dict):
                    return self._payload_from_function_call(function, raw_completion=raw_completion)
        call_name = _call_name(payload)
        if call_name is not None:
            if call_name != SELECT_STRATEGY_TOOL_NAME:
                return None, f'unexpected function call: {call_name}', raw_completion
            arguments = _call_arguments(payload)
            if arguments is None:
                return None, 'select_geospatial_strategy requires arguments', raw_completion
            return arguments, None, raw_completion
        if require_function_call:
            return None, 'completion is missing select_geospatial_strategy function call', raw_completion
        return payload, None, raw_completion

    def _payload_from_function_call(
        self,
        function: dict[str, object],
        *,
        raw_completion: str | None,
    ) -> tuple[dict[str, object] | None, str | None, str | None]:
        call_name = _call_name(function)
        if call_name != SELECT_STRATEGY_TOOL_NAME:
            return None, f'unexpected function call: {call_name}', raw_completion
        arguments = _call_arguments(function)
        if arguments is None:
            return None, 'select_geospatial_strategy requires arguments', raw_completion
        return arguments, None, raw_completion

    def _selection(
        self,
        *,
        strategy_id: str,
        profile_hash: str,
        action_valid: bool,
        action_rationale: str | None,
    ) -> StrategySelection:
        return StrategySelection(
            strategy_id=strategy_id,
            source=self.strategy_source,
            profile_hash=profile_hash,
            policy_run_id=self.policy_run_id,
            policy_checkpoint_id=self.policy_checkpoint_id,
            trl_run_id=self.trl_run_id,
            training_step=self.training_step,
            action_valid=action_valid,
            action_rationale=action_rationale,
        )


def require_trl_dependencies() -> TRLDependencyBundle:
    try:
        from datasets import Dataset
        from peft import LoraConfig
        from trl import GRPOConfig, GRPOTrainer, RLOOConfig, RLOOTrainer
    except ImportError as exc:
        raise BenchmarkValidationError(
            'TRL online training dependencies are optional and are not installed. Install the RL experiment '
            'environment with TRL, Transformers, PEFT, Accelerate, and Datasets before running real online training.'
        ) from exc
    return TRLDependencyBundle(
        rloo_config=RLOOConfig,
        rloo_trainer=RLOOTrainer,
        grpo_config=GRPOConfig,
        grpo_trainer=GRPOTrainer,
        dataset=Dataset,
        lora_config=LoraConfig,
    )


def _call_name(payload: dict[str, object]) -> str | None:
    for key in ('name', 'function', 'tool_name'):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _call_arguments(payload: dict[str, object]) -> dict[str, object] | None:
    for key in ('arguments', 'args', 'parameters'):
        value = payload.get(key)
        if isinstance(value, dict):
            return value
        if isinstance(value, str) and value:
            try:
                parsed = json.loads(value)
            except JSONDecodeError:
                return None
            return parsed if isinstance(parsed, dict) else None
    return None


def _parse_json_mapping(value: str) -> dict[str, object] | None:
    try:
        parsed = json.loads(value)
    except JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict):
        return parsed
    fragment = _first_json_object_fragment(value)
    if fragment is None:
        return None
    try:
        parsed = json.loads(fragment)
    except JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _first_json_object_fragment(value: str) -> str | None:
    start = value.find('{')
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index, character in enumerate(value[start:], start=start):
        if in_string:
            if escaped:
                escaped = False
            elif character == '\\':
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character == '{':
            depth += 1
        elif character == '}':
            depth -= 1
            if depth == 0:
                return value[start:index + 1]
    return None
