## Why

The project title includes "reinforced analysis", but the current system only evaluates fixed agent-runtime variants and has so far demonstrated only an offline reward-table plus policy-stub path. That proves the evidence plumbing, but it does not yet provide a compelling Agentic RL story. A thesis-scoped online RL experiment can make the reinforcement component concrete by training a small language-model strategy controller through live geo-agent rollouts while still avoiding any claim that the main geospatial agent itself is trained end to end.

This update supersedes both the earlier conservative version and the earlier framework-specific draft. The previously implemented strategy profiles, reward construction, and run-bundle reporting remain useful infrastructure, but the target experiment is now a minimal online loop built around Hugging Face TRL with PEFT/LoRA and a project-owned rollout orchestrator. RLOO is the default algorithm because the action is a single structured language-model strategy choice and each live reward is expensive; GRPO remains an optional comparison if the rollout budget allows multiple completions per scenario.

## What Changes

- Add a TRL-backed online strategy-controller experiment where a small local language-model policy selects a bounded geospatial execution strategy before each live benchmark attempt, receives reward from the resulting geo-agent run, and is updated from those online rollouts.
- Represent strategy actions as runtime asset overlays or profiles that adjust agent guidance emphasis, such as CRS-first verification or conservative claim boundaries, without rewriting benchmark prompts or replacing OpenCode's workflow ownership.
- Build reward records from existing judge dimensions, deterministic diagnostic hints, forbidden moves, timeouts, and run-status facts.
- Keep the existing offline reward table as a development preflight and optional baseline, but require the main reported RL result to use online execution rather than lookup-only rewards.
- Integrate TRL through a bounded training harness whose custom reward function validates `select_geospatial_strategy`, launches the existing evaluation runner, scores the fresh run, and returns reward diagnostics for RLOO or optional GRPO updates.
- Export thesis-ready experiment evidence: online rollout records, LoRA policy checkpoints, strategy choices, reward components, score summaries, training curves, online evaluation tables, and failure cases with restrained interpretation guidance.
- Keep end-user app behavior unchanged; this is an experimental evaluation/training harness, not a production feature in the interactive UI.

## Capabilities

### New Capabilities
- `rl-strategy-controller-experiment`: Defines the policy action space, TRL/PEFT training harness, online rollout loop, reward construction, optional offline baseline table, checkpointed policy evaluation, and thesis evidence packet for a concept-proof reinforcement learning strategy controller.

### Modified Capabilities
- `automated-evaluation-runs`: Allow evaluation attempts to be launched under an externally selected strategy profile while preserving unchanged benchmark prompts, run-bundle isolation, and existing campaign provenance.
- `evaluation-results-reporting`: Add online RL experiment summaries that reuse judge dimensions and runtime facts without introducing inflated pass/fail claims or product-style success metrics.

## Impact

- Affected code: `app/evaluation/` runner, manifests, runtime-asset preparation, scoring/report aggregation, RL experiment modules, and a new TRL training harness kept outside the interactive app path.
- Affected assets: strategy profile manifests, TRL experiment configuration, LoRA adapter/checkpoint metadata, experiment manifests, and online rollout summaries.
- Affected tests: existing evaluation-manifest, runner, aggregation, scoring, and RL adapter tests should be extended; smoke validation should include a tiny TRL/RLOO online loop with a mocked or capped rollout path before running the remote GPU experiment.
- Dependencies: TRL, Transformers, PEFT, Accelerate, and local LM training dependencies must remain optional and isolated from the default app install path. The remote experiment should place project files and model/checkpoint outputs under `/raid/$USER/`, install Python packages through the tuna index, fetch Qwen weights through ModelScope into a local model path, use `deepseek-v4-flash` for downstream geo-agent rollouts, and avoid writing large artifacts into home except normal user-local binaries/caches that the user explicitly allowed.
