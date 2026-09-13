from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any, Sequence

from app.evaluation.app_client import EvaluationAppClient
from app.evaluation.benchmarks import BenchmarkScenario
from app.evaluation.manifests import VariantManifest
from app.evaluation.scenario_execution import ScenarioAttemptResult
from app.evaluation.session_traces import SessionTraceCapture, write_session_trace_bundle
from app.evaluation.strategy_profiles import StrategySelection


RUN_BUNDLE_SCHEMA = 'geo-agent.evaluation.run-bundle.v1'
RUN_MANIFEST_FILENAME = 'run-manifest.json'
RUN_STATUS_FILENAME = 'run-status.json'
ARTIFACT_MANIFEST_FILENAME = 'artifact-manifest.json'
ARTIFACTS_DIRNAME = 'artifacts'
LOGS_DIRNAME = 'logs'
RUNTIME_TRACES_DIRNAME = 'runtime-traces'


class RunBundleCaptureError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CapturedArtifact:
    id: str
    title: str | None
    source_path: str | None
    copied_path: Path | None
    size_bytes: int | None
    sha256: str | None
    error: str | None

    def as_json(self, bundle_root: Path) -> dict[str, object]:
        return {
            'id': self.id,
            'title': self.title,
            'source_path': self.source_path,
            'copied_path': _relative_or_absolute(self.copied_path, bundle_root) if self.copied_path else None,
            'size_bytes': self.size_bytes,
            'sha256': self.sha256,
            'error': self.error,
        }


@dataclass(frozen=True, slots=True)
class RunBundleCapture:
    run_id: str
    bundle_root: Path
    run_manifest_path: Path
    status_path: Path
    artifact_manifest_path: Path
    trace_capture: SessionTraceCapture | None
    artifact_count: int
    error_count: int


async def capture_run_bundle(
    client: EvaluationAppClient,
    result: ScenarioAttemptResult,
    scenario: BenchmarkScenario,
    run_bundle_path: Path,
    *,
    run_id: str | None = None,
    variant: VariantManifest | None = None,
    strategy: StrategySelection | None = None,
    log_paths: Sequence[Path] = (),
) -> RunBundleCapture:
    output_paths: tuple[Path, ...] = (
        run_bundle_path / RUN_MANIFEST_FILENAME,
        run_bundle_path / RUN_STATUS_FILENAME,
        run_bundle_path / ARTIFACT_MANIFEST_FILENAME,
    )
    existing: list[Path] = [path for path in output_paths if path.exists()]
    if existing:
        joined: str = ', '.join(str(path) for path in existing)
        raise RunBundleCaptureError(f'Run bundle capture would overwrite existing files: {joined}')

    run_bundle_path.mkdir(parents=True, exist_ok=True)
    resolved_run_id: str = run_id or result.session_id
    errors: list[str] = []
    archive: dict[str, Any] | None = None
    trace_capture: SessionTraceCapture | None = None

    try:
        archive = await client.export_session_archive(result.session_id)
        trace_capture = write_session_trace_bundle(archive, run_bundle_path)
    except Exception as exc:
        errors.append(f'session archive capture failed: {type(exc).__name__}: {exc}')

    captured_artifacts: list[CapturedArtifact] = []
    runtime_trace: dict[str, object] = {'status': 'unavailable'}
    if archive is not None:
        captured_artifacts = await _capture_artifacts(client, result.session_id, archive, run_bundle_path)
        runtime_trace = _capture_runtime_trace(archive, run_bundle_path)
        errors.extend(artifact.error for artifact in captured_artifacts if artifact.error is not None)
        if runtime_trace.get('error'):
            errors.append(str(runtime_trace['error']))
    copied_logs: list[dict[str, object]] = _copy_logs(log_paths, run_bundle_path)
    errors.extend(str(log['error']) for log in copied_logs if log.get('error'))

    status_payload: dict[str, Any] = _run_status_payload(result, errors, strategy=strategy)
    artifact_manifest: dict[str, Any] = {
        'schema': 'geo-agent.evaluation.artifact-capture.v1',
        'session_id': result.session_id,
        'artifact_count': len(captured_artifacts),
        'items': [artifact.as_json(run_bundle_path) for artifact in captured_artifacts],
    }
    run_manifest: dict[str, Any] = {
        'schema': RUN_BUNDLE_SCHEMA,
        'run_id': resolved_run_id,
        'session_id': result.session_id,
        'scenario': _scenario_reference(scenario),
        'variant': _variant_reference(variant),
        'strategy': _strategy_reference(strategy),
        'status': {
            'session_status': result.status,
            'terminal_reason': result.terminal_reason,
            'timed_out': result.timed_out,
        },
        'trace_capture': _trace_capture_reference(trace_capture, run_bundle_path),
        'runtime_trace': runtime_trace,
        'logs': copied_logs,
        'files': {
            'run_status': RUN_STATUS_FILENAME,
            'artifact_manifest': ARTIFACT_MANIFEST_FILENAME,
            'artifact_root': ARTIFACTS_DIRNAME,
        },
        'error_count': len(errors),
        'errors': errors,
    }

    _write_json(run_bundle_path / RUN_STATUS_FILENAME, status_payload)
    _write_json(run_bundle_path / ARTIFACT_MANIFEST_FILENAME, artifact_manifest)
    _write_json(run_bundle_path / RUN_MANIFEST_FILENAME, run_manifest)
    return RunBundleCapture(
        run_id=resolved_run_id,
        bundle_root=run_bundle_path,
        run_manifest_path=run_bundle_path / RUN_MANIFEST_FILENAME,
        status_path=run_bundle_path / RUN_STATUS_FILENAME,
        artifact_manifest_path=run_bundle_path / ARTIFACT_MANIFEST_FILENAME,
        trace_capture=trace_capture,
        artifact_count=len(captured_artifacts),
        error_count=len(errors),
    )


