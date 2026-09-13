## ADDED Requirements

### Requirement: Evaluation attempts support externally selected strategy profiles
The evaluation pipeline SHALL allow an experimental controller to launch an attempt with a selected strategy profile while preserving existing prompt, data, runtime, and provenance guarantees.

#### Scenario: Strategy-controlled attempt preserves benchmark prompt
- **WHEN** a policy-selected strategy profile is applied to a scenario attempt
- **THEN** the runner submits the scenario prompt verbatim through the app API
- **AND** the strategy profile is applied through runtime asset preparation or equivalent evaluation configuration rather than through prompt rewriting

#### Scenario: Strategy profile is recorded in the run bundle
- **WHEN** a strategy-controlled attempt is allocated or executed
- **THEN** the run bundle records the strategy identifier, strategy profile source, profile hash, policy run identifier when available, and whether the strategy came from a trained policy, offline sweep, or manual baseline

#### Scenario: Strategy-controlled attempt uses existing isolation modes
- **WHEN** a strategy-controlled attempt runs through local-process or docker-per-attempt execution
- **THEN** it follows the same dataset attachment, tool catalog, budget, cleanup, and run-bundle isolation rules as other evaluation attempts

### Requirement: Evaluation campaigns can generate strategy reward sweeps
The evaluation pipeline SHALL support bounded reward-sweep runs that evaluate configured strategy profiles across selected benchmark scenarios for RL training data.

#### Scenario: Reward sweep expands scenario-strategy combinations
- **WHEN** a reward-sweep configuration names a scenario selector and a set of strategy profiles
- **THEN** the runner plans one attempt per selected scenario-strategy pair, subject to explicit max-attempt or attempt-id limits

#### Scenario: Reward sweep preserves comparable controls
- **WHEN** a reward sweep compares strategy profiles
- **THEN** each profile uses the same benchmark fixture, data policy, model fairness settings, tool policy, runtime budget, judge model, and scoring mode unless the sweep manifest explicitly marks a development-only exception

#### Scenario: Reward sweep failures remain attempt outcomes
- **WHEN** a strategy profile attempt fails, times out, or cannot be scored
- **THEN** the runner writes a standard run status and preserves the failure for reward construction rather than silently retrying under another profile

### Requirement: Evaluation runner supports TRL online rollouts
The evaluation pipeline SHALL allow the TRL rollout bridge to launch live strategy-controlled attempts for online policy training while preserving the same provenance guarantees as other evaluation campaigns.

#### Scenario: TRL rollout allocates a standard run bundle
- **WHEN** a TRL online reward request needs execution of a selected strategy
- **THEN** the evaluation runner allocates a standard run bundle under the configured experiment root
- **AND** the run bundle records the TRL run id, policy checkpoint or LoRA adapter id, training step, selected strategy, action validity, and downstream model configuration

#### Scenario: TRL rollout uses explicit cost controls
- **WHEN** the TRL rollout bridge launches geo-agent attempts
- **THEN** it applies configured attempt ids, scenario selectors, wall-clock budgets, and parallel rollout caps
- **AND** remote downstream geo-agent attempts use `deepseek-v4-flash` unless an experiment manifest explicitly records a different model

#### Scenario: TRL rollout failures are trainable outcomes
- **WHEN** an online rollout fails, times out, cannot parse the policy action, or cannot obtain a judge score
- **THEN** the rollout bridge returns a structured reward failure or penalty to TRL
- **AND** the failed attempt remains traceable through run status, logs, and any partial artifacts
