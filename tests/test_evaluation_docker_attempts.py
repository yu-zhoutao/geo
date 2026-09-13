from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import json
from pathlib import Path
import time
from typing import Any

import pytest

from app.config import Settings
from app.evaluation.benchmarks import BenchmarkValidationError
from app.evaluation.docker_attempts import (
    DOCKER_ATTEMPT_METADATA_FILENAME,
    DockerAttemptOptions,
    DockerAttemptRequest,
    _docker_context_host,
    docker_attempt_environment,
    docker_attempt_volumes,
    redact_environment,
    run_docker_attempt,
)
from app.evaluation.runner import allocate_run_bundle, execute_campaign_run, initialize_campaign_run


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _campaign_path() -> Path:
    return _repo_root() / 'app' / 'evaluation_assets' / 'campaigns' / 'thesis-balanced-v1.yaml'


def _variant_root() -> Path:
    return _repo_root() / 'app' / 'evaluation_assets' / 'variants'


def _request(tmp_path: Path, data_dir: Path) -> DockerAttemptRequest:
    initialized = initialize_campaign_run(
        _campaign_path(),
        variant_root=_variant_root(),
        output_root=tmp_path,
        timestamp=datetime(2026, 4, 29, 1, 2, 3, tzinfo=UTC),
    )
    planned_attempt = next(
        attempt for attempt in initialized.planned_attempts if attempt.id == 'full-system__P01__r001'
    )
    allocation = allocate_run_bundle(planned_attempt)
    scenario = next(scenario for scenario in initialized.scenarios if scenario.id == 'P01')
    variant = next(variant for variant in initialized.variants if variant.id == 'full-system')
    return DockerAttemptRequest(
        campaign=initialized.campaign,
        allocation=allocation,
        scenario=scenario,
        variant=variant,
        options=DockerAttemptOptions(image='geo-agent-eval:test', data_dir=data_dir),
    )


def _strategy_request(tmp_path: Path, data_dir: Path) -> DockerAttemptRequest:
    initialized = initialize_campaign_run(
        _campaign_path(),
        variant_root=_variant_root(),
        output_root=tmp_path,
        timestamp=datetime(2026, 4, 29, 1, 2, 3, tzinfo=UTC),
        strategy_profile_ids=('crs_first',),
        strategy_policy_checkpoint_id='checkpoint-0001',
        strategy_trl_run_id='trl-run-1',
        strategy_training_step=2,
    )
    planned_attempt = next(
        attempt for attempt in initialized.planned_attempts if attempt.id == 'full-system__crs_first__P01__r001'
    )
    allocation = allocate_run_bundle(planned_attempt)
    scenario = next(scenario for scenario in initialized.scenarios if scenario.id == 'P01')
    variant = next(variant for variant in initialized.variants if variant.id == 'full-system')
    return DockerAttemptRequest(
        campaign=initialized.campaign,
        allocation=allocation,
        scenario=scenario,
        variant=variant,
        options=DockerAttemptOptions(image='geo-agent-eval:test', data_dir=data_dir),
    )


class FakeImage:
    id = 'sha256:test-image'


class FakeContainer:
    def __init__(
        self,
        *,
        bundle_path: Path,
        run_id: str,
        exit_code: int = 0,
        write_bundle: bool = True,
        wait_delay: float = 0.0,
        remove_error: Exception | None = None,
        log_text: bytes = b'container log with secret-key',
    ) -> None:
        self.id = 'container-123'
        self.name = 'geo-agent-eval-test'
        self.image = FakeImage()
        self.bundle_path = bundle_path
        self.run_id = run_id
        self.exit_code = exit_code
        self.write_bundle = write_bundle
        self.wait_delay = wait_delay
        self.remove_error = remove_error
        self.log_text = log_text
        self.stopped = False
        self.removed = False

    def wait(self) -> dict[str, int]:
        if self.wait_delay:
            time.sleep(self.wait_delay)
        if self.write_bundle:
            _write_minimal_bundle(self.bundle_path, self.run_id)
        return {'StatusCode': self.exit_code}

    def logs(self, *, stdout: bool = True, stderr: bool = True) -> bytes:
        return self.log_text

    def stop(self, *, timeout: int) -> None:
        self.stopped = True

    def remove(self, *, force: bool) -> None:
        self.removed = True
        if self.remove_error is not None:
            raise self.remove_error


