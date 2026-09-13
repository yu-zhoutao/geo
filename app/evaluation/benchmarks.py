from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


Split = Literal['dev', 'test', 'stress']
Difficulty = Literal['L1', 'L2', 'L3']
TaskFamily = Literal['kde', 'spatial_interpolation', 'spatial_hotspot', 'unsupported-future-family', 'reporting-review']
ControlState = Literal['proceed', 'clarify', 'repair', 'stop']
DatasetPackMode = Literal['synthetic', 'repo-files']
ClarificationAnswerPolicy = Literal['stop-at-question', 'answer-once']

VALID_SPLITS: set[str] = {'dev', 'test', 'stress'}
VALID_DIFFICULTIES: set[str] = {'L1', 'L2', 'L3'}
VALID_TASK_FAMILIES: set[str] = {
    'kde',
    'spatial_interpolation',
    'spatial_hotspot',
    'unsupported-future-family',
    'reporting-review',
}
VALID_CONTROL_STATES: set[str] = {'proceed', 'clarify', 'repair', 'stop'}
VALID_DATASET_PACK_MODES: set[str] = {'synthetic', 'repo-files'}
VALID_CLARIFICATION_ANSWER_POLICIES: set[str] = {'stop-at-question', 'answer-once'}
REQUIRED_SCENARIO_FIELDS: tuple[str, ...] = (
    'id',
    'split',
    'difficulty',
    'task_family',
    'gold_control_state',
    'user_prompt',
    'dataset_root',
    'dataset_pack_mode',
    'dataset_pack',
    'forbidden_moves',
    'oracle_id',
    'judge_rubric',
    'scoring_weight',
    'subset_tags',
    'hazard_categories',
)


class BenchmarkValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class BenchmarkScenario:
    id: str
    path: Path
    split: Split
    difficulty: Difficulty
    task_family: TaskFamily
    gold_control_state: ControlState
    user_prompt: str
    dataset_root: str
    dataset_pack_mode: DatasetPackMode
    dataset_pack: tuple[str, ...]
    required_artifacts: tuple[str, ...]
    forbidden_moves: tuple[str, ...]
    oracle_id: str
    deterministic_checks: tuple[str, ...]
    judge_rubric: str
    scoring_weight: float
    subset_tags: tuple[str, ...]
    hazard_categories: tuple[str, ...]
    clarification_answer_policy: ClarificationAnswerPolicy = 'stop-at-question'
    clarification_answers: tuple[str, ...] = ()
    required_claim_terms: tuple[str, ...] = ()
    forbidden_claim_terms: tuple[str, ...] = ()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_benchmark_root() -> Path:
    return repo_root() / 'app' / 'agent_assets' / 'benchmarks'


def load_benchmark_scenarios(benchmark_root: Path | None = None) -> list[BenchmarkScenario]:
    root: Path = benchmark_root or default_benchmark_root()
    scenarios: list[BenchmarkScenario] = [
        load_benchmark_scenario(path)
        for path in scenario_paths(root)
    ]
    return scenarios


def validate_benchmark_suite(benchmark_root: Path | None = None) -> list[BenchmarkScenario]:
    root: Path = benchmark_root or default_benchmark_root()
    scenarios: list[BenchmarkScenario] = load_benchmark_scenarios(root)
    seen_ids: set[str] = set()
    for scenario in scenarios:
        if scenario.id in seen_ids:
            raise BenchmarkValidationError(f'Duplicate benchmark scenario id: {scenario.id}')
        seen_ids.add(scenario.id)
        validate_benchmark_scenario(scenario)
    validate_representative_subsets(scenarios)
    return scenarios


def validate_benchmark_scenario(scenario: BenchmarkScenario) -> None:
    if scenario.split not in VALID_SPLITS:
        raise BenchmarkValidationError(f'{scenario.path} has invalid split: {scenario.split}')
    if scenario.difficulty not in VALID_DIFFICULTIES:
        raise BenchmarkValidationError(f'{scenario.path} has invalid difficulty: {scenario.difficulty}')
    if scenario.task_family not in VALID_TASK_FAMILIES:
        raise BenchmarkValidationError(f'{scenario.path} has invalid task family: {scenario.task_family}')
    if scenario.gold_control_state not in VALID_CONTROL_STATES:
        raise BenchmarkValidationError(f'{scenario.path} has invalid control state: {scenario.gold_control_state}')
    if scenario.dataset_pack_mode not in VALID_DATASET_PACK_MODES:
        raise BenchmarkValidationError(f'{scenario.path} has invalid dataset pack mode: {scenario.dataset_pack_mode}')
    if not scenario.dataset_pack:
        raise BenchmarkValidationError(f'{scenario.path} has no dataset pack references')
    if not scenario.oracle_id:
        raise BenchmarkValidationError(f'{scenario.path} has no oracle id')
    if not scenario.judge_rubric:
        raise BenchmarkValidationError(f'{scenario.path} has no judge rubric')
    if scenario.scoring_weight <= 0:
        raise BenchmarkValidationError(f'{scenario.path} has non-positive scoring weight')
    if 'full-suite' not in scenario.subset_tags:
        raise BenchmarkValidationError(f'{scenario.path} is missing the full-suite subset tag')
    if not scenario.hazard_categories:
        raise BenchmarkValidationError(f'{scenario.path} has no hazard categories')
    if scenario.dataset_pack_mode == 'repo-files':
        validate_dataset_pack_files(scenario)
    if scenario.clarification_answer_policy == 'answer-once' and not scenario.clarification_answers:
        raise BenchmarkValidationError(f'{scenario.path} defines answer-once without clarification answers')


