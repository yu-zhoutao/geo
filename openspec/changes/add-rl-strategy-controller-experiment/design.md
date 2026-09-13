## Context

The repository already has the pieces needed for a thesis-facing reinforcement learning concept proof: versioned geospatial benchmark scenarios, real app-backed evaluation attempts, Docker-per-attempt isolation, dimension-only LLM judge scoring, run bundles, variant overlays, strategy profile metadata, reward records, and a policy-stub smoke path. The first implementation proved the evidence plumbing but did not yet train a language-model policy. What is missing is a narrow online Agentic RL loop that can justify the "reinforced" wording without overstating the project as an end-to-end trained geospatial agent.

This design treats reinforcement learning as a strategy-selection layer around the existing OpenCode-backed multi-agent runtime. A small local language-model policy chooses a bounded execution strategy before each benchmark attempt. The selected strategy changes runtime asset emphasis through evaluation overlays; the user prompt still enters the main agent flow unchanged, OpenCode remains the workflow owner, and geospatial computation still happens through the existing local Python/MCP-backed execution path.

The preferred framework is Hugging Face TRL with PEFT/LoRA. TRL is already shaped around language-model post-training, online generation, custom reward functions, and checkpointed training loops. A project-owned online rollout orchestrator should sit between TRL and the geo-agent evaluation runner: TRL owns policy sampling and update mechanics, while the orchestrator validates function-call actions, launches fresh app-backed attempts, scores the resulting run bundles, and returns scalar rewards plus diagnostics. Prior environment-framing work remains useful background context, but it is not the implementation target for this minimal experiment.

## Goals / Non-Goals

**Goals:**
- Add a concept-proof online Agentic RL experiment that trains a small language-model policy to select geospatial execution strategies for benchmark scenarios.
- Use TRL RLOO as the default online policy update method, with GRPO kept as an optional comparison when the rollout budget allows multiple completions per prompt.
- Use PEFT/LoRA so the experiment can train a local small model on one 8-card RTX 4090 machine without full fine-tuning.
- Reuse existing evaluation campaigns, run bundles, judge dimensions, deterministic scenario hints, and variant-overlay mechanisms.
- Keep offline reward-table generation as preflight, debugging, and baseline evidence, while requiring the main reported RL training loop to collect fresh online rollouts from the current policy.
- Keep RL integration outside the interactive web app path and treat it as an experimental training harness.
- Produce thesis-ready evidence that is useful but restrained: score tables, strategy-choice summaries, reward components, training curves, and failure cases.

**Non-Goals:**
- Do not train or claim to train a general geospatial analysis model or end-to-end multi-agent system.
- Do not reproduce large-scale Agentic RL papers, multi-task benchmark suites, or large-model results.
- Do not replace OpenCode's session, planning, subagent, tool, or trace ownership.
- Do not rewrite benchmark prompts, inject hidden workflow steps, or use canned result scripts.
- Do not require RL dependencies for normal app startup, frontend use, or non-RL evaluation campaigns.
- Do not present RL results as product capabilities unless later evidence supports that expansion.

## Decisions

### Decision: Train a strategy controller rather than a geospatial agent

The policy action is a structured strategy choice such as `balanced`, `crs_first`, `claim_conservative`, `repair_stop_first`, or `sensitivity_first`. Each strategy maps to an evaluation runtime profile or agent asset overlay that changes guidance emphasis while preserving the same user prompt, model budget, tool catalog, and benchmark data.

Why this over end-to-end agent RL?
- Full agent trajectories are slow, expensive, and hard to assign credit across roles, tools, and final reports.
- A strategy controller produces an interpretable action that can be reported in the thesis.
- The existing evaluation runner can score whether the selected strategy helped with CRS safety, claim validity, repair/stop judgment, and overall task success.

Why this over a table-only bandit?
- A table-only controller is simpler but does not provide a real language-model policy update.
- A small model emitting a structured action keeps the experiment recognizably agentic while staying bounded.

