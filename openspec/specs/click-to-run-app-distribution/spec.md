# click-to-run-app-distribution Specification

## Purpose
TBD - created by archiving change redesign-geospatial-mcp-primitives. Update Purpose after archive.
## Requirements
### Requirement: Distribution bundles application runtime assets
The system SHALL support a click-to-run distribution model that packages the frontend build output, backend service code, app-owned geospatial agent assets, MCP server code, runtime config templates, and knowledge manifests as application-owned runtime assets.

#### Scenario: Packaged app starts without repository checkout
- **WHEN** the user launches a packaged click-to-run build outside the development repository
- **THEN** the backend can locate the bundled frontend assets, backend package, geospatial agent assets, MCP server code, and runtime config templates from application-owned resource paths.

#### Scenario: Packaged runtime assets are materialized into app support
- **WHEN** the packaged app prepares runtime support on first launch
- **THEN** it materializes or validates the generated OpenCode home layout, bundled skills, runtime knowledge manifest, MCP wiring, and workspace roots under the app support directory.

### Requirement: Distribution owns the geospatial Python environment
The packaged app SHALL provide bundled `uv`, a separate geospatial runtime project, a Python 3.12 request, and network-based first-run provisioning into an app-support virtual environment so it avoids relying on user-global Python packages.

#### Scenario: Packaged environment is ready
- **WHEN** the packaged app starts in an environment with all bundled runtime dependencies available
- **THEN** `get_session_context` reports the managed Python command contract and package readiness without requiring manual user installation.

#### Scenario: First-run provisioning uses bundled uv and network install
- **WHEN** the packaged app starts and the app-support geospatial virtual environment is missing or stale
- **THEN** the app runs bundled `uv` against the packaged geospatial runtime project with Python 3.12 and network dependency installation
- **AND** provisioning is blocking for geospatial session execution until the environment is ready or failed
- **AND** it reports structured progress, real-time logs, or failure rather than asking the user to hand-install geospatial packages.

#### Scenario: App-support environment is reused after provisioning
- **WHEN** the packaged app starts and the app-support geospatial virtual environment already satisfies the packaged lockfile and Python 3.12 requirement
- **THEN** the app reuses that environment instead of reinstalling dependencies.

#### Scenario: Developer paths are not required
- **WHEN** a packaged session runs an agent-authored Python script
- **THEN** `GEO_AGENT_REPO_ROOT` resolves to the packaged application resource root or app-owned project root rather than to the original development checkout
- **AND** `UV_PROJECT_ENVIRONMENT` resolves to a mutable app-support path.

### Requirement: Distribution preserves runtime isolation
The click-to-run package SHALL preserve the same runtime-isolation principles as the development app.

#### Scenario: Packaged app avoids user-global OpenCode config
- **WHEN** the packaged backend starts the managed OpenCode runtime
- **THEN** it uses application-owned config, skills, MCP wiring, and runtime directories instead of inheriting uncontrolled user-global OpenCode configuration.

#### Scenario: Packaged app writes mutable state to app support
- **WHEN** the packaged app creates sessions, workspaces, generated scripts, artifacts, evidence ledgers, or runtime traces
- **THEN** those mutable files are written under the app support directory or another explicit app-owned data directory rather than inside read-only packaged resources.

### Requirement: Distribution exposes packaged asset diagnostics
The backend SHALL expose diagnostics that confirm packaged asset and environment resolution for local demo troubleshooting.

#### Scenario: Health check reports packaged asset status
- **WHEN** the app health endpoint or runtime readiness check runs in a packaged build
- **THEN** it reports whether frontend assets, agent assets, MCP server code, runtime config assets, OpenCode runtime access, and geospatial Python package readiness have been resolved.

#### Scenario: Packaged asset mismatch blocks runtime readiness
- **WHEN** a required packaged asset, lockfile, runtime template, or environment component is missing or incompatible
- **THEN** the backend reports a structured not-ready state instead of starting a misleading partially configured session.

