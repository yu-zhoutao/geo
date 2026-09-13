from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any, Protocol

from app.config import Settings, get_settings
from app.evaluation.benchmarks import BenchmarkScenario
from app.evaluation.judge_rubrics import JudgeRubric, get_judge_rubric
from app.evaluation.run_bundles import ARTIFACT_MANIFEST_FILENAME, RUN_STATUS_FILENAME
from app.evaluation.session_traces import SESSION_JSON_FILENAME, TRANSCRIPT_FILENAME


JUDGE_PACKET_SCHEMA = 'geo-agent.evaluation.judge-packet.v1'
JUDGE_RESULT_SCHEMA = 'geo-agent.evaluation.judge-result.v1'
JUDGE_INPUT_FILENAME = 'judge-input.json'
JUDGE_SCORE_FILENAME = 'judge-score.json'
JUDGE_TRANSCRIPT_MAX_MESSAGES = 20
JUDGE_TRANSCRIPT_TEXT_LIMIT = 1200
EXTERNAL_EVIDENCE_FILENAME = 'external-evidence.json'


class JudgeOutputError(ValueError):
    pass


class JudgeProvider(Protocol):
    async def complete(self, *, messages: list[dict[str, str]], model: str, temperature: float) -> str: ...


@dataclass(frozen=True, slots=True)
class JudgeConfig:
    model: str
    temperature: float = 0.0
    max_retries: int = 1

    def as_json(self) -> dict[str, object]:
        return {
            'model': self.model,
            'temperature': self.temperature,
            'max_retries': self.max_retries,
        }


@dataclass(frozen=True, slots=True)
class JudgePacket:
    scenario_id: str
    payload: dict[str, Any]

    def as_json(self) -> dict[str, object]:
        return self.payload


@dataclass(frozen=True, slots=True)
class JudgeAttempt:
    index: int
    raw_response: str
    parsed_score: dict[str, Any] | None
    error: str | None

    def as_json(self) -> dict[str, object]:
        return {
            'index': self.index,
            'raw_response': self.raw_response,
            'parsed_score': self.parsed_score,
            'error': self.error,
        }


@dataclass(frozen=True, slots=True)
class JudgeResult:
    scenario_id: str
    model: str
    temperature: float
    attempts: tuple[JudgeAttempt, ...]
    parsed_score: dict[str, Any] | None
    judged_at: datetime

    def as_json(self) -> dict[str, object]:
        return {
            'schema': JUDGE_RESULT_SCHEMA,
            'scenario_id': self.scenario_id,
            'model': self.model,
            'temperature': self.temperature,
            'judged_at': self.judged_at.isoformat(),
            'attempts': [attempt.as_json() for attempt in self.attempts],
            'parsed_score': self.parsed_score,
        }


class GLMJudgeProvider:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def complete(self, *, messages: list[dict[str, str]], model: str, temperature: float) -> str:
        return await asyncio.to_thread(self._complete_sync, messages, model, temperature)

    def _complete_sync(self, messages: list[dict[str, str]], model: str, temperature: float) -> str:
        if not self.settings.glm_api_key:
            raise JudgeOutputError('GLM judge provider is not configured')
        from zai import ZhipuAiClient

        client = ZhipuAiClient(api_key=self.settings.glm_api_key)
        response = client.chat.completions.create(
            model=model,
            temperature=temperature,
            messages=messages,
        )
        return str(response.choices[0].message.content).strip()


class DeepSeekJudgeProvider:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        base_url: str = 'https://api.deepseek.com/v1',
    ) -> None:
        self.settings = settings or get_settings()
        self.base_url = base_url

    async def complete(self, *, messages: list[dict[str, str]], model: str, temperature: float) -> str:
        return await asyncio.to_thread(self._complete_sync, messages, model, temperature)

    def _complete_sync(self, messages: list[dict[str, str]], model: str, temperature: float) -> str:
        if not self.settings.deepseek_api_key:
            raise JudgeOutputError('DeepSeek judge provider is not configured')
        from openai import OpenAI

        client = OpenAI(api_key=self.settings.deepseek_api_key, base_url=self.base_url)
        response = client.chat.completions.create(
            model=model,
            temperature=temperature,
            messages=messages,
        )
        return str(response.choices[0].message.content).strip()


