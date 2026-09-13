## Purpose
Define the application-owned geospatial agent asset model, skill-pack structure, validation rules, generated managed-home runtime behavior, and knowledge-manifest requirements.
## Requirements
### Requirement: Application-owned geospatial agent assets are the source of truth
The system SHALL store application-scoped geospatial subagent definitions, skill packages, supporting references, and evaluation materials under an app-owned asset tree rather than in inline backend strings or repository-scoped development runtime config.

#### Scenario: App-owned asset tree is available to the backend
- **WHEN** the backend prepares geospatial runtime support
- **THEN** it discovers the source geospatial agent assets from an application-owned directory such as `app/agent_assets/`

#### Scenario: Development runtime config does not become product truth
- **WHEN** repository-scoped `.opencode` files exist for development workflows
- **THEN** the application does not treat them as the source of truth for product geospatial agents or skills

### Requirement: Skill packages use self-contained operational handbooks
The system SHALL keep the operational guidance for each geospatial skill inside `SKILL.md` so the runtime can read workflow, domain rules, failure modes, and worked examples in one pass rather than splitting core method guidance across multiple markdown files.

#### Scenario: Standard self-contained skill structure is available
- **WHEN** a geospatial skill package is authored for application use
- **THEN** `SKILL.md` contains the operational workflow, detailed rules, failure modes, and worked examples needed for execution

#### Scenario: Runtime skill packages keep only necessary support files external
- **WHEN** a geospatial skill package needs external files alongside `SKILL.md`
- **THEN** those files are limited to genuinely needed executable snippets or code examples rather than fragmented markdown rulebooks or local evaluation fixture directories

#### Scenario: Runtime skill package omits local evaluation fixtures
- **WHEN** a geospatial skill package is validated for runtime use
- **THEN** the package is not required or expected to include a local evaluation-fixture directory

### Requirement: Rulebook-grade skills can define stable rules, failure modes, and artifact contracts
The system SHALL allow high-risk geospatial skill packs to define stable rule identifiers, named failure modes, artifact-field expectations, and explicit policy defaults so operator reasoning and guardrails can be reused consistently across prompts, review logic, and central benchmark fixtures.

#### Scenario: Skill package exposes stable rule and failure identifiers
- **WHEN** a KDE or CRS-safety skill package is authored for application use
- **THEN** it can define stable rule IDs and failure-mode IDs that downstream agents and benchmark fixtures can reference consistently

#### Scenario: Skill package declares artifact expectations and local policy defaults
- **WHEN** a skill package includes method-critical checks such as CRS safety, bandwidth provenance, or claim discipline
- **THEN** it can declare the artifact fields and pack-specific policy defaults needed to make those checks inspectable without implying that every threshold is a universal GIS law

### Requirement: Benchmark fixtures can assert control states and guardrails
The system SHALL keep executable scenario checks in central benchmark fixtures that assert expected control states, required artifact fields, and forbidden output phrases so scenario-based checks can validate professional guardrail behavior rather than prose style alone.

#### Scenario: Benchmark fixture asserts expected control state
- **WHEN** a benchmark includes a negative or positive scenario fixture
- **THEN** the fixture can record the expected `proceed`, `clarify`, `repair`, or `stop` outcome for that case

#### Scenario: Benchmark fixture asserts artifact and language constraints
- **WHEN** a benchmark includes a scenario fixture for a method-critical failure mode
- **THEN** the fixture can record required artifact fields and forbidden output phrases that should not survive the run

### Requirement: Agent assets are validated before runtime generation
The backend SHALL validate geospatial agent assets before generating managed runtime config, including required files, required prompt sections, valid frontmatter, and valid skill references.

#### Scenario: Missing required agent sections block runtime preparation
- **WHEN** a geospatial agent asset omits a required section such as `Mission`, `Workflow`, or `Stop Conditions`
- **THEN** runtime preparation fails with a structured asset validation error instead of generating a partial config bundle

#### Scenario: Invalid skill references block runtime preparation
- **WHEN** an agent or skill references a missing or malformed skill package
- **THEN** runtime preparation fails with a structured asset validation error instead of silently dropping the reference

### Requirement: Generated runtime config is materialized from validated assets
The backend SHALL materialize managed OpenCode runtime knowledge from validated geospatial agent assets into the application-managed OpenCode home layout under the app support directory, and the managed runtime SHALL consume that generated home-scoped config instead of the source asset directory directly or a separate `runtime-config` bundle.

#### Scenario: Managed runtime config is generated from validated assets
- **WHEN** the backend prepares the OpenCode runtime for application use
- **THEN** it writes the generated OpenCode config, validated geospatial skills, and related knowledge metadata into the managed `.config/opencode/` tree that the runtime can load

