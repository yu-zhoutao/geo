## Purpose
Define the backend-hosted geospatial MCP server capability, including lifecycle ownership, session-aware tool context, and structured tool schemas for the managed OpenCode runtime.
## Requirements
### Requirement: Backend-hosted geospatial MCP server lifecycle
The Python backend SHALL host, supervise, and clean up an application-owned geospatial MCP server that exposes reliable domain tools to the managed OpenCode runtime in the local demo environment.

#### Scenario: Backend starts MCP server for runtime use
- **WHEN** the backend prepares runtime support for a geospatial session
- **THEN** it starts or makes available the bundled geospatial MCP server under application-owned configuration and process supervision

#### Scenario: Backend shutdown cleans up MCP server resources
- **WHEN** the backend exits, restarts, or tears down runtime support
- **THEN** it terminates or releases the backend-managed geospatial MCP server resources along with any child processes that belong to that MCP lifecycle

### Requirement: MCP tools are session-aware and workspace-aware
The geospatial MCP server SHALL expose only minimal tools that operate against a backend-owned geospatial session context record, resolved through an opaque `session_context_id` or the active MCP session binding, so the runtime can discover workspace state, publish agent-authored todos, and record evidence without repeating raw path-heavy arguments.

#### Scenario: Tool catalog is minimal
- **WHEN** the managed runtime lists the application-owned geospatial MCP tools
- **THEN** the catalog contains `get_session_context`, `update_todos`, and `record_run_evidence`
- **AND** it does not contain workflow, operator, artifact-summary, or plan-writer tools that generate or prescribe the agent's steps.

#### Scenario: Tool call resolves active session context
- **WHEN** the runtime invokes a geospatial MCP tool with a valid `session_context_id` or active MCP session binding
- **THEN** the tool resolves the relevant workspace, attached data directories, environment contract, and evidence state needed for reliable execution
- **AND** the agent-facing result does not expose internal runtime ids, MCP ids, prompt history, database paths, ledger paths, or app support metadata.

#### Scenario: Missing required session context blocks execution cleanly
- **WHEN** a geospatial MCP tool is called without a valid `session_context_id` and without an active backend-owned geospatial context record
- **THEN** the tool returns a compact XML-like failure result that identifies the missing prerequisite instead of producing ambiguous output.

#### Scenario: Tool updates evidence state after execution
- **WHEN** a geospatial MCP tool records artifact, verification, dataset, parameter, or claim evidence
- **THEN** the backend-owned geospatial session context and evidence ledger are updated so later context inspection and dashboard reloads can observe the new state.

### Requirement: Explicit session context inspection tool is available
The geospatial MCP server SHALL expose a `get_session_context` tool that returns the merged backend-owned geospatial session context for the active run without exposing or implying an application-managed workspace layout.

#### Scenario: Agent inspects current geospatial context
- **WHEN** the runtime invokes `get_session_context` with a valid context handle or active MCP session binding
- **THEN** the agent-facing result is compact XML-like text containing the current workspace root path, enabled attached data directories, managed Python readiness, and the environment-variable-based Python execution command
- **AND** the workspace section contains only the workspace root path, not enumerated subdirectories such as `.geo/scripts`, `.geo/intermediate`, `.geo/artifacts`, or `.geo/evidence`
- **AND** the result does not list files, detect generated outputs, replay interaction history, expose internal ids, or expose app-owned database, ledger, manifest, or support paths.

#### Scenario: Unknown context handle fails cleanly
- **WHEN** the runtime invokes `get_session_context` with an unknown or expired context handle
- **THEN** the tool returns a compact XML-like failure result that explains the missing context instead of returning ambiguous empty state.

### Requirement: MCP tool schemas are typed and agent-facing results are compact text
Every geospatial MCP tool SHALL publish typed input schemas with explicit field descriptions, required-field metadata, closed enum values for constrained parameters, and nested object constraints where applicable; the tools SHALL keep structured backend payloads for validation and UI side effects, and return compact XML-like pure-text results to the agent; geospatial MCP tools SHALL NOT include app-generated workflow-plan payloads, task classifiers, operator outputs, canned result templates, internal ids, or path-heavy serialized session records.

#### Scenario: Tool schemas expose agent-usable argument contracts
- **WHEN** the managed runtime lists `get_session_context`, `update_todos`, or `record_run_evidence`
- **THEN** each tool schema includes parameter descriptions that explain when and how to pass each argument
- **AND** todo entries require `content`, restrict `status` to the supported todo states, and reject unrelated item fields such as `task`, `role`, `detail`, or `priority`
- **AND** evidence recording schemas enumerate the supported record types, artifact formats, artifact stages, and display hints instead of exposing those fields as unconstrained strings.

#### Scenario: Successful context call returns compact execution guidance
- **WHEN** `get_session_context` completes successfully
- **THEN** its agent-facing result includes only explicit status, the workspace path, enabled attached data roots, managed Python readiness, and concise evidence-reporting instructions
- **AND** the result does not include a `plan` field, fixed workflow projection, or method-specific prepared-input contract.

