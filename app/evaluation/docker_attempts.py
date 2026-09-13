from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence
from uuid import uuid4

from app.config import Settings, get_settings
from app.evaluation.benchmarks import BenchmarkScenario, BenchmarkValidationError, repo_root
from app.evaluation.manifests import CampaignManifest, VariantManifest
from app.evaluation.run_bundles import (
    RUN_MANIFEST_FILENAME,
    RUN_STATUS_FILENAME,
    RunBundleCapture,
    load_run_bundle_capture,
    write_failed_run_bundle,
)
from app.evaluation.runner import (
    RunBundleAllocation,
    _attempt_budget_seconds,
    _write_json,
)


DOCKER_ATTEMPT_METADATA_FILENAME = 'container-metadata.json'
DOCKER_CONTAINER_LOG_FILENAME = 'container.log'
DOCKER_BACKEND_SCHEMA = 'geo-agent.evaluation.docker-attempt.v1'
DEFAULT_DOCKER_IMAGE = 'geo-agent-eval:latest'
DEFAULT_CONTAINER_DATA_PATH = '/data'
DEFAULT_CONTAINER_RUN_BUNDLE_PATH = '/evaluation-run'
SECRET_ENV_NAMES: set[str] = {
    'GEO_AGENT_GLM_API_KEY',
    'GEO_AGENT_DEEPSEEK_API_KEY',
}


class DockerAttemptError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DockerAttemptOptions:
    image: str = DEFAULT_DOCKER_IMAGE
    data_dir: Path | None = None
    container_data_path: str = DEFAULT_CONTAINER_DATA_PATH
    container_run_bundle_path: str = DEFAULT_CONTAINER_RUN_BUNDLE_PATH
    stop_timeout_seconds: int = 10


@dataclass(frozen=True, slots=True)
class DockerAttemptRequest:
    campaign: CampaignManifest
    allocation: RunBundleAllocation
    scenario: BenchmarkScenario
    variant: VariantManifest
    options: DockerAttemptOptions


