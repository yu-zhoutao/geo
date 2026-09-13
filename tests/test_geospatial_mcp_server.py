from __future__ import annotations

import asyncio
import json
from pathlib import Path
import subprocess
import sys

import pytest

from app.config import Settings
from app.models import DataDirectoryAttachment, GeospatialSessionContext
from app.services.session_store import SessionStore


async def _list_tools(server) -> list[object]:
    return await server.list_tools()


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        state_dir=tmp_path / '.state',
        app_support_dir=tmp_path / 'support',
        database_path=tmp_path / 'support' / 'metadata.db',
        workspace_root=tmp_path / 'support' / 'workspace',
        geospatial_python_auto_provision=False,
    )


def _save_context(settings: Settings, workspace: Path) -> None:
    store = SessionStore(settings=settings)
    store.save_geospatial_session_context(
        GeospatialSessionContext(
            id='context-1',
            session_id='session-1',
            prompt='对北京出租车轨迹做 KDE 热点分析',
            workspace_path=str(workspace),
            attached_data_directories=[
                DataDirectoryAttachment(id='dir-1', path=str(workspace / 'attached-data'), enabled=True),
            ],
        )
    )


def test_geospatial_mcp_server_exposes_minimal_tool_catalog(tmp_path: Path) -> None:
    from app.services.geospatial_mcp_server import build_geospatial_mcp_server

    server = build_geospatial_mcp_server(_settings(tmp_path))
    tools = asyncio.run(_list_tools(server))
    tool_by_name = {tool.name: tool for tool in tools}

    assert set(tool_by_name) == {'get_session_context', 'record_run_evidence', 'update_todos'}
    context_tool = tool_by_name['get_session_context']
    assert 'session_context_id' in context_tool.parameters['properties']
    assert 'active geospatial session' in context_tool.description
    assert 'opaque backend-owned session context id' in context_tool.parameters['properties']['session_context_id']['description']

    todo_tool = tool_by_name['update_todos']
    todo_properties = todo_tool.parameters['properties']
    assert 'agent-authored todo list' in todo_tool.description
    assert 'entries' in todo_properties
    todo_entry_schema = todo_properties['entries']['items']
    assert todo_entry_schema['additionalProperties'] is False
    assert todo_entry_schema['required'] == ['content']
    assert set(todo_entry_schema['properties']) == {'id', 'content', 'status'}
    assert 'Use content, not task' in todo_entry_schema['properties']['content']['description']
    assert todo_entry_schema['properties']['content']['minLength'] == 1
    assert todo_entry_schema['properties']['status']['enum'] == ['pending', 'in_progress', 'completed', 'blocked']

    evidence_tool = tool_by_name['record_run_evidence']
    evidence_properties = tool_by_name['record_run_evidence'].parameters['properties']
    assert 'Record one evidence ledger entry' in evidence_tool.description
    assert {'record_type', 'title', 'path', 'format', 'artifact_stage', 'display_hint', 'provenance'}.issubset(evidence_properties)
    assert evidence_properties['record_type']['enum'] == [
        'artifact',
        'dataset_profile',
        'verification_fact',
        'parameter_snapshot',
        'claim_trace',
    ]
    assert 'Use artifact only for a durable file' in evidence_properties['record_type']['description']
    assert evidence_properties['format']['anyOf'][0]['enum'] == [
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
    assert evidence_properties['artifact_stage']['anyOf'][0]['enum'] == ['intermediate', 'final']
    assert evidence_properties['display_hint']['anyOf'][0]['enum'] == [
        'image',
        'map',
        'table',
        'markdown',
        'json',
        'text',
        'html',
        'download',
        'other',
    ]
    assert 'Required when record_type is artifact' in evidence_properties['path']['description']
    assert 'Required when record_type is artifact' in evidence_properties['format']['description']
    assert 'Required when record_type is artifact' in evidence_properties['artifact_stage']['description']
    assert 'Required when record_type is artifact' in evidence_properties['display_hint']['description']
    assert 'human-readable' in evidence_properties['format']['description']
    assert 'open-only' in evidence_properties['display_hint']['description']


def test_get_session_context_payload_returns_runtime_contract(tmp_path: Path) -> None:
    from app.services.geospatial_mcp_server import get_session_context_payload

    settings = _settings(tmp_path)
    workspace = tmp_path / 'workspace'
    (workspace / 'attached-data').mkdir(parents=True)
    _save_context(settings, workspace)

    payload = get_session_context_payload(session_context_id='context-1', settings=settings)

    assert payload['status'] == 'completed'
    assert payload['tool'] == {'name': 'get_session_context', 'family': 'context'}
    assert payload['session_context_id'] == 'context-1'
    assert payload['workspace']['root'] == str(workspace)
    assert set(payload['workspace']) == {'root'}
    assert payload['attached_data'][0]['path'] == str(workspace / 'attached-data')
    assert payload['environment']['variables']['GEO_AGENT_GEO_PYTHON_VERSION'] == '3.12'
    assert 'GEO_AGENT_ARTIFACT_DIR' not in payload['environment']['variables']
    assert payload['environment']['recommended_command'][0].endswith('uv')
    assert 'python <script>' in payload['environment']['recommended_command_display']
    assert 'geopandas' in payload['package_readiness']['packages']
    assert payload['evidence']['records'] == []
    assert payload['artifacts'] == []
    assert not (workspace / '.geo').exists()


def test_get_session_context_output_is_compact_xml_text(tmp_path: Path) -> None:
    from app.services.geospatial_mcp_server import format_get_session_context_output, get_session_context_payload

    settings = _settings(tmp_path)
    workspace = tmp_path / 'workspace'
    (workspace / 'attached-data').mkdir(parents=True)
    _save_context(settings, workspace)

    output = format_get_session_context_output(get_session_context_payload(session_context_id='context-1', settings=settings))

    assert output.startswith('<context status="completed">')
    assert f'<workspace>{workspace}</workspace>' in output
    assert '<directory enabled="true"' in output
    assert 'python &lt;script&gt;' in output
    assert 'record_run_evidence' in output
    assert 'context-1' not in output
    assert 'session-1' not in output
    assert '对北京出租车轨迹做 KDE 热点分析' not in output
    assert '.geo/scripts</scripts>' not in output
    assert 'evidence_ledger_path' not in output
    assert 'ledger.jsonl' not in output


def test_get_session_context_payload_binds_unmapped_mcp_session_to_latest_context(tmp_path: Path) -> None:
    from app.services.geospatial_mcp_server import get_session_context_payload

    settings = _settings(tmp_path)
    workspace = tmp_path / 'workspace'
    (workspace / 'attached-data').mkdir(parents=True)
    _save_context(settings, workspace)

    payload = get_session_context_payload(mcp_session_id='mcp-session-1', settings=settings)

    assert payload['status'] == 'completed'
    assert payload['session_context_id'] == 'context-1'
    context = SessionStore(settings=settings).load_geospatial_session_context('context-1')
    assert context is not None
    assert context.mcp_session_id == 'mcp-session-1'


def test_package_readiness_validates_managed_python_imports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import geospatial_runtime

    settings = Settings(
        state_dir=tmp_path / '.state',
        app_support_dir=tmp_path / 'support',
        database_path=tmp_path / 'support' / 'metadata.db',
        workspace_root=tmp_path / 'support' / 'workspace',
        geospatial_python_auto_provision=False,
        geospatial_python_version=f'{sys.version_info.major}.{sys.version_info.minor}',
    )
    python_path = geospatial_runtime.geospatial_python_executable(settings)
    python_path.parent.mkdir(parents=True)
    python_path.symlink_to(sys.executable)
    monkeypatch.setattr(geospatial_runtime, 'REQUIRED_GEOSPATIAL_PACKAGES', ('json',))

    readiness = geospatial_runtime.package_readiness(settings)

    assert readiness['status'] == 'ready'
    assert readiness['validation']['python_version_ok'] is True
    assert readiness['validation']['missing_packages'] == []


def test_package_readiness_includes_pysal_packages() -> None:
    from app.services import geospatial_runtime

    assert 'esda' in geospatial_runtime.REQUIRED_GEOSPATIAL_PACKAGES
    assert 'libpysal' in geospatial_runtime.REQUIRED_GEOSPATIAL_PACKAGES


def test_geospatial_python_validation_reports_missing_pysal_packages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import geospatial_runtime

    settings = Settings(
        state_dir=tmp_path / '.state',
        app_support_dir=tmp_path / 'support',
        database_path=tmp_path / 'support' / 'metadata.db',
        workspace_root=tmp_path / 'support' / 'workspace',
        geospatial_python_auto_provision=False,
        geospatial_python_version=f'{sys.version_info.major}.{sys.version_info.minor}',
    )
    python_path = geospatial_runtime.geospatial_python_executable(settings)
    python_path.parent.mkdir(parents=True)
    python_path.symlink_to(sys.executable)

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout=json.dumps(
                {
                    'installed_python_version': f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}',
                    'python_version_ok': True,
                    'missing_packages': ['esda', 'libpysal'],
                    'import_failures': [
                        {'module': 'esda', 'error': 'No module named esda'},
                        {'module': 'libpysal', 'error': 'No module named libpysal'},
                    ],
                }
            ),
        )

    monkeypatch.setattr(geospatial_runtime.subprocess, 'run', fake_run)

    validation = geospatial_runtime.validate_geospatial_python_environment(settings)

    assert validation['status'] == 'failed'
    assert validation['python_version_ok'] is True
    assert validation['missing_packages'] == ['esda', 'libpysal']
    assert validation['import_failures'][0]['module'] == 'esda'


