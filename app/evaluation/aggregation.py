from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import csv
import json
from pathlib import Path
from typing import Any, Iterable

from app.evaluation.judge_rubrics import GEOSPATIAL_AGENT_RUBRIC
from app.evaluation.llm_judge import JUDGE_SCORE_FILENAME
from app.evaluation.rl_rewards import REWARD_RECORD_FILENAME
from app.evaluation.run_bundles import RUN_MANIFEST_FILENAME, RUN_STATUS_FILENAME


CAMPAIGN_AGGREGATE_SCHEMA = 'geo-agent.evaluation.dimension-score-summary.v1'
CAMPAIGN_SUMMARY_FILENAME = 'campaign-summary.json'
RUN_SCORES_FILENAME = 'run-scores.csv'
VARIANT_DIMENSION_SCORES_FILENAME = 'variant-dimension-scores.csv'
SCENARIO_DIMENSION_SCORES_FILENAME = 'scenario-dimension-scores.csv'
VARIANT_SCENARIO_SCORES_FILENAME = 'variant-scenario-scores.csv'
THESIS_SUMMARY_FILENAME = 'thesis-summary.md'
RL_STRATEGY_SUMMARY_FILENAME = 'rl-strategy-summary.json'
RL_THESIS_PACKET_FILENAME = 'rl-thesis-evidence.md'
EXPORT_DIRNAME = 'exports'
DIMENSION_IDS: tuple[str, ...] = tuple(dimension.id for dimension in GEOSPATIAL_AGENT_RUBRIC.dimensions)


@dataclass(frozen=True, slots=True)
class RunRecord:
    run_id: str
    bundle_path: Path
    variant_id: str
    variant_label: str | None
    variant_kind: str | None
    scenario_id: str
    scenario_fixture_path: str | None
    split: str
    difficulty: str
    task_family: str
    gold_control_state: str
    hazard_categories: tuple[str, ...]
    dimension_scores: dict[str, int]
    dimension_reasons: dict[str, str]
    judge_status: str
    judge_summary: str | None
    judge_model: str | None
    judged_at: str | None
    judge_attempt_count: int
    judge_error_count: int
    session_status: str
    terminal_reason: str
    timed_out: bool | None
    duration_seconds: float | None
    continuation_count: int
    error_count: int
    errors: tuple[str, ...]
    evidence_pack_path: str | None
    evidence_manifest_hash: str | None
    external_evidence_file: str | None
    judge_score_path: str | None
    strategy_id: str | None
    strategy_source: str | None
    strategy_profile_hash: str | None
    policy_run_id: str | None
    policy_checkpoint_id: str | None
    trl_run_id: str | None
    training_step: int | None
    strategy_action_valid: bool | None
    reward: float | None
    reward_source: str | None
    reward_components: dict[str, float]


def aggregate_campaign(campaign_root: Path, *, export_root: Path | None = None) -> dict[str, object]:
    records: list[RunRecord] = load_run_records(campaign_root)
    root: Path = export_root or campaign_root / EXPORT_DIRNAME
    root.mkdir(parents=True, exist_ok=True)
    summary: dict[str, object] = {
        'schema': CAMPAIGN_AGGREGATE_SCHEMA,
        'campaign_root': str(campaign_root),
        'run_count': len(records),
        'scored_run_count': _scored_count(records),
        'dimension_ids': list(DIMENSION_IDS),
        'per_run': [_record_json(record, campaign_root) for record in records],
        'per_scenario': _group_summaries(records, ('scenario_id',)),
        'per_variant': _group_summaries(records, ('variant_id',)),
        'per_task_family': _group_summaries(records, ('task_family',)),
        'per_split': _group_summaries(records, ('split',)),
        'per_control_state': _group_summaries(records, ('gold_control_state',)),
        'per_difficulty': _group_summaries(records, ('difficulty',)),
        'per_variant_scenario': _group_summaries(records, ('variant_id', 'scenario_id')),
        'per_variant_control_state': _group_summaries(records, ('variant_id', 'gold_control_state')),
        'per_risk_category': _risk_category_summaries(records),
    }
    _write_json(root / CAMPAIGN_SUMMARY_FILENAME, summary)
    _write_csv(root / RUN_SCORES_FILENAME, _run_score_rows(records, campaign_root))
    _write_csv(root / VARIANT_DIMENSION_SCORES_FILENAME, _group_summaries(records, ('variant_id',)))
    _write_csv(root / SCENARIO_DIMENSION_SCORES_FILENAME, _group_summaries(records, ('scenario_id',)))
    _write_csv(root / VARIANT_SCENARIO_SCORES_FILENAME, _group_summaries(records, ('variant_id', 'scenario_id')))
    rl_summary = _rl_strategy_summary(records, campaign_root)
    if rl_summary is not None:
        summary['rl_strategy_experiment'] = rl_summary
        _write_json(root / RL_STRATEGY_SUMMARY_FILENAME, rl_summary)
        _write_rl_markdown(root / RL_THESIS_PACKET_FILENAME, rl_summary)
    _write_markdown(root / THESIS_SUMMARY_FILENAME, summary)
    return summary


