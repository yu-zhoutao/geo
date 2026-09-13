## ADDED Requirements

### Requirement: Evaluation reporting exports RL strategy experiment summaries
The system SHALL export RL strategy-controller experiment summaries that reuse judge dimensions and runtime facts while avoiding inflated pass/fail claims.

#### Scenario: RL summary includes per-attempt strategy outcomes
- **WHEN** an RL strategy experiment finishes scoring
- **THEN** the summary includes per-attempt scenario metadata, strategy metadata, policy metadata when available, reward components, judge dimension scores, judge dimension reasons, and runtime status facts

#### Scenario: RL summary includes grouped strategy comparisons
- **WHEN** an RL strategy experiment summary is generated
- **THEN** it reports grouped averages by strategy, policy checkpoint, scenario family, semantic expected outcome, split, difficulty, and risk category where available
- **AND** it does not recast those grouped averages as universal success rates or product-readiness claims

#### Scenario: RL summary distinguishes training and held-out evaluation
- **WHEN** both offline reward-table training data and frozen-policy evaluation data exist
- **THEN** the exported summary labels which results came from offline reward lookup, online development attempts, and held-out frozen-policy evaluation attempts

#### Scenario: RL summary includes TRL training evidence
- **WHEN** an online TRL strategy-controller run produces checkpoints
- **THEN** the summary includes policy model id, LoRA adapter or checkpoint ids, online episode counts, policy-sampled strategy distribution, reward trajectory, invalid-action rate, rollout duration, downstream model configuration, and source run-bundle references
- **AND** it separates base-policy, trained-checkpoint, fixed-strategy baseline, offline preflight, online training, and held-out online evaluation rows

### Requirement: Thesis RL evidence packet uses cautious interpretation
The system SHALL generate thesis-facing RL experiment evidence that supports restrained academic discussion rather than promotional claims.

#### Scenario: Thesis packet describes the experiment boundary
- **WHEN** the thesis RL evidence packet is generated
- **THEN** it states that the experiment optimizes a strategy-selection layer around the existing geospatial multi-agent system
- **AND** it states that the experiment does not constitute end-to-end training of a general geospatial analysis model

#### Scenario: Thesis packet includes limitations and failure cases
- **WHEN** the thesis RL evidence packet is generated
- **THEN** it includes representative failure cases, underperforming dimensions or scenario groups when present, and limitations related to scenario count, judge variability, reward design, and profile sensitivity

#### Scenario: Thesis packet preserves reproducibility references
- **WHEN** the thesis RL evidence packet cites a result table, curve, or qualitative case
- **THEN** it references the source experiment manifest, reward configuration, policy checkpoint or run identifier, run bundles, and judge files needed to trace the evidence

#### Scenario: Thesis packet distinguishes online TRL from offline lookup
- **WHEN** the thesis packet describes the TRL experiment
- **THEN** it states whether each result was produced by offline reward lookup, online TRL/RLOO training, or frozen-policy online evaluation
- **AND** it does not use lookup-only policy-stub evidence as the main proof of reinforcement learning
- **AND** it states that the trained component is the strategy controller, not the downstream OpenCode-backed geospatial agent
