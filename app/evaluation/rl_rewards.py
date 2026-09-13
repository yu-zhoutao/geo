from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from app.evaluation.judge_rubrics import GEOSPATIAL_AGENT_RUBRIC
from app.evaluation.llm_judge import JUDGE_SCORE_FILENAME
from app.evaluation.run_bundles import RUN_MANIFEST_FILENAME, RUN_STATUS_FILENAME


REWARD_RECORD_SCHEMA = 'geo-agent.evaluation.rl-reward.v1'
REWARD_TABLE_SCHEMA = 'geo-agent.evaluation.rl-reward-table.v1'
REWARD_RECORD_FILENAME = 'rl-reward.json'
REWARD_TABLE_FILENAME = 'rl-reward-table.json'
DEFAULT_REWARD_FORMULA_ID = 'geospatial-strategy-reward-v1'
DEFAULT_DIMENSION_WEIGHTS: dict[str, float] = {
    'method_selection': 0.16,
    'data_readiness': 0.14,
    'crs_and_units': 0.18,
    'parameterization': 0.12,
    'execution_correctness': 0.14,
    'uncertainty_and_sensitivity': 0.12,
    'claim_validity': 0.14,
}
DIMENSION_IDS: set[str] = {dimension.id for dimension in GEOSPATIAL_AGENT_RUBRIC.dimensions}


@dataclass(frozen=True, slots=True)
class RewardConfig:
    formula_id: str = DEFAULT_REWARD_FORMULA_ID
    judge_rubric_id: str = GEOSPATIAL_AGENT_RUBRIC.id
    dimension_weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_DIMENSION_WEIGHTS))
    timeout_penalty: float = 0.20
    error_penalty: float = 0.05
    forbidden_move_penalty: float = 0.30
    invalid_action_penalty: float = 0.10

    def as_json(self) -> dict[str, object]:
        return {
            'formula_id': self.formula_id,
            'judge_rubric_id': self.judge_rubric_id,
            'dimension_weights': dict(sorted(self.dimension_weights.items())),
            'timeout_penalty': self.timeout_penalty,
            'error_penalty': self.error_penalty,
            'forbidden_move_penalty': self.forbidden_move_penalty,
            'invalid_action_penalty': self.invalid_action_penalty,
        }


@dataclass(frozen=True, slots=True)
class RewardRecord:
    run_id: str
    run_bundle_path: Path
    scenario_id: str
    scenario_fixture_hash: str | None
    strategy_id: str | None
    strategy_profile_hash: str | None
    reward: float
    components: dict[str, float]
    reward_source: str
    config: RewardConfig
    runtime_status: dict[str, object]
    created_at: datetime
    source_files: dict[str, str]

    def as_json(self) -> dict[str, object]:
        return {
            'schema': REWARD_RECORD_SCHEMA,
            'run_id': self.run_id,
            'run_bundle_path': str(self.run_bundle_path),
            'scenario_id': self.scenario_id,
            'scenario_fixture_hash': self.scenario_fixture_hash,
            'strategy_id': self.strategy_id,
            'strategy_profile_hash': self.strategy_profile_hash,
            'reward': self.reward,
            'components': dict(sorted(self.components.items())),
            'reward_source': self.reward_source,
            'config': self.config.as_json(),
            'runtime_status': self.runtime_status,
            'created_at': self.created_at.isoformat(),
            'source_files': self.source_files,
        }