#### Scenario: Generated config is treated as build output
- **WHEN** source agent assets change in application code
- **THEN** the backend can regenerate the managed home-scoped runtime config bundle without requiring manual edits to generated OpenCode config files

### Requirement: Generated runtime bundle includes a knowledge manifest
The backend SHALL write a runtime knowledge manifest into the same managed OpenCode config root as the generated runtime config so a specific run can be tied back to the exact packaged agents and skills that were active in that home-scoped runtime environment.

#### Scenario: Knowledge manifest records generated asset inventory
- **WHEN** the backend generates the managed OpenCode runtime config from validated geospatial assets
- **THEN** it also writes a manifest in the managed `.config/opencode/` tree that includes the packaged agents, packaged skills, generation timestamp, and source-version metadata needed for later inspection

#### Scenario: Knowledge manifest supports reproducibility review
- **WHEN** a geospatial run is inspected after execution
- **THEN** the backend or reviewer can determine which generated home-scoped knowledge bundle was active for that run without inferring it only from free-form logs or a duplicate runtime bundle directory

### Requirement: Skills teach managed Python geospatial execution
Application-owned geospatial skills SHALL include concrete guidance for writing and running small Python scripts in the managed geospatial environment instead of instructing agents to call hidden MCP workflow tools or rely on predefined workspace subdirectories.

#### Scenario: Skill includes command contract
- **WHEN** a geospatial skill explains executable local analysis work
- **THEN** it references the managed command pattern `"$GEO_AGENT_UV_BIN" --project "$GEO_AGENT_GEO_PYTHON_PROJECT" run --python "$GEO_AGENT_GEO_PYTHON_VERSION" python <script>` and the workspace environment variables available to the runtime
- **AND** `<script>` is described as an agent-chosen path inside the shared workspace rather than a required `.geo/scripts` path.

#### Scenario: Skill includes library snippets
- **WHEN** a skill covers vector, raster, CRS, KDE, visualization, or report-oriented work
- **THEN** it includes concise Python snippets using the relevant project-managed packages such as GeoPandas, Shapely, PyProj, Rasterio, NumPy, Pandas, SciPy, scikit-learn, or Matplotlib.

#### Scenario: Skill examples avoid fixed workspace layout
- **WHEN** a skill shows where to place scripts, maps, tables, reports, intermediate files, or derived datasets
- **THEN** it uses agent-chosen example paths and states that the workspace has no required internal directory layout
- **AND** it does not prescribe `.geo/scripts`, `.geo/intermediate`, `.geo/artifacts`, `.geo/evidence`, or equivalent application-owned directories.

### Requirement: Skills preserve geospatial guardrails outside MCP workflows
Application-owned geospatial skills SHALL preserve method-critical guardrails for CRS, bounding boxes, units, overlap, parameter records, map honesty, and evidence-to-claim discipline even though MCP no longer performs those operations directly.

#### Scenario: CRS safety remains explicit
- **WHEN** a skill teaches distance-based vector or raster analysis
- **THEN** it requires the agent-authored script or evidence record to track source CRS, analysis CRS, linear units, and any reprojection decision.

#### Scenario: Bounding box safety remains explicit
- **WHEN** a skill teaches spatial filtering, clipping, masking, or overlay
- **THEN** it requires the agent-authored script or evidence record to track the relevant bounding boxes and overlap outcome.

#### Scenario: Claims remain tied to evidence
- **WHEN** a skill teaches report or conclusion synthesis
- **THEN** it requires substantive geospatial claims to reference registered artifacts, parameter records, verification facts, or claim-trace evidence.

### Requirement: Skills demonstrate evidence recording
Application-owned geospatial skills SHALL show agents how to record generated artifacts and verification facts through `record_run_evidence` without implying that unregistered workspace files are visible to the UI.

#### Scenario: Skill records artifact example
- **WHEN** a skill includes an example that generates a map, report, table, or derived dataset
- **THEN** it also includes an example evidence record containing the output path, file format, display hint, artifact stage, provenance summary, relevant inputs, and method-critical metadata
- **AND** the example makes clear that the artifact file must already exist inside the workspace before `record_run_evidence` is called.

#### Scenario: Skill records verification example
- **WHEN** a skill includes a CRS, overlap, parameter, or claim-discipline check
- **THEN** it also includes an example verification evidence record with status, reason code, checked inputs, and conclusion.

