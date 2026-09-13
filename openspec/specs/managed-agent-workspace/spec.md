## Purpose
Define the managed local workspace boundary for OpenCode session execution, shared workspace usage, isolated runtime state, and app-versus-agent file ownership.
## Requirements
### Requirement: Workspace root uses OS-standard application-support directories
The backend SHALL resolve a standard local application-support root for workspaces using platform-appropriate locations instead of storing active workspaces inside the repository or `.state` directory.

#### Scenario: macOS workspace root is resolved
- **WHEN** the application runs on macOS
- **THEN** the backend resolves the workspace root under `~/Library/Application Support/<app>/` or an equivalent application-support path managed by the app

#### Scenario: Windows workspace root is resolved
- **WHEN** the application runs on Windows
- **THEN** the backend resolves the workspace root under `%AppData%/<app>/` or an equivalent roaming application-data path managed by the app

### Requirement: Runtime state directories are isolated from user-global config
The backend SHALL provision application-owned runtime state directories for OpenCode so managed sessions do not depend on uncontrolled user-global runtime state.

#### Scenario: OpenCode state stays inside application-owned directories
- **WHEN** the backend starts the OpenCode server for local app use
- **THEN** config, cache, state, auth, and other runtime directories are resolved to application-owned paths rather than to uncontrolled user-global defaults

#### Scenario: Runtime traces stay associated with the shared workspace and session reference
- **WHEN** an OpenCode-managed session produces runtime trace or event state on disk
- **THEN** those files or app-owned trace references remain discoverable from application-owned workspace or runtime paths associated with the originating session

### Requirement: Workspace is shared across sessions
The application SHALL use one shared OpenCode workspace directory for all interactive local sessions rather than creating a dedicated workspace subdirectory per session, and that shared workspace SHALL be application-created rather than user-selected.

#### Scenario: New session reuses the shared workspace
- **WHEN** the backend creates a new local app session
- **THEN** the assigned workspace path is the shared application workspace rather than a newly created session-specific subdirectory

#### Scenario: Interactive sessions do not select alternate workspaces
- **WHEN** a user starts or resumes an interactive local app session
- **THEN** the session uses the configured shared application workspace
- **AND** the dashboard does not ask the user to choose a different workspace root.

### Requirement: Application and agent file ownership are separated
The application MUST manage the shared workspace root and metadata references, but every file or subdirectory inside the shared workspace MUST be created, modified, or deleted by the runtime, an agent, or the user rather than by application-managed metadata, layout, or artifact-indexing code.

#### Scenario: App initializes only the workspace root
- **WHEN** the shared workspace is initialized
- **THEN** the application may create the workspace root directory if it does not exist
- **AND** it does not create predefined child directories, hidden metadata directories, evidence ledgers, artifact manifests, request snapshots, prepared-input records, or other app-managed files inside that workspace.

#### Scenario: Agent-generated outputs remain discoverable only when registered
- **WHEN** the runtime or agent creates files inside the shared workspace during execution
- **THEN** those files remain agent-owned workspace contents
- **AND** the backend surfaces them in the dashboard only after the agent explicitly registers them through the supported evidence-recording path.

#### Scenario: App-owned metadata stays outside the workspace
- **WHEN** the backend stores session context, evidence records, artifact indexes, request snapshots, prepared-input records, or runtime support metadata
- **THEN** those records are stored in application-owned database or support paths outside the shared workspace.

#### Scenario: Workspace has no required internal layout
- **WHEN** an agent writes scripts, outputs, intermediate files, maps, reports, or derived datasets
- **THEN** the agent may choose any path inside the shared workspace
- **AND** the application does not require `.geo/scripts`, `.geo/intermediate`, `.geo/artifacts`, `.geo/evidence`, or any equivalent predefined directory layout.

### Requirement: Runtime work is bound to the shared workspace
The backend SHALL run OpenCode session work with the shared workspace as its effective working directory or equivalent runtime-scoped file root.

#### Scenario: Agent writes into shared workspace
- **WHEN** a session executes an agent task that creates files
- **THEN** those files are created within the assigned shared workspace rather than in repository-local temp directories by default

### Requirement: Session workspace identity is surfaced to the user
The application SHALL expose the active session workspace directory as visible session context rather than keeping it hidden as backend-only state.

#### Scenario: Workspace path is visible in the app
- **WHEN** a session has an assigned workspace directory
- **THEN** the dashboard can display that workspace path as part of the active session context

### Requirement: Isolated storage roots carry workspace and runtime directories
The backend SHALL derive the shared workspace and application-owned runtime directories from the configured storage roots in tests as well as normal local execution.

