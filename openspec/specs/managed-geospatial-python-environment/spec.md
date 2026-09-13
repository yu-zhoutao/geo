# managed-geospatial-python-environment Specification

## Purpose
TBD - created by archiving change redesign-geospatial-mcp-primitives. Update Purpose after archive.
## Requirements
### Requirement: Managed geospatial Python environment is available
The application SHALL provide an application-managed Python environment for OpenCode geospatial sessions using a separate geospatial runtime project, bundled `uv`, Python 3.12, and an app-support virtual environment that includes commonly used geospatial analysis libraries needed by agent-authored scripts.

#### Scenario: Runtime environment includes geospatial packages
- **WHEN** the backend prepares runtime support for a geospatial session
- **THEN** the Python environment used by runtime-authored scripts includes GeoPandas, Pyogrio, Shapely, PyProj, Rasterio, NumPy, Pandas, SciPy, scikit-learn, Matplotlib, MapClassify, PyArrow, OpenPyXL, Pillow, Contextily, Folium, Rasterstats, esda, and libpysal
- **AND** the user is not required to install those packages manually outside the application bootstrap path.

#### Scenario: Environment uses Python 3.12
- **WHEN** the backend provisions or validates the geospatial Python environment
- **THEN** it requests Python 3.12 through bundled `uv`
- **AND** it verifies that the resolved interpreter uses Python 3.12 before reporting the environment ready.

#### Scenario: Environment does not pollute app development venv
- **WHEN** the backend runs in development or packaged mode
- **THEN** the geospatial virtual environment is created under the configured app-support runtime path through `UV_PROJECT_ENVIRONMENT`
- **AND** it does not reuse or mutate the backend application's own development virtual environment.

#### Scenario: Development and packaged modes use the same provisioning flow
- **WHEN** the app starts in development mode or packaged mode
- **THEN** it uses the same bundled-uv provisioning command shape and the same geospatial runtime project dependency declarations, differing only in resolved resource and app-support paths.

#### Scenario: PySAL packages are validated before geospatial sessions run
- **WHEN** environment readiness validation runs for the managed geospatial Python environment
- **THEN** it verifies that `esda` and `libpysal` can be imported from the same managed environment used by agent-authored scripts
- **AND** it reports a structured environment-not-ready state if either import fails.

#### Scenario: Missing geospatial package blocks readiness
- **WHEN** a required geospatial package cannot be imported from the managed Python environment
- **THEN** the backend reports a structured runtime-not-ready or environment-not-ready state instead of letting the agent discover the missing package after starting analysis.

#### Scenario: Provisioning blocks geospatial sessions until ready
- **WHEN** the managed geospatial Python environment is missing, stale, or currently provisioning
- **THEN** the backend does not start a geospatial analysis session that depends on that environment
- **AND** it exposes provisioning status, phase-estimated progress, and logs until the environment is ready or has failed.

#### Scenario: Provisioning does not block backend startup
- **WHEN** the application starts and the managed geospatial Python environment requires provisioning
- **THEN** backend startup completes without waiting for dependency installation to finish
- **AND** `/api/health` remains available so the dashboard can show provisioning progress and logs.
- **AND** startup and health reporting do not synchronously run geospatial package import validation on the request path.

#### Scenario: Provisioning logs stream while install runs
- **WHEN** bundled-uv provisioning emits stdout or stderr output
- **THEN** the backend appends those lines to the geospatial environment status while the process is still running
- **AND** the dashboard can poll `/api/health` to display updated logs before provisioning exits.

#### Scenario: Provisioning progress is phase-estimated
- **WHEN** the backend reports geospatial environment provisioning progress
- **THEN** the numeric progress represents coarse phases such as checking, installing, validating, and ready
- **AND** it does not increase merely because more log lines were emitted.

#### Scenario: Provisioning failure includes explicit error logs
- **WHEN** bundled-uv provisioning or package validation fails
- **THEN** the backend appends at least one concrete error log line prefixed with `ERROR:`
- **AND** failed provisioning progress remains at the failed phase rather than reporting `1.0` unless the environment is ready.

#### Scenario: Validation timeout is not reported as missing packages
- **WHEN** geospatial package validation times out or the validation subprocess fails before producing import results
- **THEN** the backend reports the validation failure reason in logs
- **AND** it does not claim that every required geospatial package is missing.

### Requirement: Python execution command is stable
The system SHALL expose a stable command contract for agent-authored geospatial scripts using the application-managed project environment.

#### Scenario: Agent receives recommended command
- **WHEN** the runtime calls `get_session_context`
- **THEN** the result includes the recommended command pattern `"$GEO_AGENT_UV_BIN" --project "$GEO_AGENT_GEO_PYTHON_PROJECT" run --python "$GEO_AGENT_GEO_PYTHON_VERSION" python <script>` and the workspace path needed to execute it.

#### Scenario: Command preserves workspace execution evidence
- **WHEN** an agent writes a script under the session workspace and runs it with the recommended command
- **THEN** the script file, command transcript, generated outputs, and any recorded evidence remain inside the managed workspace evidence chain.

### Requirement: Geospatial environment variables are injected
The backend SHALL inject the environment variables needed for agent-authored geospatial scripts into managed OpenCode sessions without exposing a predefined artifact subdirectory.

#### Scenario: Runtime environment exposes workspace and context paths
- **WHEN** a managed OpenCode session starts for a geospatial request
- **THEN** the runtime process has `GEO_AGENT_REPO_ROOT`, `GEO_AGENT_UV_BIN`, `GEO_AGENT_GEO_PYTHON_PROJECT`, `GEO_AGENT_GEO_PYTHON_VERSION`, `UV_PROJECT_ENVIRONMENT`, `GEO_AGENT_WORKSPACE_PATH`, `GEO_AGENT_SESSION_CONTEXT_ID`, and `GEO_AGENT_ATTACHED_DATA_DIRS_JSON` available to bash and Python subprocesses
- **AND** it does not expose `GEO_AGENT_ARTIFACT_DIR` or another application-defined output subdirectory variable.

#### Scenario: Context tool reports environment variables
- **WHEN** the runtime invokes `get_session_context`
- **THEN** the result includes the workspace root and the stable command contract so the agent can verify the active execution context before running scripts
- **AND** it does not instruct the agent to use an application-defined artifact directory.

### Requirement: Workspace artifact reporting is explicit
The managed geospatial workspace SHALL let agents create scripts, intermediate files, artifacts, and evidence records without backend-owned file discovery, prescribed workflow stages, or prescribed output directories.

#### Scenario: Session context includes workspace path only
- **WHEN** the runtime invokes `get_session_context`
- **THEN** the agent-facing result includes the session workspace path
- **AND** it does not list `.geo/scripts`, `.geo/intermediate`, `.geo/artifacts`, `.geo/evidence`, or other backend-reserved subdirectories.

#### Scenario: Backend does not discover artifacts implicitly
- **WHEN** files are created under the workspace
- **THEN** the dashboard does not surface them as artifacts until the agent explicitly reports them with `record_run_evidence`.

