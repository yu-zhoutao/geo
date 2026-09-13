## Context

The current evaluation runner is already the right top-level boundary for thesis experiments: it validates campaign manifests, allocates run bundles, starts the app, submits unchanged benchmark prompts, captures traces and artifacts, scores results, and writes campaign summaries. Its weak point is isolation. In the local-process path, the evaluated app and OpenCode runtime run on the host and can potentially see host filesystem state beyond the intended attempt workspace. Tightening OpenCode permissions would help, but it also risks breaking legitimate geospatial execution because the app, attached data directories, and runtime support paths are not all under a single OpenCode working directory today.

This change keeps the app behavior unchanged and makes isolation an evaluation-runner concern. The existing Python runner remains the single campaign entry point, but an opt-in Docker backend starts one container per non-deterministic attempt. Each container receives only the current attempt run bundle as writable storage and the project `data/` directory as read-only input. The container contains the app, OpenCode, evaluation pipeline, bundled assets, and geospatial Python environment needed to execute exactly one attempt.

## Goals / Non-Goals

**Goals:**
- Preserve the current campaign runner CLI and Python orchestration as the main entry point.
- Add an opt-in Docker-per-attempt execution backend controlled by runner configuration or CLI flags.
- Give every non-deterministic attempt a fresh container filesystem and process tree.
- Mount only `data/` read-only and the current run bundle writable into the attempt container.
- Pass API keys and provider/model settings through environment variables rather than mounted secret files.
- Keep existing run-bundle shape, scoring artifacts, trace capture, and aggregation outputs.
- Record enough container metadata, logs, image identity, and exit status to make failures thesis-debuggable.

**Non-Goals:**
- Do not change the interactive app's OpenCode permission model in this change.
- Do not containerize the frontend or turn the project into a production deployment stack.
- Do not run the entire campaign inside one long-lived container.
- Do not mount the repository, `.env`, sibling run bundles, or the whole campaign root into attempt containers.
- Do not require Docker for the default local-process evaluation path.
- Do not use containers to replace the app/runtime API boundary with fixed workflow scripts.

## Decisions

### Decision: Keep host-side campaign orchestration and containerize only attempts

The existing runner should still initialize campaign directories, snapshot manifests, select attempts, apply resume policy, and run aggregation. For each selected non-deterministic attempt, it should create the attempt bundle directory on the host and then use the Docker SDK to run a single attempt container.

Why this over running the whole campaign inside one container?
- Per-attempt containers give a stronger fairness boundary because previous attempts cannot leave process, cache, or workspace state for later attempts.
- Host-side orchestration can continue to append attempts, resume runs, and aggregate existing bundles without a new container-internal campaign coordinator.
- Debugging remains simple: one container exit maps to one run bundle and one planned attempt.

Why Docker SDK over shelling out to `docker run`?
- The SDK exposes container IDs, image IDs, mount metadata, logs, exit statuses, and cleanup errors as structured data.
- Timeout and cancellation can stop and remove a known container rather than relying on shell process handling.
- Tests can mock Docker client calls without requiring a real daemon.
- On Docker Desktop hosts where the CLI uses a named context socket, the runner can still create an SDK client by resolving the current Docker context endpoint instead of requiring a global `/var/run/docker.sock`.

### Decision: Use a single-attempt container entrypoint

The image should provide a module or console entrypoint that accepts the planned attempt identity and output path, for example variant ID, scenario ID, repeat index, run ID, campaign timing/budget settings, scoring mode, and judge settings. Inside the container, the entrypoint should start the app through the existing evaluation app lifecycle helper, execute the scenario through the existing app API client, capture the run bundle, run scoring, write logs, and exit.

This entrypoint must not become a second campaign runner. It handles one attempt and receives all campaign-level choices from the host runner. Deterministic GIS reference attempts can remain host-side because they do not execute OpenCode and do not benefit much from containerizing the agent runtime boundary.

### Decision: Restrict mounts to `/data:ro` and `/evaluation-run:rw`

The attempt container should mount:
- host project `data/` as `/data` with read-only mode
- the allocated attempt run bundle directory as `/evaluation-run` with read-write mode

