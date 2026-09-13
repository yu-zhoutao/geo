from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any

from app.config import Settings, get_settings


REQUIRED_GEOSPATIAL_PACKAGES: tuple[str, ...] = (
    'geopandas',
    'pyogrio',
    'shapely',
    'pyproj',
    'rasterio',
    'numpy',
    'pandas',
    'scipy',
    'sklearn',
    'matplotlib',
    'mapclassify',
    'pyarrow',
    'openpyxl',
    'PIL',
    'contextily',
    'esda',
    'folium',
    'libpysal',
    'rasterstats',
    'xarray',
    'rioxarray',
    'pymannkendall',
    'netCDF4',
)
SUPPORTED_ARTIFACT_FORMATS: set[str] = {
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
}
SUPPORTED_DISPLAY_HINTS: set[str] = {
    'image',
    'map',
    'table',
    'markdown',
    'json',
    'text',
    'html',
    'download',
    'other',
}
PACKAGE_IMPORT_MODULES: dict[str, str] = {
    'PIL': 'PIL',
    'sklearn': 'sklearn',
}
_READINESS_CACHE: dict[tuple[str, str, str, tuple[str, ...]], dict[str, Any]] = {}
GEOSPATIAL_VALIDATION_TIMEOUT_SECONDS = 120


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_uv_bin(settings: Settings | None = None) -> str:
    resolved = settings or get_settings()
    if resolved.uv_bin:
        return resolved.uv_bin
    packaged_uv = repo_root() / 'app' / 'runtime_assets' / 'bin' / ('uv.exe' if os.name == 'nt' else 'uv')
    if packaged_uv.exists():
        return str(packaged_uv)
    return shutil.which('uv') or 'uv'


def workspace_layout(workspace_path: str | Path) -> dict[str, str]:
    root = Path(workspace_path)
    root.mkdir(parents=True, exist_ok=True)
    return {'root': str(root)}


def geospatial_environment_variables(*, settings: Settings, workspace_path: str | Path, session_context_id: str | None = None) -> dict[str, str]:
    workspace = Path(workspace_path).expanduser().resolve()
    return {
        'GEO_AGENT_REPO_ROOT': str(repo_root()),
        'GEO_AGENT_UV_BIN': resolve_uv_bin(settings),
        'GEO_AGENT_GEO_PYTHON_PROJECT': str(settings.resolved_geospatial_python_project().expanduser().resolve()),
        'GEO_AGENT_GEO_PYTHON_VERSION': settings.geospatial_python_version,
        'UV_PROJECT_ENVIRONMENT': str(settings.resolved_geospatial_python_environment().expanduser().resolve()),
        'GEO_AGENT_WORKSPACE_PATH': str(workspace),
        'GEO_AGENT_SESSION_CONTEXT_ID': session_context_id or '',
    }


def geospatial_python_command(settings: Settings | None = None) -> list[str]:
    resolved = settings or get_settings()
    return [
        resolve_uv_bin(resolved),
        '--project',
        str(resolved.resolved_geospatial_python_project()),
        'run',
        '--python',
        resolved.geospatial_python_version,
        'python',
        '<script>',
    ]


def geospatial_python_command_display(settings: Settings | None = None) -> str:
    command = geospatial_python_command(settings)
    return ' '.join(f'"{part}"' if ' ' in part and part != '<script>' else part for part in command)


def geospatial_python_executable(settings: Settings | None = None) -> Path:
    resolved = settings or get_settings()
    environment = resolved.resolved_geospatial_python_environment()
    executable = 'python.exe' if os.name == 'nt' else 'python'
    bin_dir = 'Scripts' if os.name == 'nt' else 'bin'
    return environment / bin_dir / executable