#### Scenario: Successful evidence call returns compact confirmation
- **WHEN** `record_run_evidence` records an artifact, dataset profile, verification fact, parameter snapshot, or claim trace
- **THEN** its agent-facing result confirms the record type, title, artifact stage, display hint, and normalized path when present
- **AND** it does not expose ledger paths, generated record ids, or serialized backend session state.

#### Scenario: Successful todo call returns compact confirmation
- **WHEN** `update_todos` records the current agent-authored todo list for UI display
- **THEN** its agent-facing result confirms the number of accepted items and their statuses
- **AND** it does not generate steps, impose an operator sequence, expose internal ids, or serialize backend session state.

#### Scenario: Failed tool call remains actionable to the agent
- **WHEN** a geospatial MCP tool fails or blocks execution
- **THEN** its XML-like result includes a reason attribute and a short repair-oriented message
- **AND** the result does not replace the agent's reasoning process with generated plan steps.

### Requirement: MCP exposes an agent-authored todo tool
The geospatial MCP server SHALL expose `update_todos` as a low-level UI state bridge that accepts only the agent's current todo entries and SHALL NOT generate, validate, sequence, or prescribe a geospatial workflow.

#### Scenario: Agent updates current todos
- **WHEN** an agent calls `update_todos` with entries containing content or label plus a status
- **THEN** the backend updates the app-visible todo state for that agent
- **AND** the transcript keeps the corresponding tool call visible as evidence that the todo state was agent-authored.

#### Scenario: Todo entry validation is repairable
- **WHEN** an agent calls `update_todos` with malformed entries or unsupported statuses
- **THEN** the XML-like failure result identifies the validation problem and gives a concise fix the agent can apply.

#### Scenario: Native OpenCode todo tool is not used
- **WHEN** the backend generates OpenCode runtime configuration
- **THEN** OpenCode's native `todowrite` tool is denied so app-visible todos come from `update_todos`.

### Requirement: MCP exposes an evidence recording tool
The geospatial MCP server SHALL expose `record_run_evidence` as the only geospatial evidence-writing MCP tool, and it SHALL append agent-authored evidence records to app-owned storage without interpreting the workflow, generating outputs, scanning the workspace, or writing application-managed files into the workspace.

#### Scenario: Agent records generated artifact
- **WHEN** an agent calls `record_run_evidence` with an artifact record containing a path, title, file format, artifact stage, display hint, category, and provenance summary
- **THEN** the tool validates that the path belongs to the managed workspace
- **AND** the path may be submitted as a workspace-relative path or as an absolute path inside the workspace
- **AND** the tool verifies that the referenced file exists before accepting the artifact
- **AND** the stored artifact path is normalized to a path relative to the workspace
- **AND** it appends the evidence and artifact metadata to app-owned storage outside the workspace
- **AND** it updates backend session state needed by the dashboard to display the artifact without asking the user to locate the file manually.

#### Scenario: Tool does not discover workspace files implicitly
- **WHEN** an agent writes files anywhere under the managed workspace
- **THEN** the MCP server does not scan, detect, list, or promote those files automatically
- **AND** only files explicitly reported through `record_run_evidence` become evidence-backed dashboard artifacts.

#### Scenario: Agent records staged artifact for UI display
- **WHEN** an agent records an artifact with `artifact_stage` set to `intermediate` or `final`
- **THEN** the tool preserves that stage exactly in app-owned evidence metadata
- **AND** it requires the artifact `format` and `display_hint` fields so the dashboard can choose inline, final-artifact, preview, or download presentation.

#### Scenario: Artifact format is explicit
- **WHEN** an artifact evidence record is submitted
- **THEN** its `format` is one of the supported explicit values such as `png`, `jpg`, `svg`, `html`, `md`, `pdf`, `csv`, `tsv`, `json`, `geojson`, `parquet`, `gpkg`, `shp`, `tif`, `txt`, or `zip`
- **AND** unknown formats are rejected or normalized to a download-only representation with a clear warning.

#### Scenario: Agent records verification fact
- **WHEN** an agent calls `record_run_evidence` with a verification record containing a status, reason code, checked inputs, and conclusion
- **THEN** the tool stores the verification fact in app-owned evidence metadata without changing the agent's plan or deciding whether the run should continue.

#### Scenario: Evidence writer rejects workflow instructions
- **WHEN** an agent passes plan steps, operator sequencing instructions, or generated report conclusions as authoritative workflow state to `record_run_evidence`
- **THEN** the tool rejects or ignores those workflow-control fields and returns a validation failure or warning.

#### Scenario: Artifact registration failure is repairable by the agent
- **WHEN** artifact registration fails because the path is missing, outside the workspace, nonexistent, or has unsupported metadata
- **THEN** the agent-facing XML-like failure result includes a short reason, the submitted path when available, the workspace root when available, and a concise repair instruction
- **AND** the result does not expose app-owned ledger paths, database paths, internal ids, or serialized backend session state.