#### Scenario: Skill explains explicit UI artifact registration
- **WHEN** a skill discusses generated outputs that the user should see in the dashboard
- **THEN** it instructs the agent to register each durable UI-facing artifact through `record_run_evidence`
- **AND** it does not suggest that writing a file into a particular workspace directory is enough for the UI to display it.

### Requirement: Skill assets support runtime use and UI identification
Application-owned geospatial skill assets SHALL include enough stable identity and display metadata for generated prompts, runtime manifests, and explicit skill-use transcript rows to refer to the same skill consistently.

#### Scenario: Skill identity is stable across generated config
- **WHEN** a geospatial skill package is validated and generated into the managed OpenCode home
- **THEN** the generated metadata preserves a stable skill id or package name plus a concise display label when available
- **AND** role prompts and runtime manifests refer to that same identity.

#### Scenario: Skill usage can be displayed concisely
- **WHEN** runtime metadata later reports that a bundled skill was used
- **THEN** the dashboard can use the skill asset identity or display label to show a compact skill-use row
- **AND** it does not need to parse long skill instructions to name the skill.

### Requirement: Skills remain operational guidance rather than app workflows
Application-owned geospatial skills SHALL teach professional method choices, guardrails, examples, and evidence expectations without becoming fixed app-owned execution plans.

#### Scenario: Skill instructions support autonomous runtime decisions
- **WHEN** a managed agent reads a relevant geospatial skill
- **THEN** the skill gives operational rules, failure modes, snippets, and evidence expectations that the agent can apply to the current task
- **AND** it does not require a predetermined role sequence, hardcoded workspace layout, or hidden MCP workflow operator.

#### Scenario: Skill examples prefer user-readable evidence
- **WHEN** a skill demonstrates artifact registration
- **THEN** user-facing examples prefer Markdown, text, HTML, table, or image artifacts
- **AND** machine-readable datasets are described as reproducible open-only evidence or as companions to readable artifacts.

### Requirement: Interpolation and hotspot operator assets are generated into the managed runtime
The system SHALL add application-owned `operator-interpolation` and `operator-spatial-hotspot` specialist assets, validate them with the existing asset rules, and generate them into the managed OpenCode home-scoped runtime config.

#### Scenario: New operator agents are validated
- **WHEN** the backend prepares geospatial agent assets
- **THEN** it validates that `operator-interpolation` and `operator-spatial-hotspot` contain required prompt sections, valid frontmatter, and valid skill references.

#### Scenario: New operator agents are generated
- **WHEN** the managed runtime config is materialized from validated assets
- **THEN** the generated OpenCode config includes the interpolation and spatial-hotspot specialists with their referenced skills.

#### Scenario: Knowledge manifest records new assets
- **WHEN** the backend writes the runtime knowledge manifest
- **THEN** the manifest includes the new operator agents, skill packages, source-version metadata, and generation timestamp needed to audit which task-family guidance was active.

### Requirement: Interpolation skills teach IDW execution without fixed workflows
The system SHALL provide application-owned interpolation skill guidance that teaches method selection, IDW execution, CRS safety, parameter disclosure, artifact registration, validation, and interpretation limits without prescribing a fixed app-owned workflow.

#### Scenario: IDW skill uses managed Python command contract
- **WHEN** the interpolation skill explains executable analysis work
- **THEN** it references the managed command pattern `"$GEO_AGENT_UV_BIN" --project "$GEO_AGENT_GEO_PYTHON_PROJECT" run --python "$GEO_AGENT_GEO_PYTHON_VERSION" python <script>`
- **AND** it describes `<script>` as an agent-chosen path inside the shared workspace.

#### Scenario: IDW skill preserves method guardrails
- **WHEN** the interpolation skill teaches IDW
- **THEN** it requires numeric sampled point values, CRS and unit checks, parameter records, validation or limitation evidence, and artifact registration before final interpretation.

#### Scenario: IDW skill includes prototype policy defaults
- **WHEN** the interpolation skill defines executable IDW behavior
- **THEN** it includes concise rules for sample-count gates, `power=2`, valid power range, variable-neighborhood `k=12`, cell-size heuristic, duplicate-point handling, LOOCV or holdout validation metrics, and extrapolation disclosure.

#### Scenario: IDW skill avoids workflow substitution
- **WHEN** the interpolation skill provides examples or snippets
- **THEN** the examples support autonomous runtime decisions and do not require a predetermined role sequence, reserved workspace layout, or hidden MCP operator.

### Requirement: Hotspot skills teach PySAL-backed Gi* execution
The system SHALL provide application-owned hotspot skill guidance that teaches Getis-Ord Gi* execution with PySAL `esda` and `libpysal`, spatial-weight safety, significance interpretation, artifact registration, and claim discipline.