async def run_docker_attempt(
    request: DockerAttemptRequest,
    *,
    docker_client: Any | None = None,
) -> RunBundleCapture:
    started_at: datetime = datetime.now(UTC)
    allocation = request.allocation
    scenario = request.scenario
    variant = request.variant
    options = _resolve_options(request.options)

    try:
        _validate_docker_paths(options, allocation.path)
        client = docker_client if docker_client is not None else _docker_client_from_env()
        command = docker_attempt_command(request)
        environment = docker_attempt_environment(get_settings())
        volumes = docker_attempt_volumes(options, allocation.path)
        metadata = docker_attempt_metadata(
            request,
            command=command,
            environment=environment,
            volumes=volumes,
            started_at=started_at,
        )
        _write_json(allocation.path / DOCKER_ATTEMPT_METADATA_FILENAME, metadata)
        container = await asyncio.to_thread(
            client.containers.run,
            options.image,
            command=command,
            detach=True,
            environment=environment,
            volumes=volumes,
            working_dir='/app',
            name=_container_name(allocation.id),
        )
        cleanup_error: str | None = None
        try:
            result = await _wait_for_container(container, timeout_seconds=_docker_timeout_seconds(request))
            exit_code: int | None = _container_exit_code(result)
            terminal_error: str | None = None if exit_code == 0 else f'container exited with code {exit_code}'
        except asyncio.CancelledError:
            await _stop_container(container, timeout_seconds=options.stop_timeout_seconds)
            _write_docker_logs(container, allocation.path, environment)
            cleanup_error = await _remove_container(container)
            _finalize_container_metadata(
                allocation.path,
                container=container,
                exit_code=None,
                finished_at=datetime.now(UTC),
                cleanup='cleanup_failed' if cleanup_error else 'stopped_after_cancellation',
                error=cleanup_error or 'container execution cancelled',
            )
            if not (allocation.path / RUN_MANIFEST_FILENAME).exists():
                write_failed_run_bundle(
                    allocation.path,
                    run_id=allocation.id,
                    session_id=f'container-cancelled-{allocation.id}',
                    scenario=scenario,
                    variant=variant,
                    terminal_reason='container_cancelled',
                    errors=['Docker attempt container execution was cancelled.'],
                    strategy=allocation.planned_attempt.strategy,
                    started_at=started_at,
                    finished_at=datetime.now(UTC),
                )
                _merge_container_metadata_reference(allocation.path)
            else:
                _append_run_bundle_error(allocation.path, 'Docker attempt container execution was cancelled.')
            raise
        except TimeoutError:
            await _stop_container(container, timeout_seconds=options.stop_timeout_seconds)
            _write_docker_logs(container, allocation.path, environment)
            cleanup_error = await _remove_container(container)
            _finalize_container_metadata(
                allocation.path,
                container=container,
                exit_code=None,
                finished_at=datetime.now(UTC),
                cleanup='cleanup_failed' if cleanup_error else 'stopped_after_timeout',
                error=cleanup_error or 'container timed out',
            )
            if not (allocation.path / RUN_MANIFEST_FILENAME).exists():
                capture = write_failed_run_bundle(
                    allocation.path,
                    run_id=allocation.id,
                    session_id=f'container-timeout-{allocation.id}',
                    scenario=scenario,
                    variant=variant,
                    terminal_reason='container_timeout',
                    errors=['Docker attempt container timed out.'],
                    strategy=allocation.planned_attempt.strategy,
                    started_at=started_at,
                    finished_at=datetime.now(UTC),
                )
                _merge_container_metadata_reference(allocation.path)
                return capture
            _append_run_bundle_error(allocation.path, 'Docker attempt container timed out.')
            return load_run_bundle_capture(allocation.path)

        _write_docker_logs(container, allocation.path, environment)
        cleanup_error = await _remove_container(container)
        cleanup = 'cleanup_failed' if cleanup_error else 'removed'
        terminal_error = cleanup_error or terminal_error
        _finalize_container_metadata(
            allocation.path,
            container=container,
            exit_code=exit_code,
            finished_at=datetime.now(UTC),
            cleanup=cleanup,
            error=terminal_error,
        )
        if cleanup_error:
            _append_run_bundle_error(allocation.path, cleanup_error)
        if exit_code != 0:
            _append_run_bundle_error(allocation.path, f'Docker attempt container exited with code {exit_code}.')
            if not (allocation.path / RUN_MANIFEST_FILENAME).exists():
                capture = write_failed_run_bundle(
                    allocation.path,
                    run_id=allocation.id,
                    session_id=f'container-failed-{allocation.id}',
                    scenario=scenario,
                    variant=variant,
                    terminal_reason='container_failed',
                    errors=[f'Docker attempt container exited with code {exit_code}.'],
                    strategy=allocation.planned_attempt.strategy,
                    started_at=started_at,
                    finished_at=datetime.now(UTC),
                )
                _merge_container_metadata_reference(allocation.path)
                return capture
        return load_run_bundle_capture(allocation.path)
    except Exception as exc:
        if isinstance(exc, BenchmarkValidationError):
            detail = str(exc)
        else:
            detail = f'{type(exc).__name__}: {exc}'
        if not (allocation.path / RUN_MANIFEST_FILENAME).exists():
            return write_failed_run_bundle(
                allocation.path,
                run_id=allocation.id,
                session_id=f'container-error-{allocation.id}',
                scenario=scenario,
                variant=variant,
                terminal_reason='container_start_failed',
                errors=[detail],
                strategy=allocation.planned_attempt.strategy,
                started_at=started_at,
                finished_at=datetime.now(UTC),
            )
        _append_run_bundle_error(allocation.path, detail)
        return load_run_bundle_capture(allocation.path)


