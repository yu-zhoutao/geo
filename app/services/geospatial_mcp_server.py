from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import UTC, datetime
from html import escape
import json
import os
from pathlib import Path
import sys
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastmcp import Context, FastMCP
from pydantic import BaseModel, ConfigDict, Field

from app.config import Settings, get_settings
from app.models import AnalysisType, Artifact, GeospatialSessionContext
from app.services.geospatial_runtime import (
    SUPPORTED_ARTIFACT_FORMATS,
    SUPPORTED_DISPLAY_HINTS,
    geospatial_environment_variables,
    geospatial_python_command,
    geospatial_python_command_display,
    package_readiness,
    repo_root,
    workspace_layout,
)
from app.services.artifacts import upsert_artifact_by_path
from app.services.session_store import SessionStore

GEOSPATIAL_MCP_SERVER_NAME = 'geospatial'
GEOSPATIAL_MCP_SERVER_TITLE = 'Application-managed geospatial MCP server'
GEOSPATIAL_MCP_MODULE = 'app.services.geospatial_mcp_server'
EVIDENCE_RECORD_TYPES = {'artifact', 'dataset_profile', 'verification_fact', 'parameter_snapshot', 'claim_trace'}
ARTIFACT_STAGES = {'intermediate', 'final'}
WORKFLOW_CONTROL_FIELDS = {'plan', 'plans', 'steps', 'workflow', 'operator_sequence', 'execution_plan'}
TODO_STATUSES = {'pending', 'in_progress', 'completed', 'blocked'}
AGENT_PYTHON_COMMAND = '"$GEO_AGENT_UV_BIN" --project "$GEO_AGENT_GEO_PYTHON_PROJECT" run --python "$GEO_AGENT_GEO_PYTHON_VERSION" python <script>'
PREVIEW_HINT_FORMATS: dict[str, set[str]] = {
    'image': {'png', 'jpg', 'svg'},
    'map': {'png', 'jpg', 'svg', 'html'},
    'table': {'csv', 'tsv'},
    'markdown': {'md', 'txt'},
    'text': {'txt', 'md', 'csv', 'tsv'},
    'html': {'html'},
}
OPEN_ONLY_DISPLAY_HINTS = {'download', 'other'}
TodoStatus = Literal['pending', 'in_progress', 'completed', 'blocked']
EvidenceRecordType = Literal['artifact', 'dataset_profile', 'verification_fact', 'parameter_snapshot', 'claim_trace']
ArtifactFormat = Literal[
    'png',
    'jpg',
    'svg',
    'html',
    'md',
    'pdf',
    'csv',
    'tsv',
    'json',
    'geojson',
    'parquet',
    'gpkg',
    'shp',
    'tif',
    'txt',
    'zip',
    'other',
]
ArtifactStage = Literal['intermediate', 'final']
DisplayHint = Literal['image', 'map', 'table', 'markdown', 'json', 'text', 'html', 'download', 'other']
SessionContextIdParameter = Annotated[
    str | None,
    Field(
        description=(
            'Optional opaque backend-owned session context id returned by get_session_context. '
            'Usually omit this after the first context lookup because the MCP session is bound automatically.'
        ),
    ),
]
EvidenceDataParameter = Annotated[
    dict[str, Any] | None,
    Field(
        description=(
            'Optional machine-readable evidence payload. Use this for dataset_profile, verification_fact, '
            'parameter_snapshot, and claim_trace records. Do not include workflow control fields such as plan, '
            'steps, workflow, or operator_sequence.'
        ),
    ),
]
EvidenceRecordTypeParameter = Annotated[
    EvidenceRecordType,
    Field(
        description=(
            'Evidence record kind. Use artifact only for a durable file that already exists in the workspace. '
            'Use dataset_profile for data inspection metadata, verification_fact for CRS/bbox/quality checks, '
            'parameter_snapshot for method settings, and claim_trace for final claim-to-evidence linkage.'
        ),
    ),
]
EvidenceTitleParameter = Annotated[
    str,
    Field(
        min_length=1,
        description='Human-readable evidence title shown in the transcript and artifact list.',
    ),
]
ArtifactPathParameter = Annotated[
    str | None,
    Field(
        description=(
            'Required when record_type is artifact. Workspace-relative or absolute path to a file that has '
            'already been written inside the managed workspace, such as outputs/kde-map.png.'
        ),
    ),
]
ArtifactFormatParameter = Annotated[
    ArtifactFormat | None,
    Field(
        description=(
            'Required when record_type is artifact. File format extension without a dot; choose previewable '
            'human-readable values such as png, html, md, csv, tsv, or txt for outputs the UI can show. '
            'Use other for JSON, GeoTIFF, GeoPackage, shapefile data, rasters, archives, binaries, or unknown '
            'machine-readable files that should be open-only.'
        ),
    ),
]
ArtifactStageParameter = Annotated[
    ArtifactStage | None,
    Field(
        description=(
            'Required when record_type is artifact. Use intermediate for process evidence, diagnostics, audit '
            'outputs, and parameter files; use final only for user-facing deliverables.'
        ),
    ),
]
DisplayHintParameter = Annotated[
    DisplayHint | None,
    Field(
        description=(
            'Required when record_type is artifact. UI rendering hint: image/map/table/markdown/text/html for '
            'previewable human-readable files. Use other or download for open-only files, including JSON, gpkg, '
            'tif, zip, shp, parquet, archives, rasters, and binaries.'
        ),
    ),
]
EvidenceCategoryParameter = Annotated[
    str | None,
    Field(
        description=(
            'Optional short grouping label such as map, raster, report, metadata, prepared, verification, table, '
            'dataset, image, html, json, text, archive, audit, or spatial-prep.'
        ),
    ),
]
AnalysisTypeParameter = Annotated[
    AnalysisType | None,
    Field(
        description=(
            'Optional task family for routing and recovery metadata. Supported families include kde, '
            'spatial_interpolation, spatial_hotspot, land_cover_change, spatiotemporal_pattern, '
            'time_series_trend, terrain_analysis, and unsupervised_clustering.'
        ),
    ),
]
EvidenceDescriptionParameter = Annotated[
    str | None,
    Field(
        description='Optional concise description explaining what the evidence proves or why the artifact matters.',
    ),
]
EvidenceProvenanceParameter = Annotated[
    dict[str, Any] | None,
    Field(
        description=(
            'Optional provenance object. Prefer script_path, command, inputs, parameters, crs, bbox, and '
            'runtime notes. Do not include workflow control fields such as plan, steps, workflow, or operator_sequence.'
        ),
    ),
]