It should not mount the repository root, `.env`, the whole `evaluation-runs` tree, the campaign root, Docker socket, user home directory, or OpenCode/user-global config directories. Container-local state paths should be used for app support, metadata database, workspace root, runtime config, cache, and temporary geospatial Python work. Synthetic benchmark dataset packs can be materialized inside `/evaluation-run/dataset-pack`; external benchmark data can be referenced under `/data`.

Why this over mounting the full campaign root?
- A full campaign mount would let an agent inspect sibling variants, previous repeats, judge results, or failure cases.
- A single run bundle mount preserves only the current attempt's evidence.
- Read-only `/data` allows reusable city datasets without allowing the agent to mutate source data.

### Decision: Secrets enter as environment variables only

The host runner should pass a filtered environment to the container, including model provider keys and model selection variables needed by the app and judge. It should not mount `.env` or copy secret files into the run bundle. The run bundle may record non-secret provider metadata, but it must not persist API key values.

### Decision: Image identity and asset identity are evidence

The run bundle should record the Docker image reference, image ID or digest when available, container ID, relevant image labels such as source revision when available, and the container-reported app/benchmark/variant asset hashes. If the image does not contain the requested scenario or variant, the container should fail the attempt with a structured run status rather than falling back to host files.

This keeps container execution reproducible without mounting the repository. When local assets change, the operator should rebuild the evaluation image before running Docker-backed campaigns.

### Decision: Network remains available by default

The container needs outbound network access for GLM or DeepSeek API calls, so the Docker backend should not default to `network_disabled=True`. The file isolation boundary is the main fairness mechanism. If later thesis runs need a deterministic offline smoke test, that can be a separate mode using mocked providers or deterministic references.

### Decision: Container failure is an attempt outcome

If Docker is unavailable, the image is missing, the container cannot start, the app inside the container fails readiness, the attempt times out, or the container exits non-zero, the host runner should write a standard run status with container failure details and logs where available. It should not silently retry with the local-process backend, because that would change the isolation condition for the attempt.

## Risks / Trade-offs

- [Docker adds setup cost] -> Mitigation: keep local-process as default and make Docker backend opt-in; fail with a clear message when Docker SDK or daemon is unavailable.
- [Image assets drift from host manifests] -> Mitigation: record image identity and container-side asset hashes; require rebuilding the image after benchmark or agent-asset edits for official Docker-backed runs.
- [Large image build time] -> Mitigation: layer dependency installation before copying frequently changed app assets, install OpenCode in a separate stage whose `OPENCODE_VERSION` build arg defaults to `latest` and resolves through the release redirect rather than the rate-limited GitHub API, use BuildKit cache mounts for apt/pip/uv/OpenCode downloads, and avoid rebuilding for data changes because `data/` is mounted read-only.
- [Provider APIs still introduce nondeterminism] -> Mitigation: keep model, judge, temperature, prompt, scenario, and data fixed and record provider/model metadata; Docker isolation addresses filesystem/process contamination, not LLM stochasticity.
- [Container cleanup failure leaves stopped containers] -> Mitigation: track container IDs, stop on timeout/cancellation, request removal after completion, and record cleanup errors in the attempt bundle.
- [Mount misconfiguration leaks host state] -> Mitigation: centralize mount construction and test that Docker backend requests only `/data:ro` and one `/evaluation-run:rw` mount.

## Migration Plan

1. Add Docker execution support behind an explicit runner backend option while preserving the existing local-process path.
2. Add the evaluation image definition and single-attempt entrypoint.
3. Add tests for Docker backend planning, mount construction, environment filtering, timeout handling, and failure recording using mocked Docker SDK objects.
4. Build the image locally and run one smoke attempt with `data/` mounted read-only.
5. Compare the resulting run bundle shape with a local-process attempt and adjust only evidence fields needed for container metadata.
6. Use the Docker backend for thesis comparison runs once smoke output is complete and reproducible.

Rollback is straightforward: run the existing local-process backend and ignore the Docker image and Docker-specific runner flags. No existing archive format is removed.

## Open Questions

- Should official thesis runs fail on image revision mismatch by default, or only record the mismatch as evidence?
- Should the Docker backend eventually support custom external benchmark/variant roots through additional read-only mounts, or should official campaigns require image-contained assets?
- Should deterministic GIS reference attempts remain host-side permanently, or should they also be containerized for symmetry once the main path is stable?