def load_run_records(campaign_root: Path) -> list[RunRecord]:
    records: list[RunRecord] = []
    for manifest_path in sorted((campaign_root / 'runs').glob('**/' + RUN_MANIFEST_FILENAME)):
        bundle_path: Path = manifest_path.parent
        run_manifest: dict[str, Any] = _load_json(manifest_path)
        run_status: dict[str, Any] = _load_json(bundle_path / RUN_STATUS_FILENAME, default={})
        judge_score_path: Path = bundle_path / JUDGE_SCORE_FILENAME
        judge_score: dict[str, Any] = _load_json(judge_score_path, default={})
        reward_record: dict[str, Any] = _load_json(bundle_path / REWARD_RECORD_FILENAME, default={})
        parsed_score: dict[str, Any] = _object(judge_score.get('parsed_score'))
        dimensions: dict[str, Any] = _object(parsed_score.get('dimensions'))
        scenario: dict[str, Any] = _object(run_manifest.get('scenario'))
        variant: dict[str, Any] = _object(run_manifest.get('variant'))
        external_evidence: dict[str, Any] = _object(run_manifest.get('external_evidence'))
        strategy: dict[str, Any] = _object(run_manifest.get('strategy')) or _object(run_status.get('strategy'))
        records.append(
            RunRecord(
                run_id=_string(run_manifest.get('run_id'), bundle_path.name),
                bundle_path=bundle_path,
                variant_id=_string(variant.get('id'), 'unknown-variant'),
                variant_label=_optional_string(variant.get('label')),
                variant_kind=_optional_string(variant.get('kind')),
                scenario_id=_string(scenario.get('id'), 'unknown-scenario'),
                scenario_fixture_path=_optional_string(scenario.get('fixture_path')),
                split=_string(scenario.get('split'), 'unknown-split'),
                difficulty=_string(scenario.get('difficulty'), 'unknown-difficulty'),
                task_family=_string(scenario.get('task_family'), 'unknown-family'),
                gold_control_state=_string(scenario.get('gold_control_state'), 'unknown-control-state'),
                hazard_categories=_string_tuple(scenario.get('hazard_categories')),
                dimension_scores=_dimension_scores(dimensions),
                dimension_reasons=_dimension_reasons(dimensions),
                judge_status=_judge_status(judge_score_path, dimensions),
                judge_summary=_optional_string(parsed_score.get('summary')),
                judge_model=_optional_string(judge_score.get('model')),
                judged_at=_optional_string(judge_score.get('judged_at')),
                judge_attempt_count=len(_object_list(judge_score.get('attempts'))),
                judge_error_count=_judge_error_count(judge_score),
                session_status=_string(run_status.get('session_status'), 'unknown'),
                terminal_reason=_string(run_status.get('terminal_reason'), 'unknown'),
                timed_out=_optional_bool(run_status.get('timed_out')),
                duration_seconds=_optional_float(run_status.get('duration_seconds')),
                continuation_count=_nonnegative_int(run_status.get('continuation_count')),
                error_count=_nonnegative_int(run_status.get('error_count')),
                errors=_string_tuple(run_status.get('errors')),
                evidence_pack_path=_optional_string(external_evidence.get('pack_path')),
                evidence_manifest_hash=_optional_string(external_evidence.get('manifest_hash')),
                external_evidence_file=_optional_string(external_evidence.get('path') or external_evidence.get('file')),
                judge_score_path=(
                    _relative_or_absolute(judge_score_path, campaign_root)
                    if judge_score_path.exists()
                    else None
                ),
                strategy_id=_optional_string(strategy.get('strategy_id')),
                strategy_source=_optional_string(strategy.get('source')),
                strategy_profile_hash=_optional_string(strategy.get('profile_hash')),
                policy_run_id=_optional_string(strategy.get('policy_run_id')),
                policy_checkpoint_id=_optional_string(strategy.get('policy_checkpoint_id')),
                trl_run_id=_optional_string(strategy.get('trl_run_id')),
                training_step=_optional_int(strategy.get('training_step')),
                strategy_action_valid=_optional_bool(strategy.get('action_valid')),
                reward=_optional_float(reward_record.get('reward')),
                reward_source=_optional_string(reward_record.get('reward_source')),
                reward_components=_float_mapping(reward_record.get('components')),
            )
        )
    return records