class TodoEntry(BaseModel):
    model_config = ConfigDict(extra='forbid')

    content: str = Field(
        min_length=1,
        description=(
            'Visible todo text. Use content, not task. Keep this as one concise agent-authored action such as '
            '"检查 CRS" or "记录最终地图".'
        ),
    )
    status: TodoStatus = Field(
        default='pending',
        description=(
            'Current item state. Use pending for not started, in_progress for the current active item, '
            'completed for finished work, and blocked only when execution is waiting on an unresolved blocker.'
        ),
    )
    id: str | None = Field(
        default=None,
        description='Optional stable todo id. Omit it unless you are updating a previously published item.',
    )


def build_geospatial_mcp_environment() -> dict[str, str]:
    root = repo_root()
    current = os.environ.get('PYTHONPATH')
    pythonpath = str(root) if not current else os.pathsep.join([str(root), current])
    return {'PYTHONPATH': pythonpath}


def build_geospatial_mcp_command(settings: Settings) -> list[str]:
    return [
        sys.executable,
        '-m',
        GEOSPATIAL_MCP_MODULE,
        '--state-dir',
        str(settings.state_dir.expanduser().resolve()),
        '--app-support-dir',
        str(settings.resolved_app_support_dir().expanduser().resolve()),
        '--database-path',
        str(settings.resolved_database_path().expanduser().resolve()),
        '--workspace-root',
        str(settings.resolved_workspace_root().expanduser().resolve()),
        '--geospatial-python-project',
        str(settings.resolved_geospatial_python_project().expanduser().resolve()),
        '--geospatial-python-version',
        settings.geospatial_python_version,
    ]


