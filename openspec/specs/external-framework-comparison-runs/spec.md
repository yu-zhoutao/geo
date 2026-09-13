# external-framework-comparison-runs Specification

## Purpose
Define how independently executed GIS Copilot and GeoCogent runs are selected, preserved, validated, imported, and scored for thesis comparison without requiring them to use this project's app runtime or trace schema.
## Requirements
### Requirement: External framework comparison uses existing benchmark scenarios
The system SHALL run external framework comparisons against selected existing geospatial benchmark scenarios instead of creating separate prompts or separate oracles for GIS Copilot and GeoCogent.

#### Scenario: External comparison preserves scenario prompt
- **WHEN** an external framework evidence pack is prepared for a scenario
- **THEN** the evidence pack references the original scenario fixture and records the exact scenario `user_prompt` used for the external run
- **AND** any operator setup instructions are recorded separately from the prompt

#### Scenario: External comparison preserves scenario data
- **WHEN** an external framework run uses local data
- **THEN** the evidence pack records the scenario dataset references, copied dataset-pack path or source data path, and any framework-specific import steps needed to make the same data available

#### Scenario: External comparison subset is balanced
- **WHEN** the thesis external-comparison scenario selector is validated
- **THEN** it includes real-data scenarios covering `proceed`, `clarify`, `repair`, and `stop` expected outcomes unless the selector explicitly documents a temporary installation or cost constraint

#### Scenario: External comparison uses repeated attempts
- **WHEN** the thesis external-comparison selector is validated
- **THEN** it records the configured repeat count for every framework/scenario setup so grouped exports can report three-attempt averages consistently with internal ablation campaigns

### Requirement: External evidence packs preserve auditable execution evidence
The system SHALL define a local evidence-pack format for independently executed external framework runs so their outputs can be reviewed and scored without requiring app session traces.

#### Scenario: Evidence pack records framework identity
- **WHEN** an evidence pack is created
- **THEN** it records the external framework id, framework label, Zotero item key or citation note, source repository or artifact reference when available, version or commit when known, execution environment notes, model settings, and run timestamp

#### Scenario: Evidence pack records run evidence
- **WHEN** an external framework run completes, blocks, fails, or is stopped manually
- **THEN** the evidence pack stores or references the run transcript or logs, generated code or tool-call notes when available, final answer or failure note, output artifacts, runtime duration, timeout status, and operator notes

#### Scenario: Evidence pack hashes artifacts
- **WHEN** an evidence pack references local artifact files
- **THEN** the validation or import step records stable hashes for those artifacts so later scoring and thesis tables can be traced back to the same bytes

#### Scenario: Real external comparison outputs are archived outside versioned assets
- **WHEN** real external framework evidence packs or scored campaign outputs are produced for thesis comparison
- **THEN** they are stored under the project-root `evaluation-runs/` archive tree
- **AND** versioned evaluation assets contain only reusable manifests, templates, procedures, and small example evidence

### Requirement: External evidence packs validate before scoring
The system SHALL validate external framework evidence packs before LLM judge scoring so incomplete comparison evidence fails early.

#### Scenario: Missing required evidence blocks scoring
- **WHEN** an evidence pack omits the framework id, scenario id, original prompt, run status, final answer or failure note, and at least one transcript, log, generated-code, tool-note, or artifact reference
- **THEN** validation fails with a clear error and the pack is not sent to the judge

#### Scenario: Scenario reference must resolve
- **WHEN** an evidence pack references a scenario id or scenario fixture path
- **THEN** validation confirms that the scenario exists in the configured benchmark root and that the evidence pack prompt matches the fixture prompt

#### Scenario: External artifact paths must resolve
- **WHEN** an evidence pack lists artifacts or logs
- **THEN** validation confirms that each required path exists under the evidence-pack root or an explicitly allowed local source path

### Requirement: External evidence imports produce scoreable records
The system SHALL convert validated external evidence packs into judge-compatible inputs or minimal run-like records for the existing dimension-only scoring pipeline.

#### Scenario: Importer builds judge input from external evidence
- **WHEN** a validated evidence pack is imported for scoring
- **THEN** the importer creates a judge input that includes scenario oracle context, the original prompt, external transcript or log excerpts, final answer or failure note, artifact summaries, framework metadata, and runtime facts
- **AND** it does not require app-specific session traces, todo state, subagent activity, MCP evidence records, or control-state fields

#### Scenario: Importer records external run provenance
- **WHEN** a validated evidence pack is imported
- **THEN** the imported record preserves the evidence-pack path, evidence-pack hash or manifest hash, framework id, scenario id, repeat index, runtime facts, and artifact references needed for aggregation and audit

#### Scenario: Importer avoids fabricated traces
- **WHEN** external evidence is converted into a scoreable record
- **THEN** the system MUST NOT fabricate OpenCode messages, app session events, subagent calls, tool invocations, or artifact registrations that did not exist in the external framework run

### Requirement: External framework execution stays isolated from app runtime
The system SHALL keep GIS Copilot and GeoCogent execution separate from the interactive app, backend-managed OpenCode runtime, and backend-hosted MCP tool configuration.

#### Scenario: External framework is not launched as app runtime variant
- **WHEN** an external comparison run is prepared
- **THEN** GIS Copilot and GeoCogent setup and execution instructions are stored as experiment assets or operator notes rather than as OpenCode runtime agent assets or backend MCP configuration

#### Scenario: Interactive app behavior is unchanged
- **WHEN** external comparison support is added
- **THEN** the Vue frontend, normal FastAPI session APIs, SSE transcript streaming, OpenCode runtime lifecycle, and backend-hosted geospatial MCP capabilities continue to behave as before

#### Scenario: Local geospatial execution remains task support
- **WHEN** external evidence is validated or imported
- **THEN** local Python utilities may inspect files, compute hashes, summarize artifacts, and build judge packets, but they do not become a hidden deterministic replacement for the external framework's own run