def write_failed_run_bundle(
    run_bundle_path: Path,
    *,
    run_id: str,
    session_id: str,
    scenario: BenchmarkScenario,
    variant: VariantManifest | None,
    terminal_reason: str,
    errors: Sequence[str],
    strategy: StrategySelection | None = None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
) -> RunBundleCapture:
    output_paths: tuple[Path, ...] = (
        run_bundle_path / RUN_MANIFEST_FILENAME,
        run_bundle_path / RUN_STATUS_FILENAME,
        run_bundle_path / ARTIFACT_MANIFEST_FILENAME,
    )
    existing: list[Path] = [path for path in output_paths if path.exists()]
    if existing:
        joined: str = ', '.join(str(path) for path in existing)
        raise RunBundleCaptureError(f'Failure run bundle would overwrite existing files: {joined}')

    started: datetime = started_at or datetime.now(UTC)
    finished: datetime = finished_at or datetime.now(UTC)
    run_bundle_path.mkdir(parents=True, exist_ok=True)
    error_items: list[str] = [str(error) for error in errors if str(error)]
    run_status: dict[str, object] = {
        'schema': 'geo-agent.evaluation.run-status.v1',
        'session_id': session_id,
        'session_status': 'failed',
        'terminal_reason': terminal_reason,
        'timed_out': terminal_reason == 'container_timeout',
        'started_at': started.isoformat(),
        'finished_at': finished.isoformat(),
        'duration_seconds': (finished - started).total_seconds(),
        'continuation_count': 0,
        'clarification_answer_count': 0,
        'clarification_question_ids': [],
        'error_count': len(error_items),
        'errors': error_items,
        'strategy': _strategy_reference(strategy),
    }
    artifact_manifest: dict[str, object] = {
        'schema': 'geo-agent.evaluation.artifact-capture.v1',
        'session_id': session_id,
        'artifact_count': 0,
        'items': [],
    }
    run_manifest: dict[str, object] = {
        'schema': RUN_BUNDLE_SCHEMA,
        'run_id': run_id,
        'session_id': session_id,
        'scenario': _scenario_reference(scenario),
        'variant': _variant_reference(variant),
        'strategy': _strategy_reference(strategy),
        'status': {
            'session_status': 'failed',
            'terminal_reason': terminal_reason,
            'timed_out': terminal_reason == 'container_timeout',
        },
        'trace_capture': None,
        'runtime_trace': {'status': 'unavailable'},
        'logs': [],
        'files': {
            'run_status': RUN_STATUS_FILENAME,
            'artifact_manifest': ARTIFACT_MANIFEST_FILENAME,
            'artifact_root': ARTIFACTS_DIRNAME,
        },
        'error_count': len(error_items),
        'errors': error_items,
    }

    _write_json(run_bundle_path / RUN_STATUS_FILENAME, run_status)
    _write_json(run_bundle_path / ARTIFACT_MANIFEST_FILENAME, artifact_manifest)
    _write_json(run_bundle_path / RUN_MANIFEST_FILENAME, run_manifest)
    return RunBundleCapture(
        run_id=run_id,
        bundle_root=run_bundle_path,
        run_manifest_path=run_bundle_path / RUN_MANIFEST_FILENAME,
        status_path=run_bundle_path / RUN_STATUS_FILENAME,
        artifact_manifest_path=run_bundle_path / ARTIFACT_MANIFEST_FILENAME,
        trace_capture=None,
        artifact_count=0,
        error_count=len(error_items),
    )


