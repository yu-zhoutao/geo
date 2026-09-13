from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.evaluation.app_client import EvaluationAppClient
from app.evaluation.benchmarks import BenchmarkScenario, BenchmarkValidationError, repo_root
from app.evaluation.synthetic_datasets import materialize_synthetic_dataset_pack


TERMINAL_SESSION_STATUSES: set[str] = {'completed', 'failed', 'idle', 'waiting_for_input'}
CONTINUATION_PROMPT = (
    '请继续刚才的任务，从已完成且有证据的步骤之后继续；'
    '不要重做已经完成的分析，只补齐未完成的交付物。'
)
CONTINUATION_STATUSES: set[str] = {'failed', 'idle'}


@dataclass(frozen=True, slots=True)
class ScenarioAttemptResult:
    session_id: str
    status: str
    terminal_reason: str
    timed_out: bool
    session: dict[str, Any]
    started_at: datetime
    finished_at: datetime
    clarification_answer_count: int = 0
    clarification_question_ids: tuple[str, ...] = ()
    continuation_count: int = 0


async def execute_scenario_attempt(
    client: EvaluationAppClient,
    scenario: BenchmarkScenario,
    *,
    data_attachments: list[dict[str, object]] | None = None,
    wall_clock_budget_seconds: float,
    poll_interval_seconds: float = 1.0,
    max_continuations: int = 2,
) -> ScenarioAttemptResult:
    if max_continuations < 0:
        raise BenchmarkValidationError('max_continuations must be non-negative')
    started_at: datetime = datetime.now(UTC)
    created_session: dict[str, Any] = await client.create_session()
    session_id: str = _session_id(created_session)
    attachments: list[dict[str, object]] = (
        data_attachments
        if data_attachments is not None
        else scenario_data_attachments(scenario)
    )
    await client.update_data_directories(session_id, attachments)
    await client.submit_message(session_id, scenario.user_prompt)

    deadline: float | None = None
    if wall_clock_budget_seconds > 0:
        deadline = asyncio.get_running_loop().time() + wall_clock_budget_seconds
    answered_question_ids: list[str] = []
    continuation_count = 0

    while True:
        session: dict[str, Any] = await client.get_session(session_id)
        status: str = str(session.get('status') or '')
        budget_expired = deadline is not None and asyncio.get_running_loop().time() >= deadline
        if status in CONTINUATION_STATUSES and continuation_count < max_continuations and not budget_expired:
            await client.submit_message(session_id, CONTINUATION_PROMPT)
            continuation_count += 1
            continue
        if status == 'waiting_for_input':
            question_id: str | None = _question_id(session)
            if _should_answer_clarification(scenario, question_id, answered_question_ids):
                await client.answer_question(
                    session_id,
                    str(question_id),
                    answers=list(scenario.clarification_answers),
                )
                answered_question_ids.append(str(question_id))
                continue
            return ScenarioAttemptResult(
                session_id=session_id,
                status=status,
                terminal_reason=_clarification_terminal_reason(scenario, question_id),
                timed_out=False,
                session=session,
                started_at=started_at,
                finished_at=datetime.now(UTC),
                clarification_answer_count=len(answered_question_ids),
                clarification_question_ids=tuple(answered_question_ids),
                continuation_count=continuation_count,
            )
        if status in TERMINAL_SESSION_STATUSES:
            return ScenarioAttemptResult(
                session_id=session_id,
                status=status,
                terminal_reason=status,
                timed_out=False,
                session=session,
                started_at=started_at,
                finished_at=datetime.now(UTC),
                clarification_answer_count=len(answered_question_ids),
                clarification_question_ids=tuple(answered_question_ids),
                continuation_count=continuation_count,
            )
        if budget_expired:
            await client.interrupt_session(session_id)
            interrupted_session: dict[str, Any] = await client.get_session(session_id)
            return ScenarioAttemptResult(
                session_id=session_id,
                status=str(interrupted_session.get('status') or 'interrupted'),
                terminal_reason='timeout',
                timed_out=True,
                session=interrupted_session,
                started_at=started_at,
                finished_at=datetime.now(UTC),
                clarification_answer_count=len(answered_question_ids),
                clarification_question_ids=tuple(answered_question_ids),
                continuation_count=continuation_count,
            )
        await asyncio.sleep(_next_poll_interval(poll_interval_seconds, deadline))


def scenario_data_attachments(scenario: BenchmarkScenario) -> list[dict[str, object]]:
    dataset_root: Path = Path(scenario.dataset_root)
    if not dataset_root.is_absolute():
        dataset_root = repo_root() / dataset_root
    return _scenario_data_attachment_payload(scenario, dataset_root)


def prepare_scenario_data_attachments(scenario: BenchmarkScenario, output_root: Path) -> list[dict[str, object]]:
    if scenario.dataset_pack_mode == 'repo-files':
        return scenario_data_attachments(scenario)
    dataset_root: Path = output_root.resolve()
    dataset_root.mkdir(parents=True, exist_ok=True)
    materialize_synthetic_dataset_pack(scenario, dataset_root)
    return _scenario_data_attachment_payload(scenario, dataset_root)


def _scenario_data_attachment_payload(scenario: BenchmarkScenario, dataset_root: Path) -> list[dict[str, object]]:
    return [
        {
            'id': f'scenario-{scenario.id.lower()}-dataset-root',
            'path': str(dataset_root.resolve()),
            'enabled': True,
            'label': f'{scenario.id} dataset root',
        }
    ]


def _session_id(session: dict[str, Any]) -> str:
    raw_session_id = session.get('id')
    if not isinstance(raw_session_id, str) or not raw_session_id:
        raise BenchmarkValidationError('App API did not return a session id')
    return raw_session_id


def _should_answer_clarification(
    scenario: BenchmarkScenario,
    question_id: str | None,
    answered_question_ids: list[str],
) -> bool:
    return (
        scenario.clarification_answer_policy == 'answer-once'
        and bool(scenario.clarification_answers)
        and question_id is not None
        and question_id not in answered_question_ids
    )


def _clarification_terminal_reason(scenario: BenchmarkScenario, question_id: str | None) -> str:
    if scenario.gold_control_state == 'clarify' and question_id is not None:
        return 'expected_clarification'
    return 'waiting_for_input'


def _question_id(session: dict[str, Any]) -> str | None:
    question = session.get('question')
    if not isinstance(question, dict):
        return None
    raw_question_id = question.get('id')
    return raw_question_id if isinstance(raw_question_id, str) and raw_question_id else None


def _next_poll_interval(poll_interval_seconds: float, deadline: float | None) -> float:
    if poll_interval_seconds <= 0:
        raise BenchmarkValidationError('poll_interval_seconds must be positive')
    if deadline is None:
        return poll_interval_seconds
    remaining: float = deadline - asyncio.get_running_loop().time()
    return max(0.0, min(poll_interval_seconds, remaining))
