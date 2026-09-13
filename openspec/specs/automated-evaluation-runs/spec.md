# automated-evaluation-runs Specification

## Purpose
TBD - created by archiving change add-geospatial-evaluation-pipeline. Update Purpose after archive.
## Requirements
### Requirement: Evaluation campaigns are defined by versioned manifests
The system SHALL define evaluation campaigns with versioned manifests that pin benchmark selection, variants, repeats, fairness controls, budgets, scoring mode, and output policy for reproducible comparison runs.

#### Scenario: Campaign manifest defines a repeatable comparison
- **WHEN** a new evaluation campaign is created
- **THEN** it records the benchmark suite or scenario selector, participating variants, repeat count, run budgets, scoring mode, and output directory policy needed to rerun the campaign consistently later

#### Scenario: Campaign manifest pins fairness controls across variants
- **WHEN** a campaign compares multiple framework variants or baselines
- **THEN** it records runtime provider/model settings, dataset conditions, tool catalog constraints, runtime limits, separate judge provider/model settings, and scoring controls needed to make the comparison meaningful

#### Scenario: Runtime provider experiments keep judge settings fixed
- **WHEN** a campaign compares GLM and DeepSeek runtime runs
- **THEN** the runtime provider and model can vary by environment or manifest, while the LLM judge provider, judge model, rubric, and scoring settings remain fixed for comparable results

#### Scenario: Balanced thesis campaign is expressible
- **WHEN** the thesis campaign manifest is authored
- **THEN** it can express full-system runs over the curated real-data thesis core subset while limiting ablations and structural baselines to smaller representative real-data subsets

### Requirement: Variant manifests support internal framework overlays
The system SHALL allow internal variants to point to specific agent assets, skill availability, role availability, model settings, and runtime budgets so campaigns can compare framework structure without changing benchmark fixtures.

#### Scenario: Full-system variant uses the default bundle
- **WHEN** a campaign runs the `full-system` variant
- **THEN** the runner uses the current multi-agent geospatial bundle with professional skills and skeptical review enabled

#### Scenario: Single-agent variant disables specialist decomposition
- **WHEN** a campaign runs the `single-agent` variant
- **THEN** the runner uses a variant runtime definition where one geo agent owns triage, design, data audit, execution, reporting, and review responsibilities

#### Scenario: No-skills variant disables professional skill access
- **WHEN** a campaign runs the `no-skills` variant
- **THEN** the runner uses the same role structure as the full system while preventing those roles from reading or applying bundled geospatial skills

#### Scenario: No-skeptical-review variant disables the adversarial reviewer
- **WHEN** a campaign runs the `no-skeptical-review` variant
- **THEN** the runner uses a variant runtime definition where the skeptical-review role is unavailable and final release does not require that role's approval

### Requirement: Evaluation runner executes campaigns through app APIs
The evaluation pipeline SHALL execute agent benchmark runs through the app's HTTP API boundary rather than by directly calling internal session services or bypassing the runtime.

#### Scenario: Runner starts a headless app-backed run
- **WHEN** the runner executes a scenario attempt
- **THEN** it creates or targets an isolated app instance, waits for health readiness, creates a session through the app API, attaches data directories through the app API, and submits the scenario prompt unchanged

#### Scenario: Runner collects completed session state through APIs
- **WHEN** a scenario attempt reaches a terminal state or times out
- **THEN** the runner retrieves the canonical session archive trace JSON through the app archive API and derives session JSON, messages, timeline entries, plan groups, verification entries, artifacts, evidence records, and runtime trace references from that archive

#### Scenario: Runner fetches registered artifact content through APIs
- **WHEN** a run registers artifacts needed for scoring or thesis packets
- **THEN** the runner copies those artifacts through app-supported artifact resolution or content endpoints and records hashes in the run bundle

#### Scenario: Runner keeps session trace archive separate from artifact bytes
- **WHEN** a scenario attempt is captured
- **THEN** the runner stores the app-exported session archive unchanged as `session-trace.json` and captures registered artifact contents as separate hashed files rather than embedding artifact bytes in the trace JSON