def validate_dataset_pack_files(scenario: BenchmarkScenario) -> None:
    dataset_root: Path = Path(scenario.dataset_root)
    if not dataset_root.is_absolute():
        dataset_root = repo_root() / dataset_root
    for item in scenario.dataset_pack:
        candidate: Path = dataset_root / item
        if not candidate.exists():
            raise BenchmarkValidationError(f'{scenario.path} references missing dataset pack file: {candidate}')


def validate_representative_subsets(scenarios: list[BenchmarkScenario]) -> None:
    ablation: list[BenchmarkScenario] = [
        scenario for scenario in scenarios
        if 'ablation-representative' in scenario.subset_tags
    ]
    if not ablation:
        raise BenchmarkValidationError('No ablation-representative benchmark scenarios are defined')

    control_states: set[str] = {scenario.gold_control_state for scenario in ablation}
    missing_states: set[str] = VALID_CONTROL_STATES - control_states
    if missing_states:
        missing: str = ', '.join(sorted(missing_states))
        raise BenchmarkValidationError(f'Ablation subset is missing control states: {missing}')

    if not any(scenario.split == 'stress' for scenario in ablation):
        raise BenchmarkValidationError('Ablation subset has no stress scenario')
    if not any(scenario.task_family == 'reporting-review' for scenario in ablation):
        raise BenchmarkValidationError('Ablation subset has no reporting-review scenario')
    if not any(scenario.task_family == 'spatial_interpolation' for scenario in ablation):
        raise BenchmarkValidationError('Ablation subset has no spatial_interpolation scenario')
    if not any(scenario.task_family == 'spatial_hotspot' for scenario in ablation):
        raise BenchmarkValidationError('Ablation subset has no spatial_hotspot scenario')
    if not any(_has_hazard(scenario, 'crs') or _has_hazard(scenario, 'area-of-use') for scenario in ablation):
        raise BenchmarkValidationError('Ablation subset has no CRS or unit hazard scenario')
    if not any(_has_hazard(scenario, 'study-area') or _has_hazard(scenario, 'overlap') for scenario in ablation):
        raise BenchmarkValidationError('Ablation subset has no study-area or overlap hazard scenario')
    if not any(_has_hazard(scenario, 'unsupported') for scenario in ablation):
        raise BenchmarkValidationError('Ablation subset has no unsupported-family hazard scenario')


def scenario_paths(benchmark_root: Path) -> list[Path]:
    paths: list[Path] = [
        *sorted((benchmark_root / 'core').glob('*.yaml')),
        *sorted((benchmark_root / 'stress').glob('*.yaml')),
    ]
    return paths


def load_benchmark_scenario(path: Path) -> BenchmarkScenario:
    payload: dict[str, Any] = load_simple_yaml(path)
    missing_fields: list[str] = [
        field for field in REQUIRED_SCENARIO_FIELDS
        if field not in payload or _is_missing_value(payload[field])
    ]
    if missing_fields:
        missing: str = ', '.join(missing_fields)
        raise BenchmarkValidationError(f'{path} is missing required fields: {missing}')

    return BenchmarkScenario(
        id=_as_str(payload, 'id'),
        path=path,
        split=_as_literal(_as_str(payload, 'split'), VALID_SPLITS, 'split', path),  # type: ignore[arg-type]
        difficulty=_as_literal(_as_str(payload, 'difficulty'), VALID_DIFFICULTIES, 'difficulty', path),  # type: ignore[arg-type]
        task_family=_as_literal(_as_str(payload, 'task_family'), VALID_TASK_FAMILIES, 'task_family', path),  # type: ignore[arg-type]
        gold_control_state=_as_literal(_as_str(payload, 'gold_control_state'), VALID_CONTROL_STATES, 'gold_control_state', path),  # type: ignore[arg-type]
        user_prompt=_as_str(payload, 'user_prompt'),
        dataset_root=_as_str(payload, 'dataset_root'),
        dataset_pack_mode=_as_literal(_as_str(payload, 'dataset_pack_mode'), VALID_DATASET_PACK_MODES, 'dataset_pack_mode', path),  # type: ignore[arg-type]
        dataset_pack=_as_tuple(payload, 'dataset_pack'),
        required_artifacts=_optional_tuple(payload, 'required_artifacts'),
        forbidden_moves=_as_tuple(payload, 'forbidden_moves'),
        oracle_id=_as_str(payload, 'oracle_id'),
        deterministic_checks=_optional_tuple(payload, 'deterministic_checks'),
        judge_rubric=_as_str(payload, 'judge_rubric'),
        scoring_weight=_as_float(payload, 'scoring_weight'),
        subset_tags=_as_tuple(payload, 'subset_tags'),
        hazard_categories=_as_tuple(payload, 'hazard_categories'),
        clarification_answer_policy=_as_optional_literal(
            payload,
            'clarification_answer_policy',
            'stop-at-question',
            VALID_CLARIFICATION_ANSWER_POLICIES,
            path,
        ),  # type: ignore[arg-type]
        clarification_answers=_optional_tuple(payload, 'clarification_answers'),
        required_claim_terms=_optional_tuple(payload, 'required_claim_terms'),
        forbidden_claim_terms=_optional_tuple(payload, 'forbidden_claim_terms'),
    )