def load_run_bundle_capture(run_bundle_path: Path) -> RunBundleCapture:
    run_manifest_path: Path = run_bundle_path / RUN_MANIFEST_FILENAME
    status_path: Path = run_bundle_path / RUN_STATUS_FILENAME
    artifact_manifest_path: Path = run_bundle_path / ARTIFACT_MANIFEST_FILENAME
    run_manifest: dict[str, Any] = _load_json(run_manifest_path)
    status: dict[str, Any] = _load_json(status_path)
    artifact_manifest: dict[str, Any] = _load_json(artifact_manifest_path)
    run_id = run_manifest.get('run_id')
    if not isinstance(run_id, str) or not run_id:
        raise RunBundleCaptureError(f'Run manifest does not include a run_id: {run_manifest_path}')
    return RunBundleCapture(
        run_id=run_id,
        bundle_root=run_bundle_path,
        run_manifest_path=run_manifest_path,
        status_path=status_path,
        artifact_manifest_path=artifact_manifest_path,
        trace_capture=None,
        artifact_count=_int_value(artifact_manifest.get('artifact_count')),
        error_count=_int_value(status.get('error_count')),
    )


async def _capture_artifacts(
    client: EvaluationAppClient,
    session_id: str,
    archive: dict[str, Any],
    run_bundle_path: Path,
) -> list[CapturedArtifact]:
    artifacts_root: Path = run_bundle_path / ARTIFACTS_DIRNAME
    artifacts: list[CapturedArtifact] = []
    for index, artifact in enumerate(_session_artifacts(archive), start=1):
        artifact_id: str | None = _optional_string(artifact.get('id'))
        if artifact_id is None:
            artifacts.append(
                CapturedArtifact(
                    id=f'unnamed-artifact-{index:03d}',
                    title=_optional_string(artifact.get('title')),
                    source_path=_optional_string(artifact.get('path')),
                    copied_path=None,
                    size_bytes=None,
                    sha256=None,
                    error='artifact metadata is missing an id',
                )
            )
            continue
        try:
            content: bytes = await client.fetch_artifact_content(session_id, artifact_id)
            artifacts_root.mkdir(parents=True, exist_ok=True)
            output_path: Path = _unique_file_path(
                artifacts_root / _artifact_filename(artifact_id, _optional_string(artifact.get('path')), index)
            )
            output_path.write_bytes(content)
            artifacts.append(
                CapturedArtifact(
                    id=artifact_id,
                    title=_optional_string(artifact.get('title')),
                    source_path=_optional_string(artifact.get('path')),
                    copied_path=output_path,
                    size_bytes=len(content),
                    sha256=_sha256_bytes(content),
                    error=None,
                )
            )
        except Exception as exc:
            artifacts.append(
                CapturedArtifact(
                    id=artifact_id,
                    title=_optional_string(artifact.get('title')),
                    source_path=_optional_string(artifact.get('path')),
                    copied_path=None,
                    size_bytes=None,
                    sha256=None,
                    error=f'artifact capture failed: {type(exc).__name__}: {exc}',
                )
            )
    return artifacts


