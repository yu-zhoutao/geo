## 1. Strategy Profile Contracts

- [x] 1.1 Define typed strategy profile models, manifest validation, and profile hash generation for bounded strategy ids.
- [x] 1.2 Add initial strategy profiles for `balanced`, `crs_first`, `claim_conservative`, `repair_stop_first`, and `sensitivity_first`.
- [x] 1.3 Implement runtime asset overlay preparation so profiles adjust guidance emphasis without rewriting scenario prompts.
- [x] 1.4 Extend manifest validation tests to reject unknown strategy ids, missing profile assets, and duplicate strategy definitions.

## 2. Strategy-Controlled Evaluation Attempts

- [x] 2.1 Extend planned attempt metadata to carry optional strategy source, strategy id, profile hash, policy run id, and action validity.
- [x] 2.2 Update local-process evaluation execution to apply a selected strategy profile through existing runtime asset preparation.
- [x] 2.3 Update docker-per-attempt request metadata so selected strategy evidence is available inside the attempt container.
- [x] 2.4 Preserve strategy metadata in run manifests, run status, and run-bundle capture outputs.
- [x] 2.5 Extend existing runner and Docker-attempt tests for prompt preservation, profile evidence, failure recording, and isolation behavior.

## 3. Reward Construction And Offline Sweep

- [x] 3.1 Implement versioned reward configuration models with judge-dimension weights and execution-policy penalties.
- [x] 3.2 Implement reward construction from judge score files, run status facts, forbidden move diagnostics, and invalid action records.
- [x] 3.3 Add an offline reward-sweep planner that expands selected scenarios by configured strategy profiles.
- [x] 3.4 Write reward-table artifacts with source run-bundle references, scenario hashes, profile hashes, reward components, and structured failures.
- [x] 3.5 Extend scoring and aggregation tests for reward calculations, failure penalties, reward-table serialization, and reproducibility references.

## 4. RL Task Adapter And Policy-Stub Harness

- [x] 4.1 Add optional RL dependency handling so default app and evaluation imports do not require online training libraries.
- [x] 4.2 Implement a strategy-task adapter that presents safe scenario metadata and registers `select_geospatial_strategy` as the policy action.
- [x] 4.3 Validate policy actions and record invalid, missing, or unsupported function-call outputs without silent repair.
- [x] 4.4 Implement reward lookup from offline tables for training and online evaluation execution for frozen-policy validation.
- [x] 4.5 Add a bounded training/evaluation command path that records policy model identity, checkpoint id, reward config, scenario selector, and run metadata.

## 5. RL Reporting And Thesis Evidence

- [x] 5.1 Export per-attempt RL summaries with strategy metadata, policy metadata, reward components, judge dimensions, and runtime facts.
- [x] 5.2 Export grouped RL summaries by strategy, checkpoint, task family, expected outcome, split, difficulty, and risk category.
- [x] 5.3 Generate a thesis evidence packet that separates offline reward-table results from held-out frozen-policy evaluation results.
- [x] 5.4 Include limitations, failure cases, underperforming groups, and cautious interpretation text in the thesis packet.
- [x] 5.5 Extend existing aggregation/reporting tests to verify grouped summaries and restrained thesis-packet wording.

## 6. End-To-End Validation

- [x] 6.1 Run OpenSpec validation for the change.
- [x] 6.2 Run focused Python tests for manifests, runner planning, reward construction, RL adapter behavior, and reporting.
- [x] 6.3 Run one small reward-sweep smoke campaign over a bounded scenario selector and inspect generated run bundles.
- [x] 6.4 Run one frozen-policy smoke evaluation using offline reward lookup or a minimal policy stub and verify thesis evidence export.

## 7. TRL Online Rollout Integration

- [x] 7.1 Add an optional TRL/Transformers/PEFT/Accelerate dependency boundary so default app, scoring, and non-RL evaluation imports do not require local model training libraries or GPU-only packages.
- [x] 7.2 Implement a TRL-facing prompt/dataset builder that presents safe benchmark observations and asks the local policy model to emit a `select_geospatial_strategy` structured action.
- [x] 7.3 Validate generated function-call actions without silent repair, including malformed JSON, missing function calls, unsupported strategy ids, unsafe payloads, and missing rationales when required by the manifest.
- [x] 7.4 Connect valid actions to the existing evaluation runner so each online training episode launches a fresh strategy-controlled geo-agent attempt and writes a standard run bundle.
- [x] 7.5 Return TRL-compatible custom reward values and diagnostics from fresh run bundles, including reward components, judge score source, runtime penalties, invalid-action penalties, timeout/failure status, and source artifact paths.

## 8. Online Policy Training Harness

- [x] 8.1 Add an online TRL experiment manifest with scenario selector, strategy set, episode cap, parallel rollout cap, wall-clock budget, reward config, algorithm id, policy model id, LoRA settings, checkpoint root, downstream model provider, and output root.
- [x] 8.2 Implement a bounded RLOO training command path that starts the TRL training loop and refuses unbounded runs without explicit episode, total wall-clock, and per-rollout wall-clock limits.
- [x] 8.3 Configure the remote experiment defaults for `/raid/$USER/` storage, `deepseek-v4-flash` downstream geo-agent rollouts, tuna-backed Python dependency installation, ModelScope-backed Qwen model download, and minimal home-directory writes.
- [x] 8.4 Save LoRA adapter checkpoints, rollout records, sampled completions/function calls, training metrics, invalid-action statistics, and policy-update metadata under the experiment output root.
- [x] 8.5 Support a tiny smoke mode with mocked or capped online rollouts before running expensive live geo-agent episodes on the remote GPU machine, and keep long runs alive by retrying failed live rollouts and recording unrecoverable rollout infrastructure errors as explicit zero-reward rows.
- [x] 8.6 Keep GRPO behind an optional algorithm flag for a small ablation only when the rollout budget can support grouped completions.

## 9. Frozen-Policy Online Evaluation

- [x] 9.1 Add a frozen-policy evaluation command that loads a trained base model plus LoRA adapter checkpoint, samples strategy actions on configured evaluation scenarios, and launches fresh app-backed attempts.
- [x] 9.2 Compare base policy, trained checkpoint, fixed-strategy baselines, and offline policy-stub baseline without mixing reward sources.
- [x] 9.3 Preserve model/checkpoint identity, action validity, strategy distribution, downstream model configuration, run bundles, judge files, reward records, and failure cases for every evaluation row.
- [x] 9.4 Run a minimal online matrix over representative scenarios such as `P01`, `C06`, `R04`, and `X01`, with explicit caps if the full matrix is too expensive.

## 10. Online RL Reporting And Validation

- [x] 10.1 Extend RL aggregation exports with TRL online training curves, rollout counts, invalid-action rate, checkpoint summaries, reward trajectories, and source run-bundle links.
- [x] 10.2 Update the thesis evidence packet to distinguish offline reward-table preflight, online TRL/RLOO training, frozen-policy online evaluation, and policy-stub baseline evidence.
- [x] 10.3 Include cautious wording that names the experiment as a lightweight online strategy-controller RL loop, not end-to-end reinforcement learning of the OpenCode-backed geospatial agent.
- [x] 10.4 Extend tests for TRL action validation, manifest validation, reward-source labeling, online rollout failure recording, checkpoint metadata, and reporting boundaries.
- [x] 10.5 Run OpenSpec validation, focused local tests, a mocked/capped online smoke test, and one remote tiny TRL/RLOO online run before treating the updated experiment as thesis evidence.
