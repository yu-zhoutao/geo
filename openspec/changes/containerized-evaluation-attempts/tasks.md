## 1. Docker Image And Entrypoint

- [x] 1.1 Add Docker SDK support as an optional runner dependency with clear runtime errors when unavailable.
- [x] 1.2 Add `evaluation.Dockerfile` that installs system geospatial libraries, Python dependencies, OpenCode runtime dependency, app code, evaluation assets, and the managed geospatial Python environment, with cache mounts for repeated builds.
- [x] 1.3 Add a Docker ignore file or build context rules that exclude local run outputs, virtual environments, caches, `.env`, and other host-only files from the evaluation image.
- [x] 1.4 Add an evaluation single-attempt entrypoint module that accepts attempt identity, campaign settings, model settings, scoring settings, `/data`, and `/evaluation-run`.
- [x] 1.5 Ensure the image records source revision and build metadata labels when available.

## 2. Runner Backend Selection

- [x] 2.1 Add runner execution backend types for `local-process` and `docker-per-attempt` while keeping `local-process` as the default.
- [x] 2.2 Add CLI flags for selecting Docker execution, Docker image reference, host data directory, container data mount path, and container run bundle mount path.
- [x] 2.3 Keep campaign initialization, planned attempt selection, resume policy, deterministic reference handling, and aggregation in the host runner.
- [x] 2.4 Route non-deterministic planned attempts through the Docker backend only when explicitly selected.

## 3. Docker Attempt Orchestration

- [x] 3.1 Implement a Docker attempt runner that creates one container per non-deterministic planned attempt using the Python Docker SDK.
- [x] 3.2 Construct mounts so only host `data/` is mounted read-only at `/data` and the current attempt run bundle is mounted read-write at `/evaluation-run`.
- [x] 3.3 Pass only required non-secret and secret environment variables into the container, and ensure secret values are redacted from persisted metadata.
- [x] 3.4 Supervise container timeout and cancellation so active containers are stopped and removed when the host runner is interrupted.
- [x] 3.5 Capture container stdout/stderr or Docker logs, exit code, image ID, container ID, mount summary, and cleanup outcome into the run bundle.

## 4. Container Attempt Execution

- [x] 4.1 Inside the container entrypoint, load the requested scenario and variant from image-contained assets and fail the attempt if either is unavailable.
- [x] 4.2 Configure container-local app state, metadata database, workspace root, runtime config, cache, and temporary directories.
- [x] 4.3 Start the backend app inside the container through the existing evaluation app lifecycle helper and execute the scenario through the app API client.
- [x] 4.4 Materialize synthetic dataset packs under `/evaluation-run/dataset-pack` and resolve reusable repo-file data through `/data` for Docker-backed attempts.
- [x] 4.5 Capture the standard run bundle, deterministic score, judge input/response/score when configured, and app logs under `/evaluation-run`.
- [x] 4.6 Write a failed run status and useful diagnostics when app readiness, runtime execution, scoring, or trace capture fails inside the container.

## 5. Tests And Validation

- [x] 5.1 Add unit tests for Docker backend selection and default local-process behavior.
- [x] 5.2 Add unit tests with mocked Docker SDK objects proving mount construction excludes the repo root, `.env`, sibling run bundles, campaign root, user home, and Docker socket.
- [x] 5.3 Add unit tests proving environment metadata redacts API keys and secret values.
- [x] 5.4 Add unit tests for container timeout, non-zero exit, missing Docker daemon/image, and cleanup-error run status handling.
- [x] 5.5 Add entrypoint tests for single-attempt argument parsing, missing scenario/variant failure, synthetic dataset materialization, and `/data` dataset resolution.
- [x] 5.6 Run the existing evaluation test suite to verify local-process behavior remains unchanged.
- [x] 5.7 Build the evaluation image locally and run one Docker-backed smoke attempt against a representative case with `data/` mounted read-only.
- [x] 5.8 Verify the smoke run bundle contains standard score artifacts plus container metadata and does not contain secret values or unrelated host files.
