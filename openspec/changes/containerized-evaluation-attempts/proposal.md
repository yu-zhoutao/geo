## Why

The evaluation runner currently starts the app and OpenCode directly on the host, which leaves filesystem cleanliness and fairness dependent on application/runtime permissions. Containerizing each logical attempt gives the thesis experiments a stronger isolation boundary without changing the app's current OpenCode authorization model.

## What Changes

- Add a Docker-based evaluation execution backend that keeps the existing campaign runner as the single entry point while running each non-deterministic scenario attempt in a fresh short-lived container.
- Add a dedicated evaluation image definition containing the app, evaluation pipeline, OpenCode runtime dependency, bundled agent assets, and geospatial Python environment needed to run a scenario attempt.
- Add a container attempt entrypoint that executes exactly one planned attempt, writes the standard run bundle into `/evaluation-run`, and exits with a machine-readable status.
- Mount only the current attempt run bundle as writable storage and mount the project `data/` directory read-only as `/data`; do not mount the repository, `.env`, sibling run bundles, or the whole campaign root into the attempt container.
- Pass provider credentials and runtime model settings through environment variables instead of mounting secret files.
- Preserve the current local-process runner path as the default and make Docker execution opt-in through runner configuration or CLI flags.
- Keep deterministic GIS reference attempts host-side unless a later change needs to containerize them.

## Capabilities

### New Capabilities
- `containerized-evaluation-attempts`: Defines Docker-per-attempt evaluation execution, mount boundaries, container entrypoint behavior, runner integration, and failure/log capture semantics.

### Modified Capabilities
- None.

## Impact

- Affected code: evaluation runner orchestration, app lifecycle invocation, run-bundle capture flow, campaign CLI, tests around campaign execution, and new Docker build/entrypoint files.
- New dependency: Docker Engine at runtime for the opt-in Docker backend, plus Python Docker SDK for runner-side container control.
- Runtime impact: each non-deterministic attempt runs in its own container with only `/data:ro` and `/evaluation-run:rw` mounted; app state, runtime config, caches, and workspaces are container-local or attempt-local.
- Evaluation output impact: run bundles remain under project-root `evaluation-runs/` and keep the existing archive shape, with additional container metadata and logs for reproducibility.