def _record_json(record: RunRecord, campaign_root: Path) -> dict[str, object]:
    return {
        'run_id': record.run_id,
        'bundle_path': _relative_or_absolute(record.bundle_path, campaign_root),
        'variant_id': record.variant_id,
        'variant_label': record.variant_label,
        'variant_kind': record.variant_kind,
        'scenario_id': record.scenario_id,
        'scenario_fixture_path': record.scenario_fixture_path,
        'split': record.split,
        'difficulty': record.difficulty,
        'task_family': record.task_family,
        'gold_control_state': record.gold_control_state,
        'hazard_categories': list(record.hazard_categories),
        'judge_status': record.judge_status,
        'judge_summary': record.judge_summary,
        'judge_model': record.judge_model,
        'judged_at': record.judged_at,
        'judge_attempt_count': record.judge_attempt_count,
        'judge_error_count': record.judge_error_count,
        'dimension_scores': {
            dimension_id: record.dimension_scores[dimension_id]
            for dimension_id in DIMENSION_IDS
            if dimension_id in record.dimension_scores
        },
        'dimension_reasons': {
            dimension_id: record.dimension_reasons[dimension_id]
            for dimension_id in DIMENSION_IDS
            if dimension_id in record.dimension_reasons
        },
        'average_score': _record_average(record),
        'session_status': record.session_status,
        'terminal_reason': record.terminal_reason,
        'timed_out': record.timed_out,
        'duration_seconds': record.duration_seconds,
        'continuation_count': record.continuation_count,
        'error_count': record.error_count,
        'errors': list(record.errors),
        'evidence_pack_path': record.evidence_pack_path,
        'evidence_manifest_hash': record.evidence_manifest_hash,
        'external_evidence_file': record.external_evidence_file,
        'judge_score_path': record.judge_score_path,
        'strategy_id': record.strategy_id,
        'strategy_source': record.strategy_source,
        'strategy_profile_hash': record.strategy_profile_hash,
        'policy_run_id': record.policy_run_id,
        'policy_checkpoint_id': record.policy_checkpoint_id,
        'trl_run_id': record.trl_run_id,
        'training_step': record.training_step,
        'strategy_action_valid': record.strategy_action_valid,
        'reward': record.reward,
        'reward_source': record.reward_source,
        'reward_components': record.reward_components,
    }


