from __future__ import annotations

from argparse import ArgumentParser
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

from app.evaluation.benchmarks import (
    BenchmarkScenario,
    BenchmarkValidationError,
    default_benchmark_root,
    load_benchmark_scenario,
    load_simple_yaml,
    repo_root,
    scenario_paths,
)
from app.evaluation.run_bundles import (
    ARTIFACT_MANIFEST_FILENAME,
    ARTIFACTS_DIRNAME,
    RUN_BUNDLE_SCHEMA,
    RUN_MANIFEST_FILENAME,
    RUN_STATUS_FILENAME,
)


EXTERNAL_EVIDENCE_FILENAME = 'external-evidence.json'
EXTERNAL_EVIDENCE_SCHEMA = 'geo-agent.evaluation.external-evidence.v1'
EXTERNAL_EVIDENCE_PACK_SCHEMA = 'geo-agent.evaluation.external-evidence-pack.v1'
EXTERNAL_FRAMEWORK_RUN_SCHEMA = 'geo-agent.evaluation.external-run-bundle.v1'
EXTERNAL_COMPARISON_SELECTOR_SCHEMA = 'geo-agent.evaluation.external-comparison-selector.v1'
VALID_EXTERNAL_RUN_STATUSES: set[str] = {'completed', 'failed', 'blocked', 'stopped', 'timeout'}
EVIDENCE_KINDS: tuple[str, ...] = ('transcript', 'logs', 'generated_code', 'tool_notes', 'artifacts')
TEXT_EXCERPT_LIMIT = 4000


@dataclass(frozen=True, slots=True)
class ExternalFrameworkManifest:
    id: str
    path: Path
    label: str
    framework_type: str
    expected_execution_mode: str
    zotero_key: str
    citation_note: str
    source_url: str
    paper_url: str
    default_model: str
    runtime_notes: str


@dataclass(frozen=True, slots=True)
class ExternalComparisonSelector:
    id: str
    path: Path
    label: str
    benchmark_root: str
    scenario_selector: str
    scenario_ids: tuple[str, ...]
    framework_ids: tuple[str, ...]
    repeat_count: int
    judge_rubric: str
    notes: str
    scenarios: tuple[BenchmarkScenario, ...] = ()
    frameworks: tuple[ExternalFrameworkManifest, ...] = ()


@dataclass(frozen=True, slots=True)
class ExternalRunStatus:
    status: str
    terminal_reason: str
    timed_out: bool
    duration_seconds: float | None
    started_at: str | None
    finished_at: str | None
    errors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExternalEvidenceFile:
    kind: str
    path: Path
    relative_path: str
    size_bytes: int
    sha256: str
    text_excerpt: str | None

    def as_json(self) -> dict[str, object]:
        return {
            'kind': self.kind,
            'path': self.relative_path,
            'size_bytes': self.size_bytes,
            'sha256': self.sha256,
            'text_excerpt': self.text_excerpt,
        }


@dataclass(frozen=True, slots=True)
class ExternalEvidencePack:
    path: Path
    root: Path
    manifest_hash: str
    framework: ExternalFrameworkManifest
    scenario: BenchmarkScenario
    repeat_index: int
    run_id: str
    original_prompt: str
    dataset_root: str
    dataset_pack: tuple[str, ...]
    dataset_import_notes: str
    run_status: ExternalRunStatus
    model_provider: str | None
    model: str | None
    temperature: float | None
    final_answer_path: Path | None
    final_answer_text: str
    failure_note: str | None
    operator_notes_path: Path | None
    operator_notes_text: str | None
    evidence_files: tuple[ExternalEvidenceFile, ...]


@dataclass(frozen=True, slots=True)
class ImportedExternalRun:
    run_id: str
    bundle_path: Path
    scenario: BenchmarkScenario
    framework: ExternalFrameworkManifest
    evidence_manifest_hash: str


def default_external_framework_root() -> Path:
    return repo_root() / 'app' / 'evaluation_assets' / 'external_frameworks'


def default_external_comparison_root() -> Path:
    return repo_root() / 'app' / 'evaluation_assets' / 'external_comparison'


