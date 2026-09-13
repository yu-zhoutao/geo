## ADDED Requirements

### Requirement: RL strategy controller uses bounded geospatial strategy actions
The system SHALL define a bounded action space for an RL policy that selects an evaluation strategy profile before a geospatial benchmark attempt starts.

#### Scenario: Policy selects a strategy through a structured action
- **WHEN** the RL training harness presents a benchmark scenario to the policy model
- **THEN** the policy action is captured as a structured `select_geospatial_strategy` call with a known `strategy_id`
- **AND** invalid, missing, or unsupported strategy actions are recorded as invalid policy actions instead of being silently repaired

#### Scenario: Strategy profile changes guidance without rewriting the prompt
- **WHEN** a valid strategy is selected for an attempt
- **THEN** the selected profile adjusts evaluation runtime assets or instruction emphasis only
- **AND** the original scenario prompt is submitted unchanged to the main agent flow
- **AND** the profile does not impose an application-authored fixed workflow graph or canned result script

#### Scenario: Strategy action is preserved as evidence
- **WHEN** a strategy-controlled attempt is executed
- **THEN** the run evidence records the selected strategy, policy model identity, policy checkpoint or run identifier, action validity, and action rationale when provided

### Requirement: TRL rollout bridge exposes geo-agent evaluation as a policy environment
The system SHALL provide a TRL-facing rollout bridge that turns benchmark scenarios into policy samples and returns rewards derived from geo-agent evaluation outcomes.

#### Scenario: Rollout bridge hides oracle-only fields from the policy
- **WHEN** the bridge prepares a policy input for a scenario
- **THEN** it includes task-facing prompt and safe scenario metadata needed for strategy selection
- **AND** it excludes oracle answers, judge results, gold control labels used only for scoring, and previous held-out evaluation outcomes

#### Scenario: Rollout bridge executes or resolves a selected strategy
- **WHEN** the policy selects a valid strategy
- **THEN** the bridge either resolves an offline reward-table entry for that scenario-strategy pair or launches a real app-backed evaluation attempt under the selected strategy
- **AND** online attempts use the existing evaluation runner boundary rather than calling internal session services directly

#### Scenario: Rollout bridge returns reward with diagnostics
- **WHEN** a policy sample finishes
- **THEN** the bridge returns a numeric reward and machine-readable reward components
- **AND** the diagnostics include judge dimension sources, run-status penalties, invalid-action penalties, and whether the reward came from offline lookup or online execution

### Requirement: Online TRL training uses fresh geo-agent rollouts
The RL experiment SHALL support a minimal online TRL loop where policy updates are based on live rollouts sampled from the current policy rather than only from an offline reward table.

#### Scenario: Current policy action triggers a live attempt
- **WHEN** the TRL training loop requests an online reward for a sampled completion
- **THEN** the current policy model receives a safe scenario observation and generates a `select_geospatial_strategy` structured action
- **AND** the selected strategy is executed through a fresh app-backed evaluation attempt before reward is returned
- **AND** the downstream geo-agent model configuration is recorded, including use of `deepseek-v4-flash` when the remote cost-saving setting is active

#### Scenario: Online reward cannot come from lookup-only training data
- **WHEN** an experiment is marked as online TRL training
- **THEN** rewards for policy updates come from newly captured run bundles and judge scores produced during that training run
- **AND** offline reward-table lookup is permitted only for preflight, debugging, warm-start baselines, or explicitly labeled ablations

#### Scenario: Policy update evidence is preserved
- **WHEN** a TRL online training step updates the controller policy
- **THEN** the experiment records the policy model id, LoRA adapter or checkpoint id, training step, sampled scenario id, generated structured action content, validation result, selected strategy, source run bundle, reward components, and update metadata
- **AND** policy checkpoints are stored under the configured experiment output root rather than in user-global project state

### Requirement: TRL integration remains outside the interactive app runtime
The RL experiment SHALL integrate with TRL through a bounded training harness and explicit experiment manifests instead of embedding training logic into the interactive app runtime.

#### Scenario: Training harness exposes structured actions
- **WHEN** the TRL strategy-controller training command is started
- **THEN** it configures the policy prompt or tool/action schema for `select_geospatial_strategy`
- **AND** it validates generated arguments against the configured strategy profile registry
- **AND** it returns invalid-action penalties for malformed JSON, missing structured actions, unsupported strategy ids, or unsafe action payloads