def test_geospatial_python_validation_timeout_reports_timeout_without_missing_packages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import geospatial_runtime

    settings = Settings(
        state_dir=tmp_path / '.state',
        app_support_dir=tmp_path / 'support',
        database_path=tmp_path / 'support' / 'metadata.db',
        workspace_root=tmp_path / 'support' / 'workspace',
        geospatial_python_auto_provision=False,
    )
    python_path = geospatial_runtime.geospatial_python_executable(settings)
    python_path.parent.mkdir(parents=True)
    python_path.symlink_to(sys.executable)

    def timeout_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs['timeout'])

    monkeypatch.setattr(geospatial_runtime.subprocess, 'run', timeout_run)

    validation = geospatial_runtime.validate_geospatial_python_environment(settings)

    assert validation['status'] == 'failed'
    assert validation['reason'] == 'validation_timeout'
    assert validation['missing_packages'] == []
    assert 'timed out' in validation['logs'][0]


def test_record_run_evidence_payload_registers_stage_aware_artifact(tmp_path: Path) -> None:
    from app.services.geospatial_mcp_server import format_record_run_evidence_output, get_session_context_payload, record_run_evidence_payload
    from app.services.session_store import SessionStore

    settings = _settings(tmp_path)
    workspace = tmp_path / 'workspace'
    artifact_path = workspace / 'outputs' / 'map.png'
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_bytes(b'png')
    (workspace / 'attached-data').mkdir(parents=True)
    _save_context(settings, workspace)

    payload = record_run_evidence_payload(
        session_context_id='context-1',
        record_type='artifact',
        title='KDE 热点图',
        path=str(artifact_path),
        format='png',
        artifact_stage='final',
        display_hint='image',
        category='map',
        description='最终热点图。',
        provenance={
            'script_path': 'scripts/render_map.py',
            'command': 'uv run python render_map.py',
            'inputs': [str(workspace / 'attached-data')],
            'parameters': {'bandwidth_meters': 1000},
        },
        settings=settings,
    )

    assert payload['status'] == 'completed'
    assert payload['record_type'] == 'artifact'
    assert payload['artifact']['artifact_stage'] == 'final'
    assert payload['artifact']['format'] == 'png'
    assert payload['artifact']['display_hint'] == 'image'
    assert payload['artifact']['path'] == 'outputs/map.png'
    output = format_record_run_evidence_output(payload)
    assert output.startswith('<evidence status="recorded"')
    assert '<path>outputs/map.png</path>' in output
    assert '<record_id>' in output
    assert 'ledger.jsonl' not in output

    context = SessionStore(settings=settings).load_geospatial_session_context('context-1')
    assert context is not None
    assert context.artifacts[0].title == 'KDE 热点图'
    assert context.artifacts[0].artifact_stage == 'final'
    assert context.artifacts[0].path == 'outputs/map.png'

    context_payload = get_session_context_payload(session_context_id='context-1', settings=settings)
    assert context_payload['artifacts'][0]['display_hint'] == 'image'
    assert context_payload['evidence']['records'][0]['title'] == 'KDE 热点图'
    assert context_payload['evidence']['records'][0]['artifact_stage'] == 'final'
    assert context_payload['evidence']['records'][0]['path'] == 'outputs/map.png'
    assert not (workspace / '.geo').exists()


