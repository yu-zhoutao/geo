## Purpose
Define the contract-driven geospatial specialist roster, transcript-visible professional handoffs, role boundaries, skeptical-review behavior, and permission scoping for the managed runtime.

## Requirements

### Requirement: Geospatial runtime uses a contract-driven specialist roster
The system SHALL define a contract-driven geospatial specialist roster with a primary orchestrator and explicit specialist roles for request triage, study design, data audit, spatial preparation, KDE execution, evidence cartography, report synthesis, and skeptical review.

#### Scenario: Runtime loads the contract-driven roster
- **WHEN** the backend generates the managed geospatial runtime config
- **THEN** the resulting runtime bundle includes the orchestrator and the contract-driven specialist roles required for the KDE-first workflow

#### Scenario: KDE remains the first complete operator specialist
- **WHEN** the contract-driven roster is loaded for current supported execution
- **THEN** `operator-kde` is available as the first complete operator-specific specialist without implying that all future operator specialists already exist

### Requirement: Contract-driven roster is the only transcript identity source
The contract-driven geospatial roster SHALL define the canonical transcript identity for each visible role entry, the coding-agent runtime SHALL surface transcript-attributed role activity using those canonical roster identities, the Python backend SHALL preserve that identity contract when relaying or reconstructing session evidence, the frontend SHALL derive transcript role attribution only from that roster contract, and the local Python geospatial execution layer SHALL not publish an independent alias set for those roles.

#### Scenario: Orchestrator identity remains canonical in transcript attribution
- **WHEN** the managed geospatial roster is loaded for transcript-facing runtime activity
- **THEN** the orchestrator is attributed through its canonical roster entry rather than through a deprecated frontend-only alias
- **AND** transcript presentation can resolve that entry to the current orchestrator title without inventing a second legacy name

#### Scenario: UI-facing transcript names are localized without changing roster identity
- **WHEN** the transcript or an inline subagent handoff surfaces a canonical specialist role to the reader
- **THEN** the primary visible label comes from the Chinese-facing title attached to that canonical roster identity
- **AND** the stable runtime English id does not become a second visible role-name system in the transcript UI

#### Scenario: Current roster uses the finalized Chinese titles
- **WHEN** the application resolves the current canonical geospatial roster for transcript or prompt-facing identity
- **THEN** `geo`, `request-triage`, `study-design`, `data-audit`, `spatial-prep`, `operator-kde`, `evidence-cartography`, `report-synthesizer`, and `skeptical-review` resolve respectively to `空间主理人`, `需求分诊师`, `研究策划师`, `数据核验官`, `空间整备师`, `热点分析师`, `证据制图师`, `报告整编师`, and `结果审查官`
- **AND** the application does not substitute a different Chinese display-name set for those same runtime ids

#### Scenario: Deprecated aliases are not surfaced as valid roster identities
- **WHEN** live or reconstructed session evidence is attributed to a geospatial specialist role
- **THEN** only canonical roster identities are treated as valid transcript role names
- **AND** deprecated aliases such as `planner`, `analysis`, `viz`, `report`, `reflection`, or `data-prep` are not surfaced as current contract-driven role identities

#### Scenario: Future role additions do not revive alias compatibility
- **WHEN** a later geospatial specialist is added to the managed roster
- **THEN** it is introduced as a new canonical roster identity
- **AND** the system does not require reviving deprecated alias shims to make that role visible in the transcript

#### Scenario: Role summaries derive from the same canonical identity layer
- **WHEN** the frontend opens a role profile popover from a transcript avatar or inline mention
- **THEN** the displayed role summary resolves from the same canonical identity entry used for transcript attribution
- **AND** the frontend does not invent a separate alias-based profile registry for that role

#### Scenario: Generated runtime prompts receive the same localized roster vocabulary
- **WHEN** the backend generates the managed OpenCode runtime config for the canonical geospatial roster
- **THEN** each agent prompt is prefixed or otherwise augmented with that agent's Chinese-facing display name and the shared localized roster vocabulary
- **AND** the injected naming guidance is derived from the same application-managed identity map used by the transcript UI