def build_judge_packet(scenario: BenchmarkScenario, run_bundle_path: Path) -> JudgePacket:
    rubric: JudgeRubric = get_judge_rubric(scenario.judge_rubric)
    session: dict[str, Any] = _load_json(run_bundle_path / SESSION_JSON_FILENAME, default={})
    transcript: dict[str, Any] = _load_json(run_bundle_path / TRANSCRIPT_FILENAME, default={})
    artifact_manifest: dict[str, Any] = _load_json(run_bundle_path / ARTIFACT_MANIFEST_FILENAME, default={})
    run_status: dict[str, Any] = _load_json(run_bundle_path / RUN_STATUS_FILENAME, default={})
    external_evidence: dict[str, Any] = _load_json(run_bundle_path / EXTERNAL_EVIDENCE_FILENAME, default={})
    payload: dict[str, Any] = {
        'schema': JUDGE_PACKET_SCHEMA,
        'scenario': {
            'id': scenario.id,
            'oracle_id': scenario.oracle_id,
            'gold_control_state': scenario.gold_control_state,
            'task_family': scenario.task_family,
            'difficulty': scenario.difficulty,
            'forbidden_moves': list(scenario.forbidden_moves),
            'hazard_categories': list(scenario.hazard_categories),
            'user_prompt': scenario.user_prompt,
        },
        'rubric': rubric.as_json(),
        'run_status': run_status,
        'transcript': (
            {'message_count': 0, 'messages': [], 'source': 'external-evidence-pack'}
            if external_evidence
            else _transcript_excerpt(transcript, session)
        ),
        'artifacts': _artifact_summary(artifact_manifest),
        'final_outputs': _final_output_metadata(session),
    }
    if external_evidence:
        payload['external_evidence'] = _external_evidence_summary(external_evidence)
    return JudgePacket(scenario_id=scenario.id, payload=payload)


async def run_llm_judge(
    packet: JudgePacket,
    provider: JudgeProvider,
    config: JudgeConfig,
) -> JudgeResult:
    messages: list[dict[str, str]] = build_judge_messages(packet)
    attempts: list[JudgeAttempt] = []
    parsed_score: dict[str, Any] | None = None
    for index in range(1, config.max_retries + 2):
        raw_response: str = await provider.complete(
            messages=messages,
            model=config.model,
            temperature=config.temperature,
        )
        try:
            parsed_score = validate_judge_output(raw_response, packet.payload['rubric'])
            attempts.append(JudgeAttempt(index=index, raw_response=raw_response, parsed_score=parsed_score, error=None))
            break
        except JudgeOutputError as exc:
            attempts.append(JudgeAttempt(index=index, raw_response=raw_response, parsed_score=None, error=str(exc)))
    return JudgeResult(
        scenario_id=packet.scenario_id,
        model=config.model,
        temperature=config.temperature,
        attempts=tuple(attempts),
        parsed_score=parsed_score,
        judged_at=datetime.now(UTC),
    )


async def write_judge_score(
    scenario: BenchmarkScenario,
    run_bundle_path: Path,
    provider: JudgeProvider,
    config: JudgeConfig,
) -> Path:
    output_paths: list[Path] = [
        run_bundle_path / JUDGE_INPUT_FILENAME,
        run_bundle_path / JUDGE_SCORE_FILENAME,
    ]
    existing: list[Path] = [path for path in output_paths if path.exists()]
    if existing:
        joined = ', '.join(str(path) for path in existing)
        raise ValueError(f'Judge scoring would overwrite existing files: {joined}')
    packet: JudgePacket = build_judge_packet(scenario, run_bundle_path)
    messages: list[dict[str, str]] = build_judge_messages(packet)
    result: JudgeResult = await run_llm_judge(packet, provider, config)
    _write_json(
        run_bundle_path / JUDGE_INPUT_FILENAME,
        {
            'packet': packet.as_json(),
            'messages': messages,
            'config': config.as_json(),
        },
    )
    for attempt in result.attempts:
        response_path = run_bundle_path / f'judge-response-{attempt.index:03d}.txt'
        if response_path.exists():
            raise ValueError(f'Judge scoring would overwrite existing file: {response_path}')
        response_path.write_text(attempt.raw_response + '\n', encoding='utf-8')
    _write_json(run_bundle_path / JUDGE_SCORE_FILENAME, result.as_json())
    return run_bundle_path / JUDGE_SCORE_FILENAME