class FakeContainers:
    def __init__(
        self,
        *,
        exit_code: int = 0,
        write_bundle: bool = True,
        wait_delay: float = 0.0,
        remove_error: Exception | None = None,
        results: list[dict[str, object]] | None = None,
    ) -> None:
        self.exit_code = exit_code
        self.write_bundle = write_bundle
        self.wait_delay = wait_delay
        self.remove_error = remove_error
        self.results: list[dict[str, object]] = list(results or [])
        self.calls: list[dict[str, Any]] = []
        self.last_container: FakeContainer | None = None

    def run(self, image: str, **kwargs: Any) -> FakeContainer:
        self.calls.append({'image': image, **kwargs})
        result: dict[str, object] = self.results.pop(0) if self.results else {}
        volumes = kwargs['volumes']
        bundle_path = Path(next(source for source, config in volumes.items() if config['bind'] == '/evaluation-run'))
        run_id = _arg_value(kwargs['command'], '--run-id')
        self.last_container = FakeContainer(
            bundle_path=bundle_path,
            run_id=run_id,
            exit_code=int(result.get('exit_code', self.exit_code)),
            write_bundle=bool(result.get('write_bundle', self.write_bundle)),
            wait_delay=float(result.get('wait_delay', self.wait_delay)),
            remove_error=self.remove_error,
            log_text=bytes(result.get('log_text', b'container log with secret-key')),
        )
        return self.last_container


class FakeDockerClient:
    def __init__(self, containers: FakeContainers) -> None:
        self.containers = containers


@pytest.mark.asyncio
async def test_execute_campaign_run_routes_non_deterministic_attempt_through_docker_backend(tmp_path: Path) -> None:
    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    fake_containers = FakeContainers()

    execution = await execute_campaign_run(
        _campaign_path(),
        variant_root=_variant_root(),
        output_root=tmp_path,
        timestamp=datetime(2026, 4, 29, 1, 2, 3, tzinfo=UTC),
        max_attempts=1,
        execution_backend='docker-per-attempt',
        docker_data_dir=data_dir,
        docker_client=FakeDockerClient(fake_containers),
    )

    assert len(execution.run_captures) == 1
    assert fake_containers.calls
    assert fake_containers.calls[0]['image'] == 'geo-agent-eval:latest'


