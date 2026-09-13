## Purpose
Define the local application bootstrap boundary so the frontend, backend, and backend-managed OpenCode server integration start and operate as a single machine-managed system.

## Requirements

### Requirement: Local full-stack bootstrap
The system SHALL provide a single-machine bootstrap path that starts the Vue frontend, the FastAPI backend, and the backend-managed OpenCode server integration without requiring the user to manually author or register agent, skill, model-provider, or MCP configuration.

#### Scenario: Fresh local startup succeeds
- **WHEN** a user follows the documented bootstrap command sequence in a clean local environment with required secrets and dataset paths available
- **THEN** the frontend and backend start successfully and the backend reports the application runtime as ready for real session work

#### Scenario: Bootstrap prepares SQLite, shared workspace, and runtime directories
- **WHEN** the backend starts in a supported local environment
- **THEN** it initializes the SQLite-backed app metadata store, resolves the shared workspace and runtime directories, and reports whether OpenCode provider and runtime configuration are ready for agent tasks

### Requirement: Backend-owned runtime lifecycle
The Python backend SHALL own OpenCode server availability checks, startup coordination, config override, reconnect behavior if startup is deferred, and shutdown cleanup for the real agent runtime integration used by the application.

#### Scenario: Runtime is prepared before use
- **WHEN** the frontend requests application status or attempts to create a session
- **THEN** the backend verifies OpenCode availability, applies the required app-owned config state, and either returns a ready state or a structured not-ready state with actionable status details

#### Scenario: Backend shutdown cleans up managed processes
- **WHEN** the backend process exits during local development or demo use
- **THEN** backend-managed OpenCode and task subprocesses are terminated and cleaned up without leaving orphaned child processes behind

### Requirement: Browser-facing app boundary
The system MUST expose browser-facing bootstrap and runtime status only through the application's own HTTP and SSE surfaces, and the browser MUST NOT depend on direct access to runtime internals.

#### Scenario: Frontend uses app-owned endpoints
- **WHEN** the task dashboard loads or subscribes to live updates
- **THEN** it obtains bootstrap status and session activity through backend endpoints and SSE streams exposed by the application

### Requirement: Backend-hosted MCP extension point
The backend SHALL define the application-managed MCP hosting boundary for geospatial capabilities so deterministic backend tools can be wired into the OpenCode runtime without restructuring the bootstrap architecture.

#### Scenario: MCP wiring path is application managed
- **WHEN** the runtime is prepared for application use
- **THEN** the backend can supply bundled MCP configuration defaults that are scoped to the application-managed environment rather than uncontrolled user-global state

### Requirement: Backend bootstrap supports injected settings
The backend SHALL provide an application bootstrap path that can build the FastAPI app and its service graph from caller-supplied `Settings` so controlled environments can override machine-local storage roots.

#### Scenario: Test bootstrap injects isolated settings
- **WHEN** a test or other controlled caller constructs the backend app with explicit `Settings`
- **THEN** the resulting FastAPI instance, runtime manager, and session service all use the injected storage and runtime paths instead of process-global defaults captured from the developer environment

### Requirement: Bootstrap service graph uses one runtime client
The local FastAPI bootstrap SHALL construct one managed OpenCode runtime client per app instance and inject that shared client into every backend service that needs runtime status, runtime lifecycle, session execution, interruption, or transcript recovery.

#### Scenario: App construction shares runtime dependency
- **WHEN** the backend builds the FastAPI app service graph
- **THEN** the runtime manager and session service are created with the same runtime client object
- **AND** no secondary session-only OpenCode runtime client is constructed by default

#### Scenario: Injected settings still isolate test app storage
- **WHEN** a test or controlled caller constructs a FastAPI app with explicit settings
- **THEN** the shared runtime client uses those injected settings
- **AND** both runtime health and session execution resolve app-support, workspace, and runtime-state paths from the same injected settings