def load_external_framework_manifest(path: Path) -> ExternalFrameworkManifest:
    payload: dict[str, Any] = load_simple_yaml(path)
    required: tuple[str, ...] = (
        'id',
        'label',
        'framework_type',
        'expected_execution_mode',
        'zotero_key',
        'citation_note',
        'source_url',
        'paper_url',
        'default_model',
        'runtime_notes',
    )
    _require_fields(path, payload, required)
    return ExternalFrameworkManifest(
        id=_as_str(payload, 'id', path),
        path=path,
        label=_as_str(payload, 'label', path),
        framework_type=_as_str(payload, 'framework_type', path),
        expected_execution_mode=_as_str(payload, 'expected_execution_mode', path),
        zotero_key=_as_str(payload, 'zotero_key', path),
        citation_note=_as_str(payload, 'citation_note', path),
        source_url=_as_str(payload, 'source_url', path),
        paper_url=_as_str(payload, 'paper_url', path),
        default_model=_as_str(payload, 'default_model', path),
        runtime_notes=_as_str(payload, 'runtime_notes', path),
    )


def validate_external_framework_manifests(root: Path | None = None) -> tuple[ExternalFrameworkManifest, ...]:
    framework_root: Path = root or default_external_framework_root()
    frameworks: list[ExternalFrameworkManifest] = [
        load_external_framework_manifest(path)
        for path in sorted(framework_root.glob('*.yaml'))
    ]
    if not frameworks:
        raise BenchmarkValidationError(f'No external framework manifests found: {framework_root}')
    seen: set[str] = set()
    for framework in frameworks:
        if framework.id in seen:
            raise BenchmarkValidationError(f'Duplicate external framework id: {framework.id}')
        seen.add(framework.id)
    return tuple(frameworks)


def load_external_comparison_selector(path: Path) -> ExternalComparisonSelector:
    payload: dict[str, Any] = load_simple_yaml(path)
    required: tuple[str, ...] = (
        'id',
        'label',
        'benchmark_root',
        'scenario_selector',
        'scenario_ids',
        'framework_ids',
        'repeat_count',
        'judge_rubric',
        'notes',
    )
    _require_fields(path, payload, required)
    return ExternalComparisonSelector(
        id=_as_str(payload, 'id', path),
        path=path,
        label=_as_str(payload, 'label', path),
        benchmark_root=_as_str(payload, 'benchmark_root', path),
        scenario_selector=_as_str(payload, 'scenario_selector', path),
        scenario_ids=_as_tuple(payload, 'scenario_ids', path),
        framework_ids=_as_tuple(payload, 'framework_ids', path),
        repeat_count=_as_positive_int(payload, 'repeat_count', path),
        judge_rubric=_as_str(payload, 'judge_rubric', path),
        notes=_as_str(payload, 'notes', path),
    )


def validate_external_comparison_selector(
    path: Path,
    *,
    framework_root: Path | None = None,
    benchmark_root: Path | None = None,
) -> ExternalComparisonSelector:
    selector: ExternalComparisonSelector = load_external_comparison_selector(path)
    frameworks_by_id: dict[str, ExternalFrameworkManifest] = {
        framework.id: framework
        for framework in validate_external_framework_manifests(framework_root)
    }
    missing_frameworks: list[str] = [
        framework_id
        for framework_id in selector.framework_ids
        if framework_id not in frameworks_by_id
    ]
    if missing_frameworks:
        missing: str = ', '.join(missing_frameworks)
        raise BenchmarkValidationError(f'{path} references missing external frameworks: {missing}')

    resolved_benchmark_root: Path = benchmark_root or _resolve_repo_path(selector.benchmark_root)
    scenarios: list[BenchmarkScenario] = _load_external_scenarios(resolved_benchmark_root)
    scenario_by_id: dict[str, BenchmarkScenario] = {scenario.id: scenario for scenario in scenarios}
    selected: list[BenchmarkScenario] = []
    for scenario_id in selector.scenario_ids:
        scenario: BenchmarkScenario | None = scenario_by_id.get(scenario_id)
        if scenario is None:
            raise BenchmarkValidationError(f'{path} references missing scenario: {scenario_id}')
        if selector.scenario_selector not in scenario.subset_tags:
            raise BenchmarkValidationError(
                f'{path} scenario {scenario_id} is not in selector tag: {selector.scenario_selector}'
            )
        if scenario.judge_rubric != selector.judge_rubric:
            raise BenchmarkValidationError(f'{path} scenario {scenario_id} uses different judge rubric')
        selected.append(scenario)
    if not 4 <= len(selected) <= 6:
        raise BenchmarkValidationError(f'{path} must select 4-6 scenarios')
    states: set[str] = {scenario.gold_control_state for scenario in selected}
    if states != {'proceed', 'clarify', 'repair', 'stop'}:
        missing: str = ', '.join(sorted({'proceed', 'clarify', 'repair', 'stop'} - states))
        raise BenchmarkValidationError(f'{path} external comparison subset is missing control states: {missing}')
    return ExternalComparisonSelector(
        id=selector.id,
        path=selector.path,
        label=selector.label,
        benchmark_root=selector.benchmark_root,
        scenario_selector=selector.scenario_selector,
        scenario_ids=selector.scenario_ids,
        framework_ids=selector.framework_ids,
        repeat_count=selector.repeat_count,
        judge_rubric=selector.judge_rubric,
        notes=selector.notes,
        scenarios=tuple(selected),
        frameworks=tuple(frameworks_by_id[framework_id] for framework_id in selector.framework_ids),
    )