def docker_attempt_command(request: DockerAttemptRequest) -> list[str]:
    campaign = request.campaign
    allocation = request.allocation
    options = _resolve_options(request.options)
    command: list[str] = [
        '--run-id',
        allocation.id,
        '--variant-id',
        request.variant.id,
        '--scenario-id',
        request.scenario.id,
        '--repeat-index',
        str(allocation.planned_attempt.repeat_index),
        '--attempt-number',
        str(allocation.attempt_number),
        '--run-bundle-path',
        options.container_run_bundle_path,
        '--data-root',
        options.container_data_path,
        '--wall-clock-budget-seconds',
        str(_attempt_budget_seconds(campaign, request.variant)),
        '--readiness-timeout-seconds',
        str(campaign.runner_readiness_timeout_seconds),
        '--scoring-mode',
        campaign.scoring_mode,
        '--judge-model',
        campaign.judge_model,
        '--judge-temperature',
        str(campaign.judge_temperature),
        '--fairness-model',
        campaign.fairness_model,
    ]
    strategy = allocation.planned_attempt.strategy
    if strategy is not None:
        command.extend(
            [
                '--strategy-id',
                strategy.strategy_id,
                '--strategy-source',
                strategy.source,
                '--strategy-profile-hash',
                strategy.profile_hash,
            ]
        )
        if strategy.policy_run_id is not None:
            command.extend(['--policy-run-id', strategy.policy_run_id])
        if strategy.policy_checkpoint_id is not None:
            command.extend(['--policy-checkpoint-id', strategy.policy_checkpoint_id])
        if strategy.trl_run_id is not None:
            command.extend(['--trl-run-id', strategy.trl_run_id])
        if strategy.training_step is not None:
            command.extend(['--training-step', str(strategy.training_step)])
        if strategy.action_rationale is not None:
            command.extend(['--strategy-action-rationale', strategy.action_rationale])
    return command


def docker_attempt_volumes(options: DockerAttemptOptions, run_bundle_path: Path) -> dict[str, dict[str, str]]:
    resolved = _resolve_options(options)
    return {
        str(resolved.data_dir): {'bind': resolved.container_data_path, 'mode': 'ro'},
        str(run_bundle_path.resolve()): {'bind': resolved.container_run_bundle_path, 'mode': 'rw'},
    }


def docker_attempt_environment(settings: Settings | None = None) -> dict[str, str]:
    resolved = settings or get_settings()
    env: dict[str, str] = {
        'GEO_AGENT_MODEL_PROVIDER': resolved.model_provider,
        'GEO_AGENT_GLM_MODEL': resolved.glm_model,
        'GEO_AGENT_DEEPSEEK_MODEL': resolved.deepseek_model,
        'GEO_AGENT_OPENCODE_BINARY': 'opencode',
    }
    if resolved.glm_api_key:
        env['GEO_AGENT_GLM_API_KEY'] = resolved.glm_api_key
    if resolved.deepseek_api_key:
        env['GEO_AGENT_DEEPSEEK_API_KEY'] = resolved.deepseek_api_key
    return env


def docker_attempt_metadata(
    request: DockerAttemptRequest,
    *,
    command: Sequence[str],
    environment: Mapping[str, str],
    volumes: Mapping[str, Mapping[str, str]],
    started_at: datetime,
) -> dict[str, object]:
    return {
        'schema': DOCKER_BACKEND_SCHEMA,
        'backend': 'docker-per-attempt',
        'run_id': request.allocation.id,
        'planned_attempt_id': request.allocation.planned_attempt.id,
        'strategy': (
            request.allocation.planned_attempt.strategy.as_json()
            if request.allocation.planned_attempt.strategy is not None
            else None
        ),
        'image': {'reference': _resolve_options(request.options).image},
        'container': {'id': None, 'name': None, 'exit_code': None},
        'command': list(command),
        'mounts': _volume_summary(volumes),
        'environment': redact_environment(environment),
        'started_at': started_at.isoformat(),
        'finished_at': None,
        'cleanup': None,
        'error': None,
    }


