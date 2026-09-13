from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from app.evaluation.run_bundles import ARTIFACT_MANIFEST_FILENAME, RUN_MANIFEST_FILENAME, RUN_STATUS_FILENAME
from app.evaluation.session_traces import SESSION_JSON_FILENAME


RUN_COST_SCHEMA = 'geo-agent.evaluation.run-cost.v1'
TOKEN_KEYS: set[str] = {
    'input_tokens',
    'output_tokens',
    'total_tokens',
    'prompt_tokens',
    'completion_tokens',
}


@dataclass(frozen=True, slots=True)
class RunCost:
    wall_clock_seconds: float | None
    token_counts: dict[str, int]
    tool_call_count: int
    failed_tool_call_count: int
    artifact_count: int
    retry_count: int
    failed_attempt: bool
    unavailable: tuple[str, ...]

    def as_json(self) -> dict[str, object]:
        return {
            'schema': RUN_COST_SCHEMA,
            'wall_clock_seconds': self.wall_clock_seconds,
            'token_counts': self.token_counts,
            'tool_call_count': self.tool_call_count,
            'failed_tool_call_count': self.failed_tool_call_count,
            'artifact_count': self.artifact_count,
            'retry_count': self.retry_count,
            'failed_attempt': self.failed_attempt,
            'unavailable': list(self.unavailable),
        }


def extract_run_costs(run_bundle_path: Path) -> RunCost:
    run_status: dict[str, Any] = _load_json(run_bundle_path / RUN_STATUS_FILENAME, default={})
    session: dict[str, Any] = _load_json(run_bundle_path / SESSION_JSON_FILENAME, default={})
    artifact_manifest: dict[str, Any] = _load_json(run_bundle_path / ARTIFACT_MANIFEST_FILENAME, default={})
    run_manifest: dict[str, Any] = _load_json(run_bundle_path / RUN_MANIFEST_FILENAME, default={})

    wall_clock_seconds: float | None = _optional_float(run_status.get('duration_seconds'))
    token_counts: dict[str, int] = _token_counts(session)
    unavailable: list[str] = []
    if wall_clock_seconds is None:
        unavailable.append('wall_clock_seconds')
    if not token_counts:
        unavailable.append('token_counts')

    tool_call_count, failed_tool_call_count = _tool_counts(session)
    return RunCost(
        wall_clock_seconds=wall_clock_seconds,
        token_counts=token_counts,
        tool_call_count=tool_call_count,
        failed_tool_call_count=failed_tool_call_count,
        artifact_count=_artifact_count(artifact_manifest),
        retry_count=_retry_count(run_status, session),
        failed_attempt=_failed_attempt(run_status, run_manifest),
        unavailable=tuple(unavailable),
    )


def _tool_counts(session: dict[str, Any]) -> tuple[int, int]:
    count: int = 0
    failed: int = 0
    for message in _object_list(session.get('messages')):
        for part in _object_list(message.get('parts')):
            if part.get('type') != 'tool':
                continue
            count += 1
            state = part.get('state')
            status = state.get('status') if isinstance(state, dict) else None
            if status in {'failed', 'error'}:
                failed += 1
    return count, failed


def _token_counts(payload: object) -> dict[str, int]:
    counts: dict[str, int] = {}

    def visit(value: object) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in TOKEN_KEYS:
                    token_count = _optional_int(item)
                    if token_count is not None:
                        counts[key] = counts.get(key, 0) + token_count
                visit(item)
            return
        if isinstance(value, list):
            for item in value:
                visit(item)

    visit(payload)
    if 'total_tokens' not in counts and ('input_tokens' in counts or 'output_tokens' in counts):
        counts['total_tokens'] = counts.get('input_tokens', 0) + counts.get('output_tokens', 0)
    if 'total_tokens' not in counts and ('prompt_tokens' in counts or 'completion_tokens' in counts):
        counts['total_tokens'] = counts.get('prompt_tokens', 0) + counts.get('completion_tokens', 0)
    return counts


def _artifact_count(artifact_manifest: dict[str, Any]) -> int:
    raw_count = _optional_int(artifact_manifest.get('artifact_count'))
    if raw_count is not None:
        return raw_count
    return len(_object_list(artifact_manifest.get('items')))


def _retry_count(run_status: dict[str, Any], session: dict[str, Any]) -> int:
    raw_count = _optional_int(run_status.get('retry_count'))
    if raw_count is not None:
        return raw_count
    return _sum_retry_counts(session)


def _sum_retry_counts(payload: object) -> int:
    total: int = 0
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in {'retry_count', 'retries'}:
                total += _optional_int(value) or 0
            else:
                total += _sum_retry_counts(value)
    elif isinstance(payload, list):
        total += sum(_sum_retry_counts(item) for item in payload)
    return total


def _failed_attempt(
    run_status: dict[str, Any],
    run_manifest: dict[str, Any],
) -> bool:
    return (
        bool(run_status.get('timed_out'))
        or run_status.get('session_status') == 'failed'
        or (_optional_int(run_manifest.get('error_count')) or 0) > 0
    )


def _object_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _optional_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _load_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if default is not None and not path.exists():
        return dict(default)
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'Expected JSON object: {path}')
    return payload