@pytest.mark.asyncio
async def test_execute_campaign_run_rejects_removed_deterministic_reference_attempt_with_docker_backend(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    fake_containers = FakeContainers()

    with pytest.raises(BenchmarkValidationError, match='Unknown planned attempt id'):
        await execute_campaign_run(
            _campaign_path(),
            variant_root=_variant_root(),
            output_root=tmp_path,
            timestamp=datetime(2026, 4, 29, 1, 2, 3, tzinfo=UTC),
            attempt_ids=('deterministic-gis-reference__P01__r001',),
            execution_backend='docker-per-attempt',
            docker_data_dir=data_dir,
            docker_client=FakeDockerClient(fake_containers),
        )

    assert not fake_containers.calls


@pytest.mark.asyncio
async def test_execute_campaign_run_retries_rate_limited_docker_attempt_without_counting_extra_repeat(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    fake_containers = FakeContainers(
        results=[
            {'exit_code': 2, 'write_bundle': False, 'log_text': b'HTTP 429 too many requests'},
            {'exit_code': 0, 'write_bundle': True, 'log_text': b'ok'},
        ]
    )

    execution = await execute_campaign_run(
        _campaign_path(),
        variant_root=_variant_root(),
        output_root=tmp_path,
        timestamp=datetime(2026, 4, 29, 1, 2, 3, tzinfo=UTC),
        max_attempts=1,
        execution_backend='docker-per-attempt',
        docker_data_dir=data_dir,
        docker_client=FakeDockerClient(fake_containers),
        infrastructure_max_retries=1,
    )

    bundle_root = execution.run_captures[0].bundle_root
    status = json.loads((bundle_root / 'run-status.json').read_text(encoding='utf-8'))

    assert len(fake_containers.calls) == 2
    assert execution.run_captures[0].run_id == 'full-system__C06__r001'
    assert status['terminal_reason'] == 'completed'
    assert bundle_root.name == 'repeat-001'
    assert not bundle_root.with_name('repeat-001-attempt-002').exists()


@pytest.mark.asyncio
async def test_docker_attempt_mounts_only_data_and_current_run_bundle(tmp_path: Path) -> None:
    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    fake_containers = FakeContainers()
    request = _request(tmp_path, data_dir)

    capture = await run_docker_attempt(request, docker_client=FakeDockerClient(fake_containers))

    call = fake_containers.calls[0]
    volumes = call['volumes']
    assert capture.run_id == 'full-system__P01__r001'
    assert volumes == docker_attempt_volumes(request.options, request.allocation.path)
    assert volumes[str(data_dir.resolve())] == {'bind': '/data', 'mode': 'ro'}
    assert volumes[str(request.allocation.path.resolve())] == {'bind': '/evaluation-run', 'mode': 'rw'}
    assert str(_repo_root()) not in volumes
    assert str(_repo_root() / '.env') not in volumes
    assert str(request.allocation.path.parent) not in volumes
    metadata = json.loads((request.allocation.path / DOCKER_ATTEMPT_METADATA_FILENAME).read_text(encoding='utf-8'))
    assert sorted(metadata['mounts'], key=lambda item: item['target']) == [
        {'source': str(data_dir.resolve()), 'target': '/data', 'mode': 'ro'},
        {'source': str(request.allocation.path.resolve()), 'target': '/evaluation-run', 'mode': 'rw'},
    ]


@pytest.mark.asyncio
async def test_docker_attempt_command_and_metadata_include_strategy(tmp_path: Path) -> None:
    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    fake_containers = FakeContainers()
    request = _strategy_request(tmp_path, data_dir)

    await run_docker_attempt(request, docker_client=FakeDockerClient(fake_containers))

    command = fake_containers.calls[0]['command']
    metadata = json.loads((request.allocation.path / DOCKER_ATTEMPT_METADATA_FILENAME).read_text(encoding='utf-8'))
    assert _arg_value(command, '--strategy-id') == 'crs_first'
    assert _arg_value(command, '--strategy-source') == 'offline-sweep'
    assert _arg_value(command, '--strategy-profile-hash') == request.allocation.planned_attempt.strategy.profile_hash
    assert _arg_value(command, '--policy-checkpoint-id') == 'checkpoint-0001'
    assert _arg_value(command, '--trl-run-id') == 'trl-run-1'
    assert _arg_value(command, '--training-step') == '2'
    assert metadata['strategy']['strategy_id'] == 'crs_first'
    assert metadata['strategy']['policy_checkpoint_id'] == 'checkpoint-0001'


def test_docker_attempt_environment_redacts_secrets() -> None:
    environment = docker_attempt_environment(
        Settings(
            model_provider='deepseek',
            glm_api_key='glm-secret',
            deepseek_api_key='deepseek-secret',
            deepseek_model='deepseek-v4-flash',
        )
    )

    redacted = redact_environment(environment)

    assert environment['GEO_AGENT_DEEPSEEK_API_KEY'] == 'deepseek-secret'
    assert redacted['GEO_AGENT_GLM_API_KEY'] == '[redacted]'
    assert redacted['GEO_AGENT_DEEPSEEK_API_KEY'] == '[redacted]'
    assert redacted['GEO_AGENT_DEEPSEEK_MODEL'] == 'deepseek-v4-flash'


def test_docker_context_host_reads_current_cli_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_root = tmp_path / '.docker'
    meta_root = config_root / 'contexts' / 'meta' / 'context-id'
    meta_root.mkdir(parents=True)
    _write_json(config_root / 'config.json', {'currentContext': 'desktop-linux'})
    _write_json(
        meta_root / 'meta.json',
        {
            'Name': 'desktop-linux',
            'Endpoints': {
                'docker': {
                    'Host': 'unix:///tmp/docker.sock',
                    'SkipTLSVerify': False,
                },
            },
        },
    )
    monkeypatch.setenv('HOME', str(tmp_path))

    assert _docker_context_host() == 'unix:///tmp/docker.sock'


@pytest.mark.asyncio
async def test_docker_attempt_records_nonzero_exit_as_failed_bundle(tmp_path: Path) -> None:
    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    request = _request(tmp_path, data_dir)
    fake_containers = FakeContainers(exit_code=2, write_bundle=False)

    capture = await run_docker_attempt(request, docker_client=FakeDockerClient(fake_containers))

    status = json.loads((capture.bundle_root / 'run-status.json').read_text(encoding='utf-8'))
    metadata = json.loads((capture.bundle_root / DOCKER_ATTEMPT_METADATA_FILENAME).read_text(encoding='utf-8'))
    assert capture.error_count == 1
    assert status['session_status'] == 'failed'
    assert status['terminal_reason'] == 'container_failed'
    assert metadata['container']['exit_code'] == 2


@pytest.mark.asyncio
async def test_docker_attempt_timeout_stops_container_and_records_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    request = _request(tmp_path, data_dir)
    fake_containers = FakeContainers(wait_delay=0.1)
    monkeypatch.setattr('app.evaluation.docker_attempts._docker_timeout_seconds', lambda _request: 0.01)

    capture = await run_docker_attempt(request, docker_client=FakeDockerClient(fake_containers))

    status = json.loads((capture.bundle_root / 'run-status.json').read_text(encoding='utf-8'))
    assert status['terminal_reason'] == 'container_timeout'
    assert fake_containers.last_container is not None
    assert fake_containers.last_container.stopped is True


@pytest.mark.asyncio
async def test_docker_attempt_cancellation_stops_and_removes_container(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def cancelled_wait(_container: Any, *, timeout_seconds: float | None) -> object:
        raise asyncio.CancelledError

    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    request = _request(tmp_path, data_dir)
    fake_containers = FakeContainers(write_bundle=False)
    monkeypatch.setattr('app.evaluation.docker_attempts._wait_for_container', cancelled_wait)

    with pytest.raises(asyncio.CancelledError):
        await run_docker_attempt(request, docker_client=FakeDockerClient(fake_containers))

    status = json.loads((request.allocation.path / 'run-status.json').read_text(encoding='utf-8'))
    metadata = json.loads((request.allocation.path / DOCKER_ATTEMPT_METADATA_FILENAME).read_text(encoding='utf-8'))
    assert status['terminal_reason'] == 'container_cancelled'
    assert metadata['cleanup'] == 'stopped_after_cancellation'
    assert fake_containers.last_container is not None
    assert fake_containers.last_container.stopped is True
    assert fake_containers.last_container.removed is True


@pytest.mark.asyncio
async def test_docker_attempt_records_cleanup_error(tmp_path: Path) -> None:
    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    request = _request(tmp_path, data_dir)
    fake_containers = FakeContainers(remove_error=RuntimeError('remove failed'))

    capture = await run_docker_attempt(request, docker_client=FakeDockerClient(fake_containers))

    status = json.loads((capture.bundle_root / 'run-status.json').read_text(encoding='utf-8'))
    metadata = json.loads((capture.bundle_root / DOCKER_ATTEMPT_METADATA_FILENAME).read_text(encoding='utf-8'))
    assert capture.error_count == 1
    assert 'cleanup failed' in status['errors'][0]
    assert metadata['cleanup'] == 'cleanup_failed'


def _write_minimal_bundle(bundle_path: Path, run_id: str) -> None:
    _write_json(
        bundle_path / 'run-status.json',
        {
            'schema': 'geo-agent.evaluation.run-status.v1',
            'session_id': 'session-1',
            'session_status': 'completed',
            'terminal_reason': 'completed',
            'timed_out': False,
            'error_count': 0,
            'errors': [],
        },
    )
    _write_json(
        bundle_path / 'artifact-manifest.json',
        {
            'schema': 'geo-agent.evaluation.artifact-capture.v1',
            'session_id': 'session-1',
            'artifact_count': 0,
            'items': [],
        },
    )
    _write_json(
        bundle_path / 'run-manifest.json',
        {
            'schema': 'geo-agent.evaluation.run-bundle.v1',
            'run_id': run_id,
            'session_id': 'session-1',
            'error_count': 0,
            'errors': [],
        },
    )


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def _arg_value(command: list[str], name: str) -> str:
    return command[command.index(name) + 1]