def _capture_runtime_trace(archive: dict[str, Any], run_bundle_path: Path) -> dict[str, object]:
    trace_path_text: str | None = _runtime_trace_path(archive)
    if trace_path_text is None:
        return {'status': 'unavailable'}
    source_path: Path | None = _resolve_runtime_trace_source(archive, trace_path_text)
    if source_path is None:
        return {'status': 'reference-only', 'source_path': trace_path_text}
    if not source_path.exists():
        return {
            'status': 'missing',
            'source_path': str(source_path),
            'error': f'runtime trace file does not exist: {source_path}',
        }

    trace_root: Path = run_bundle_path / RUNTIME_TRACES_DIRNAME
    trace_root.mkdir(parents=True, exist_ok=True)
    copied_path: Path = _unique_file_path(trace_root / _safe_file_name(source_path.name, 'runtime-trace.jsonl'))
    shutil.copy2(source_path, copied_path)
    return {
        'status': 'copied',
        'source_path': str(source_path),
        'copied_path': _relative_or_absolute(copied_path, run_bundle_path),
        'size_bytes': copied_path.stat().st_size,
        'sha256': _sha256_file(copied_path),
    }


def _copy_logs(log_paths: Sequence[Path], run_bundle_path: Path) -> list[dict[str, object]]:
    copied_logs: list[dict[str, object]] = []
    if not log_paths:
        return copied_logs
    logs_root: Path = run_bundle_path / LOGS_DIRNAME
    logs_root.mkdir(parents=True, exist_ok=True)
    for index, source_path in enumerate(log_paths, start=1):
        if not source_path.exists():
            copied_logs.append(
                {
                    'status': 'missing',
                    'source_path': str(source_path),
                    'error': f'log file does not exist: {source_path}',
                }
            )
            continue
        copied_path: Path = _unique_file_path(
            logs_root / _safe_file_name(source_path.name, f'log-{index:03d}.txt')
        )
        shutil.copy2(source_path, copied_path)
        copied_logs.append(
            {
                'status': 'copied',
                'source_path': str(source_path),
                'copied_path': _relative_or_absolute(copied_path, run_bundle_path),
                'size_bytes': copied_path.stat().st_size,
                'sha256': _sha256_file(copied_path),
            }
        )
    return copied_logs


def _run_status_payload(
    result: ScenarioAttemptResult,
    errors: list[str],
    *,
    strategy: StrategySelection | None,
) -> dict[str, object]:
    return {
        'schema': 'geo-agent.evaluation.run-status.v1',
        'session_id': result.session_id,
        'session_status': result.status,
        'terminal_reason': result.terminal_reason,
        'timed_out': result.timed_out,
        'started_at': result.started_at.isoformat(),
        'finished_at': result.finished_at.isoformat(),
        'duration_seconds': (result.finished_at - result.started_at).total_seconds(),
        'continuation_count': result.continuation_count,
        'clarification_answer_count': result.clarification_answer_count,
        'clarification_question_ids': list(result.clarification_question_ids),
        'error_count': len(errors),
        'errors': errors,
        'strategy': _strategy_reference(strategy),
    }


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
        'subset_tags': list(scenario.subset_tags),
        'hazard_categories': list(scenario.hazard_categories),
        'forbidden_moves': list(scenario.forbidden_moves),
    }