def build_geospatial_mcp_config(settings: Settings | None = None) -> dict[str, Any]:
    resolved = settings or get_settings()
    return {
        'type': 'local',
        'enabled': True,
        'command': build_geospatial_mcp_command(resolved),
        'environment': build_geospatial_mcp_environment(),
    }


def list_geospatial_mcp_capabilities() -> list[dict[str, object]]:
    return [
        {
            'id': GEOSPATIAL_MCP_SERVER_NAME,
            'title': GEOSPATIAL_MCP_SERVER_TITLE,
            'transport': 'local stdio MCP',
            'tools': [
                'get_session_context',
                'update_todos',
                'record_run_evidence',
            ],
        }
    ]


def _tool_descriptor(*, name: str, family: str) -> dict[str, str]:
    return {
        'name': name,
        'family': family,
    }


def _context_store(settings: Settings) -> SessionStore:
    return SessionStore(settings=settings)


def _resolve_session_context(
    *,
    settings: Settings,
    session_context_id: str | None,
    mcp_session_id: str | None,
) -> GeospatialSessionContext | None:
    store = _context_store(settings)
    context = store.load_geospatial_session_context(session_context_id)
    if context is None:
        context = store.load_geospatial_session_context_by_mcp_session(mcp_session_id)
    if context is None and session_context_id is None:
        context = store.load_latest_geospatial_session_context()
    if context is not None and mcp_session_id is not None and context.mcp_session_id != mcp_session_id:
        context.mcp_session_id = mcp_session_id
        context.updated_at = datetime.now(UTC)
        store.save_geospatial_session_context(context)
    return context


def _failure(
    *,
    tool_name: str,
    family: str,
    summary: str,
    reason: str,
    session_context_id: str | None = None,
    path: str | None = None,
    workspace: str | None = None,
    fix: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        'status': 'failed',
        'summary': summary,
        'tool': _tool_descriptor(name=tool_name, family=family),
        'reason': reason,
    }
    if session_context_id is not None:
        payload['session_context_id'] = session_context_id
    if path is not None:
        payload['path'] = path
    if workspace is not None:
        payload['workspace'] = workspace
    if fix is not None:
        payload['fix'] = fix
    return payload


def _xml_text(value: object) -> str:
    return escape(str(value), quote=False)


def _xml_attr(value: object) -> str:
    return escape(str(value), quote=True)


def _format_error_output(payload: dict[str, Any]) -> str:
    tool = payload.get('tool')
    tool_name = tool.get('name') if isinstance(tool, dict) else 'geospatial'
    lines = [
        f'<error tool="{_xml_attr(tool_name)}" reason="{_xml_attr(payload.get("reason", "unknown"))}">',
        f'  <message>{_xml_text(payload.get("summary", "The tool call failed."))}</message>',
    ]
    if payload.get('path') is not None:
        lines.append(f'  <path>{_xml_text(payload["path"])}</path>')
    if payload.get('workspace') is not None:
        lines.append(f'  <workspace>{_xml_text(payload["workspace"])}</workspace>')
    if payload.get('fix') is not None:
        lines.append(f'  <fix>{_xml_text(payload["fix"])}</fix>')
    lines.append('</error>')
    return '\n'.join(lines)