def test_record_run_evidence_payload_preserves_idw_raster_metadata(tmp_path: Path) -> None:
    from app.services.geospatial_mcp_server import record_run_evidence_payload
    from app.services.session_store import SessionStore

    settings = _settings(tmp_path)
    workspace = tmp_path / 'workspace'
    artifact_path = workspace / 'outputs' / 'idw-surface.tif'
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_bytes(b'tif')
    _save_context(settings, workspace)

    payload = record_run_evidence_payload(
        session_context_id='context-1',
        record_type='artifact',
        title='IDW 插值栅格',
        path=str(artifact_path),
        format='tif',
        artifact_stage='final',
        display_hint='download',
        category='raster',
        analysis_type='spatial_interpolation',
        description='IDW 输出栅格。',
        data={'validation': {'MAE': 3.1, 'RMSE': 4.6, 'bias': -0.2}, 'extrapolation_policy': 'masked'},
        provenance={'parameters': {'value_field': 'pm25', 'power': 2, 'k': 12}},
        settings=settings,
    )

    assert payload['status'] == 'completed'
    assert payload['analysis_type'] == 'spatial_interpolation'
    assert payload['artifact']['kind'] == 'raster'
    assert payload['artifact']['analysis_type'] == 'spatial_interpolation'
    assert payload['artifact']['provenance']['parameters']['power'] == 2

    records = SessionStore(settings=settings).list_geospatial_evidence_records('context-1')
    assert records[0]['analysis_type'] == 'spatial_interpolation'
    assert records[0]['data']['analysis_type'] == 'spatial_interpolation'
    assert records[0]['data']['validation']['RMSE'] == 4.6
    assert records[0]['data']['extrapolation_policy'] == 'masked'