#### Scenario: Training harness remains optional
- **WHEN** the normal web app, non-RL evaluation runner, or scoring pipeline imports application modules
- **THEN** TRL, Transformers, PEFT, Accelerate, local model training, and GPU-only dependencies are not required unless the RL training command path is invoked

#### Scenario: Online training command enforces bounded resources
- **WHEN** an online TRL run starts
- **THEN** the command records scenario selector, strategy set, algorithm id, episode cap, parallel rollout cap, wall-clock budget, policy model id, LoRA configuration, reward formula id, downstream model provider, and output root
- **AND** it refuses unbounded training runs that omit episode or wall-clock limits

#### Scenario: RLOO is the default algorithm and GRPO is optional
- **WHEN** an online training manifest omits the algorithm id
- **THEN** the system selects RLOO as the default policy update method
- **AND** GRPO can be selected only through an explicit algorithm setting that records grouped-completion rollout requirements

### Requirement: Reward construction reuses thesis evaluation dimensions
The RL experiment SHALL compute rewards from existing judge dimensions, deterministic benchmark hints, forbidden behavior checks, and runtime facts rather than from opaque success labels.

#### Scenario: Reward uses existing judge scores
- **WHEN** a judged run is available for reward construction
- **THEN** the reward builder derives positive terms from existing dimension scores such as method selection, CRS and units, execution correctness, uncertainty and sensitivity, claim validity, repair or stop judgment, and overall task success
- **AND** the reward record preserves each weighted component used in the final scalar reward

#### Scenario: Reward penalizes execution and policy failures
- **WHEN** a run times out, records unresolved errors, triggers declared forbidden moves, or receives an invalid strategy action
- **THEN** the reward builder applies configured penalties and records them separately from judge-score components

#### Scenario: Reward configuration is versioned
- **WHEN** an RL experiment run starts
- **THEN** the reward formula identifier, weights, penalties, judge rubric identifier, and scenario selector are preserved in experiment metadata

### Requirement: Offline reward-table generation supports low-cost preflight
The RL experiment SHALL support generating a reward table by running candidate strategies across selected training scenarios before online model training.

#### Scenario: Reward table covers configured strategy-scenario pairs
- **WHEN** offline reward-table generation runs for a selector and strategy set
- **THEN** it records one entry for each completed scenario-strategy attempt or a structured failure entry when the attempt cannot produce reward

#### Scenario: Reward table stores reproducible attempt references
- **WHEN** a reward-table entry is written
- **THEN** it references the source run bundle, scenario fixture hash, strategy profile hash, judge score file, reward configuration, and runtime status

#### Scenario: Training can use reward lookup without hiding final evaluation cost
- **WHEN** policy training uses the offline reward table
- **THEN** the training metadata marks rewards as lookup-derived
- **AND** final thesis evaluation still supports frozen-policy online attempts whose rewards are produced from fresh run bundles

#### Scenario: Offline reward table is not the primary online RL result
- **WHEN** an RL evidence packet includes offline reward-table results
- **THEN** those results are labeled as fixed-strategy sweep, preflight, or lookup baseline evidence
- **AND** they are not described as online TRL training unless fresh policy-sampled run bundles were used for policy updates

### Requirement: RL experiment outputs thesis-ready but restrained evidence
The RL experiment SHALL export evidence suitable for thesis writing while making the limited scope of the reinforcement learning result explicit.

#### Scenario: Experiment summary reports strategy-layer results
- **WHEN** an RL experiment summary is generated
- **THEN** it reports strategy choices, reward components, judge dimension summaries, runtime facts, and representative failure cases
- **AND** it labels the result as a strategy-controller or concept-proof experiment rather than as end-to-end geospatial agent training

#### Scenario: Thesis packet includes limitations
- **WHEN** a thesis-ready RL evidence packet is exported
- **THEN** it includes limitations such as scenario count, judge noise, profile sensitivity, offline-reward use, and the difference between policy strategy selection and full agent capability improvement

#### Scenario: Negative and mixed outcomes are preserved
- **WHEN** the RL policy underperforms a baseline on a scenario group or dimension
- **THEN** the reporting artifact preserves that outcome and does not suppress it from aggregate summaries

#### Scenario: Thesis packet names the online scope precisely
- **WHEN** the thesis packet describes the updated TRL experiment
- **THEN** it states that the trained policy is a lightweight strategy controller and that the action space is a single pre-run strategy choice
- **AND** it distinguishes online controller training from full multi-turn geo-agent trajectory optimization
- **AND** it avoids claiming end-to-end reinforcement learning of the OpenCode-backed geospatial agent