### Decision: Use TRL RLOO as the default training framework

RLOO is the default because the environment produces one expensive scalar reward for a policy-generated strategy action. It is simpler than PPO-style training, fits online language-model optimization, and can use a custom reward function that performs real geo-agent rollouts. GRPO remains an optional comparison if the experiment can afford grouped completions per scenario.

The training harness should use PEFT/LoRA by default. Full-model fine-tuning is out of scope for the concept proof and would make storage, runtime, and reproducibility less manageable. The exact small base model remains configurable, but the default should be a small open causal language model that can emit the `select_geospatial_strategy` JSON/function-call form reliably after a short warm-up or instruction template.

### Decision: Let the project orchestrator own expensive online rollouts

TRL should not call app internals directly. A narrow orchestration layer should turn policy completions into validated actions, launch the existing evaluation runner for valid actions, invoke scoring, write standard reward records, and return rewards to TRL. Invalid or unsafe completions receive structured penalties without silent repair.

The orchestrator should still preserve TRL-facing training state: policy model id, LoRA adapter/checkpoint id, batch/step id, prompt, completion/function-call text, validation result, selected strategy, source run bundle, judge score source, reward components, and duration/cost facts.

### Decision: Treat offline reward tables as preflight, not the main RL result

The first implementation created `(scenario_id, strategy_id) -> reward` tables and a policy-stub lookup. Those artifacts remain useful for debugging reward formulas, comparing fixed strategies, and bootstrapping a tiny warm start. They are not sufficient for the updated thesis story.

The updated experiment must collect online training rollouts from the current policy. Each policy update should be traceable to strategy actions sampled by the current or explicitly named policy checkpoint, the resulting live geo-agent run bundles, and the rewards produced from those runs. A frozen-policy online evaluation after training is the main reported evidence. Offline reward-table results can be reported only as a development baseline or ablation.

### Decision: Keep the online RL problem single-action but agentic

The controller takes one action before a downstream multi-turn geo-agent episode. This is closer to an online contextual-bandit-style problem than full multi-step agent RL, but the environment response is a real agentic rollout with tools, artifacts, judge scoring, and failure modes. The thesis should name this precisely as a lightweight online strategy-controller RL loop, not as full end-to-end agent training.

This bounded shape keeps the experiment feasible on one 8-card RTX 4090 machine. The main geo-agent rollouts should use `deepseek-v4-flash` for cost control; the local policy model, LoRA adapters, and training state should live under `/raid/$USER/` on the remote node.

Remote setup should treat network reliability as part of the experiment boundary: Python packages are installed through the Tsinghua tuna index, and Qwen policy-model weights are downloaded through ModelScope into a local `/raid/$USER/geo-agent/models/...` path before training. The training manifest should reference that local path so TRL does not depend on Hugging Face Hub connectivity during the run.

Each online reward rollout should also have its own wall-clock guard. This keeps a single slow agent episode from silently expanding the RL run into an overnight evaluation campaign, while still preserving whatever artifacts, timeout status, judge score, and reward components the bounded attempt produces.

Rollout infrastructure failures should not crash the TRL trainer. The reward bridge should retry a failed live rollout once by default; if all attempts fail because the app API, session polling, scoring, or artifact capture is unavailable, the episode is recorded as `online-rollout-error` with a neutral zero reward and explicit error diagnostics. These rows are training-continuity evidence, not policy-quality evidence, and should be separated in thesis analysis.

### Decision: Build rewards from existing judge dimensions and runtime facts

Reward should be derived from existing judge scores and run facts rather than new opaque success labels. The default reward should emphasize overall task success, method selection, CRS and units, claim validity, repair/stop judgment, execution correctness, and uncertainty/sensitivity. Timeout, invalid strategy calls, unresolved errors, and forbidden moves apply penalties.