def redact_environment(environment: Mapping[str, str]) -> dict[str, str]:
    return {
        name: '[redacted]' if _is_secret_name(name) else value
        for name, value in sorted(environment.items())
    }


def redact_text(text: str, environment: Mapping[str, str]) -> str:
    redacted = text
    for name, value in environment.items():
        if value and _is_secret_name(name):
            redacted = redacted.replace(value, '[redacted]')
    return redacted


def _resolve_options(options: DockerAttemptOptions) -> DockerAttemptOptions:
    data_dir = options.data_dir or repo_root() / 'data'
    return DockerAttemptOptions(
        image=options.image,
        data_dir=data_dir.expanduser().resolve(),
        container_data_path=options.container_data_path,
        container_run_bundle_path=options.container_run_bundle_path,
        stop_timeout_seconds=options.stop_timeout_seconds,
    )


def _validate_docker_paths(options: DockerAttemptOptions, run_bundle_path: Path) -> None:
    if options.data_dir is None or not options.data_dir.is_dir():
        raise BenchmarkValidationError(f'Docker data directory does not exist: {options.data_dir}')
    if not run_bundle_path.exists():
        raise BenchmarkValidationError(f'Docker run bundle directory does not exist: {run_bundle_path}')


def _docker_client_from_env() -> Any:
    try:
        import docker
    except ImportError as exc:
        raise DockerAttemptError(
            'Docker SDK is not installed. Install the optional docker extra before using '
            'docker-per-attempt execution.'
        ) from exc
    try:
        return docker.from_env()
    except Exception as env_exc:
        context_host = _docker_context_host()
        if context_host is not None:
            try:
                return docker.DockerClient(base_url=context_host)
            except Exception as context_exc:
                raise DockerAttemptError(
                    f'Docker daemon is not available: {env_exc}; Docker context {context_host} failed: {context_exc}'
                ) from context_exc
        raise DockerAttemptError(f'Docker daemon is not available: {env_exc}') from env_exc


def _docker_context_host() -> str | None:
    context_name = os.getenv('DOCKER_CONTEXT') or _docker_config_current_context()
    if not context_name or context_name == 'default':
        return None
    meta_root = Path.home() / '.docker' / 'contexts' / 'meta'
    if not meta_root.is_dir():
        return None
    for meta_path in sorted(meta_root.glob('*/meta.json')):
        payload = _load_json(meta_path, default={})
        if payload.get('Name') != context_name:
            continue
        endpoints = payload.get('Endpoints')
        if not isinstance(endpoints, dict):
            return None
        docker_endpoint = endpoints.get('docker')
        if not isinstance(docker_endpoint, dict):
            return None
        host = docker_endpoint.get('Host')
        return host if isinstance(host, str) and host else None
    return None


def _docker_config_current_context() -> str | None:
    config = _load_json(Path.home() / '.docker' / 'config.json', default={})
    context_name = config.get('currentContext')
    return context_name if isinstance(context_name, str) and context_name else None


async def _wait_for_container(container: Any, *, timeout_seconds: float | None) -> Any:
    if timeout_seconds is None or timeout_seconds <= 0:
        return await asyncio.to_thread(container.wait)
    return await asyncio.wait_for(asyncio.to_thread(container.wait), timeout=timeout_seconds)


async def _stop_container(container: Any, *, timeout_seconds: int) -> None:
    await asyncio.to_thread(container.stop, timeout=timeout_seconds)


async def _remove_container(container: Any) -> str | None:
    try:
        await asyncio.to_thread(container.remove, force=True)
    except Exception as exc:
        return f'container cleanup failed: {type(exc).__name__}: {exc}'
    return None