def validate_geospatial_python_environment(settings: Settings | None = None) -> dict[str, Any]:
    resolved = settings or get_settings()
    python_executable = geospatial_python_executable(resolved)
    if not python_executable.exists():
        return {
            'status': 'not_ready',
            'python_executable': str(python_executable),
            'python_version_ok': False,
            'installed_python_version': None,
            'missing_packages': list(REQUIRED_GEOSPATIAL_PACKAGES),
            'import_failures': [],
            'logs': ['Managed geospatial Python executable does not exist yet.'],
        }

    import_modules = [PACKAGE_IMPORT_MODULES.get(package, package) for package in REQUIRED_GEOSPATIAL_PACKAGES]
    script = f"""
import importlib
import json
import sys

expected = {json.dumps(resolved.geospatial_python_version)}
modules = {json.dumps(import_modules)}
missing = []
failures = []
for module_name in modules:
    try:
        importlib.import_module(module_name)
    except Exception as exc:
        missing.append(module_name)
        failures.append({{'module': module_name, 'error': str(exc)}})
installed = '.'.join(str(part) for part in sys.version_info[:3])
expected_parts = tuple(int(part) for part in expected.split('.') if part.isdigit())
python_version_ok = sys.version_info[:len(expected_parts)] == expected_parts
print(json.dumps({{
    'installed_python_version': installed,
    'python_version_ok': python_version_ok,
    'missing_packages': missing,
    'import_failures': failures,
}}))
"""
    try:
        process = subprocess.run(
            [str(python_executable), '-c', script],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=GEOSPATIAL_VALIDATION_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        timeout = int(exc.timeout or GEOSPATIAL_VALIDATION_TIMEOUT_SECONDS)
        return {
            'status': 'failed',
            'reason': 'validation_timeout',
            'python_executable': str(python_executable),
            'python_version_ok': False,
            'installed_python_version': None,
            'missing_packages': [],
            'import_failures': [],
            'logs': [f'Managed geospatial Python validation timed out after {timeout} seconds.'],
            'returncode': None,
        }
    logs = process.stdout.splitlines()
    if process.returncode != 0 or not logs:
        return {
            'status': 'failed',
            'reason': 'validation_process_failed',
            'python_executable': str(python_executable),
            'python_version_ok': False,
            'installed_python_version': None,
            'missing_packages': [],
            'import_failures': [],
            'logs': logs or ['Managed geospatial Python validation did not produce output.'],
            'returncode': process.returncode,
        }

    try:
        result = json.loads(logs[-1])
    except json.JSONDecodeError as exc:
        return {
            'status': 'failed',
            'reason': 'validation_output_parse_failed',
            'python_executable': str(python_executable),
            'python_version_ok': False,
            'installed_python_version': None,
            'missing_packages': [],
            'import_failures': [],
            'logs': [*logs, f'Managed geospatial Python validation output could not be parsed: {exc}'],
            'returncode': process.returncode,
        }
    missing_packages = list(result.get('missing_packages') or [])
    python_version_ok = bool(result.get('python_version_ok'))
    return {
        'status': 'ready' if python_version_ok and not missing_packages else 'failed',
        'python_executable': str(python_executable),
        'python_version_ok': python_version_ok,
        'installed_python_version': result.get('installed_python_version'),
        'missing_packages': missing_packages,
        'import_failures': list(result.get('import_failures') or []),
        'logs': logs,
        'returncode': process.returncode,
    }


def _readiness_cache_key(settings: Settings) -> tuple[str, str, str, tuple[str, ...]]:
    return (
        str(settings.resolved_geospatial_python_project()),
        str(settings.resolved_geospatial_python_environment()),
        settings.geospatial_python_version,
        tuple(REQUIRED_GEOSPATIAL_PACKAGES),
    )


def package_readiness(settings: Settings | None = None, *, force_validation: bool = False) -> dict[str, Any]:
    resolved = settings or get_settings()
    venv = resolved.resolved_geospatial_python_environment()
    project = resolved.resolved_geospatial_python_project()
    cache_key = _readiness_cache_key(resolved)
    if not force_validation and cache_key in _READINESS_CACHE:
        return copy.deepcopy(_READINESS_CACHE[cache_key])
    validation = validate_geospatial_python_environment(resolved)
    readiness = {
        'status': validation['status'],
        'python_version': resolved.geospatial_python_version,
        'project_path': str(project),
        'environment_path': str(venv),
        'uv_bin': resolve_uv_bin(resolved),
        'packages': list(REQUIRED_GEOSPATIAL_PACKAGES),
        'validation': validation,
    }
    _READINESS_CACHE[cache_key] = copy.deepcopy(readiness)
    return readiness


def package_status_snapshot(settings: Settings | None = None) -> dict[str, Any]:
    resolved = settings or get_settings()
    python_executable = geospatial_python_executable(resolved)
    log = (
        'Managed geospatial Python executable exists but has not been validated yet.'
        if python_executable.exists()
        else 'Managed geospatial Python executable does not exist yet.'
    )
    return {
        'status': 'not_ready',
        'python_version': resolved.geospatial_python_version,
        'project_path': str(resolved.resolved_geospatial_python_project()),
        'environment_path': str(resolved.resolved_geospatial_python_environment()),
        'uv_bin': resolve_uv_bin(resolved),
        'packages': list(REQUIRED_GEOSPATIAL_PACKAGES),
        'validation': {
            'status': 'not_ready',
            'python_executable': str(python_executable),
            'python_version_ok': False,
            'installed_python_version': None,
            'missing_packages': list(REQUIRED_GEOSPATIAL_PACKAGES),
            'import_failures': [],
            'logs': [log],
        },
    }


def provisioning_command(settings: Settings | None = None) -> list[str]:
    resolved = settings or get_settings()
    return [
        resolve_uv_bin(resolved),
        'sync',
        '--project',
        str(resolved.resolved_geospatial_python_project()),
        '--python',
        resolved.geospatial_python_version,
        '--managed-python',
        '--frozen',
    ]


def provisioning_environment(settings: Settings | None = None) -> dict[str, str]:
    resolved = settings or get_settings()
    env = os.environ.copy()
    env['UV_PROJECT_ENVIRONMENT'] = str(resolved.resolved_geospatial_python_environment())
    return env


async def provision_geospatial_python_environment_streaming(
    settings: Settings | None = None,
    *,
    on_log: Callable[[str], Awaitable[None]] | None = None,
) -> dict[str, Any]:
    resolved = settings or get_settings()
    command = provisioning_command(resolved)
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=str(resolved.resolved_geospatial_python_project()),
        env=provisioning_environment(resolved),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    logs: list[str] = []
    if process.stdout is not None:
        while True:
            raw_line = await process.stdout.readline()
            if not raw_line:
                break
            line = raw_line.decode(errors='replace').rstrip()
            if not line:
                continue
            logs.append(line)
            if on_log is not None:
                await on_log(line)
    returncode = await process.wait()
    if returncode == 0 and on_log is not None:
        await on_log('Validating managed geospatial Python imports.')
    readiness = await asyncio.to_thread(package_readiness, resolved, force_validation=True)
    status = 'ready' if returncode == 0 and readiness['status'] == 'ready' else 'failed'
    progress = 1.0 if status == 'ready' else (0.9 if returncode == 0 else 0.35)
    return {
        'status': status,
        'progress': progress,
        'command': command,
        'logs': logs,
        'returncode': returncode,
        'package_readiness': readiness,
    }


def provision_geospatial_python_environment(settings: Settings | None = None) -> dict[str, Any]:
    resolved = settings or get_settings()
    command = provisioning_command(resolved)
    process = subprocess.run(
        command,
        cwd=str(resolved.resolved_geospatial_python_project()),
        env=provisioning_environment(resolved),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    logs = process.stdout.splitlines()
    readiness = package_readiness(resolved, force_validation=True)
    status = 'ready' if process.returncode == 0 and readiness['status'] == 'ready' else 'failed'
    progress = 1.0 if status == 'ready' else (0.9 if process.returncode == 0 else 0.35)
    return {
        'status': status,
        'progress': progress,
        'command': command,
        'logs': logs,
        'returncode': process.returncode,
        'package_readiness': readiness,
    }
