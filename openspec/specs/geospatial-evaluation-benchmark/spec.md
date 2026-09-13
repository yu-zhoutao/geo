# geospatial-evaluation-benchmark Specification

## Purpose
TBD - created by archiving change add-geospatial-evaluation-pipeline. Update Purpose after archive.
## Requirements
### Requirement: Geospatial evaluation uses versioned scenario fixtures
The system SHALL define geospatial evaluation cases as versioned scenario fixtures rather than as ad hoc prompts so benchmark behavior can be reproduced across framework variants and thesis runs.

#### Scenario: Scenario fixture records semantic benchmark oracle
- **WHEN** a new geospatial benchmark case is authored
- **THEN** it records the user request, dataset pack, semantic expected outcome, and oracle information needed by the LLM judge to assess whether the run behaved professionally
- **AND** semantic expected outcomes such as `proceed`, `clarify`, `repair`, and `stop` describe the professional behavior expected in the transcript and final output rather than requiring a framework-specific structured output field

#### Scenario: Scenario fixture records benchmark hazards
- **WHEN** a benchmark case encodes a method-critical hazard or expected success path
- **THEN** it records task-output hints, forbidden behaviors, fatal error classes, and claim or map constraints as semantic judge context and optional diagnostic checks
- **AND** those fields do not require the evaluated agent to emit app-specific artifact schemas or control-state records

#### Scenario: Scenario fixture is preserved for run provenance
- **WHEN** an evaluation run starts for a scenario
- **THEN** the runner records the scenario fixture path, fixture hash, and resolved scenario payload in the run bundle

### Requirement: Benchmark fixtures include complete thesis scoring metadata
The benchmark SHALL include enough metadata for dimension-only LLM judge scoring and stratified reporting without relying on unstated reviewer assumptions.

#### Scenario: Fixture defines judge scoring fields
- **WHEN** a scenario needs qualitative scoring
- **THEN** it declares the judge rubric dimensions or rubric reference needed to score method selection, data readiness, CRS and units, parameterization, execution correctness, uncertainty and sensitivity, claim validity, map and report quality, repair or stop judgment, and overall task success

#### Scenario: Fixture defines optional judge-context fields
- **WHEN** a scenario encodes machine-checkable hints such as forbidden terms, required claim terms, expected control behavior, or artifact expectations
- **THEN** those hints are available to the judge packet as semantic context
- **AND** missing or mismatched app-owned structured records do not create separate pass/fail scoring results

#### Scenario: Fixture defines dataset pack resolution
- **WHEN** a scenario references local data
- **THEN** it declares dataset-pack paths or data-root-relative paths that the runner can resolve and attach through app APIs

### Requirement: Benchmark fixtures cover semantic outcomes, difficulty, and task families
The benchmark SHALL support scenario metadata for `proceed`, `clarify`, `repair`, and `stop` semantic outcomes, task-family tags, and difficulty labels so results can be stratified by decision type and complexity.

#### Scenario: Benchmark case is labeled by semantic expected outcome
- **WHEN** a scenario is added to the benchmark suite
- **THEN** it declares whether correct professional behavior is `proceed`, `clarify`, `repair`, or `stop`
- **AND** the label is used for judge context and reporting stratification rather than as a mandatory structured control-state output

#### Scenario: Benchmark case is labeled by task family
- **WHEN** a scenario is added to the benchmark suite
- **THEN** it declares whether the scenario targets KDE, spatial interpolation, spatial hotspot analysis, an unsupported future task family, reporting review, or another explicit evaluation family

#### Scenario: Benchmark case is labeled by difficulty
- **WHEN** a scenario is added to the benchmark suite
- **THEN** it declares a difficulty label that campaign reports can use for stratified result summaries

### Requirement: Benchmark supports dev, test, and stress splits
The system SHALL organize benchmark fixtures into explicit splits so prompt authors can iterate on development cases while test and stress cases remain suitable for thesis evaluation.

#### Scenario: Development cases support iteration
- **WHEN** a benchmark case is marked as dev
- **THEN** it can be used for day-to-day prompt, skill, and runner debugging without being treated as a locked thesis result by default

#### Scenario: Test and stress cases stay separate from development iteration
- **WHEN** a benchmark case is marked as test or stress
- **THEN** the evaluation pipeline can select it separately from dev cases and preserve its fixture hash in campaign outputs

#### Scenario: Stress cases target framework failure modes
- **WHEN** a benchmark case is marked as stress
- **THEN** it can encode long-horizon routing, distractor tools, seeded defects, specialist disagreement, transient tool failures, CRS area-of-use hazards, or other framework-level risks

### Requirement: Benchmark defines representative subsets for ablations and baselines
The benchmark SHALL define representative subset tags so internal ablations and structural baselines can run a balanced, lower-cost scenario sample without changing the benchmark oracle.

#### Scenario: Ablation subset covers all control states
- **WHEN** the ablation campaign selects the representative subset
- **THEN** the selected scenarios include `proceed`, `clarify`, `repair`, and `stop` cases

#### Scenario: Ablation subset covers key geospatial hazards
- **WHEN** the ablation campaign selects the representative subset
- **THEN** the selected scenarios include KDE method-fit hazards, CRS or unit hazards, study-area or overlap hazards, reporting-review hazards, and at least one stress scenario

#### Scenario: Deterministic reference subset is limited to applicable proceed cases
- **WHEN** the deterministic GIS reference variant selects scenarios
- **THEN** it only selects cases where deterministic spatial output comparison is meaningful and does not claim to evaluate autonomous agent behavior

#### Scenario: Thesis subset uses real local datasets
- **WHEN** the thesis campaign selects the `thesis-core-real-v1` subset
- **THEN** the selected scenarios use existing `data/` directory datasets instead of synthetic fixtures and cover KDE, spatial interpolation, spatial hotspot, ambiguous requests, repair behavior, and unsupported claim boundaries

### Requirement: Benchmark fixtures can support internal and optional external framework comparison
The benchmark SHALL be expressed independently of any single framework implementation so the same fixtures can evaluate our framework variants and later adapter-backed external baselines under the same oracle.

#### Scenario: Internal variant reuses the same benchmark case
- **WHEN** a campaign compares full-system, single-agent, no-skills, or no-skeptical-review variants
- **THEN** each variant is evaluated against the same scenario fixture and oracle definition

#### Scenario: Optional external baseline reuses the same benchmark case
- **WHEN** a later campaign compares our framework to an adapter-backed external framework
- **THEN** the external run consumes the same scenario fixture, dataset pack, and oracle definitions without requiring a separate benchmark copy

### Requirement: Benchmark validation is automated
The system SHALL validate benchmark fixtures before campaign execution so incomplete or inconsistent evaluation cases fail early.

#### Scenario: Invalid fixture blocks campaign start
- **WHEN** a campaign references a fixture with missing required prompt, unresolved dataset paths, duplicate scenario identifiers, invalid semantic oracle labels, or missing judge rubric metadata
- **THEN** the runner refuses to start the campaign and reports the validation error

#### Scenario: Representative subset coverage is validated
- **WHEN** a campaign references a representative subset
- **THEN** validation confirms that the subset covers required semantic outcomes, task families, and hazard categories before any agent run starts

#### Scenario: Diagnostic check declarations are optional
- **WHEN** a benchmark fixture omits deterministic check declarations or framework-specific artifact expectations
- **THEN** validation still succeeds if the fixture has enough prompt, data, oracle, and judge rubric metadata for qualitative scoring