def _write_docker_logs(container: Any, run_bundle_path: Path, environment: Mapping[str, str]) -> None:
    logs_root = run_bundle_path / 'logs'
    logs_root.mkdir(parents=True, exist_ok=True)
    try:
        raw_logs = container.logs(stdout=True, stderr=True)
    except Exception as exc:
        raw_logs = f'container log capture failed: {type(exc).__name__}: {exc}'.encode()
    text = raw_logs.decode('utf-8', errors='replace') if isinstance(raw_logs, bytes) else str(raw_logs)
    (logs_root / DOCKER_CONTAINER_LOG_FILENAME).write_text(redact_text(text, environment), encoding='utf-8')


def _finalize_container_metadata(
    run_bundle_path: Path,
    *,
    container: Any,
    exit_code: int | None,
    finished_at: datetime,
    cleanup: str,
    error: str | None,
) -> None:
    metadata_path = run_bundle_path / DOCKER_ATTEMPT_METADATA_FILENAME
    metadata = _load_json(metadata_path, default={})
    image = getattr(container, 'image', None)
    image_id = getattr(image, 'id', None)
    metadata['image'] = dict(metadata.get('image') if isinstance(metadata.get('image'), dict) else {})
    metadata['image']['id'] = image_id if isinstance(image_id, str) else None
    metadata['container'] = {
        'id': getattr(container, 'id', None),
        'name': getattr(container, 'name', None),
        'exit_code': exit_code,
    }
    metadata['finished_at'] = finished_at.isoformat()
    metadata['cleanup'] = cleanup
    metadata['error'] = error
    _write_json(metadata_path, metadata)
    _merge_container_metadata_reference(run_bundle_path)


def _merge_container_metadata_reference(run_bundle_path: Path) -> None:
    run_manifest_path = run_bundle_path / RUN_MANIFEST_FILENAME
    if not run_manifest_path.exists():
        return
    payload = _load_json(run_manifest_path, default={})
    payload['container'] = {'metadata_path': DOCKER_ATTEMPT_METADATA_FILENAME}
    _write_json(run_manifest_path, payload)


def _append_run_bundle_error(run_bundle_path: Path, error: str) -> None:
    if not error:
        return
    for filename in (RUN_STATUS_FILENAME, RUN_MANIFEST_FILENAME):
        path = run_bundle_path / filename
        if not path.exists():
            continue
        payload = _load_json(path, default={})
        errors = payload.get('errors')
        error_list = [str(item) for item in errors] if isinstance(errors, list) else []
        if error not in error_list:
            error_list.append(error)
        payload['errors'] = error_list
        payload['error_count'] = len(error_list)
        _write_json(path, payload)


def _volume_summary(volumes: Mapping[str, Mapping[str, str]]) -> list[dict[str, str]]:
    return [
        {
            'source': str(source),
            'target': str(config.get('bind', '')),
            'mode': str(config.get('mode', '')),
        }
        for source, config in sorted(volumes.items())
    ]


def _container_exit_code(result: object) -> int:
    if isinstance(result, dict):
        status_code = result.get('StatusCode')
        if isinstance(status_code, int):
            return status_code
    return 1


def _docker_timeout_seconds(request: DockerAttemptRequest) -> float | None:
    budget = _attempt_budget_seconds(request.campaign, request.variant)
    if budget <= 0:
        return None
    return budget + max(float(request.campaign.runner_readiness_timeout_seconds), 30.0)


def _container_name(run_id: str) -> str:
    safe = ''.join(char if char.isalnum() or char in {'-', '_'} else '-' for char in run_id.lower())
    return f'geo-agent-eval-{safe}-{uuid4().hex[:8]}'


def _is_secret_name(name: str) -> bool:
    upper = name.upper()
    return name in SECRET_ENV_NAMES or any(token in upper for token in ('KEY', 'TOKEN', 'SECRET'))


def _load_json(path: Path, *, default: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return default
    if not isinstance(payload, dict):
        return default
    return payload
