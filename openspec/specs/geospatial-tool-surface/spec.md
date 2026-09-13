## Purpose
Define the generic geospatial tool surface exposed to the managed runtime, including shared preprocessing contracts, operator-specific extensibility, structured tool responses, and artifact traceability.
## Requirements
### Requirement: Generic geospatial tool taxonomy
The backend SHALL expose geospatial support to the managed OpenCode runtime through a minimal backend-hosted MCP taxonomy that separates context discovery, todo publication, and evidence recording from actual GIS computation; actual vector, raster, CRS, statistical, visualization, and report-generation operations SHALL be performed by runtime-authored scripts or shell commands in the managed geospatial Python environment.

#### Scenario: Agent discovers context before execution
- **WHEN** the geospatial agent prepares to execute a supported analysis request
- **THEN** it can call `get_session_context` to discover the workspace, attached data, environment variables, package availability, and evidence ledger without depending on a KDE-only workflow wrapper.

#### Scenario: Agent publishes todos without a workflow wrapper
- **WHEN** the geospatial agent wants the dashboard to display its current todo state
- **THEN** it can call `update_todos` with its own entries without asking the MCP server to design, sequence, or execute the workflow.

#### Scenario: Agent performs GIS operations through scripts
- **WHEN** a task requires dataset inspection, CRS repair, clipping, KDE, map rendering, or another geospatial operation
- **THEN** the runtime performs that work through visible bash commands and agent-authored Python scripts rather than through MCP tools that hide the operation.

#### Scenario: Future operators do not expand MCP workflow tools
- **WHEN** a new spatial analysis family is introduced after KDE
- **THEN** the system adds skill guidance, snippets, tests, and evidence expectations for that family without adding a new MCP workflow wrapper for the operator.

### Requirement: Tool responses are structured and traceable
Every geospatial MCP tool SHALL keep enough backend-side structured payloads for validation, state updates, and dashboard traceability while returning compact agent-facing XML-like text that avoids internal ids, app-owned storage paths, and predefined workspace layout details.

#### Scenario: Context tool returns reusable execution metadata
- **WHEN** `get_session_context` completes successfully
- **THEN** its agent-facing result includes the workspace root, attached data roots, Python command contract, package readiness, and evidence-reporting instructions for that run context
- **AND** it does not include a workspace layout, evidence ledger path, artifact manifest path, request snapshot path, prepared-input path, or session history.

#### Scenario: Evidence tool returns artifact confirmation without internal storage details
- **WHEN** `record_run_evidence` completes successfully
- **THEN** its agent-facing result confirms the evidence category and, for artifacts, the normalized workspace-relative artifact path, artifact stage, file format, and display hint
- **AND** it does not expose app-owned ledger paths, generated record ids, database paths, serialized backend session state, or task-scoring pass/fail signals.

#### Scenario: Tool failure remains actionable
- **WHEN** a geospatial MCP tool fails or blocks execution
- **THEN** it returns a compact XML-like failure result that identifies the failed condition and preserves enough agent-facing context for repair, user clarification, or run termination.

### Requirement: Artifact-producing tools register reproducible evidence
The geospatial tool surface SHALL allow artifacts produced by agent-authored scripts to be registered as reproducible evidence, preserving originating session context, script or command provenance, filesystem location, and verification context in app-owned metadata without requiring the artifact to be created by an MCP operator.

#### Scenario: Generated map artifact is tied to the run record
- **WHEN** an agent-authored Python script generates a map, report, manifest, table, or derived dataset inside the shared workspace
- **THEN** the agent can call `record_run_evidence` to register a structured artifact reference that the backend and dashboard can associate with the originating session and task state
- **AND** the registration succeeds only when the referenced file already exists inside the shared workspace.

#### Scenario: Artifact stage controls dashboard placement
- **WHEN** an artifact is registered as `intermediate`
- **THEN** the dashboard can display it as inline execution evidence or in an intermediate evidence surface
- **AND** when an artifact is registered as `final`, the dashboard can promote it to final-artifact surfaces while still keeping the transcript evidence link.

#### Scenario: Evidence record preserves script provenance
- **WHEN** an artifact is registered after script execution
- **THEN** the evidence record can include the script path, command used, input paths, output paths, parameters, and relevant verification facts needed for reproducibility review
- **AND** script and output paths are preserved as agent-authored workspace-relative or external input references rather than as app-imposed workspace layout references.

#### Scenario: Evidence registration is not a task-performance requirement
- **WHEN** an evaluation run produces a transcript and outputs that are sufficient for the LLM judge to assess geospatial analysis quality
- **THEN** missing MCP evidence registration, missing artifact-stage metadata, or missing app-specific claim-trace records are reported as traceability or reproducibility gaps
- **AND** those gaps do not by themselves mark the task-performance result failed.

### Requirement: Artifact registration distinguishes previewable and open-only formats
The geospatial MCP evidence tool SHALL let agents register both human-readable previewable artifacts and non-previewable open-only artifacts, while describing the expected parameter values clearly enough for the agent to choose the right category.

#### Scenario: Human-readable artifacts declare previewable hints
- **WHEN** an agent registers an artifact intended for direct user reading or inspection
- **THEN** the tool schema and description identify supported previewable choices such as image, HTML, Markdown, plain text, and table-like CSV or TSV
- **AND** the tool response preserves the normalized artifact stage, format, display hint, title, description, and workspace-relative path.

#### Scenario: Machine-oriented artifacts use open-only category
- **WHEN** an agent registers JSON, GeoTIFF, GeoPackage, shapefile component data, archive, raster, binary, or another machine-oriented file
- **THEN** the schema permits an `other` or equivalent open-only format or display hint
- **AND** the tool description explains that the dashboard will not preview that file in-app.

#### Scenario: Invalid preview hints return actionable errors
- **WHEN** an artifact registration uses a preview hint that is unsupported for the declared file format
- **THEN** the tool failure identifies the unsupported value
- **AND** it tells the agent to either choose a supported human-readable preview type or register the file as open-only.

### Requirement: Artifact guidance favors human-readable deliverables
The geospatial MCP evidence tool SHALL encourage agents to submit user-facing maps, reports, tables, text, Markdown, or HTML artifacts for dashboard review when the underlying work also creates machine-readable datasets.

#### Scenario: Agent records a companion readable artifact
- **WHEN** an analysis produces a machine-readable dataset that is important to the result
- **THEN** the tool description recommends registering a human-readable companion artifact or summary when the user needs to inspect the result in the dashboard
- **AND** it still permits registering the machine-readable dataset as reproducible open-only evidence.

#### Scenario: JSON is not presented as a preferred artifact format
- **WHEN** the tool schema or examples describe artifact registration
- **THEN** JSON is treated as machine-readable evidence rather than as a preferred dashboard preview artifact
- **AND** examples for user-facing output prefer Markdown, text, HTML, image, or table artifacts.
