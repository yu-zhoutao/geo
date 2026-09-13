## Purpose
Define the OpenCode-backed KDE execution capability, including the bundled agent session boundary, geospatial MCP tool usage, verification gates, and reproducible workspace evidence.

## Requirements

### Requirement: Runtime-backed KDE agent sessions
The system SHALL execute KDE requests through a backend-managed OpenCode server session that uses configured models, an orchestrator, contract-driven geospatial specialist agents, application-owned geospatial skill packages, and backend-hosted MCP tools without requiring the user to provide manual runtime configuration, and the managed session SHALL own planning, todo evolution, role dispatch, repair behavior, clarification flow, and stop behavior for the KDE run.

#### Scenario: User starts a KDE run from a natural-language request
- **WHEN** a user submits a KDE-oriented geospatial request from the dashboard
- **THEN** the backend starts or resumes a real OpenCode-managed agent session with the application-generated KDE execution context
- **AND** the run proceeds through model-guided planning, specialist dispatch, MCP tool use, verification, and artifact generation inside that managed session boundary

#### Scenario: Agent session remains responsible for workflow progression
- **WHEN** the KDE run advances from triage to study design, preprocessing, operator execution, visualization, reporting, or skeptical review
- **THEN** the managed agent session decides which specialist role or MCP tool to use next based on observations rather than relying on a backend-authored workflow script or helper recipe to dictate the full sequence

#### Scenario: Specialist roles can be interleaved during KDE work
- **WHEN** the managed session needs to revisit study design, perform early skeptical review, request cartographic packaging, or ask reporting help before the run is complete
- **THEN** it can interleave specialist activity without being constrained to a fixed stage order

#### Scenario: Missing configuration is handled by the application boundary
- **WHEN** required OpenCode runtime or model configuration for the KDE flow is not available or not ready
- **THEN** the backend returns a structured not-ready or failed state
- **AND** the user is not asked to manually create runtime config, skills, agents, or MCP files to continue

### Requirement: KDE execution uses agent-authored local scripts
The system SHALL run KDE work through agent-authored Python scripts executed in the managed geospatial environment, using backend-hosted MCP only for session-context discovery and evidence registration rather than for dataset inspection, preprocessing, KDE computation, visualization, or report generation.

#### Scenario: Beijing FCD KDE run completes with real outputs
- **WHEN** the managed KDE session executes successfully on the configured Beijing FCD point data and study-area boundary
- **THEN** the real agent runtime writes and runs visible workspace scripts to inspect the data, normalize CRS, prepare the study area, compute KDE outputs, and generate local artifacts
- **AND** it registers durable outputs through `record_run_evidence` after those files already exist

#### Scenario: Required dataset is unavailable
- **WHEN** the requested KDE run cannot resolve a required local dataset or study-area boundary
- **THEN** the run enters a blocked or failed state with a machine-readable explanation of the missing dependency

### Requirement: Verification gates control repair and blocking
The system SHALL run explicit verification checkpoints during KDE task triage, study design, preprocessing, parameter selection, visualization review, and output validation, and SHALL use those checkpoints together with visible skeptical-review activity to decide whether to continue, repair, block, or fail the run.

#### Scenario: Recoverable validation issue triggers repair or clarification
- **WHEN** the verifier detects a recoverable issue such as an unsuitable default bandwidth or an unresolved study-area choice
- **THEN** the real agent session either adjusts the run through an explicit repair step or asks the user a structured follow-up question before continuing

#### Scenario: Unsafe run is blocked before final output
- **WHEN** a required geospatial validation fails and cannot be repaired automatically
- **THEN** the run does not produce a misleading final KDE conclusion
- **AND** the failure state records the violated verification condition

#### Scenario: Skeptical review can interrupt intermediate KDE work
- **WHEN** the managed runtime invokes skeptical review before the KDE run is finalized
- **THEN** the resulting verification outcome can trigger repair, clarification, retry, or termination without requiring review to wait for a final report stage

### Requirement: KDE execution enforces operator-specific hard gates
The system SHALL enforce KDE-specific validity gates before and during operator execution, including point-event semantics, projected linear-unit distance space, explicit study-window overlap, bandwidth provenance, defensible weighting, and cell-size disclosure.

#### Scenario: Non-event inputs are refused for KDE
- **WHEN** the prepared input points are not defensible event locations for a descriptive density analysis
- **THEN** the KDE workflow returns `clarify` or `stop` instead of silently treating those inputs as valid events

#### Scenario: Planar KDE does not proceed in geographic degrees
- **WHEN** the working CRS for a KDE run remains geographic or otherwise lacks defensible linear units for the requested distance semantics
- **THEN** the workflow repairs the CRS choice or stops before operator execution rather than running a misleading planar KDE

#### Scenario: KDE parameters and output units are recorded explicitly
- **WHEN** a KDE run proceeds to execution
- **THEN** the resulting artifacts record bandwidth, bandwidth units, cell size, cell-size units, weighting policy, and output value mode instead of leaving them implicit in tool defaults or captions

### Requirement: KDE claims remain bounded by method limits
The system SHALL surface KDE-specific interpretation boundaries in the managed run so density outputs are not presented as statistical significance, causal explanation, or generic risk proof.

#### Scenario: Density output is not described as significance
- **WHEN** the KDE workflow produces a density surface and downstream reporting artifacts
- **THEN** the managed session preserves method caveats that prevent density from being described as a significance test result by default

#### Scenario: KDE caveats remain visible in downstream artifacts
- **WHEN** a map package or report summary is created from KDE outputs
- **THEN** it includes the KDE-specific caveats needed to keep the final interpretation within the method's actual limits

#### Scenario: KDE output is not upgraded into causal or standalone risk claims
- **WHEN** downstream narrative or cartographic artifacts are synthesized from KDE outputs without a denominator or causal design
- **THEN** the workflow keeps the claim at descriptive density or concentration language instead of allowing causal, safety, or per-capita risk claims to survive into the final output

### Requirement: KDE runs produce reproducible workspace evidence
The managed agent session SHALL write reproducible manifests or equivalent evidence artifacts inside the assigned workspace using agent-chosen paths, and the application SHALL surface only files explicitly registered through `record_run_evidence` so the dashboard and later experiments can inspect the KDE evidence chain without backend-managed workspace directories.

#### Scenario: Run manifest records execution evidence
- **WHEN** a KDE run completes or terminates early
- **THEN** the agent-authored workspace contains a manifest or equivalent structured record with resolved inputs, parameters, verification checkpoints, generated outputs, and workspace-relative paths
- **AND** the dashboard displays it only after the agent registers it through the evidence tool

#### Scenario: Generated outputs remain tied to the originating run
- **WHEN** the dashboard or backend reloads session state after a restart
- **THEN** the system restores the registered KDE artifacts and manifest for that session from app-owned evidence records without scanning the workspace for unreported files

#### Scenario: Evidence chain remains inspectable for later review
- **WHEN** a KDE run is reviewed after completion
- **THEN** the preserved workspace evidence can be associated with the run's todo evolution, specialist-agent activity, and verification outcomes for reproducibility analysis