def validate_external_evidence_pack(
    path: Path,
    *,
    framework_root: Path | None = None,
    benchmark_root: Path | None = None,
) -> ExternalEvidencePack:
    manifest_path: Path = _evidence_manifest_path(path)
    root: Path = manifest_path.parent
    payload: dict[str, Any] = _load_json(manifest_path)
    _require_fields(
        manifest_path,
        payload,
        (
            'schema',
            'framework_id',
            'scenario_id',
            'repeat_index',
            'original_prompt',
            'dataset_root',
            'dataset_pack',
            'run_status',
            'model',
            'evidence',
        ),
    )
    if _as_str(payload, 'schema', manifest_path) != EXTERNAL_EVIDENCE_PACK_SCHEMA:
        raise BenchmarkValidationError(f'{manifest_path} has invalid schema')
    framework: ExternalFrameworkManifest = _framework_by_id(
        _as_str(payload, 'framework_id', manifest_path),
        framework_root,
        manifest_path,
    )
    scenario: BenchmarkScenario = _scenario_by_id(
        _as_str(payload, 'scenario_id', manifest_path),
        benchmark_root,
        manifest_path,
    )
    original_prompt: str = _as_str(payload, 'original_prompt', manifest_path)
    if original_prompt != scenario.user_prompt:
        raise BenchmarkValidationError(f'{manifest_path} prompt does not match scenario {scenario.id}')
    dataset_root: str = _as_str(payload, 'dataset_root', manifest_path)
    dataset_pack: tuple[str, ...] = _as_tuple(payload, 'dataset_pack', manifest_path)
    if dataset_root != scenario.dataset_root:
        raise BenchmarkValidationError(f'{manifest_path} dataset root does not match scenario {scenario.id}')
    if dataset_pack != scenario.dataset_pack:
        raise BenchmarkValidationError(f'{manifest_path} dataset pack does not match scenario {scenario.id}')

    run_status: ExternalRunStatus = _external_run_status(_object(payload.get('run_status')), manifest_path)
    model_payload: dict[str, Any] = _object(payload.get('model'))
    evidence_payload: dict[str, Any] = _object(payload.get('evidence'))
    evidence_files: tuple[ExternalEvidenceFile, ...] = _evidence_files(root, evidence_payload, manifest_path)
    final_answer_path, final_answer_text = _final_answer(root, payload, manifest_path)
    failure_note: str | None = _optional_string(payload.get('failure_note'))
    if not final_answer_text and not failure_note:
        raise BenchmarkValidationError(f'{manifest_path} requires final answer or failure note')
    operator_notes_path, operator_notes_text = _optional_text_file(
        root,
        payload.get('operator_notes_path'),
        manifest_path,
    )
    repeat_index: int = _as_positive_int(payload, 'repeat_index', manifest_path)
    run_id: str = _optional_string(payload.get('run_id')) or f'{framework.id}__{scenario.id}__r{repeat_index:03d}'
    return ExternalEvidencePack(
        path=manifest_path,
        root=root,
        manifest_hash=_sha256_file(manifest_path),
        framework=framework,
        scenario=scenario,
        repeat_index=repeat_index,
        run_id=run_id,
        original_prompt=original_prompt,
        dataset_root=dataset_root,
        dataset_pack=dataset_pack,
        dataset_import_notes=_optional_string(payload.get('dataset_import_notes')) or '',
        run_status=run_status,
        model_provider=_optional_string(model_payload.get('provider')),
        model=_optional_string(model_payload.get('model')),
        temperature=_optional_float(model_payload.get('temperature')),
        final_answer_path=final_answer_path,
        final_answer_text=final_answer_text,
        failure_note=failure_note,
        operator_notes_path=operator_notes_path,
        operator_notes_text=operator_notes_text,
        evidence_files=evidence_files,
    )