def _run_score_rows(records: list[RunRecord], campaign_root: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for record in records:
        row: dict[str, object] = {
            'run_id': record.run_id,
            'bundle_path': _relative_or_absolute(record.bundle_path, campaign_root),
            'variant_id': record.variant_id,
            'variant_label': record.variant_label,
            'variant_kind': record.variant_kind,
            'scenario_id': record.scenario_id,
            'scenario_fixture_path': record.scenario_fixture_path,
            'split': record.split,
            'difficulty': record.difficulty,
            'task_family': record.task_family,
            'gold_control_state': record.gold_control_state,
            'hazard_categories': '; '.join(record.hazard_categories),
            'judge_status': record.judge_status,
            'average_score': _record_average(record),
            'judge_model': record.judge_model,
            'judged_at': record.judged_at,
            'judge_attempt_count': record.judge_attempt_count,
            'judge_error_count': record.judge_error_count,
            'session_status': record.session_status,
            'terminal_reason': record.terminal_reason,
            'timed_out': record.timed_out,
            'duration_seconds': record.duration_seconds,
            'continuation_count': record.continuation_count,
            'error_count': record.error_count,
            'errors': '; '.join(record.errors),
            'evidence_pack_path': record.evidence_pack_path,
            'evidence_manifest_hash': record.evidence_manifest_hash,
            'external_evidence_file': record.external_evidence_file,
            'judge_score_path': record.judge_score_path,
            'strategy_id': record.strategy_id,
            'strategy_source': record.strategy_source,
            'strategy_profile_hash': record.strategy_profile_hash,
            'policy_run_id': record.policy_run_id,
            'policy_checkpoint_id': record.policy_checkpoint_id,
            'trl_run_id': record.trl_run_id,
            'training_step': record.training_step,
            'strategy_action_valid': record.strategy_action_valid,
            'reward': record.reward,
            'reward_source': record.reward_source,
        }
        for dimension_id in DIMENSION_IDS:
            row[f'{dimension_id}_score'] = record.dimension_scores.get(dimension_id)
            row[f'{dimension_id}_reason'] = record.dimension_reasons.get(dimension_id)
        rows.append(row)
    return rows


def _group_summaries(records: list[RunRecord], keys: tuple[str, ...]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, ...], list[RunRecord]] = defaultdict(list)
    for record in records:
        grouped[tuple(str(getattr(record, key)) for key in keys)].append(record)
    rows: list[dict[str, object]] = []
    for group_key, items in sorted(grouped.items()):
        row: dict[str, object] = {
            **{key: group_key[index] for index, key in enumerate(keys)},
            'run_count': len(items),
            'scored_run_count': _scored_count(items),
            'average_score': _mean(_record_average(record) for record in items),
            'average_reward': _mean(record.reward for record in items),
        }
        if 'variant_id' in keys:
            row['variant_label'] = _common_optional_string(record.variant_label for record in items)
            row['variant_kind'] = _common_optional_string(record.variant_kind for record in items)
        for dimension_id in DIMENSION_IDS:
            row[f'{dimension_id}_average'] = _mean(
                record.dimension_scores.get(dimension_id)
                for record in items
                if record.judge_status == 'scored'
            )
        rows.append(row)
    return rows


def _risk_category_summaries(records: list[RunRecord]) -> list[dict[str, object]]:
    grouped: dict[str, list[RunRecord]] = defaultdict(list)
    for record in records:
        categories: tuple[str, ...] = record.hazard_categories or ('unknown-risk-category',)
        for category in categories:
            grouped[category].append(record)
    rows: list[dict[str, object]] = []
    for category, items in sorted(grouped.items()):
        row: dict[str, object] = {
            'risk_category': category,
            'run_count': len(items),
            'scored_run_count': _scored_count(items),
            'average_score': _mean(_record_average(record) for record in items),
            'average_reward': _mean(record.reward for record in items),
        }
        for dimension_id in DIMENSION_IDS:
            row[f'{dimension_id}_average'] = _mean(
                record.dimension_scores.get(dimension_id)
                for record in items
                if record.judge_status == 'scored'
            )
        rows.append(row)
    return rows