def build_reward_record(
    run_bundle_path: Path,
    *,
    config: RewardConfig | None = None,
    reward_source: str = 'online-evaluation',
) -> RewardRecord:
    resolved_config = config or RewardConfig()
    run_manifest_path = run_bundle_path / RUN_MANIFEST_FILENAME
    run_status_path = run_bundle_path / RUN_STATUS_FILENAME
    judge_score_path = run_bundle_path / JUDGE_SCORE_FILENAME
    run_manifest: dict[str, Any] = _load_json(run_manifest_path)
    run_status: dict[str, Any] = _load_json(run_status_path, default={})
    judge_score: dict[str, Any] = _load_json(judge_score_path, default={})
    dimensions: dict[str, Any] = _object(_object(judge_score.get('parsed_score')).get('dimensions'))

    components: dict[str, float] = {}
    for dimension_id, weight in resolved_config.dimension_weights.items():
        if dimension_id not in DIMENSION_IDS:
            continue
        score = _dimension_score(dimensions, dimension_id)
        if score is None:
            continue
        components[f'dimension.{dimension_id}'] = round((score / 5.0) * weight, 6)

    if _bool(run_status.get('timed_out')):
        components['penalty.timeout'] = -resolved_config.timeout_penalty
    error_count = _nonnegative_int(run_status.get('error_count'))
    if error_count:
        components['penalty.errors'] = -round(error_count * resolved_config.error_penalty, 6)
    forbidden_move_count = _forbidden_move_count(run_status, run_manifest)
    if forbidden_move_count:
        components['penalty.forbidden_moves'] = -round(forbidden_move_count * resolved_config.forbidden_move_penalty, 6)
    strategy = _object(run_manifest.get('strategy')) or _object(run_status.get('strategy'))
    if strategy and strategy.get('action_valid') is False:
        components['penalty.invalid_action'] = -resolved_config.invalid_action_penalty

    reward = round(sum(components.values()), 6)
    scenario = _object(run_manifest.get('scenario'))
    status_reference = _object(run_manifest.get('status'))
    return RewardRecord(
        run_id=_string(run_manifest.get('run_id'), run_bundle_path.name),
        run_bundle_path=run_bundle_path,
        scenario_id=_string(scenario.get('id'), 'unknown-scenario'),
        scenario_fixture_hash=_optional_string(scenario.get('fixture_hash')),
        strategy_id=_optional_string(strategy.get('strategy_id')) if strategy else None,
        strategy_profile_hash=_optional_string(strategy.get('profile_hash')) if strategy else None,
        reward=reward,
        components=components,
        reward_source=reward_source,
        config=resolved_config,
        runtime_status={
            'session_status': _string(
                run_status.get('session_status') or status_reference.get('session_status'),
                'unknown',
            ),
            'terminal_reason': _string(
                run_status.get('terminal_reason') or status_reference.get('terminal_reason'),
                'unknown',
            ),
            'timed_out': _bool(run_status.get('timed_out') or status_reference.get('timed_out')),
            'error_count': error_count,
        },
        created_at=datetime.now(UTC),
        source_files={
            'run_manifest': RUN_MANIFEST_FILENAME,
            'run_status': RUN_STATUS_FILENAME,
            'judge_score': JUDGE_SCORE_FILENAME,
        },
    )


def write_reward_record(
    run_bundle_path: Path,
    *,
    config: RewardConfig | None = None,
    reward_source: str = 'online-evaluation',
) -> Path:
    record = build_reward_record(run_bundle_path, config=config, reward_source=reward_source)
    output_path = run_bundle_path / REWARD_RECORD_FILENAME
    _write_json(output_path, record.as_json())
    return output_path


def write_reward_table(
    run_bundle_paths: list[Path],
    output_path: Path,
    *,
    config: RewardConfig | None = None,
    reward_source: str = 'offline-sweep',
) -> dict[str, object]:
    records: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    for run_bundle_path in run_bundle_paths:
        try:
            record = build_reward_record(run_bundle_path, config=config, reward_source=reward_source)
            records.append(record.as_json())
        except Exception as exc:
            failures.append(
                {
                    'run_bundle_path': str(run_bundle_path),
                    'error_type': type(exc).__name__,
                    'error': str(exc),
                }
            )
    payload: dict[str, object] = {
        'schema': REWARD_TABLE_SCHEMA,
        'created_at': datetime.now(UTC).isoformat(),
        'reward_config': (config or RewardConfig()).as_json(),
        'record_count': len(records),
        'failure_count': len(failures),
        'records': records,
        'failures': failures,
    }
    _write_json(output_path, payload)
    return payload


def load_reward_table(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    payload: dict[str, Any] = _load_json(path)
    table: dict[tuple[str, str], dict[str, Any]] = {}
    records = payload.get('records')
    if not isinstance(records, list):
        return table
    for item in records:
        if not isinstance(item, dict):
            continue
        scenario_id = item.get('scenario_id')
        strategy_id = item.get('strategy_id')
        if isinstance(scenario_id, str) and isinstance(strategy_id, str):
            table[(scenario_id, strategy_id)] = item
    return table


def _dimension_score(dimensions: dict[str, Any], dimension_id: str) -> int | None:
    value = _object(dimensions.get(dimension_id))
    score = value.get('score')
    if isinstance(score, int) and not isinstance(score, bool) and 1 <= score <= 5:
        return score
    return None


def _forbidden_move_count(run_status: dict[str, Any], run_manifest: dict[str, Any]) -> int:
    explicit = run_status.get('forbidden_move_count')
    if isinstance(explicit, int) and not isinstance(explicit, bool) and explicit >= 0:
        return explicit
    for payload in (run_status, run_manifest):
        moves = payload.get('forbidden_moves')
        if isinstance(moves, list):
            return len([move for move in moves if isinstance(move, str) and move])
    return 0


def _load_json(path: Path, *, default: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        if default is not None:
            return default
        raise
    if not isinstance(payload, dict):
        return default or {}
    return payload


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def _object(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _bool(value: object) -> bool:
    return value if isinstance(value, bool) else False


def _nonnegative_int(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 0


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _string(value: object, default: str) -> str:
    return value if isinstance(value, str) and value else default