def load_simple_yaml(path: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    current_list_key: str | None = None
    current_list_values: list[str] = []
    current_block_key: str | None = None
    current_block_lines: list[str] = []

    def commit_list() -> None:
        nonlocal current_list_key, current_list_values
        if current_list_key is not None:
            payload[current_list_key] = tuple(current_list_values)
            current_list_key = None
            current_list_values = []

    def commit_block() -> None:
        nonlocal current_block_key, current_block_lines
        if current_block_key is not None:
            payload[current_block_key] = '\n'.join(current_block_lines).strip()
            current_block_key = None
            current_block_lines = []

    for raw in path.read_text(encoding='utf-8').splitlines():
        if current_block_key is not None and (raw.startswith(' ') or not raw.strip()):
            current_block_lines.append(raw[2:] if raw.startswith('  ') else raw)
            continue
        if current_block_key is not None:
            commit_block()
        if raw.startswith('  - ') and current_list_key is not None:
            current_list_values.append(raw[4:].strip())
            continue
        if raw.startswith(' ') or not raw.strip() or ':' not in raw:
            continue
        commit_list()
        key, value = raw.split(':', 1)
        field: str = key.strip()
        raw_value: str = value.strip()
        if raw_value == '|':
            current_block_key = field
            current_block_lines = []
        elif raw_value == '':
            current_list_key = field
            current_list_values = []
        else:
            payload[field] = parse_scalar(raw_value)

    commit_block()
    commit_list()
    return payload


def parse_scalar(raw_value: str) -> str | tuple[str, ...] | float:
    if raw_value.startswith('[') and raw_value.endswith(']'):
        content: str = raw_value[1:-1].strip()
        if not content:
            return ()
        return tuple(item.strip() for item in content.split(',') if item.strip())
    try:
        return float(raw_value)
    except ValueError:
        return raw_value


def _as_str(payload: dict[str, Any], field: str) -> str:
    value: Any = payload[field]
    if not isinstance(value, str):
        raise BenchmarkValidationError(f'{field} must be a string')
    return value


def _as_tuple(payload: dict[str, Any], field: str) -> tuple[str, ...]:
    value: Any = payload[field]
    if isinstance(value, tuple) and all(isinstance(item, str) for item in value):
        return value
    if isinstance(value, str):
        return (value,)
    raise BenchmarkValidationError(f'{field} must be a list of strings')


def _as_float(payload: dict[str, Any], field: str) -> float:
    value: Any = payload[field]
    if isinstance(value, float):
        return value
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError as exc:
            raise BenchmarkValidationError(f'{field} must be a number') from exc
    raise BenchmarkValidationError(f'{field} must be a number')


def _as_literal(value: str, valid: set[str], field: str, path: Path) -> Any:
    if value not in valid:
        allowed: str = ', '.join(sorted(valid))
        raise BenchmarkValidationError(f'{path} has invalid {field}: {value}; expected one of {allowed}')
    return value


def _as_optional_literal(
    payload: dict[str, Any],
    field: str,
    default: str,
    valid: set[str],
    path: Path,
) -> Any:
    if field not in payload or _is_missing_value(payload[field]):
        return default
    return _as_literal(_as_str(payload, field), valid, field, path)


def _optional_tuple(payload: dict[str, Any], field: str) -> tuple[str, ...]:
    if field not in payload or _is_missing_value(payload[field]):
        return ()
    return _as_tuple(payload, field)


def _has_hazard(scenario: BenchmarkScenario, needle: str) -> bool:
    return any(needle in category for category in scenario.hazard_categories)


def _is_missing_value(value: Any) -> bool:
    return value == '' or value == () or value == []
