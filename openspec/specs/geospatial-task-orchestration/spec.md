## Purpose
Define the runtime-owned geospatial task and evidence contract for agent-directed analysis, verification state, and artifact traceability.
## Requirements
### Requirement: Structured geospatial task evidence remains runtime-owned
The system SHALL preserve structured geospatial task evidence when it is emitted by the managed runtime or registered through MCP, including the requested analysis family, support status, resolved input layers, CRS metadata, study-area context, operator-family decision, verification requirements, specialist control decisions, downstream handoff assumptions, expected outputs, and execution evidence; the backend SHALL NOT create a separate app-authored task-normalization workflow that predetermines those fields for the agent.

#### Scenario: Agent initializes task evidence before execution
- **WHEN** a user submits a geospatial analysis request through the dashboard
- **THEN** the managed runtime may create or update a structured geospatial task representation before operator execution begins

#### Scenario: Agent session reads and advances the task contract
- **WHEN** the managed OpenCode session plans or updates a supported run
- **THEN** it can inspect the structured geospatial task contract and record resolved execution decisions, repair outcomes, blocking conditions, and downstream assumptions from MCP tool observations without the backend prescribing the full step order in advance

#### Scenario: Task contract remains analysis-family aware
- **WHEN** the task contract is created for a KDE run
- **THEN** it records KDE as the selected operator family while keeping reusable fields for preprocessing, verification, workflow control, and outputs separate from KDE-specific parameters

#### Scenario: Task contract records agent-resolved local inputs
- **WHEN** the managed runtime resolves local datasets and study-area assets needed for a KDE run
- **THEN** the task contract can record the selected input layers, their source paths, and the effective execution context used by the runtime

### Requirement: Operator execution supports KDE-first scripts
The system SHALL support KDE as the first complete operator family through skill guidance, reusable Python snippets, and evidence expectations that let the managed agent interleave preprocessing, analysis, visualization, reporting, and reflection decisions without adding backend-owned MCP operator wrappers.

#### Scenario: KDE runs through agent-directed scripts
- **WHEN** a prepared task specifies KDE as its analysis type
- **THEN** the managed agent can write and execute KDE-specific Python code using prepared inputs, record operator parameters, and register KDE outputs through the generic evidence tool

#### Scenario: Future operators fit the same dispatch boundary
- **WHEN** a later spatial analysis task type is introduced
- **THEN** it can add skill guidance, snippets, and evidence expectations without requiring a redesign of session orchestration or artifact tracking

#### Scenario: Operator dispatch supports verification-driven retry or block
- **WHEN** a KDE operator result fails a required verification checkpoint
- **THEN** the system either records an agent-directed repair attempt or transitions the task into a blocked or failed state rather than silently marking the run complete

### Requirement: Verification state is explicit and traceable
The system SHALL expose explicit verification state for geospatial runs, including preprocessing validity, CRS or unit suitability, operator-result checks, repair attempts, reflection outcomes, and blocking conditions, so failures and warnings can be traced through the execution record even when the workflow is owned by the managed agent session.

#### Scenario: Verification checkpoints are emitted during a run
- **WHEN** the system processes a structured geospatial task
- **THEN** it records verification checkpoints or status updates as part of the task state instead of leaving them only in free-form logs

#### Scenario: Verification failure blocks unsafe execution
- **WHEN** a required geospatial validation fails and cannot be repaired automatically
- **THEN** the run enters a blocked or failed state with a machine-readable explanation of the violated verification condition

#### Scenario: Repair actions remain visible in task state
- **WHEN** the system retries a step or asks the user for clarification in response to a verification issue
- **THEN** the task state records that repair path and the resulting verification outcome

#### Scenario: Reflection can run at any stage
- **WHEN** the managed runtime invokes reflection before, during, or after operator execution
- **THEN** the resulting verification evidence is attached to the task record without assuming reflection is a final-only phase

### Requirement: Orchestrator decisions remain visible in task evidence
The system SHALL record enough structured evidence about orchestrator-directed specialist activity for task progression, support status, workflow-control decisions, verification reasoning, and reproducibility review without turning that record into a backend-owned fixed step script.