def _variant_reference(variant: VariantManifest | None) -> dict[str, object] | None:
    if variant is None:
        return None
    return {
        'id': variant.id,
        'kind': variant.kind,
        'manifest_path': str(variant.path),
        'manifest_hash': _sha256_file(variant.path),
    }


def _strategy_reference(strategy: StrategySelection | None) -> dict[str, object] | None:
    if strategy is None:
        return None
    return strategy.as_json()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError as exc:
        raise RunBundleCaptureError(f'Missing run bundle file: {path}') from exc
    except json.JSONDecodeError as exc:
        raise RunBundleCaptureError(f'Invalid JSON in run bundle file: {path}') from exc
    if not isinstance(payload, dict):
        raise RunBundleCaptureError(f'Run bundle file is not a JSON object: {path}')
    return payload


def _int_value(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _trace_capture_reference(
    trace_capture: SessionTraceCapture | None,
    bundle_root: Path,
) -> dict[str, object] | None:
    if trace_capture is None:
        return None
    return {
        'session_id': trace_capture.session_id,
        'session_status': trace_capture.session_status,
        'runtime_session_id': trace_capture.runtime_session_id,
        'runtime_trace_path': trace_capture.runtime_trace_path,
        'message_count': trace_capture.message_count,
        'evidence_record_count': trace_capture.evidence_record_count,
        'artifact_count': trace_capture.artifact_count,
        'session_trace_path': _relative_or_absolute(trace_capture.session_trace_path, bundle_root),
        'manifest_path': _relative_or_absolute(trace_capture.manifest_path, bundle_root),
    }


def _session_artifacts(archive: dict[str, Any]) -> list[dict[str, Any]]:
    session = archive.get('session')
    if not isinstance(session, dict):
        return []
    artifacts = session.get('artifacts')
    if not isinstance(artifacts, list):
        return []
    return [artifact for artifact in artifacts if isinstance(artifact, dict)]


def _runtime_trace_path(archive: dict[str, Any]) -> str | None:
    runtime_trace = archive.get('runtime_trace')
    if isinstance(runtime_trace, dict):
        trace_path = _optional_string(runtime_trace.get('trace_path'))
        if trace_path is not None:
            return trace_path
    session = archive.get('session')
    if isinstance(session, dict):
        return _optional_string(session.get('runtime_trace_path'))
    return None


def _resolve_runtime_trace_source(archive: dict[str, Any], trace_path_text: str) -> Path | None:
    trace_path: Path = Path(trace_path_text)
    if trace_path.is_absolute():
        return trace_path
    session = archive.get('session')
    if isinstance(session, dict):
        workspace_path = _optional_string(session.get('workspace_path'))
        if workspace_path is not None:
            return Path(workspace_path) / trace_path
    return None


def _artifact_filename(artifact_id: str, source_path: str | None, index: int) -> str:
    suffix: str = Path(source_path or '').suffix or '.bin'
    return f'{_safe_file_name(artifact_id, f"artifact-{index:03d}")}{suffix}'


def _unique_file_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem: str = path.stem
    suffix: str = path.suffix
    for index in range(2, 1000):
        candidate: Path = path.with_name(f'{stem}-{index:03d}{suffix}')
        if not candidate.exists():
            return candidate
    raise RunBundleCaptureError(f'Could not allocate unique file path under: {path.parent}')


def _safe_file_name(value: str, fallback: str) -> str:
    safe: str = ''.join(
        character if character.isalnum() or character in {'-', '_', '.'} else '-'
        for character in value
    )
    return safe.strip('-_.') or fallback


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _relative_or_absolute(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