def format_get_session_context_output(payload: dict[str, Any]) -> str:
    if payload.get('status') != 'completed':
        return _format_error_output(payload)

    package_readiness_payload = payload.get('package_readiness')
    package_readiness_status = package_readiness_payload.get('status') if isinstance(package_readiness_payload, dict) else 'unknown'
    workspace = payload.get('workspace')
    workspace_path = workspace.get('root') if isinstance(workspace, dict) else ''
    attached_data = [item for item in payload.get('attached_data', []) if isinstance(item, dict) and item.get('enabled', True)]
    lines = [
        '<context status="completed">',
        f'  <workspace>{_xml_text(workspace_path)}</workspace>',
        '  <python>',
        f'    <status>{_xml_text(package_readiness_status)}</status>',
        f'    <command>{_xml_text(AGENT_PYTHON_COMMAND)}</command>',
    ]
    if package_readiness_status != 'ready' and isinstance(package_readiness_payload, dict):
        validation = package_readiness_payload.get('validation')
        if isinstance(validation, dict):
            missing_packages = validation.get('missing_packages')
            if isinstance(missing_packages, list) and missing_packages:
                lines.append(f'    <missing>{_xml_text(", ".join(str(item) for item in missing_packages))}</missing>')
    lines.extend(
        [
            '  </python>',
            '  <data>',
        ]
    )
    if attached_data:
        for item in attached_data:
            label = item.get('label')
            label_attr = f' label="{_xml_attr(label)}"' if label else ''
            lines.append(f'    <directory enabled="true"{label_attr}>{_xml_text(item.get("path", ""))}</directory>')
    else:
        lines.append('    <none>No enabled attached data directories.</none>')
    lines.extend(
        [
            '  </data>',
            '  <reporting>Write files under the workspace. Register each durable output with record_run_evidence; paths may be workspace-relative or absolute inside the workspace.</reporting>',
            '</context>',
        ]
    )
    return '\n'.join(lines)


def format_record_run_evidence_output(payload: dict[str, Any]) -> str:
    if payload.get('status') != 'completed':
        return _format_error_output(payload)

    artifact = payload.get('artifact')
    title = payload.get('title')
    if isinstance(artifact, dict):
        title = artifact.get('title', title)
    record_type = payload.get('record_type', 'evidence')
    lines = [
        f'<evidence status="recorded" type="{_xml_attr(record_type)}">',
        f'  <record_id>{_xml_text(payload.get("record_id", ""))}</record_id>',
        f'  <title>{_xml_text(title or "Untitled evidence")}</title>',
    ]
    if isinstance(artifact, dict):
        lines.extend(
            [
                f'  <path>{_xml_text(artifact.get("path", ""))}</path>',
                f'  <stage>{_xml_text(artifact.get("artifact_stage", ""))}</stage>',
                f'  <display>{_xml_text(artifact.get("display_hint", ""))}</display>',
                '  <message>Artifact registered for the UI.</message>',
            ]
        )
    else:
        lines.append('  <message>Evidence record stored.</message>')
    lines.append('</evidence>')
    return '\n'.join(lines)


def format_update_todos_output(payload: dict[str, Any]) -> str:
    if payload.get('status') != 'completed':
        return _format_error_output(payload)

    entries = [entry for entry in payload.get('entries', []) if isinstance(entry, dict)]
    lines = [
        '<todos status="updated">',
        f'  <count>{len(entries)}</count>',
    ]
    for entry in entries:
        lines.append(f'  <item status="{_xml_attr(entry.get("status", "pending"))}">{_xml_text(entry.get("label", ""))}</item>')
    lines.extend(
        [
            '  <message>待办列表已登记到界面。</message>',
            '</todos>',
        ]
    )
    return '\n'.join(lines)


def _attached_data_payload(context: GeospatialSessionContext) -> list[dict[str, Any]]:
    return [item.model_dump(mode='json') for item in context.attached_data_directories]


def _environment_payload(*, settings: Settings, context: GeospatialSessionContext) -> dict[str, Any]:
    variables = geospatial_environment_variables(
        settings=settings,
        workspace_path=context.workspace_path,
        session_context_id=context.id,
    )
    variables['GEO_AGENT_ATTACHED_DATA_DIRS_JSON'] = json.dumps(_attached_data_payload(context), ensure_ascii=False)
    return {
        'variables': variables,
        'recommended_command': geospatial_python_command(settings),
        'recommended_command_display': geospatial_python_command_display(settings),
    }