def test_record_run_evidence_payload_preserves_gistar_verification_metadata(tmp_path: Path) -> None:
    from app.services.geospatial_mcp_server import record_run_evidence_payload
    from app.services.session_store import SessionStore

    settings = _settings(tmp_path)
    workspace = tmp_path / 'workspace'
    _save_context(settings, workspace)

    payload = record_run_evidence_payload(
        session_context_id='context-1',
        record_type='verification_fact',
        title='Gi* 权重和显著性验证',
        category='weights',
        analysis_type='spatial_hotspot',
        data={
            'weights': {'type': 'Queen contiguity', 'island_weight': 'nan'},
            'significance': {'p_value': 'gi_p_sim', 'FDR': 'benjamini_hochberg'},
            'method': {'pysal': 'esda.G_Local', 'star': True},
        },
        provenance={'packages': {'esda': '2.9.0', 'libpysal': '4.14.1'}},
        settings=settings,
    )

    assert payload['status'] == 'completed'
    assert payload['analysis_type'] == 'spatial_hotspot'
    assert payload['artifact'] is None

    records = SessionStore(settings=settings).list_geospatial_evidence_records('context-1')
    assert records[0]['analysis_type'] == 'spatial_hotspot'
    assert records[0]['data']['analysis_type'] == 'spatial_hotspot'
    assert records[0]['data']['weights']['island_weight'] == 'nan'
    assert records[0]['data']['significance']['FDR'] == 'benjamini_hochberg'


