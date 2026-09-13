## Purpose
Define the persisted evaluation archive layout, the boundary between durable experiment evidence and reusable runtime state, and the pruning behavior for future campaign outputs.

## Requirements

### Requirement: Evaluation archives use a project-root output directory
The system SHALL write future evaluation campaign archives under a project-root `evaluation-runs` directory by default.

#### Scenario: Default campaign root is project visible
- **WHEN** a campaign is initialized without an explicit output root
- **THEN** the campaign root is created under `PROJECT_ROOT/evaluation-runs`

#### Scenario: Explicit output root remains supported
- **WHEN** a campaign is initialized with an explicit output root
- **THEN** the runner uses that output root instead of the default project-root `evaluation-runs` directory

### Requirement: Timestamped campaign directories are the first archive layer
The system SHALL store timestamped campaign directories directly beneath the selected evaluation output root.

#### Scenario: Timestamped directory is not nested under a label
- **WHEN** a campaign uses the timestamped campaign output policy
- **THEN** the campaign directory path is `OUTPUT_ROOT/YYYYMMDDThhmmssZ-CAMPAIGN_ID` with no additional grouping layer

#### Scenario: Run labels do not alter archive paths
- **WHEN** a caller or future campaign supplies a diagnostic label for human context
- **THEN** the label may be recorded in campaign metadata but MUST NOT create an extra path component above the timestamped campaign directory

### Requirement: Archives contain durable evaluation evidence only
The system SHALL keep durable experiment evidence in the campaign archive and SHALL exclude reusable or rebuildable runtime state from the default archive contents.

#### Scenario: Required evidence files are preserved
- **WHEN** a scenario attempt is captured
- **THEN** the run bundle preserves run status, run manifest, app-exported session trace, derived session JSON, transcript JSON, evidence records, artifact manifest, captured artifact files, deterministic score files, judge input, judge response, judge score, and necessary attempt logs

#### Scenario: Rebuildable runtime state is not archived by default
- **WHEN** a campaign completes under the default archive policy
- **THEN** the campaign archive does not contain campaign-local geospatial Python virtual environments, campaign-local app support roots, campaign-local OpenCode runtime config roots, OpenCode node modules, or runtime caches

### Requirement: Per-attempt workspaces and dataset packs remain isolated
The system SHALL preserve per-attempt isolation for files that the agent reads, writes, or mutates during an evaluated scenario.

#### Scenario: Attempt workspace is isolated
- **WHEN** the same scenario is run multiple times or under multiple variants
- **THEN** each attempt receives its own run-bundle workspace directory and files written by one attempt do not overwrite another attempt

#### Scenario: Dataset pack is preserved with the attempt
- **WHEN** the runner materializes or attaches scenario data for an attempt
- **THEN** the attempt run bundle stores the dataset pack or dataset-pack manifest needed to identify the exact data presented to the agent

### Requirement: Evaluation app startup uses existing app runtime paths
The evaluation runner SHALL let the app resolve its existing default runtime paths instead of forcing campaign-local app support or runtime config roots solely for archive isolation.

#### Scenario: App support path is not campaign-localized
- **WHEN** the evaluation runner starts a headless app instance
- **THEN** it does not set `GEO_AGENT_APP_SUPPORT_DIR` to a path inside the campaign archive

#### Scenario: Runtime config path is not campaign-localized
- **WHEN** the evaluation runner starts a headless app instance
- **THEN** it does not set `GEO_AGENT_RUNTIME_CONFIG_ROOT` to a path inside the campaign archive

#### Scenario: App behavior remains responsible for runtime setup
- **WHEN** the headless evaluation app provisions geospatial Python or OpenCode runtime state
- **THEN** those reusable runtime files are written according to the app's normal settings rather than into the evaluation archive

### Requirement: Archive directories are created lazily
The system SHALL avoid creating empty or unused directories inside timestamped campaign archives.

#### Scenario: Initialization creates no unused runtime directories
- **WHEN** a campaign is initialized before any attempt runs
- **THEN** the campaign root contains only files and directories needed for the plan, manifest snapshots, and later run allocation, and it does not contain empty `app-support`, campaign-level `runtime-config`, or campaign-level `workspace` directories

#### Scenario: Writers create directories when content is emitted
- **WHEN** a runner component writes logs, exports, run bundles, artifacts, or runtime snapshots
- **THEN** the component creates only the target directories required for those files

### Requirement: Evaluation responsibilities remain separated across system boundaries
The system SHALL keep evaluation archive management in the Python evaluation runner while preserving existing responsibilities for the frontend, backend app, runtime, MCP capabilities, and local geospatial execution layer.

#### Scenario: Frontend responsibilities are unchanged
- **WHEN** archive layout changes are implemented
- **THEN** the Vue frontend remains responsible only for app UI behavior and does not read or write evaluation archives directly

#### Scenario: Backend and runner responsibilities are explicit
- **WHEN** a campaign is executed
- **THEN** the Python evaluation runner owns archive layout, campaign planning, run-bundle capture, scoring, aggregation, and cleanup of app subprocesses it starts

#### Scenario: Runtime and geospatial execution responsibilities are unchanged
- **WHEN** a scenario prompt is evaluated
- **THEN** the managed OpenCode runtime remains responsible for agent session execution, subagent activity, skills, MCP tool calls, and tool history, while backend-hosted MCP capabilities and local geospatial Python execution continue to provide domain operations behind the runtime tool boundary