def build_judge_messages(packet: JudgePacket) -> list[dict[str, str]]:
    dimension_ids: list[str] = [
        str(dimension.get('id'))
        for dimension in packet.payload['rubric'].get('dimensions', [])
        if isinstance(dimension, dict) and isinstance(dimension.get('id'), str)
    ]
    return [
        {
            'role': 'system',
            'content': (
                'You are a strict geospatial evaluation judge. '
                'Score semantic task performance from the user request, transcript, final answer, and visible outputs: '
                'method choice, data readiness, CRS/units, parameters, execution, uncertainty, and claim validity. '
                'Use clarification, repair, or stop behavior only as evidence for those geospatial quality dimensions; '
                'do not require every framework to expose the same interaction protocol. '
                'Do not reward or penalize framework-specific traceability conventions such as whether the run '
                'produced study_design.json, claim_trace.json, evidence-records.json, or a particular internal '
                'artifact schema. Do not reward or penalize presentation-only differences such as whether maps and '
                'reports follow this project\'s artifact conventions; consider deliverables only when they reveal whether '
                'the substantive geospatial analysis is supported or unverifiable. Treat runtime status facts such as '
                'errors, timeouts, and continuation count as context for interpreting what happened, not as separate scoring gates. '
                'A score of 5 requires actual high-quality analysis and necessary verification; simply stating caveats '
                'without checking them should usually cap the relevant dimension at 4. '
                'Return raw JSON only, with no Markdown fences or explanatory text.'
            ),
        },
        {
            'role': 'user',
            'content': (
                'Score the run using exactly this JSON output schema:\n'
                '{'
                '"dimensions": {'
                + ', '.join(f'"{dimension_id}": {{"score": 1, "reason": "..."}}' for dimension_id in dimension_ids)
                + '}, '
                '"summary": "..."'
                '}\n\n'
                'Use integer scores from 1 to 5 only. Base the scores on the preserved agent process and outputs; '
                'ignore missing framework traceability files unless their missing content also means the substantive '
                'analysis is unsupported or unverifiable from the transcript and outputs.\n\n'
                'Here is the judge packet:\n'
                f'{json.dumps(packet.as_json(), ensure_ascii=False, sort_keys=True)}'
            ),
        },
    ]


def validate_judge_output(raw_response: str, rubric: object) -> dict[str, Any]:
    payload: Any = _load_judge_json(raw_response)
    if not isinstance(payload, dict):
        raise JudgeOutputError('judge response must be a JSON object')
    dimensions = _normalize_dimensions(payload.get('dimensions'))
    payload['dimensions'] = dimensions
    if not isinstance(dimensions, dict):
        raise JudgeOutputError('judge response requires dimensions object')
    rubric_dimensions = _rubric_dimension_ids(rubric)
    missing: set[str] = rubric_dimensions - set(dimensions)
    if missing:
        raise JudgeOutputError(f'judge response is missing dimensions: {", ".join(sorted(missing))}')
    for dimension_id in rubric_dimensions:
        value = dimensions.get(dimension_id)
        if not isinstance(value, dict):
            raise JudgeOutputError(f'judge dimension must be an object: {dimension_id}')
        score = value.get('score')
        reason = value.get('reason')
        if not isinstance(score, int) or isinstance(score, bool) or score < 1 or score > 5:
            raise JudgeOutputError(f'judge dimension score must be an integer 1-5: {dimension_id}')
        if not isinstance(reason, str) or not reason.strip():
            raise JudgeOutputError(f'judge dimension reason is required: {dimension_id}')
    summary = payload.get('summary')
    if not isinstance(summary, str) or not summary.strip():
        raise JudgeOutputError('judge response requires non-empty summary')
    return {'dimensions': dimensions, 'summary': summary.strip()}