def _rl_strategy_summary(records: list[RunRecord], campaign_root: Path) -> dict[str, object] | None:
    strategy_records: list[RunRecord] = [record for record in records if record.strategy_id is not None]
    if not strategy_records:
        return None
    return {
        'schema': 'geo-agent.evaluation.rl-strategy-summary.v1',
        'campaign_root': str(campaign_root),
        'run_count': len(strategy_records),
        'scored_run_count': _scored_count(strategy_records),
        'rewarded_run_count': sum(1 for record in strategy_records if record.reward is not None),
        'interpretation_boundary': (
            'This summary describes a strategy-controller experiment around the existing geospatial multi-agent '
            'system. It is not evidence of end-to-end training of a general geospatial analysis model.'
        ),
        'per_run': [_record_json(record, campaign_root) for record in strategy_records],
        'per_strategy': _group_summaries(strategy_records, ('strategy_id',)),
        'per_policy_checkpoint': _group_summaries(strategy_records, ('policy_run_id',)),
        'per_lora_checkpoint': _group_summaries(strategy_records, ('policy_checkpoint_id',)),
        'per_task_family': _group_summaries(strategy_records, ('task_family',)),
        'per_control_state': _group_summaries(strategy_records, ('gold_control_state',)),
        'per_split': _group_summaries(strategy_records, ('split',)),
        'per_difficulty': _group_summaries(strategy_records, ('difficulty',)),
        'per_risk_category': _risk_category_summaries(strategy_records),
        'online_training': _online_training_summary(strategy_records, campaign_root),
        'limitations': [
            'Scenario counts may be small for reinforcement learning conclusions.',
            'Reward values depend on the configured judge rubric and reward weights.',
            'Strategy profiles adjust guidance emphasis; they do not train the geospatial runtime itself.',
            'Negative and mixed results should be reported alongside aggregate improvements.',
        ],
        'failure_cases': [
            _record_json(record, campaign_root)
            for record in strategy_records
            if record.judge_status != 'scored' or record.error_count > 0 or (record.reward is not None and record.reward < 0)
        ],
    }


def _online_training_summary(records: list[RunRecord], campaign_root: Path) -> dict[str, object]:
    online_records: list[RunRecord] = [
        record for record in records
        if record.trl_run_id is not None
        or record.reward_source in {'online-trl-training', 'mock-online-trl-training'}
    ]
    invalid_count = sum(1 for record in online_records if record.strategy_action_valid is False)
    strategy_counts: dict[str, int] = defaultdict(int)
    for record in online_records:
        if record.strategy_id is not None:
            strategy_counts[record.strategy_id] += 1
    return {
        'episode_count': len(online_records),
        'invalid_action_count': invalid_count,
        'invalid_action_rate': round(invalid_count / len(online_records), 6) if online_records else 0.0,
        'checkpoint_ids': sorted(
            {
                record.policy_checkpoint_id
                for record in online_records
                if record.policy_checkpoint_id is not None
            }
        ),
        'trl_run_ids': sorted({record.trl_run_id for record in online_records if record.trl_run_id is not None}),
        'strategy_distribution': dict(sorted(strategy_counts.items())),
        'reward_trajectory': [
            {
                'run_id': record.run_id,
                'training_step': record.training_step,
                'reward': record.reward,
                'run_bundle_path': _relative_or_absolute(record.bundle_path, campaign_root),
            }
            for record in sorted(online_records, key=lambda item: (item.training_step is None, item.training_step or 0))
        ],
    }


def _scored_count(records: Iterable[RunRecord]) -> int:
    return sum(1 for record in records if record.judge_status == 'scored')


def _record_average(record: RunRecord) -> float | None:
    if record.judge_status != 'scored':
        return None
    return _mean(record.dimension_scores.get(dimension_id) for dimension_id in DIMENSION_IDS)


def _mean(values: Iterable[float | int | None]) -> float | None:
    resolved: list[float] = [float(value) for value in values if value is not None]
    if not resolved:
        return None
    return round(sum(resolved) / len(resolved), 4)


def _common_optional_string(values: Iterable[str | None]) -> str | None:
    resolved: list[str] = [value for value in values if value]
    if not resolved:
        return None
    first: str = resolved[0]
    if all(value == first for value in resolved):
        return first
    return None