def import_external_evidence_pack(
    path: Path,
    campaign_root: Path,
    *,
    framework_root: Path | None = None,
    benchmark_root: Path | None = None,
) -> ImportedExternalRun:
    pack: ExternalEvidencePack = validate_external_evidence_pack(
        path,
        framework_root=framework_root,
        benchmark_root=benchmark_root,
    )
    bundle_path: Path = (
        campaign_root / 'runs' / pack.framework.id / pack.scenario.id / f'repeat-{pack.repeat_index:03d}'
    )
    output_paths: tuple[Path, ...] = (
        bundle_path / RUN_MANIFEST_FILENAME,
        bundle_path / RUN_STATUS_FILENAME,
        bundle_path / ARTIFACT_MANIFEST_FILENAME,
        bundle_path / EXTERNAL_EVIDENCE_FILENAME,
    )
    existing: list[Path] = [item for item in output_paths if item.exists()]
    if existing:
        joined: str = ', '.join(str(item) for item in existing)
        raise BenchmarkValidationError(f'External evidence import would overwrite existing files: {joined}')
    bundle_path.mkdir(parents=True, exist_ok=True)
    _write_json(bundle_path / EXTERNAL_EVIDENCE_FILENAME, _external_evidence_payload(pack, bundle_path))
    _write_json(bundle_path / RUN_STATUS_FILENAME, _run_status_payload(pack))
    _write_json(bundle_path / ARTIFACT_MANIFEST_FILENAME, _artifact_manifest_payload(pack))
    _write_json(bundle_path / RUN_MANIFEST_FILENAME, _run_manifest_payload(pack, bundle_path))
    return ImportedExternalRun(
        run_id=pack.run_id,
        bundle_path=bundle_path,
        scenario=pack.scenario,
        framework=pack.framework,
        evidence_manifest_hash=pack.manifest_hash,
    )


def import_external_evidence_packs(
    path: Path,
    campaign_root: Path,
    *,
    framework_root: Path | None = None,
    benchmark_root: Path | None = None,
) -> tuple[ImportedExternalRun, ...]:
    manifest_paths: list[Path] = (
        [_evidence_manifest_path(path)]
        if _evidence_manifest_path(path).is_file()
        else sorted(path.glob('**/evidence-pack.json'))
    )
    imported: list[ImportedExternalRun] = [
        import_external_evidence_pack(
            manifest_path,
            campaign_root,
            framework_root=framework_root,
            benchmark_root=benchmark_root,
        )
        for manifest_path in manifest_paths
    ]
    return tuple(imported)