def _load_judge_json(raw_response: str) -> Any:
    cleaned: str = _strip_markdown_fence(raw_response.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start: int = cleaned.find('{')
        end: int = cleaned.rfind('}')
        if start < 0 or end <= start:
            raise JudgeOutputError('judge response is not valid JSON') from None
        try:
            return json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise JudgeOutputError('judge response is not valid JSON') from exc


def _strip_markdown_fence(value: str) -> str:
    if not value.startswith('```'):
        return value
    lines: list[str] = value.splitlines()
    if len(lines) >= 2 and lines[0].startswith('```') and lines[-1].strip() == '```':
        return '\n'.join(lines[1:-1]).strip()
    return value


def _normalize_dimensions(value: object) -> object:
    if isinstance(value, dict):
        return value
    if not isinstance(value, list):
        return value
    dimensions: dict[str, object] = {}
    for item in value:
        if not isinstance(item, dict):
            return value
        dimension_id = item.get('id')
        if not isinstance(dimension_id, str) or not dimension_id:
            return value
        dimensions[dimension_id] = item
    return dimensions


def _rubric_dimension_ids(rubric: object) -> set[str]:
    if not isinstance(rubric, dict):
        raise JudgeOutputError('judge rubric must be an object')
    dimensions = rubric.get('dimensions')
    if not isinstance(dimensions, list):
        raise JudgeOutputError('judge rubric requires dimensions list')
    ids: set[str] = set()
    for item in dimensions:
        if isinstance(item, dict) and isinstance(item.get('id'), str):
            ids.add(item['id'])
    if not ids:
        raise JudgeOutputError('judge rubric contains no dimensions')
    return ids


def _transcript_excerpt(transcript: dict[str, Any], session: dict[str, Any]) -> dict[str, object]:
    messages = transcript.get('messages')
    if not isinstance(messages, list) or not messages:
        messages = session.get('messages')
    if not isinstance(messages, list):
        messages = []
    valid_messages: list[dict[str, Any]] = [message for message in messages if isinstance(message, dict)]
    return {
        'message_count': len(messages),
        'messages': [_trim_transcript_message(message) for message in _select_transcript_messages(valid_messages)],
    }


def _select_transcript_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(messages) <= JUDGE_TRANSCRIPT_MAX_MESSAGES:
        return messages
    return [messages[0], *messages[-(JUDGE_TRANSCRIPT_MAX_MESSAGES - 1) :]]


def _trim_transcript_message(message: dict[str, Any]) -> dict[str, object]:
    trimmed: dict[str, object] = {}
    for key in ('id', 'role', 'agent', 'created_at'):
        value = message.get(key)
        if isinstance(value, str):
            trimmed[key] = value
    parts = message.get('parts')
    if isinstance(parts, list):
        trimmed_parts: list[dict[str, object]] = []
        for part in parts:
            if not isinstance(part, dict):
                continue
            trimmed_part = _trim_transcript_part(part)
            if trimmed_part is not None:
                trimmed_parts.append(trimmed_part)
        trimmed['parts'] = trimmed_parts
    return trimmed


def _trim_transcript_part(part: dict[str, Any]) -> dict[str, object] | None:
    part_type = part.get('type')
    if part_type == 'text':
        text = _trim_string(part.get('text'), JUDGE_TRANSCRIPT_TEXT_LIMIT)
        if text is None:
            return None
        return {'type': 'text', 'text': text}
    if part_type == 'tool':
        trimmed: dict[str, object] = {'type': 'tool'}
        tool = part.get('tool')
        if isinstance(tool, str) and tool:
            trimmed['tool'] = tool
        state = part.get('state')
        if isinstance(state, dict):
            trimmed_state: dict[str, object] = {}
            for key in ('status', 'title'):
                value = state.get(key)
                if isinstance(value, str) and value:
                    trimmed_state[key] = _trim_string(value, 160) or value
            if trimmed_state:
                trimmed['state'] = trimmed_state
        return trimmed
    return None


def _trim_string(value: object, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    if len(value) <= limit:
        return value
    suffix = '\n[truncated]'
    return value[: max(0, limit - len(suffix))] + suffix


def _artifact_summary(artifact_manifest: dict[str, Any]) -> dict[str, object]:
    items: list[dict[str, object]] = []
    for item in _object_list(artifact_manifest.get('items')):
        summary: dict[str, object] = {}
        for key in ('id', 'title', 'source_path', 'copied_path', 'size_bytes', 'sha256', 'error'):
            value = item.get(key)
            if isinstance(value, str):
                summary[key] = _trim_string(value, 240) or value
            elif isinstance(value, int) and not isinstance(value, bool):
                summary[key] = value
            elif value is None and key == 'error':
                summary[key] = None
        items.append(summary)
    return {
        'schema': artifact_manifest.get('schema'),
        'artifact_count': artifact_manifest.get('artifact_count', len(items)),
        'items': items,
    }


def _final_output_metadata(session: dict[str, Any]) -> dict[str, object]:
    artifacts = session.get('artifacts')
    if not isinstance(artifacts, list):
        artifacts = []
    return {
        'artifacts': [_session_artifact_summary(artifact) for artifact in artifacts if isinstance(artifact, dict)],
        'verification': (
            [_verification_summary(item) for item in session.get('verification', []) if isinstance(item, dict)]
            if isinstance(session.get('verification'), list)
            else []
        ),
    }


def _session_artifact_summary(artifact: dict[str, Any]) -> dict[str, object]:
    summary: dict[str, object] = {}
    for key in ('id', 'title', 'path', 'mime_type', 'type'):
        value = artifact.get(key)
        if isinstance(value, str) and value:
            summary[key] = _trim_string(value, 240) or value
    return summary


def _verification_summary(item: dict[str, Any]) -> dict[str, object]:
    summary: dict[str, object] = {}
    for key in ('id', 'decision', 'reason', 'summary'):
        value = item.get(key)
        if isinstance(value, str) and value:
            summary[key] = _trim_string(value, 600) or value
    return summary


def _external_evidence_summary(external_evidence: dict[str, Any]) -> dict[str, object]:
    framework: dict[str, Any] = _object(external_evidence.get('framework'))
    source_pack: dict[str, Any] = _object(external_evidence.get('source_evidence_pack'))
    run: dict[str, Any] = _object(external_evidence.get('run'))
    dataset: dict[str, Any] = _object(external_evidence.get('dataset'))
    model: dict[str, Any] = _object(external_evidence.get('model'))
    evidence_files: list[dict[str, object]] = []
    for item in _object_list(external_evidence.get('evidence_files')):
        summary: dict[str, object] = {}
        for key in ('kind', 'path', 'sha256'):
            value = item.get(key)
            if isinstance(value, str) and value:
                summary[key] = _trim_string(value, 240) or value
        size_bytes = item.get('size_bytes')
        if isinstance(size_bytes, int) and not isinstance(size_bytes, bool):
            summary['size_bytes'] = size_bytes
        excerpt = _trim_string(item.get('text_excerpt'), JUDGE_TRANSCRIPT_TEXT_LIMIT)
        if excerpt:
            summary['text_excerpt'] = excerpt
        evidence_files.append(summary)
    return {
        'framework': {
            key: value
            for key in ('id', 'label', 'framework_type', 'expected_execution_mode', 'zotero_key', 'source_url')
            if isinstance((value := framework.get(key)), str) and value
        },
        'source_evidence_pack': {
            key: value
            for key in ('path', 'manifest_hash')
            if isinstance((value := source_pack.get(key)), str) and value
        },
        'run': {
            key: value
            for key in ('run_id', 'status', 'terminal_reason', 'started_at', 'finished_at')
            if isinstance((value := run.get(key)), str) and value
        },
        'runtime_facts': {
            'timed_out': run.get('timed_out') if isinstance(run.get('timed_out'), bool) else None,
            'duration_seconds': (
                run.get('duration_seconds')
                if isinstance(run.get('duration_seconds'), int | float)
                else None
            ),
            'errors': run.get('errors') if isinstance(run.get('errors'), list) else [],
        },
        'model': {
            key: value
            for key in ('provider', 'model')
            if isinstance((value := model.get(key)), str) and value
        },
        'dataset': {
            'root': dataset.get('root') if isinstance(dataset.get('root'), str) else None,
            'pack': dataset.get('pack') if isinstance(dataset.get('pack'), list) else [],
            'import_notes': _trim_string(dataset.get('import_notes'), 800),
        },
        'final_answer': _trim_string(external_evidence.get('final_answer'), JUDGE_TRANSCRIPT_TEXT_LIMIT),
        'failure_note': _trim_string(external_evidence.get('failure_note'), 800),
        'operator_notes': _trim_string(external_evidence.get('operator_notes'), 800),
        'evidence_files': evidence_files,
    }


def _object_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _object(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _load_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if default is not None and not path.exists():
        return dict(default)
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'Expected JSON object: {path}')
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