def get_session_context_payload(
    *,
    session_context_id: str | None = None,
    mcp_session_id: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    resolved = settings or get_settings()
    context = _resolve_session_context(settings=resolved, session_context_id=session_context_id, mcp_session_id=mcp_session_id)
    if context is None:
        return _failure(
            tool_name='get_session_context',
            family='context',
            summary='未找到对应的地理会话上下文。',
            reason='missing_session_context',
            session_context_id=session_context_id,
        )

    layout = workspace_layout(context.workspace_path)
    store = _context_store(resolved)
    records = store.list_geospatial_evidence_records(context.id)
    artifacts = [artifact.model_dump(mode='json') for artifact in context.artifacts]
    return {
        'status': 'completed',
        'summary': '已读取当前地理会话上下文。',
        'tool': _tool_descriptor(name='get_session_context', family='context'),
        'session_context_id': context.id,
        'session_context': context.model_dump(mode='json'),
        'workspace': layout,
        'attached_data': _attached_data_payload(context),
        'environment': _environment_payload(settings=resolved, context=context),
        'package_readiness': package_readiness(resolved),
        'evidence': {
            'records': records,
            'record_count': len(records),
        },
        'artifacts': artifacts,
    }


def _normalized_todo_entries(entries: list[dict[str, Any]]) -> tuple[list[dict[str, str]], list[str]]:
    normalized: list[dict[str, str]] = []
    errors: list[str] = []
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            errors.append(f'第 {index} 项必须是对象')
            continue
        raw_label = entry.get('content') if isinstance(entry.get('content'), str) else entry.get('label')
        if not isinstance(raw_label, str) or not raw_label.strip():
            errors.append(f'第 {index} 项需要非空 content 或 label')
            continue
        raw_status = entry.get('status', 'pending')
        if raw_status not in TODO_STATUSES:
            errors.append(f'第 {index} 项 status 必须是 {", ".join(sorted(TODO_STATUSES))} 之一')
            continue
        raw_id = entry.get('id')
        entry_id = raw_id.strip() if isinstance(raw_id, str) and raw_id.strip() else f'todo-{index}'
        normalized.append({'id': entry_id, 'label': raw_label.strip(), 'status': str(raw_status)})
    return normalized, errors


def update_todos_payload(
    *,
    entries: list[dict[str, Any]],
    title: str | None = None,
    session_context_id: str | None = None,
    mcp_session_id: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    resolved = settings or get_settings()
    if session_context_id is not None or mcp_session_id is not None:
        context = _resolve_session_context(settings=resolved, session_context_id=session_context_id, mcp_session_id=mcp_session_id)
        if context is None:
            return _failure(
                tool_name='update_todos',
                family='planning',
                summary='未找到对应的地理会话上下文，无法登记待办。',
                reason='missing_session_context',
                session_context_id=session_context_id,
                fix='先调用 get_session_context 绑定当前会话，再在同一个地理会话中重试 update_todos。',
            )
    if not isinstance(entries, list):
        return _failure(
            tool_name='update_todos',
            family='planning',
            summary='待办条目必须是列表。',
            reason='invalid_todo_entries',
            session_context_id=session_context_id,
            fix='请把 entries 传为对象列表，每项包含 content 或 label，并可包含 status。',
        )

    normalized_entries, errors = _normalized_todo_entries(entries)
    if errors:
        return _failure(
            tool_name='update_todos',
            family='planning',
            summary=f'待办条目格式不正确：{errors[0]}。',
            reason='invalid_todo_entries',
            session_context_id=session_context_id,
            fix='请使用类似 [{"content": "检查 CRS", "status": "pending"}] 的 entries，status 只能是 pending、in_progress、completed 或 blocked。',
        )

    normalized_title = title.strip() if isinstance(title, str) and title.strip() else '当前待办'
    return {
        'status': 'completed',
        'summary': '已更新当前待办。',
        'tool': _tool_descriptor(name='update_todos', family='planning'),
        'title': normalized_title,
        'entries': normalized_entries,
    }


def _has_workflow_control_fields(data: dict[str, Any] | None, provenance: dict[str, Any] | None) -> bool:
    payloads = [payload for payload in (data, provenance) if payload]
    return any(any(field in payload for field in WORKFLOW_CONTROL_FIELDS) for payload in payloads)


def _path_inside(parent: Path, child: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def _normalized_artifact_path(*, raw_path: str, context: GeospatialSessionContext) -> Path:
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = Path(context.workspace_path) / candidate
    return candidate.resolve()


def _allowed_artifact_path(path: Path, context: GeospatialSessionContext) -> bool:
    workspace = Path(context.workspace_path).resolve()
    return _path_inside(workspace, path)


def _workspace_relative_artifact_path(path: Path, context: GeospatialSessionContext) -> str:
    return path.relative_to(Path(context.workspace_path).resolve()).as_posix()


def _display_hint_supported_for_format(format: str, display_hint: str) -> bool:
    if display_hint in OPEN_ONLY_DISPLAY_HINTS:
        return True
    if display_hint == 'json':
        return format in {'json', 'geojson', 'other'}
    return format in PREVIEW_HINT_FORMATS.get(display_hint, set())


def _artifact_kind(category: str | None, display_hint: str | None) -> str | None:
    if category in {'manifest', 'map', 'raster', 'report', 'metadata', 'prepared', 'verification', 'table', 'dataset', 'image', 'html', 'json', 'text', 'archive', 'other'}:
        return category
    if display_hint == 'image':
        return 'image'
    if display_hint == 'table':
        return 'table'
    if display_hint == 'html':
        return 'html'
    if display_hint == 'json':
        return 'json'
    if display_hint == 'text':
        return 'text'
    if display_hint in {'download', 'other'}:
        return 'other'
    return 'metadata'


def _sync_artifact_to_session_store(*, settings: Settings, context: GeospatialSessionContext, artifact: Artifact) -> None:
    store = _context_store(settings)
    context.artifacts = upsert_artifact_by_path(context.artifacts, artifact)
    context.updated_at = datetime.now(UTC)
    store.save_geospatial_session_context(context)
    session = store.load_session(context.session_id)
    if session is None:
        return
    session.artifacts = upsert_artifact_by_path(session.artifacts, artifact)
    session.updated_at = datetime.now(UTC)
    store.save_session(session)


def record_run_evidence_payload(
    *,
    record_type: str,
    title: str,
    session_context_id: str | None = None,
    mcp_session_id: str | None = None,
    path: str | None = None,
    format: str | None = None,
    artifact_stage: str | None = None,
    display_hint: str | None = None,
    category: str | None = None,
    analysis_type: AnalysisType | None = None,
    description: str | None = None,
    provenance: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    resolved = settings or get_settings()
    normalized_record_type = record_type.strip()
    if normalized_record_type not in EVIDENCE_RECORD_TYPES:
        return _failure(
            tool_name='record_run_evidence',
            family='evidence',
            summary='证据记录类型不受支持。',
            reason='unsupported_evidence_record_type',
            session_context_id=session_context_id,
            fix=f'Use one supported record_type value: {", ".join(sorted(EVIDENCE_RECORD_TYPES))}.',
        )
    if not title.strip():
        return _failure(
            tool_name='record_run_evidence',
            family='evidence',
            summary='证据记录缺少标题。',
            reason='missing_evidence_title',
            session_context_id=session_context_id,
        )
    if _has_workflow_control_fields(data, provenance):
        return _failure(
            tool_name='record_run_evidence',
            family='evidence',
            summary='证据工具不能写入工作流控制字段。',
            reason='workflow_control_fields_not_allowed',
            session_context_id=session_context_id,
        )

    context = _resolve_session_context(settings=resolved, session_context_id=session_context_id, mcp_session_id=mcp_session_id)
    if context is None:
        return _failure(
            tool_name='record_run_evidence',
            family='evidence',
            summary='未找到对应的地理会话上下文。',
            reason='missing_session_context',
            session_context_id=session_context_id,
        )

    layout = workspace_layout(context.workspace_path)
    workspace_path = layout['root']
    record_id = f'evidence-{uuid4().hex[:8]}'
    now = datetime.now(UTC).isoformat()
    evidence_data = dict(data or {})
    if analysis_type is not None and 'analysis_type' not in evidence_data:
        evidence_data['analysis_type'] = analysis_type
    base_record: dict[str, Any] = {
        'id': record_id,
        'record_type': normalized_record_type,
        'title': title.strip(),
        'description': description,
        'category': category,
        'analysis_type': analysis_type,
        'session_context_id': context.id,
        'created_at': now,
        'provenance': provenance or {},
        'data': evidence_data,
    }

    artifact_payload: dict[str, Any] | None = None
    if normalized_record_type == 'artifact':
        if path is None or not path.strip():
            return _failure(
                tool_name='record_run_evidence',
                family='evidence',
                summary='产物证据缺少文件路径。',
                reason='missing_artifact_path',
                session_context_id=context.id,
                workspace=workspace_path,
                fix='Create the artifact file inside the workspace, then call record_run_evidence with its relative path.',
            )
        if format not in SUPPORTED_ARTIFACT_FORMATS:
            return _failure(
                tool_name='record_run_evidence',
                family='evidence',
                summary='产物格式不受支持。',
                reason='unsupported_artifact_format',
                session_context_id=context.id,
                path=path,
                workspace=workspace_path,
                fix=f'Use one supported format value: {", ".join(sorted(SUPPORTED_ARTIFACT_FORMATS))}.',
            )
        if artifact_stage not in ARTIFACT_STAGES:
            return _failure(
                tool_name='record_run_evidence',
                family='evidence',
                summary='产物阶段必须为 intermediate 或 final。',
                reason='unsupported_artifact_stage',
                session_context_id=context.id,
                path=path,
                workspace=workspace_path,
                fix=f'Set artifact_stage to one supported value: {", ".join(sorted(ARTIFACT_STAGES))}.',
            )
        if display_hint not in SUPPORTED_DISPLAY_HINTS:
            return _failure(
                tool_name='record_run_evidence',
                family='evidence',
                summary='产物显示方式不受支持。',
                reason='unsupported_display_hint',
                session_context_id=context.id,
                path=path,
                workspace=workspace_path,
                fix=f'Use one supported display_hint value: {", ".join(sorted(SUPPORTED_DISPLAY_HINTS))}.',
            )
        if not _display_hint_supported_for_format(format, display_hint):
            return _failure(
                tool_name='record_run_evidence',
                family='evidence',
                summary='产物显示方式与文件格式不匹配。',
                reason='unsupported_display_hint_for_format',
                session_context_id=context.id,
                path=path,
                workspace=workspace_path,
                fix='Choose a previewable human-readable display_hint for this format, or register the file as open-only with display_hint=other or download.',
            )
        artifact_path = _normalized_artifact_path(raw_path=path, context=context)
        if not _allowed_artifact_path(artifact_path, context):
            return _failure(
                tool_name='record_run_evidence',
                family='evidence',
                summary='产物路径不在托管工作区范围内。',
                reason='artifact_path_outside_workspace',
                session_context_id=context.id,
                path=path,
                workspace=workspace_path,
                fix='Move or write the file inside the workspace, then retry with a workspace-relative path.',
            )
        if not artifact_path.exists():
            return _failure(
                tool_name='record_run_evidence',
                family='evidence',
                summary='产物文件不存在。',
                reason='artifact_path_missing',
                session_context_id=context.id,
                path=path,
                workspace=workspace_path,
                fix='Write the file first, verify the path, then call record_run_evidence again.',
            )
        relative_artifact_path = _workspace_relative_artifact_path(artifact_path, context)

        artifact = Artifact(
            id=f'artifact-{uuid4().hex[:8]}',
            title=title.strip(),
            path=relative_artifact_path,
            kind=_artifact_kind(category, display_hint),
            analysis_type=analysis_type,
            description=description,
            format=format,
            artifact_stage=artifact_stage,
            display_hint=display_hint,
            evidence_record_id=record_id,
            provenance=provenance or {},
        )
        artifact_payload = artifact.model_dump(mode='json')
        base_record.update(artifact_payload)
        _sync_artifact_to_session_store(settings=resolved, context=context, artifact=artifact)
    else:
        context.updated_at = datetime.now(UTC)
        _context_store(resolved).save_geospatial_session_context(context)

    _context_store(resolved).append_geospatial_evidence_record(base_record)
    return {
        'status': 'completed',
        'summary': '已记录运行证据。',
        'tool': _tool_descriptor(name='record_run_evidence', family='evidence'),
        'session_context_id': context.id,
        'record_id': record_id,
        'record_type': normalized_record_type,
        'title': title.strip(),
        'description': description,
        'category': category,
        'analysis_type': analysis_type,
        'evidence': base_record,
        'artifact': artifact_payload,
    }


def build_geospatial_mcp_server(settings: Settings | None = None):
    resolved = settings or get_settings()
    mcp = FastMCP(GEOSPATIAL_MCP_SERVER_TITLE)

    @mcp.tool()
    def get_session_context(
        session_context_id: SessionContextIdParameter = None,
        ctx: Context | None = None,
    ) -> str:
        """Inspect the active geospatial session context before reading inputs, writing scripts, or recording evidence."""

        return format_get_session_context_output(
            get_session_context_payload(
                session_context_id=session_context_id,
                mcp_session_id=ctx.session_id if ctx is not None else None,
                settings=resolved,
            )
        )

    @mcp.tool()
    def update_todos(
        entries: Annotated[
            list[TodoEntry],
            Field(
                min_length=1,
                description=(
                    'Complete agent-authored todo list for the UI. Each item must use content and may use status/id; '
                    'do not send task, role, detail, priority, plan, steps, or workflow fields.'
                ),
            ),
        ],
        title: Annotated[
            str | None,
            Field(description='Optional short heading for the todo group shown in the transcript.'),
        ] = None,
        session_context_id: SessionContextIdParameter = None,
        ctx: Context | None = None,
    ) -> str:
        """Publish the current agent-authored todo list to the UI; this tool only displays status and never prescribes workflow."""

        return format_update_todos_output(
            update_todos_payload(
                entries=[entry.model_dump(exclude_none=True) for entry in entries],
                title=title,
                session_context_id=session_context_id,
                mcp_session_id=ctx.session_id if ctx is not None else None,
                settings=resolved,
            )
        )

    @mcp.tool()
    def record_run_evidence(
        record_type: EvidenceRecordTypeParameter,
        title: EvidenceTitleParameter,
        session_context_id: SessionContextIdParameter = None,
        path: ArtifactPathParameter = None,
        format: ArtifactFormatParameter = None,
        artifact_stage: ArtifactStageParameter = None,
        display_hint: DisplayHintParameter = None,
        category: EvidenceCategoryParameter = None,
        analysis_type: AnalysisTypeParameter = None,
        description: EvidenceDescriptionParameter = None,
        provenance: EvidenceProvenanceParameter = None,
        data: EvidenceDataParameter = None,
        ctx: Context | None = None,
    ) -> str:
        """Record one evidence ledger entry after real script or command execution; register files only after they exist."""

        return format_record_run_evidence_output(
            record_run_evidence_payload(
                record_type=record_type,
                title=title,
                session_context_id=session_context_id,
                mcp_session_id=ctx.session_id if ctx is not None else None,
                path=path,
                format=format,
                artifact_stage=artifact_stage,
                display_hint=display_hint,
                category=category,
                analysis_type=analysis_type,
                description=description,
                provenance=provenance,
                data=data,
                settings=resolved,
            )
        )

    return mcp


def _settings_from_argv(argv: Sequence[str] | None = None) -> Settings:
    parser = argparse.ArgumentParser()
    parser.add_argument('--state-dir', type=Path)
    parser.add_argument('--app-support-dir', type=Path)
    parser.add_argument('--database-path', type=Path)
    parser.add_argument('--workspace-root', type=Path)
    parser.add_argument('--geospatial-python-project', type=Path)
    parser.add_argument('--geospatial-python-version')
    args = parser.parse_args(argv)
    settings_kwargs: dict[str, Path | str] = {}
    if args.state_dir is not None:
        settings_kwargs['state_dir'] = args.state_dir
    if args.app_support_dir is not None:
        settings_kwargs['app_support_dir'] = args.app_support_dir
    if args.database_path is not None:
        settings_kwargs['database_path'] = args.database_path
    if args.workspace_root is not None:
        settings_kwargs['workspace_root'] = args.workspace_root
    if args.geospatial_python_project is not None:
        settings_kwargs['geospatial_python_project'] = args.geospatial_python_project
    if args.geospatial_python_version is not None:
        settings_kwargs['geospatial_python_version'] = args.geospatial_python_version
    return Settings(**settings_kwargs)


def main(argv: Sequence[str] | None = None) -> None:
    server = build_geospatial_mcp_server(_settings_from_argv(argv))
    server.run(transport='stdio')


if __name__ == '__main__':
    main()