### Requirement: Specialists publish transcript-visible professional handoffs
Each geospatial specialist SHALL return a transcript-visible handoff that communicates the professional decision, inputs reviewed, validated findings, blocking issues, downstream assumptions, and generated artifacts in a clear form suitable for later review.

#### Scenario: Specialist returns handoff after work
- **WHEN** a specialist finishes a unit of geospatial work
- **THEN** its output communicates the downstream contract needed for the next role
- **AND** the output may use natural language, tables, bullets, or structured JSON as long as the professional decision and evidence basis are visible in the transcript

#### Scenario: Structured decision fields are optional guidance
- **WHEN** a specialist expresses that the next professional action is to proceed, clarify, repair, or stop
- **THEN** the specialist is encouraged but not required to emit a machine-readable `decision` field
- **AND** missing structured decision fields do not by themselves imply failed task performance

#### Scenario: Blocking issue is surfaced explicitly
- **WHEN** a specialist encounters an issue that affects scientific validity or runtime safety
- **THEN** it surfaces the issue as a clarification, repair need, or stopping reason instead of quietly continuing with optimistic assumptions
- **AND** the issue may be expressed through transcript text, artifacts, MCP evidence, or a combination of those evidence forms

### Requirement: Role boundaries constrain what each specialist may decide
Each geospatial specialist SHALL declare scope boundaries that restrict what it may decide, what it must not decide, and what upstream context it requires before acting.

#### Scenario: Operator specialist does not bypass spatial preparation
- **WHEN** an operator specialist receives inputs that lack enough semantic, data-readiness, CRS, or study-area context for its method
- **THEN** it does not proceed as if preprocessing were already complete
- **AND** it explains the missing context or required repair in the transcript even if no structured prepared-input contract exists

#### Scenario: Visualization specialist does not upgrade analytical meaning
- **WHEN** `evidence-cartography` prepares a map package from operator outputs
- **THEN** it does not invent analytical claims that are absent from the verified analysis record or visible run evidence

### Requirement: Skeptical review can interrupt any stage
The system SHALL allow the skeptical-review specialist to inspect intermediate or final geospatial work at any stage and to trigger repair or stop decisions when it detects invalid assumptions, weak evidence grounding, or overclaimed conclusions.

#### Scenario: Skeptical review interrupts intermediate execution
- **WHEN** skeptical review is invoked before a run reaches final reporting
- **THEN** its findings can force repair, clarification, or termination without waiting for a final report phase

#### Scenario: Skeptical review inspects final claims
- **WHEN** a report draft or final artifact package is reviewed
- **THEN** skeptical review can downgrade or block claims that are not grounded in visible transcript evidence, generated outputs, registered artifacts, verification facts, or other available run evidence
- **AND** the absence of a particular app-specific evidence schema does not by itself make a claim invalid if the claim is otherwise supported by the visible analysis process and outputs

### Requirement: Specialist permissions are scoped to role boundaries
The generated runtime config SHALL assign specialist permissions and task restrictions according to role responsibility instead of giving all geospatial specialists the same unrestricted tool surface.

#### Scenario: Review-oriented roles stay read-mostly
- **WHEN** `request-triage`, `study-design`, `report-synthesizer`, or `skeptical-review` are packaged into the managed runtime
- **THEN** their permissions are limited to the read-oriented and coordination capabilities needed for their role unless a narrower exception is explicitly justified

#### Scenario: Execution-oriented roles receive only needed geospatial tools
- **WHEN** `data-audit`, `spatial-prep`, `operator-kde`, or `evidence-cartography` are packaged into the managed runtime
- **THEN** their permissions grant the geospatial execution capabilities needed for their responsibility without defaulting them to the same unrestricted access profile as every other specialist