### Requirement: Evaluation runner preserves unchanged benchmark prompts
The evaluation pipeline SHALL submit each scenario prompt to the main agent flow without hidden prompt rewriting by the app or runner.

#### Scenario: Scenario prompt is submitted verbatim
- **WHEN** a scenario attempt starts
- **THEN** the first text submitted to the app message endpoint matches the fixture `user_prompt` except for explicit scenario-defined answer continuation when a clarification flow is being tested

#### Scenario: Recovery continuation uses a fixed message
- **WHEN** a run needs continuation recovery after an interrupted or incomplete app state
- **THEN** the runner appends the same fixed continuation message to the existing session rather than rewriting the benchmark prompt, changing the data, changing the model, or creating a new session

#### Scenario: Domain guidance stays in assets and skills
- **WHEN** a campaign varies prompts, skills, or roles
- **THEN** those changes are represented in variant assets or runtime bundles rather than by rewriting the user's scenario prompt in the runner

### Requirement: Campaign runs produce isolated run bundles
The evaluation pipeline SHALL create one isolated run bundle per scenario attempt so repeated runs and variants do not overwrite one another.

#### Scenario: Repeated attempts get distinct run bundles
- **WHEN** a campaign runs the same scenario multiple times for a given variant
- **THEN** each attempt is stored as a distinct run bundle with its own config snapshots, traces, artifacts, scores, timings, and errors

#### Scenario: Run bundles avoid copying rebuildable dependencies
- **WHEN** a scenario attempt is preserved
- **THEN** the run bundle keeps per-attempt workspace, app state, logs, traces, artifacts, and score files, while omitting venvs, node modules, caches, and generated runtime config directories that can be recreated from the app/runtime configuration

#### Scenario: Partial failures preserve evidence
- **WHEN** a scenario attempt fails, times out, or the app/runtime crashes
- **THEN** the runner still writes the run manifest, logs, partial session state when available, error details, and failure score inputs

#### Scenario: Campaign resume does not overwrite prior attempts
- **WHEN** a campaign is resumed after partial completion
- **THEN** existing run bundles remain immutable and new attempts receive new run identifiers unless the user explicitly requests cleanup outside the runner

### Requirement: Campaign runner handles clarification states explicitly
The evaluation pipeline SHALL treat expected `clarify` outcomes as valid terminal states and SHALL only continue a clarification flow when the scenario defines a deterministic answer policy.

#### Scenario: Expected clarify terminates successfully
- **WHEN** a scenario's gold control state is `clarify` and the agent asks a relevant blocking question
- **THEN** the runner can stop the attempt and pass the resulting session state to scoring without answering the question

#### Scenario: Scenario-defined answer policy continues a run
- **WHEN** a scenario fixture defines a clarification answer policy
- **THEN** the runner submits the defined answer through the app question-answer API and records the continuation in the run bundle

### Requirement: Campaign runner enforces budgets and cleanup
The evaluation pipeline SHALL enforce configured runtime budgets and clean up app/runtime subprocesses after campaign completion, cancellation, timeout, or crash.

#### Scenario: Attempt budget triggers interruption
- **WHEN** a scenario attempt exceeds its configured wall-clock budget
- **THEN** the runner interrupts or stops the session through supported app/runtime controls and records the timeout as a scored run outcome

#### Scenario: Interrupted sessions receive bounded continuation recovery
- **WHEN** a session is interrupted or returns to an incomplete `idle` or `failed` state before normal scoring
- **THEN** the runner sends a fixed continuation message in the same session until the run reaches a normal terminal outcome or the logical run reaches the default `max_continuations=2`

#### Scenario: Continuation count is recorded
- **WHEN** a run bundle is written
- **THEN** the run status records `continuation_count` and relies on the session trace for the exact continuation messages

#### Scenario: Campaign shutdown cleans up child processes
- **WHEN** a campaign finishes, is cancelled, or crashes
- **THEN** the runner shuts down the app/runtime processes it started and preserves logs needed to diagnose failures