#### Scenario: Specialist activity is associated with the task
- **WHEN** the orchestrator invokes `request-triage`, `study-design`, `data-audit`, `spatial-prep`, `operator-kde`, `evidence-cartography`, `report-synthesizer`, or `skeptical-review` for a geospatial run
- **THEN** the task evidence can associate that activity with the active task and resulting observations, decisions, or artifacts

#### Scenario: Interleaved specialist usage stays traceable
- **WHEN** the orchestrator revisits an earlier responsibility such as invoking skeptical review before operator completion or requesting evidence packaging before final reporting
- **THEN** the task evidence still preserves that interleaved path without assuming a fixed role order

### Requirement: Unsupported or ambiguous tasks surface explicit control states
The system SHALL surface unsupported geospatial task families, method-critical ambiguities, and unresolved preconditions as explicit control states in the task record instead of silently coercing them into the nearest currently implemented operator path.

#### Scenario: Unsupported task family is blocked before operator execution
- **WHEN** request triage determines that a user request belongs to a geospatial task family that is not currently supported by the runtime
- **THEN** the task record enters an explicit blocked or unsupported state before operator execution begins

#### Scenario: Ambiguous method choice triggers clarification
- **WHEN** the user request omits information that changes the defensible study design or operator family choice
- **THEN** the task record moves into a clarification state rather than pretending that the missing information is harmless

### Requirement: Workflow control decisions are first-class task evidence
The system SHALL preserve each specialist's `proceed`, `clarify`, `repair`, or `stop` decision as structured task evidence so the transcript and later reviews can reconstruct why the run advanced, paused, retried, or terminated.

#### Scenario: Repair decision is recorded as structured task evidence
- **WHEN** a specialist determines that a geospatial issue is repairable within the current runtime
- **THEN** the task record stores a `repair` decision and the associated reason instead of hiding that state only in free-form logs

#### Scenario: Stop decision prevents optimistic continuation
- **WHEN** a specialist or skeptical review returns `stop`
- **THEN** the orchestrated run does not continue as though the task were still valid without a new user input or a successful repair path

#### Scenario: Workflow decision carries machine-readable reason metadata
- **WHEN** a specialist returns a blocking, repair, or clarification decision for a geospatial run
- **THEN** the task evidence can record a machine-readable reason code and the blocking evidence that triggered that decision instead of storing the rationale only as prose

### Requirement: Stage artifacts form an evidence ledger
The system SHALL preserve a structured evidence ledger for geospatial runs so key method decisions and downstream claims can be tied to stage-level artifacts rather than only to free-form transcript text.

#### Scenario: Stage artifacts are recorded through the run
- **WHEN** the orchestrated geospatial workflow advances through triage, study design, data audit, spatial preparation, operator execution, cartography, review, and reporting
- **THEN** the task evidence can include stage-level artifacts such as task intent, study design, data-audit summaries, CRS decisions, extent checks, parameter records, weight semantics, edge-handling notes, map specifications, review findings, and claim traces

#### Scenario: Final claims can be traced back to upstream evidence
- **WHEN** a final answer or report contains a substantive geospatial claim
- **THEN** the system can associate that claim with the stage artifacts and review outputs that justify it instead of relying only on a narrative summary

#### Scenario: Method-critical parameters remain inspectable
- **WHEN** a KDE-oriented run reaches operator execution and downstream reporting
- **THEN** the evidence ledger can preserve structured fields for analysis CRS, linear units, bandwidth, cell size, weighting semantics, output value mode, and edge-effect notes needed for later review

### Requirement: Geospatial artifacts carry task metadata
The system SHALL preserve agent-registered geospatial artifacts with enough task metadata to support dashboard rendering, reproducible reruns, and thesis reporting.

#### Scenario: Generated artifact retains task context
- **WHEN** a geospatial run produces an output such as a map, report, or summary file
- **THEN** `record_run_evidence` can associate that artifact with the originating task, selected operator, relevant parameters, verification summary, and workspace-relative filesystem location

#### Scenario: Artifact placeholders remain available before outputs exist
- **WHEN** a task has started but no operator outputs have been registered yet
- **THEN** the dashboard exposes an empty artifact state without scanning the workspace or inventing pending artifact records

#### Scenario: Run manifest is exposed as a first-class artifact
- **WHEN** the runtime writes a structured manifest or equivalent reproducibility record for a geospatial run
- **THEN** the system surfaces that record as part of the task's artifact set after it is explicitly registered rather than hiding it as an internal implementation detail