This keeps scoring aligned with the current thesis rubric and avoids introducing a new success metric that would be harder to defend.

### Decision: Keep thesis interpretation conservative by design

The RL experiment should emit a thesis packet that names the experiment as a concept proof or preliminary strategy-layer optimization. The packet should include negative or mixed results, failed strategy choices, and limitations such as judge noise, small scenario count, and sensitivity to strategy-profile wording.

The implementation should not generate language that claims general model improvement, universal geospatial reasoning, or production readiness.

## Risks / Trade-offs

- [Strategy profiles become hidden fixed workflows] -> Mitigation: profiles may adjust instruction emphasis but must not prescribe a step graph or rewrite the user prompt.
- [Online rollouts are too slow or expensive] -> Mitigation: use `deepseek-v4-flash`, cap scenario selectors, cap episodes, allow mocked/capped smoke runs, and record costs/durations as first-class evidence.
- [TRL assumes cheap reward functions] -> Mitigation: keep the reward function boundary asynchronous where possible, cache only development preflight results, and set small online episode caps for official runs.
- [Policy completions are malformed early in training] -> Mitigation: validate strictly, penalize invalid actions, record invalid-action rate, and optionally start from an instruction-tuned small model or short supervised warm-up.
- [Reward overfits the judge] -> Mitigation: report held-out frozen-policy results, keep reward components visible, and include failure cases.
- [Training cost grows beyond thesis value] -> Mitigation: start with a tiny online run, use offline tables only as preflight, and keep online training/evaluation bounded by scenario selectors and attempt limits.
- [RL dependencies destabilize the app] -> Mitigation: keep TRL, Transformers, PEFT, Accelerate, and GPU-only packages optional and outside default app/runtime imports.
- [Results are weak or mixed] -> Mitigation: frame the experiment as feasibility evidence and discuss limitations rather than forcing a positive claim.
- [Nested containers complicate execution] -> Mitigation: allow training harnesses to use existing local evaluation paths during development, while official reported attempts can use the current Docker-per-attempt backend if needed.
- [The result is mislabeled as pure online full RL] -> Mitigation: training samples for the main result must be online, while offline lookup artifacts are explicitly labeled as preflight/baseline. The thesis should call the action space single-step and avoid claiming full trajectory optimization.

## Migration Plan

1. Keep the completed strategy profile schemas, manifests, validation, strategy-controlled attempts, reward construction, and offline reward-table exports as foundation.
2. Add optional RL dependency groups for TRL, Transformers, PEFT, Accelerate, and local model serving/training support without affecting normal app imports.
3. Add a TRL-facing dataset/prompt builder and reward-function bridge that exposes safe scenario observations and validates `select_geospatial_strategy` completions.
4. Add an online rollout executor that validates the selected strategy, launches the existing evaluation runner under that strategy, scores the fresh run, writes reward records, and returns TRL-compatible reward diagnostics.
5. Add a bounded RLOO training command path with configurable local policy model, LoRA settings, checkpoint metadata, rollout caps, and cost/time guards. Keep GRPO as an optional algorithm flag.
6. Add frozen-policy online evaluation and RL summary export that distinguish base policy, trained checkpoint, fixed-strategy baselines, offline preflight, online training, and held-out online evaluation.
7. Validate first with mocked/capped online rollouts, then with a tiny remote online run, before running the thesis-scale minimal matrix.

Rollback is straightforward: remove or ignore the RL experiment commands, strategy overlays, and RL summary artifacts. Existing app sessions, default variants, and non-RL campaigns remain unchanged.

## Open Questions

- Which exact small local policy model should be the default for the 8-card 4090 environment?
- Should the first official online run use local-process execution for speed, or Docker-per-attempt execution for stronger isolation?
- How many online episodes are affordable enough for thesis evidence while still showing a real policy update?
- Should GRPO be run as a small ablation, or should the first thesis result stay with RLOO only to preserve rollout budget?
