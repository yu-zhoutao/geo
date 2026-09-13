## ADDED Requirements

### Requirement: Evaluation runner supports opt-in Docker attempt execution
The system SHALL let the existing evaluation runner execute non-deterministic planned attempts through a Docker-per-attempt backend while preserving the current local-process backend as the default.

#### Scenario: Local execution remains default
- **WHEN** a campaign is executed without selecting the Docker backend
- **THEN** the runner uses the existing local app-process execution path

#### Scenario: Docker backend is selected explicitly
- **WHEN** a campaign is executed with the Docker backend selected
- **THEN** the runner initializes the campaign on the host and launches one Docker container for each selected non-deterministic planned attempt

#### Scenario: Deterministic reference stays host-side
- **WHEN** a selected planned attempt uses the deterministic GIS reference variant
- **THEN** the runner writes the deterministic reference run bundle without starting an attempt container

#### Scenario: Missing Docker runtime fails clearly
- **WHEN** the Docker backend is selected but the Docker SDK, Docker daemon, or configured image is unavailable
- **THEN** the runner fails the affected attempt with a structured error rather than silently falling back to local-process execution

### Requirement: Attempt containers expose only bounded filesystem mounts
The Docker backend SHALL start each attempt container with only the project data directory mounted read-only and the current attempt run bundle mounted read-write.

#### Scenario: Attempt receives read-only data mount
- **WHEN** the runner starts an attempt container
- **THEN** it mounts the selected host `data/` directory at `/data` in read-only mode

#### Scenario: Attempt receives only its run bundle as writable mount
- **WHEN** the runner starts an attempt container
- **THEN** it mounts the allocated attempt run bundle directory at `/evaluation-run` in read-write mode

#### Scenario: Sibling run bundles are not visible
- **WHEN** an attempt container is running
- **THEN** sibling run bundles, the campaign root, and the project `evaluation-runs/` root are not mounted into the container

#### Scenario: Host repository and secrets are not mounted
- **WHEN** an attempt container is running
- **THEN** the host repository root, host `.env` file, user home directory, Docker socket, and user-global OpenCode config directories are not mounted into the container

#### Scenario: Container-local runtime state is isolated
- **WHEN** the app and OpenCode runtime run inside an attempt container
- **THEN** app support, metadata database, workspace root, runtime config, cache, and temporary files resolve to container-local paths or current attempt paths rather than host-global paths

### Requirement: Container attempt entrypoint runs exactly one planned attempt
The evaluation image SHALL provide a single-attempt entrypoint that runs one selected scenario/variant/repeat through the app API boundary and writes the standard run bundle under `/evaluation-run`.

#### Scenario: Entrypoint receives attempt identity
- **WHEN** the host runner starts an attempt container
- **THEN** it passes the planned attempt ID, variant ID, scenario ID, repeat index, campaign budget settings, scoring mode, judge configuration, and run ID to the container entrypoint

#### Scenario: Entrypoint uses real app runtime path
- **WHEN** the container entrypoint executes an agent-backed attempt
- **THEN** it starts the backend app, uses the app API client to create a session, attaches scenario data, submits the scenario prompt unchanged, supervises runtime state, captures the run bundle, and runs configured scoring

#### Scenario: Entrypoint does not orchestrate campaigns
- **WHEN** the container entrypoint starts
- **THEN** it handles only the single planned attempt described by its inputs and does not select additional scenarios, variants, or repeats

#### Scenario: Missing scenario or variant in image is fatal
- **WHEN** the container image cannot load the requested scenario or variant asset
- **THEN** the entrypoint writes a failed run status for that attempt instead of reading host repository files

### Requirement: Docker-backed attempts preserve standard run evidence
Docker-backed attempts SHALL produce the same core run-bundle evidence as local-process attempts and SHALL add container metadata needed to audit isolation.

#### Scenario: Standard run files are written
- **WHEN** a Docker-backed attempt reaches terminal state or fails after container startup
- **THEN** the run bundle contains run status, run manifest, session trace when available, transcript when available, evidence records when available, artifact manifest, copied artifacts, deterministic score, judge artifacts when configured, and attempt logs

#### Scenario: Container metadata is recorded
- **WHEN** a Docker-backed attempt completes or fails
- **THEN** the run bundle records Docker image reference, image ID or digest when available, container ID when available, mount summary, non-secret environment summary, exit code, start time, finish time, and cleanup outcome

#### Scenario: API secrets are excluded from artifacts
- **WHEN** the runner writes Docker attempt metadata, logs, or manifests
- **THEN** provider API key values and secret environment values are not persisted in the run bundle

#### Scenario: Aggregation reads Docker-backed bundles
- **WHEN** campaign aggregation processes a campaign containing Docker-backed run bundles
- **THEN** it reads the same score and status files used by local-process bundles and does not require direct access to container-local state

### Requirement: Docker backend manages container lifecycle and failure capture
The Docker backend SHALL own container creation, timeout supervision, cancellation, log capture, and cleanup for every Docker-backed attempt.

#### Scenario: Timeout stops the attempt container
- **WHEN** a Docker-backed attempt exceeds its configured wall-clock budget
- **THEN** the runner stops the container, records a timeout status, captures available logs, and does not continue the same attempt on the host

#### Scenario: Cancellation stops the attempt container
- **WHEN** the campaign runner is interrupted while a Docker-backed attempt is running
- **THEN** the runner attempts to stop and remove the active container before exiting

#### Scenario: Non-zero container exit is captured
- **WHEN** an attempt container exits with a non-zero status
- **THEN** the runner records the exit code, captured stdout/stderr or Docker logs, and container metadata in the run bundle

#### Scenario: Cleanup errors are visible
- **WHEN** the runner cannot remove or clean up a completed attempt container
- **THEN** it records the cleanup error in the run bundle without marking the attempt as a normal completion solely because cleanup failed

### Requirement: Docker-backed attempts use read-only shared datasets safely
The Docker backend SHALL expose reusable evaluation datasets through `/data` as read-only input while preserving per-attempt dataset materialization under the current run bundle.

#### Scenario: Repo-file datasets resolve under mounted data when configured
- **WHEN** a scenario references external reusable data for Docker-backed execution
- **THEN** the container resolves that dataset through `/data` and treats it as read-only input

#### Scenario: Synthetic dataset packs remain per-attempt
- **WHEN** a scenario uses synthetic dataset pack mode
- **THEN** the container materializes the dataset pack under `/evaluation-run/dataset-pack` for that attempt

#### Scenario: Agent outputs do not write into data source
- **WHEN** an agent creates scripts, intermediate files, maps, reports, or derived datasets during a Docker-backed attempt
- **THEN** durable outputs are written under the attempt workspace or `/evaluation-run` and not into `/data`