#### Scenario: Gi* skill uses PySAL snippets
- **WHEN** the hotspot skill explains executable analysis work
- **THEN** it includes concise Python snippets or pseudocode that use `esda` and `libpysal` from the managed geospatial environment rather than hand-written Gi* formulas.

#### Scenario: Gi* skill requires spatial-weight evidence
- **WHEN** the hotspot skill teaches Gi*
- **THEN** it requires the agent to record support geometry, attribute field, weight construction, transform, neighbor or distance settings, island policy, significance settings, and CRS decisions.

#### Scenario: Gi* skill includes PySAL parameter policy
- **WHEN** the hotspot skill defines executable Gi* behavior
- **THEN** it requires `esda.G_Local` with `star=True`, explicit `transform`, explicit `permutations`, fixed seed, declared `island_weight` policy, and output fields for z-scores, simulated p-values, bins, labels, neighbor counts, and weight metadata.

#### Scenario: Gi* skill includes prototype weight defaults
- **WHEN** the hotspot skill explains default spatial-weight selection
- **THEN** it documents Queen contiguity for polygon or grid units, optional KNN with explicit `k` for measured-point demo support, and clarification before distance-band thresholds are guessed.

#### Scenario: Gi* skill distinguishes statistical hotspots from density maps
- **WHEN** the hotspot skill describes interpretation
- **THEN** it requires claims to distinguish significant local clusters from raw high values, KDE density, and causal explanation.

### Requirement: Benchmark fixtures cover new task-family control states
The system SHALL add central benchmark scenarios for interpolation and hotspot tasks that cover expected `proceed`, `clarify`, `repair`, and `stop` outcomes.

#### Scenario: Interpolation benchmark fixtures assert control states
- **WHEN** interpolation benchmark materials are checked
- **THEN** they include representative fixtures for valid IDW execution, missing value-field clarification, CRS repair, missing-CRS stop, invalid-field stop, conflicting-duplicate clarification, and invalid-sample stop conditions.

#### Scenario: Hotspot benchmark fixtures assert control states
- **WHEN** hotspot benchmark materials are checked
- **THEN** they include representative fixtures for valid Gi* execution, missing aggregation-unit clarification, count-versus-rate clarification, distance-CRS repair, omitted-`star=True` repair, small-feature-count stop or demo-only clarification, invalid-field stop, island-weight clarification, and invalid-weight stop conditions.

#### Scenario: Fixtures assert evidence expectations
- **WHEN** the new benchmark fixtures describe expected outcomes
- **THEN** they assert required artifact fields and forbidden output moves that prevent KDE, IDW, and Gi* from being conflated.

### Requirement: Skill-local evaluation fixtures are removed from runtime skill packaging
The system SHALL keep runtime skill packages free of per-skill evaluation fixture directories; benchmark assets are the maintained evaluation surface.

#### Scenario: Existing skill-local fixtures are deleted
- **WHEN** implementation removes local skill evaluation fixture directories
- **THEN** runtime skill packages retain only `SKILL.md` and genuinely needed supporting files.

#### Scenario: Runtime skill packages do not require local evaluation fixtures
- **WHEN** the backend validates and materializes application-owned skills
- **THEN** a skill package is not rejected merely because it lacks local evaluation fixtures
- **AND** the independent evaluation pipeline remains responsible for executable benchmark scenarios.

### Requirement: Existing shared skills are hardened for multi-family execution
The system SHALL update existing triage, study design, data audit, CRS, KDE, artifact, reporting, and review skills so they remain accurate and executable after IDW and Gi* become supported task families.

#### Scenario: Supported-family language is current
- **WHEN** an existing skill discusses interpolation or statistical hotspot testing
- **THEN** it identifies IDW interpolation and PySAL-backed Gi* as supported after this change instead of describing them only as unsupported future families.

#### Scenario: High-risk skills include concise execution aids
- **WHEN** a lower-capability model reads a high-risk skill such as triage, study design, CRS safety, data semantic audit, KDE runbook, artifact traceability, or skeptical review
- **THEN** the skill provides a compact checklist or decision table in addition to prose explanations.

#### Scenario: Output contracts include typed examples
- **WHEN** a skill defines an output contract that downstream roles or tests must inspect
- **THEN** the skill includes a concise typed example or field contract that shows required keys, allowed control states, and method-specific evidence fields.

#### Scenario: Cross-skill handoffs are explicit
- **WHEN** a shared skill hands work to an operator or reviewer
- **THEN** it states the next role, required evidence fields, and assumptions that downstream roles may rely on without forcing a fixed app-owned workflow order.