def test_record_run_evidence_payload_deduplicates_artifacts_by_path(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    from app.models import Session
    from app.services.geospatial_mcp_server import record_run_evidence_payload

    settings = _settings(tmp_path)
    workspace = tmp_path / 'workspace'
    artifact_path = workspace / 'outputs' / 'map.png'
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_bytes(b'png')
    _save_context(settings, workspace)
    store = SessionStore(settings=settings)
    now = datetime.now(UTC)
    store.save_session(Session(id='session-1', title='会话', status='idle', created_at=now, updated_at=now, workspace_path=str(workspace)))

    record_run_evidence_payload(
        session_context_id='context-1',
        record_type='artifact',
        title='旧版热点图',
        path=str(artifact_path),
        format='png',
        artifact_stage='intermediate',
        display_hint='image',
        category='map',
        settings=settings,
    )
    record_run_evidence_payload(
        session_context_id='context-1',
        record_type='artifact',
        title='新版热点图',
        path=str(artifact_path),
        format='png',
        artifact_stage='final',
        display_hint='image',
        category='map',
        settings=settings,
    )

    context = store.load_geospatial_session_context('context-1')
    session = store.load_session('session-1')

    assert context is not None
    assert session is not None
    assert [artifact.title for artifact in context.artifacts] == ['新版热点图']
    assert [artifact.artifact_stage for artifact in context.artifacts] == ['final']
    assert [artifact.title for artifact in session.artifacts] == ['新版热点图']


def test_record_run_evidence_payload_rejects_outside_artifact_path(tmp_path: Path) -> None:
    from app.services.geospatial_mcp_server import record_run_evidence_payload

    settings = _settings(tmp_path)
    workspace = tmp_path / 'workspace'
    outside = tmp_path / 'outside.png'
    outside.write_bytes(b'png')
    _save_context(settings, workspace)

    payload = record_run_evidence_payload(
        session_context_id='context-1',
        record_type='artifact',
        title='外部图片',
        path=str(outside),
        format='png',
        artifact_stage='intermediate',
        display_hint='image',
        settings=settings,
    )

    assert payload['status'] == 'failed'
    assert payload['reason'] == 'artifact_path_outside_workspace'


def test_record_run_evidence_output_explains_missing_artifact_path(tmp_path: Path) -> None:
    from app.services.geospatial_mcp_server import format_record_run_evidence_output, record_run_evidence_payload

    settings = _settings(tmp_path)
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    _save_context(settings, workspace)

    payload = record_run_evidence_payload(
        session_context_id='context-1',
        record_type='artifact',
        title='尚未生成的图片',
        path='outputs/missing.png',
        format='png',
        artifact_stage='intermediate',
        display_hint='image',
        settings=settings,
    )
    output = format_record_run_evidence_output(payload)

    assert payload['status'] == 'failed'
    assert payload['reason'] == 'artifact_path_missing'
    assert '<path>outputs/missing.png</path>' in output
    assert f'<workspace>{workspace}</workspace>' in output
    assert '<fix>Write the file first, verify the path, then call record_run_evidence again.</fix>' in output


def test_record_run_evidence_payload_rejects_preview_hint_for_open_only_format(tmp_path: Path) -> None:
    from app.services.geospatial_mcp_server import record_run_evidence_payload

    settings = _settings(tmp_path)
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    _save_context(settings, workspace)
    (workspace / 'density.tif').write_text('raster', encoding='utf-8')

    payload = record_run_evidence_payload(
        record_type='artifact',
        title='KDE 密度栅格',
        path='density.tif',
        format='tif',
        artifact_stage='final',
        display_hint='image',
        settings=settings,
    )

    assert payload['status'] == 'failed'
    assert payload['reason'] == 'unsupported_display_hint_for_format'
    assert 'open-only' in payload['fix']


def test_record_run_evidence_payload_rejects_workflow_control_fields(tmp_path: Path) -> None:
    from app.services.geospatial_mcp_server import record_run_evidence_payload

    settings = _settings(tmp_path)
    workspace = tmp_path / 'workspace'
    _save_context(settings, workspace)

    payload = record_run_evidence_payload(
        session_context_id='context-1',
        record_type='verification_fact',
        title='不要让证据工具写计划',
        data={'plan': [{'content': '硬编码步骤', 'status': 'in_progress'}]},
        settings=settings,
    )

    assert payload['status'] == 'failed'
    assert payload['reason'] == 'workflow_control_fields_not_allowed'


def test_update_todos_payload_returns_xml_friendly_agent_owned_entries(tmp_path: Path) -> None:
    from app.services.geospatial_mcp_server import format_update_todos_output, update_todos_payload

    payload = update_todos_payload(
        entries=[
            {'content': '确认研究区边界', 'status': 'in_progress'},
            {'label': '登记最终地图', 'status': 'completed'},
        ],
        settings=_settings(tmp_path),
    )

    assert payload['status'] == 'completed'
    assert payload['tool'] == {'name': 'update_todos', 'family': 'planning'}
    assert [entry['label'] for entry in payload['entries']] == ['确认研究区边界', '登记最终地图']
    assert '<todos status="updated">' in format_update_todos_output(payload)


def test_update_todos_payload_rejects_invalid_entries_with_clear_fix(tmp_path: Path) -> None:
    from app.services.geospatial_mcp_server import format_update_todos_output, update_todos_payload

    payload = update_todos_payload(entries=[{'content': '', 'status': 'done'}], settings=_settings(tmp_path))

    assert payload['status'] == 'failed'
    assert payload['reason'] == 'invalid_todo_entries'
    output = format_update_todos_output(payload)
    assert '<error tool="update_todos" reason="invalid_todo_entries">' in output
    assert '<fix>' in output