### Requirement: Task evidence supports interpolation and statistical hotspot families
The system SHALL extend runtime-owned geospatial task evidence so interpolation and statistical hotspot runs can be represented alongside KDE without adding a backend-authored fixed workflow.

#### Scenario: Interpolation task evidence is family-aware
- **WHEN** the managed runtime prepares an IDW request
- **THEN** the task record identifies interpolation as the operator family and records method-specific fields separately from shared CRS, bounding-box, verification, artifact, and claim-trace fields.

#### Scenario: Hotspot task evidence is family-aware
- **WHEN** the managed runtime prepares a Gi* request
- **THEN** the task record identifies statistical hotspot analysis as the operator family and records method-specific fields separately from shared CRS, bounding-box, verification, artifact, and claim-trace fields.

#### Scenario: Backend does not precompute task fields
- **WHEN** a user submits an interpolation or hotspot request
- **THEN** the backend preserves the prompt unchanged and lets the managed runtime create, update, and repair task evidence through runtime activity and MCP evidence tools.

### Requirement: Method-family ambiguity remains explicit across KDE, IDW, and Gi*
The system SHALL preserve method-critical ambiguity as a visible control state rather than silently coercing map-like requests into the nearest available operator.

#### Scenario: Ambiguous surface wording triggers clarification
- **WHEN** a request could mean event density, sampled-value interpolation, or statistical hotspots
- **THEN** the task evidence records a `clarify` decision with the missing method or data-support detail.

#### Scenario: Unsupported method remains blocked
- **WHEN** the user explicitly requests a method outside the implemented task families, such as Kriging as an executable operator
- **THEN** the task evidence records an unsupported or blocked state unless the user agrees to an IDW-first alternative.

#### Scenario: Repairable support mismatch is recorded
- **WHEN** a request has the right task family but requires a repairable support change, such as aggregating points before Gi* or reprojecting before IDW
- **THEN** the task evidence records a `repair` decision, the reason code, and the repair outcome.

### Requirement: Interpolation evidence preserves IDW-specific fields
The system SHALL preserve IDW-specific execution evidence in the task record so downstream artifacts and claims can be audited.

#### Scenario: IDW parameter evidence is recorded
- **WHEN** IDW execution begins or completes
- **THEN** the task evidence can record value field, valid sample count, analysis CRS, grid extent, cell size, power parameter, neighborhood rule, duplicate-point policy, masking or extrapolation policy, validation method, validation metrics, and output units.

#### Scenario: IDW verification failures affect task state
- **WHEN** interpolation validation fails because of CRS, geometry, value-field, sample-size, or extent issues
- **THEN** the task evidence records the failed condition and moves to `repair`, `clarify`, or `stop` instead of continuing optimistically.

#### Scenario: IDW artifacts attach to the shared ledger
- **WHEN** interpolation creates a map, raster, table, report, or manifest
- **THEN** each registered artifact is associated with the interpolation task, selected parameters, verification summary, and workspace-relative path.

### Requirement: Hotspot evidence preserves Gi*-specific fields
The system SHALL preserve Gi*-specific execution evidence in the task record so spatial weights, significance settings, and claims can be audited.

#### Scenario: Gi* parameter evidence is recorded
- **WHEN** Gi* execution begins or completes
- **THEN** the task evidence can record input spatial support, feature count, attribute field, count-versus-rate decision, spatial-weight type, transform, permutations, seed, neighbor counts or distance thresholds, island handling, statistic variant, significance configuration, FDR or multiple-testing policy, and PySAL package-backed execution summary.

#### Scenario: Gi* verification failures affect task state
- **WHEN** hotspot validation fails because of missing aggregation support, nonnumeric attributes, invalid spatial weights, unsuitable CRS, or mismatched geometry counts
- **THEN** the task evidence records the failed condition and moves to `repair`, `clarify`, or `stop` instead of reporting invalid significance.

#### Scenario: Gi* artifacts attach to the shared ledger
- **WHEN** hotspot analysis creates a classified map, statistic table, report, or manifest
- **THEN** each registered artifact is associated with the hotspot task, selected weights, significance settings, verification summary, and workspace-relative path.