#### Scenario: Test workspace and runtime state stay under temporary storage
- **WHEN** an isolated backend test initializes a session or runtime client with injected temporary settings
- **THEN** the shared workspace, runtime traces, and other application-owned runtime directories remain under the test's temporary storage root instead of default user-scoped application data directories

### Requirement: Evaluation campaigns use flat project-root result directories
The system SHALL write automated evaluation results under the project-root `evaluation-runs/` directory using direct timestamped campaign result directories instead of storing benchmark state under `.state` or under extra campaign-family nesting.

#### Scenario: Evaluation campaign gets a direct timestamped result root
- **WHEN** the runner starts an automated evaluation campaign
- **THEN** it writes the campaign result under `evaluation-runs/<timestamp>-<campaign-id>/` with no intermediate family, smoke-test, or suite-name directory

#### Scenario: Campaign root avoids rebuildable runtime archives
- **WHEN** a campaign result directory is created
- **THEN** it contains manifests, run bundles, runtime asset snapshots when generated, scoring files, and exports, but does not create or archive campaign-level `app-support`, `runtime-config`, `workspace`, venv, node module, or cache directories

#### Scenario: Campaign state can be deleted as one unit
- **WHEN** a user removes an evaluation campaign output directory
- **THEN** the preserved campaign evidence, copied artifacts, logs, scores, and exports for that campaign are removed without touching interactive app state or shared reusable runtime dependencies

### Requirement: Evaluation attempts isolate only necessary per-run state
The system SHALL allocate isolated per-attempt app state and workspace directories while keeping reusable runtime dependencies outside result bundles.

#### Scenario: Attempt gets isolated app state and workspace
- **WHEN** a scenario attempt starts
- **THEN** the runner configures a run-bundle-local app state root, metadata database, workspace root, and log directory for that attempt

#### Scenario: Reusable runtime state stays shared
- **WHEN** the app provisions geospatial Python dependencies, OpenCode provider packages, caches, or generated runtime config that can be rebuilt
- **THEN** those reusable dependencies are not copied into the campaign result directory unless a future replay workflow explicitly exports a compact trace artifact

#### Scenario: Interactive workspace remains unchanged
- **WHEN** an evaluation campaign starts, runs, fails, or completes
- **THEN** it does not write benchmark sessions, artifacts, runtime bundles, or score files into the normal interactive app workspace

### Requirement: Evaluation run bundles preserve benchmark provenance
The system SHALL preserve benchmark, variant, app/runtime, artifact, scoring, and error provenance inside each evaluation run bundle so later comparison work does not depend only on aggregate tables.

#### Scenario: Run bundle keeps benchmark and variant references
- **WHEN** a scenario attempt finishes during a campaign
- **THEN** its run bundle records the benchmark fixture reference, fixture hash, variant manifest reference, variant hash, campaign manifest reference, runtime bundle reference, produced artifacts, and score files needed for later inspection

#### Scenario: Run bundle keeps app session evidence
- **WHEN** a scenario attempt is captured
- **THEN** its run bundle records the app-exported session archive trace JSON plus derived app session JSON, messages or transcript data, timeline entries, plan groups, verification entries, artifact metadata, evidence records when available, and runtime trace paths

#### Scenario: Campaign results can be revisited without rerunning
- **WHEN** a campaign result is reviewed after the fact
- **THEN** the isolated run bundles provide enough provenance to inspect an individual attempt without reconstructing it from the interactive workspace

### Requirement: Evaluation artifact capture is content-addressed
The system SHALL copy registered run artifacts into the run bundle and record hashes so thesis evidence can be checked independently of live workspace paths.

#### Scenario: Registered artifact is copied into run bundle
- **WHEN** a run registers an artifact needed for scoring or thesis exports
- **THEN** the runner copies the artifact content into the run bundle and records the source session artifact id, original path, copied path, file size, and content hash

#### Scenario: Missing artifact is preserved as provenance failure
- **WHEN** session metadata references an artifact that cannot be resolved or copied
- **THEN** the run bundle records the missing artifact error for later inspection without treating framework artifact completeness as a task-performance pass/fail condition

### Requirement: Evaluation run bundles are immutable by default
The system SHALL avoid overwriting completed run bundles so repeated campaigns and resumed runs remain auditable.

#### Scenario: Existing run bundle is not overwritten
- **WHEN** a campaign is resumed or rerun
- **THEN** the runner creates new attempt identifiers for new work rather than modifying completed run bundles

#### Scenario: Score reruns preserve previous scorer outputs
- **WHEN** deterministic or judge scoring is rerun for an existing run bundle
- **THEN** the scorer records a new scorer version or score file rather than silently replacing the only copy of prior scoring evidence

