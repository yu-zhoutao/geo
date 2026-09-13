# evaluation-results-reporting Specification

## Purpose
Define dimension-only LLM judge scoring, audit artifacts, and thesis-ready evaluation exports while preserving runtime status as non-scoring provenance.
## Requirements
### Requirement: Evaluation scoring uses only LLM judge dimensions
The system SHALL treat the fixed LLM judge rubric dimensions as the only evaluation scores for thesis model and system comparisons.

#### Scenario: LLM judge returns dimension-only scores
- **WHEN** a scenario attempt is scored
- **THEN** the LLM judge returns scores and reasons for method selection, data readiness, CRS and units, parameterization, execution correctness, uncertainty and sensitivity, and claim validity
- **AND** each score is an integer from 1 to 5
- **AND** the judge result does not include task pass/fail, professional acceptability, deterministic fatal failures, judgeability failures, or traceability pass/fail fields

#### Scenario: Runtime status remains non-scoring provenance
- **WHEN** a scenario attempt finishes, fails, times out, or needs continuation recovery
- **THEN** the run bundle records terminal status, terminal reason, timeout flag, duration, error count, error messages, continuation count, and attempt metadata
- **AND** those fields are reported as execution facts rather than scoring metrics

#### Scenario: Deterministic scoring is not generated
- **WHEN** a campaign or container attempt is scored
- **THEN** the scorer writes judge inputs, raw judge responses, and judge score files only
- **AND** it does not create or consume `deterministic-score.json` for newly scored results

### Requirement: LLM judge scoring is reproducible and auditable
The system SHALL preserve judge configuration, judge prompts, raw judge responses, parsed JSON scores, and validation errors for every judged run.

#### Scenario: Judge prompt and response are saved
- **WHEN** the LLM judge scores a run
- **THEN** the run bundle stores the exact judge input packet, model configuration, raw response, parsed score JSON, and judge timestamp

#### Scenario: Judge configuration is stable across runtime-provider comparisons
- **WHEN** campaign runs are produced by different runtime providers such as GLM and DeepSeek
- **THEN** the scorer records and uses the same judge provider, judge model, rubric version, and decoding settings unless the campaign explicitly declares a judge experiment

#### Scenario: Judge output must pass schema validation
- **WHEN** the LLM judge returns a response
- **THEN** the scorer validates that all rubric dimensions are present with 1-5 scores and non-empty reasons
- **AND** invalid-output attempts are preserved instead of silently accepted

#### Scenario: Judge packet cites transcript-first evidence inputs
- **WHEN** a judge input packet is built
- **THEN** it includes scenario oracle context, the original user prompt, relevant transcript excerpts derived from the session trace archive, final answer or output metadata, artifact summaries where available, and runtime status
- **AND** it does not include deterministic-score summaries or frame missing framework-specific traceability files, MCP evidence records, registered artifact schemas, or app-owned control-state fields as task-performance failures

### Requirement: Evaluation reporting exports dimension score summaries
The system SHALL export campaign summaries in forms that are directly reusable for thesis writing and figure/table generation.

#### Scenario: Campaign export includes per-run dimension scores
- **WHEN** a campaign finishes scoring
- **THEN** it writes a per-run score table containing run identity, scenario metadata, variant metadata, run status facts, judge model metadata, each dimension score, each dimension reason, and the run's average dimension score

#### Scenario: Campaign export includes grouped dimension averages
- **WHEN** a campaign finishes scoring
- **THEN** it writes grouped averages by variant, scenario, task family, semantic expected outcome, split, difficulty, variant-by-scenario, and variant-by-outcome
- **AND** no grouped export reports task success rate, deterministic pass rate, judgeability rate, traceability rate, control-state accuracy, fatal failure rate, or unsupported-coercion rate

#### Scenario: Campaign summary remains machine-readable
- **WHEN** a campaign finishes scoring
- **THEN** `campaign-summary.json` preserves the per-run rows and grouped dimension averages for later analysis
- **AND** execution failures remain visible through run status fields rather than through score-like 0/1 metrics

#### Scenario: Thesis summary explains score interpretation
- **WHEN** a thesis summary is generated
- **THEN** it describes the run count, available scored-run count, rubric dimensions, and grouped average-score files
- **AND** it states that runtime status fields are execution facts rather than evaluation scores

### Requirement: Evaluation reporting includes imported external framework runs
The system SHALL include validated imported external framework runs in dimension-score exports when they share the same benchmark scenarios and LLM judge rubric as internal evaluation runs.

#### Scenario: External runs appear in per-run score exports
- **WHEN** imported GIS Copilot or GeoCogent evidence-pack runs have been scored by the LLM judge
- **THEN** the per-run score table includes those rows with framework id, framework label, scenario metadata, run status facts, judge model metadata, each dimension score, each dimension reason, and average dimension score

#### Scenario: External runs appear in grouped averages
- **WHEN** a campaign summary includes scored imported external framework runs
- **THEN** grouped averages include those frameworks in the same variant or framework grouping dimensions used for thesis comparison
- **AND** runtime status fields remain execution facts rather than score-like pass or fail metrics

#### Scenario: External evidence provenance is exported
- **WHEN** imported external framework rows are exported
- **THEN** each row preserves a reference to the evidence-pack path, evidence manifest hash, framework metadata, scenario fixture reference, and score file path so thesis claims can be audited

#### Scenario: Framework-specific missing fields are not scoring gates
- **WHEN** an imported external framework run lacks app-specific session traces, todo records, role traces, MCP evidence records, registered artifact schemas, or control-state fields
- **THEN** reporting does not treat those missing fields as separate task-performance failures
- **AND** the judge score remains based on the semantic evidence available in the external evidence pack

#### Scenario: Cross-framework scores use core geospatial quality dimensions
- **WHEN** external framework comparison runs are scored for thesis reporting
- **THEN** the default judge dimensions are limited to method selection, data readiness, CRS and units, parameterization, execution correctness, uncertainty and sensitivity, and claim validity
- **AND** presentation-only differences, app-specific repair/stop workflows, and aggregate overall-success labels are not separate scoring dimensions