def main(argv: Sequence[str] | None = None) -> int:
    parser = ArgumentParser(description='Import external geospatial framework evidence packs.')
    parser.add_argument('evidence_path', type=Path, help='Evidence pack JSON file or directory containing packs.')
    parser.add_argument('campaign_root', type=Path, help='Campaign root receiving imported run bundles.')
    parser.add_argument('--framework-root', type=Path, default=None)
    parser.add_argument('--benchmark-root', type=Path, default=None)
    args = parser.parse_args(argv)

    imported: tuple[ImportedExternalRun, ...] = import_external_evidence_packs(
        args.evidence_path,
        args.campaign_root,
        framework_root=args.framework_root,
        benchmark_root=args.benchmark_root,
    )
    print(
        json.dumps(
            {
                'campaign_root': str(args.campaign_root),
                'imported_count': len(imported),
                'run_ids': [item.run_id for item in imported],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _external_evidence_payload(pack: ExternalEvidencePack, bundle_path: Path) -> dict[str, object]:
    return {
        'schema': EXTERNAL_EVIDENCE_SCHEMA,
        'framework': _framework_reference(pack.framework),
        'scenario': _scenario_reference(pack.scenario),
        'source_evidence_pack': {
            'path': str(pack.path),
            'manifest_hash': pack.manifest_hash,
        },
        'run': {
            'run_id': pack.run_id,
            'repeat_index': pack.repeat_index,
            'status': pack.run_status.status,
            'terminal_reason': pack.run_status.terminal_reason,
            'timed_out': pack.run_status.timed_out,
            'duration_seconds': pack.run_status.duration_seconds,
            'started_at': pack.run_status.started_at,
            'finished_at': pack.run_status.finished_at,
            'errors': list(pack.run_status.errors),
        },
        'model': {
            'provider': pack.model_provider,
            'model': pack.model,
            'temperature': pack.temperature,
        },
        'prompt': pack.original_prompt,
        'dataset': {
            'root': pack.dataset_root,
            'pack': list(pack.dataset_pack),
            'import_notes': pack.dataset_import_notes,
        },
        'final_answer': pack.final_answer_text,
        'failure_note': pack.failure_note,
        'operator_notes': pack.operator_notes_text,
        'evidence_files': [item.as_json() for item in pack.evidence_files],
        'artifact_manifest': _relative_or_absolute(bundle_path / ARTIFACT_MANIFEST_FILENAME, bundle_path),
    }


def _run_status_payload(pack: ExternalEvidencePack) -> dict[str, object]:
    return {
        'schema': 'geo-agent.evaluation.run-status.v1',
        'session_id': f'external:{pack.run_id}',
        'session_status': pack.run_status.status,
        'terminal_reason': pack.run_status.terminal_reason,
        'timed_out': pack.run_status.timed_out,
        'started_at': pack.run_status.started_at,
        'finished_at': pack.run_status.finished_at,
        'duration_seconds': pack.run_status.duration_seconds,
        'continuation_count': 0,
        'clarification_answer_count': 0,
        'clarification_question_ids': [],
        'error_count': len(pack.run_status.errors),
        'errors': list(pack.run_status.errors),
    }


def _artifact_manifest_payload(pack: ExternalEvidencePack) -> dict[str, object]:
    artifacts: list[ExternalEvidenceFile] = [
        item
        for item in pack.evidence_files
        if item.kind == 'artifacts'
    ]
    return {
        'schema': 'geo-agent.evaluation.artifact-capture.v1',
        'session_id': f'external:{pack.run_id}',
        'artifact_count': len(artifacts),
        'items': [
            {
                'id': item.relative_path,
                'title': Path(item.relative_path).name,
                'source_path': str(item.path),
                'copied_path': None,
                'size_bytes': item.size_bytes,
                'sha256': item.sha256,
                'error': None,
            }
            for item in artifacts
        ],
    }


def _run_manifest_payload(pack: ExternalEvidencePack, bundle_path: Path) -> dict[str, object]:
    return {
        'schema': RUN_BUNDLE_SCHEMA,
        'run_bundle_kind': EXTERNAL_FRAMEWORK_RUN_SCHEMA,
        'run_id': pack.run_id,
        'session_id': f'external:{pack.run_id}',
        'scenario': _scenario_reference(pack.scenario),
        'variant': {
            **_framework_reference(pack.framework),
            'kind': 'external-framework',
        },
        'status': {
            'session_status': pack.run_status.status,
            'terminal_reason': pack.run_status.terminal_reason,
            'timed_out': pack.run_status.timed_out,
        },
        'trace_capture': None,
        'runtime_trace': {'status': 'external-evidence-pack'},
        'logs': [
            {
                'path': item.relative_path,
                'source_path': str(item.path),
                'sha256': item.sha256,
            }
            for item in pack.evidence_files
            if item.kind == 'logs'
        ],
        'external_evidence': {
            'file': EXTERNAL_EVIDENCE_FILENAME,
            'path': _relative_or_absolute(bundle_path / EXTERNAL_EVIDENCE_FILENAME, bundle_path),
            'pack_path': str(pack.path),
            'manifest_hash': pack.manifest_hash,
        },
        'files': {
            'run_status': RUN_STATUS_FILENAME,
            'artifact_manifest': ARTIFACT_MANIFEST_FILENAME,
            'artifact_root': ARTIFACTS_DIRNAME,
            'external_evidence': EXTERNAL_EVIDENCE_FILENAME,
        },
        'error_count': len(pack.run_status.errors),
        'errors': list(pack.run_status.errors),
    }


def _framework_reference(framework: ExternalFrameworkManifest) -> dict[str, object]:
    return {
        'id': framework.id,
        'label': framework.label,
        'framework_type': framework.framework_type,
        'expected_execution_mode': framework.expected_execution_mode,
        'zotero_key': framework.zotero_key,
        'citation_note': framework.citation_note,
        'source_url': framework.source_url,
        'paper_url': framework.paper_url,
        'default_model': framework.default_model,
        'manifest_path': str(framework.path),
        'manifest_hash': _sha256_file(framework.path),
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
        'oracle_id': scenario.oracle_id,
        'judge_rubric': scenario.judge_rubric,
        'subset_tags': list(scenario.subset_tags),
        'hazard_categories': list(scenario.hazard_categories),
    }


def _external_run_status(payload: dict[str, Any], path: Path) -> ExternalRunStatus:
    _require_fields(path, payload, ('status', 'terminal_reason', 'timed_out'))
    if 'errors' not in payload:
        raise BenchmarkValidationError(f'{path} is missing required fields: errors')
    status: str = _as_str(payload, 'status', path)
    if status not in VALID_EXTERNAL_RUN_STATUSES:
        allowed: str = ', '.join(sorted(VALID_EXTERNAL_RUN_STATUSES))
        raise BenchmarkValidationError(f'{path} has invalid external run status: {status}; expected one of {allowed}')
    return ExternalRunStatus(
        status=status,
        terminal_reason=_as_str(payload, 'terminal_reason', path),
        timed_out=_as_bool(payload, 'timed_out', path),
        duration_seconds=_optional_float(payload.get('duration_seconds')),
        started_at=_optional_string(payload.get('started_at')),
        finished_at=_optional_string(payload.get('finished_at')),
        errors=_as_tuple({'errors': payload.get('errors', ())}, 'errors', path),
    )


def _evidence_files(root: Path, payload: dict[str, Any], manifest_path: Path) -> tuple[ExternalEvidenceFile, ...]:
    files: list[ExternalEvidenceFile] = []
    for kind in EVIDENCE_KINDS:
        for relative_path in _optional_tuple(payload, kind, manifest_path):
            candidate: Path = _pack_file(root, relative_path, manifest_path)
            files.append(
                ExternalEvidenceFile(
                    kind=kind,
                    path=candidate,
                    relative_path=relative_path,
                    size_bytes=candidate.stat().st_size,
                    sha256=_sha256_file(candidate),
                    text_excerpt=_text_excerpt(candidate),
                )
            )
    if not files:
        raise BenchmarkValidationError(f'{manifest_path} requires at least one external evidence file')
    return tuple(files)


def _final_answer(root: Path, payload: dict[str, Any], manifest_path: Path) -> tuple[Path | None, str]:
    text: str = _optional_string(payload.get('final_answer')) or ''
    final_answer_path_value = payload.get('final_answer_path')
    if final_answer_path_value is None or final_answer_path_value == '':
        return None, text
    final_answer_path: Path = _pack_file(root, str(final_answer_path_value), manifest_path)
    return final_answer_path, final_answer_path.read_text(encoding='utf-8').strip()


def _optional_text_file(root: Path, value: object, manifest_path: Path) -> tuple[Path | None, str | None]:
    if not isinstance(value, str) or not value:
        return None, None
    path: Path = _pack_file(root, value, manifest_path)
    return path, path.read_text(encoding='utf-8').strip()


def _pack_file(root: Path, relative_path: str, manifest_path: Path) -> Path:
    if not relative_path:
        raise BenchmarkValidationError(f'{manifest_path} has empty evidence file path')
    candidate: Path = (root / relative_path).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise BenchmarkValidationError(f'{manifest_path} evidence file escapes pack root: {relative_path}') from exc
    if not candidate.exists():
        raise BenchmarkValidationError(f'{manifest_path} references missing evidence file: {relative_path}')
    if not candidate.is_file():
        raise BenchmarkValidationError(f'{manifest_path} evidence path is not a file: {relative_path}')
    return candidate


def _framework_by_id(
    framework_id: str,
    framework_root: Path | None,
    path: Path,
) -> ExternalFrameworkManifest:
    for framework in validate_external_framework_manifests(framework_root):
        if framework.id == framework_id:
            return framework
    raise BenchmarkValidationError(f'{path} references missing external framework: {framework_id}')


def _scenario_by_id(
    scenario_id: str,
    benchmark_root: Path | None,
    path: Path,
) -> BenchmarkScenario:
    for scenario in _load_external_scenarios(benchmark_root or default_benchmark_root()):
        if scenario.id == scenario_id:
            return scenario
    raise BenchmarkValidationError(f'{path} references missing scenario: {scenario_id}')


def _load_external_scenarios(benchmark_root: Path) -> list[BenchmarkScenario]:
    return [
        load_benchmark_scenario(path)
        for path in scenario_paths(benchmark_root)
    ]


def _evidence_manifest_path(path: Path) -> Path:
    return path / 'evidence-pack.json' if path.is_dir() else path


def _resolve_repo_path(value: str) -> Path:
    path: Path = Path(value)
    return path if path.is_absolute() else repo_root() / path


def _require_fields(path: Path, payload: dict[str, Any], fields: tuple[str, ...]) -> None:
    missing: list[str] = [
        field
        for field in fields
        if field not in payload or payload[field] in ('', (), [], None)
    ]
    if missing:
        raise BenchmarkValidationError(f'{path} is missing required fields: {", ".join(missing)}')


def _as_str(payload: dict[str, Any], field: str, path: Path) -> str:
    value: Any = payload[field]
    if not isinstance(value, str):
        raise BenchmarkValidationError(f'{path} field {field} must be a string')
    return value


def _as_tuple(payload: dict[str, Any], field: str, path: Path) -> tuple[str, ...]:
    value: Any = payload[field]
    if isinstance(value, tuple) and all(isinstance(item, str) for item in value):
        return value
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return tuple(value)
    if isinstance(value, str):
        return (value,)
    raise BenchmarkValidationError(f'{path} field {field} must be a list of strings')


def _optional_tuple(payload: dict[str, Any], field: str, path: Path) -> tuple[str, ...]:
    if field not in payload or payload[field] in ('', (), [], None):
        return ()
    return _as_tuple(payload, field, path)


def _as_positive_int(payload: dict[str, Any], field: str, path: Path) -> int:
    value: Any = payload[field]
    if isinstance(value, bool):
        raise BenchmarkValidationError(f'{path} field {field} must be a positive integer')
    if isinstance(value, int):
        resolved: int = value
    elif isinstance(value, float) and value.is_integer():
        resolved = int(value)
    else:
        raise BenchmarkValidationError(f'{path} field {field} must be a positive integer')
    if resolved <= 0:
        raise BenchmarkValidationError(f'{path} field {field} must be positive')
    return resolved


def _as_bool(payload: dict[str, Any], field: str, path: Path) -> bool:
    value: Any = payload[field]
    if not isinstance(value, bool):
        raise BenchmarkValidationError(f'{path} field {field} must be a boolean')
    return value


def _optional_string(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _optional_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _object(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _load_json(path: Path) -> dict[str, Any]:
    payload: object = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise BenchmarkValidationError(f'{path} must contain a JSON object')
    return payload


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _text_excerpt(path: Path) -> str | None:
    try:
        text: str = path.read_text(encoding='utf-8').strip()
    except UnicodeDecodeError:
        return None
    if len(text) <= TEXT_EXCERPT_LIMIT:
        return text
    suffix = '\n[truncated]'
    return text[: max(0, TEXT_EXCERPT_LIMIT - len(suffix))] + suffix


def _relative_or_absolute(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


if __name__ == '__main__':
    raise SystemExit(main())
