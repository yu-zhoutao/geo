from __future__ import annotations

import asyncio
from pathlib import Path

from app.config import Settings, get_settings
from app.models import RuntimeStatus
from app.services.agent_runtime import AgentRuntimeClient, build_agent_runtime_client
from app.services.geospatial_runtime import package_readiness, package_status_snapshot, provision_geospatial_python_environment_streaming


PROVISIONING_CHECKING_PROGRESS = 0.1
PROVISIONING_INSTALLING_PROGRESS = 0.35
PROVISIONING_VALIDATING_PROGRESS = 0.9


class RuntimeManager:
    def __init__(
        self,
        settings: Settings | None = None,
        state_dir: Path | None = None,
        runtime_client: AgentRuntimeClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.state_dir = state_dir if state_dir is not None else self.settings.state_dir
        self.runtime_client = runtime_client or build_agent_runtime_client(self.settings)
        self._geospatial_environment_status: dict[str, object] | None = None
        self._geospatial_environment_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self.state_dir is not None:
            self.state_dir.mkdir(parents=True, exist_ok=True)
        if self.settings.geospatial_python_auto_provision:
            self.start_geospatial_environment_provisioning()
        await self.runtime_client.start()

    async def stop(self) -> None:
        if self._geospatial_environment_task is not None and not self._geospatial_environment_task.done():
            self._geospatial_environment_task.cancel()
            try:
                await self._geospatial_environment_task
            except asyncio.CancelledError:
                pass
        await self.runtime_client.stop()

    async def ensure_ready(self) -> RuntimeStatus:
        await self.start()
        return self.status()

    def status(self) -> RuntimeStatus:
        return self.runtime_client.status()

    def start_geospatial_environment_provisioning(self) -> None:
        status = self._geospatial_environment_status
        if status is not None and status.get('status') in {'ready', 'provisioning', 'failed'}:
            return
        self._geospatial_environment_status = {
            'status': 'provisioning',
            'progress': PROVISIONING_CHECKING_PROGRESS,
            'logs': ['Checking managed geospatial Python environment.'],
        }
        if self._geospatial_environment_task is None or self._geospatial_environment_task.done():
            self._geospatial_environment_task = asyncio.create_task(self._run_geospatial_environment_provisioning())

    async def ensure_geospatial_environment(self) -> dict[str, object]:
        self.start_geospatial_environment_provisioning()
        if self._geospatial_environment_task is not None and not self._geospatial_environment_task.done():
            await self._geospatial_environment_task
        if self._geospatial_environment_status is None:
            self._geospatial_environment_status = self.geospatial_environment_status()
        return self._geospatial_environment_status

    async def _run_geospatial_environment_provisioning(self) -> None:
        async def append_log(line: str) -> None:
            current = self._geospatial_environment_status or {}
            logs = [str(item) for item in current.get('logs', []) if item is not None]
            logs.append(line)
            progress = (
                PROVISIONING_VALIDATING_PROGRESS
                if line == 'Validating managed geospatial Python imports.'
                else max(float(current.get('progress', 0.0) or 0.0), PROVISIONING_INSTALLING_PROGRESS)
            )
            self._geospatial_environment_status = {
                **current,
                'status': 'provisioning',
                'progress': progress,
                'logs': logs,
            }

        try:
            current_readiness = await asyncio.to_thread(package_readiness, self.settings)
            if current_readiness['status'] == 'ready':
                current = self._geospatial_environment_status or {}
                logs = [str(item) for item in current.get('logs', []) if item is not None]
                logs.append('Managed geospatial Python environment is ready.')
                self._geospatial_environment_status = {
                    **current_readiness,
                    'status': 'ready',
                    'progress': 1.0,
                    'logs': logs,
                }
                return
            await append_log('Installing managed geospatial Python packages with bundled uv.')
            result = await provision_geospatial_python_environment_streaming(
                self.settings,
                on_log=append_log,
            )
            current = self._geospatial_environment_status or {}
            logs = [str(item) for item in current.get('logs', []) if item is not None]
            if result.get('status') == 'failed':
                logs.extend(_provisioning_failure_logs(result))
            progress = result.get('progress') if result.get('status') != 'failed' else current.get('progress', result.get('progress'))
            self._geospatial_environment_status = {
                **result,
                'progress': progress,
                'logs': logs or [str(item) for item in result.get('logs', []) if item is not None],
            }
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            current = self._geospatial_environment_status or {}
            logs = [str(item) for item in current.get('logs', []) if item is not None]
            logs.append(f'ERROR: {exc}')
            self._geospatial_environment_status = {
                **current,
                'status': 'failed',
                'progress': current.get('progress', PROVISIONING_CHECKING_PROGRESS),
                'logs': logs,
                'detail': str(exc),
            }

    def geospatial_environment_status(self) -> dict[str, object]:
        if self._geospatial_environment_status is not None:
            return self._geospatial_environment_status
        current = package_status_snapshot(self.settings)
        return {
            **current,
            'progress': 1.0 if current['status'] == 'ready' else 0.0,
            'logs': [],
        }


def _provisioning_failure_logs(result: dict[str, object]) -> list[str]:
    logs: list[str] = []
    returncode = result.get('returncode')
    if returncode not in {None, 0}:
        logs.append(f'ERROR: uv sync failed with exit code {returncode}.')
    package_readiness = result.get('package_readiness')
    if isinstance(package_readiness, dict) and package_readiness.get('status') != 'ready':
        validation = package_readiness.get('validation')
        if isinstance(validation, dict):
            validation_logs = [
                str(line)
                for line in validation.get('logs', [])
                if line and not str(line).lstrip().startswith('{')
            ] if isinstance(validation.get('logs'), list) else []
            raw_missing_packages = validation.get('missing_packages') or []
            missing_packages = [str(package) for package in raw_missing_packages] if isinstance(raw_missing_packages, list) else []
            if missing_packages:
                logs.append(f"ERROR: Missing geospatial packages: {', '.join(missing_packages)}.")
            import_failures = validation.get('import_failures', [])
            if isinstance(import_failures, list):
                for failure in import_failures:
                    if not isinstance(failure, dict):
                        continue
                    module = failure.get('module')
                    error = failure.get('error')
                    if module and error:
                        logs.append(f'ERROR: Import failure for {module}: {error}')
            if not missing_packages and validation_logs:
                logs.extend(f'ERROR: {line}' for line in validation_logs)
    if not logs:
        logs.append('ERROR: Geospatial Python environment provisioning failed.')
    return logs