def _dimension_scores(dimensions: dict[str, Any]) -> dict[str, int]:
    scores: dict[str, int] = {}
    for dimension_id in DIMENSION_IDS:
        value: dict[str, Any] = _object(dimensions.get(dimension_id))
        score: object = value.get('score')
        if isinstance(score, int) and not isinstance(score, bool) and 1 <= score <= 5:
            scores[dimension_id] = score
    return scores


def _dimension_reasons(dimensions: dict[str, Any]) -> dict[str, str]:
    reasons: dict[str, str] = {}
    for dimension_id in DIMENSION_IDS:
        value: dict[str, Any] = _object(dimensions.get(dimension_id))
        reason: object = value.get('reason')
        if isinstance(reason, str) and reason.strip():
            reasons[dimension_id] = reason.strip()
    return reasons


def _judge_status(judge_score_path: Path, dimensions: dict[str, Any]) -> str:
    if not judge_score_path.exists():
        return 'missing'
    if set(_dimension_scores(dimensions)) == set(DIMENSION_IDS):
        return 'scored'
    return 'invalid'


def _judge_error_count(judge_score: dict[str, Any]) -> int:
    return sum(1 for attempt in _object_list(judge_score.get('attempts')) if isinstance(attempt.get('error'), str))


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        path.write_text('', encoding='utf-8')
        return
    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_markdown(path: Path, summary: dict[str, object]) -> None:
    dimension_ids = summary.get('dimension_ids')
    dimensions: list[str] = [
        str(item)
        for item in dimension_ids
        if isinstance(item, str)
    ] if isinstance(dimension_ids, list) else []
    lines: list[str] = [
        '# Evaluation Campaign Summary',
        '',
        f'- Run count: {summary["run_count"]}',
        f'- Scored run count: {summary["scored_run_count"]}',
        '- Scores are LLM judge 1-5 dimension scores; runtime status is preserved separately.',
        f'- Dimension count: {len(dimensions)}',
        f'- Dimensions: {", ".join(dimensions)}',
        '',
        'Generated files:',
        f'- `{CAMPAIGN_SUMMARY_FILENAME}`',
        f'- `{RUN_SCORES_FILENAME}`',
        f'- `{VARIANT_DIMENSION_SCORES_FILENAME}`',
        f'- `{SCENARIO_DIMENSION_SCORES_FILENAME}`',
        f'- `{VARIANT_SCENARIO_SCORES_FILENAME}`',
    ]
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def _write_rl_markdown(path: Path, summary: dict[str, object]) -> None:
    lines: list[str] = [
        '# RL Strategy Controller Evidence Packet',
        '',
        'This packet describes a strategy-selection layer around the existing geospatial multi-agent system. '
        'It does not claim end-to-end training of a general geospatial analysis model.',
        'Online TRL/RLOO rows, offline reward-table preflight rows, fixed-strategy baselines, and policy-stub '
        'rows must be interpreted as separate evidence sources.',
        '',
        f'- Strategy-controlled run count: {summary["run_count"]}',
        f'- Scored run count: {summary["scored_run_count"]}',
        f'- Rewarded run count: {summary["rewarded_run_count"]}',
        '',
        'Recommended thesis wording:',
        '',
        'The experiment is treated as a concept-proof strategy-layer reinforcement learning study. '
        'Results should be discussed as preliminary observations about policy selection under the current benchmark, '
        'not as universal geospatial reasoning improvements.',
        '',
        'Limitations:',
    ]
    limitations = summary.get('limitations')
    if isinstance(limitations, list):
        lines.extend(f'- {item}' for item in limitations if isinstance(item, str))
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def _object(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _object_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _optional_bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _optional_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _nonnegative_int(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 0


def _optional_int(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _string(value: object, default: str) -> str:
    return value if isinstance(value, str) and value else default


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item)


def _float_mapping(value: object) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, float] = {}
    for key, item in value.items():
        if isinstance(key, str) and isinstance(item, int | float) and not isinstance(item, bool):
            result[key] = float(item)
    return result


def _relative_or_absolute(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _load_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if default is not None and not path.exists():
        return dict(default)
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'Expected JSON object: {path}')
    return payload


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
