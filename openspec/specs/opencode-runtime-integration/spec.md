## Purpose
Define the backend-managed OpenCode server lifecycle, config override, auth provisioning, and async HTTP integration used by the application.
## Requirements
### Requirement: Backend-managed OpenCode server lifecycle
The backend SHALL start, monitor, and stop an OpenCode server as an application-owned child process for local geospatial agent sessions.

#### Scenario: Backend starts OpenCode server for app use
- **WHEN** the backend initializes runtime support in a local environment
- **THEN** it starts OpenCode as a backend-owned child process with application-managed working directories and runtime state paths

#### Scenario: Backend shutdown cleans up OpenCode server
- **WHEN** the backend exits or restarts
- **THEN** it terminates the managed OpenCode server and any runtime-owned child processes that belong to that server lifecycle

### Requirement: OpenCode server is bootstrapped with application-owned config
The backend SHALL boot OpenCode in an isolated configuration environment and SHALL generate the runtime's full application-owned config from validated assets under the application's geospatial agent asset tree directly into the backend-managed OpenCode home layout rooted at the app support directory, including the generated `opencode.json`, role-specific skills, runtime knowledge manifest, providers, models, MCP servers, and runtime defaults.

#### Scenario: User-global config is not inherited implicitly
- **WHEN** the backend starts the OpenCode server for the application
- **THEN** runtime directories and startup flags prevent uncontrolled external config, skills, or project-level runtime state from being loaded by default

#### Scenario: Generated runtime config is built from app-owned assets
- **WHEN** the backend prepares the OpenCode runtime for startup
- **THEN** it reads the geospatial agent source assets from the application codebase, validates them, and writes the generated runtime config needed by OpenCode into the managed XDG-style config directory under the app support root rather than into repository-scoped development config files or a duplicate `runtime-config` bundle

#### Scenario: Bundled runtime roles are available without manual setup
- **WHEN** the backend prepares the OpenCode runtime for application use
- **THEN** the bundled orchestrator and specialist-role configuration is available from the managed OpenCode home layout without requiring the user to create agent, skill, or prompt files manually
- **AND** built-in `general` and `explore` subagents are disabled in that managed runtime profile so the application-owned specialist roster remains authoritative
- **AND** built-in code-intelligence tools such as `codesearch` and `lsp` are disabled in that managed runtime profile
- **AND** any runtime-owned skills needed by those roles are generated into the managed `.config/opencode/skills/` tree from the validated app-owned assets instead of the repository's development-time `.opencode` tree
- **AND** the generated role roster is packaged through the application-owned OpenCode config in that same managed home layout instead of a separate generated runtime bundle directory

### Requirement: OpenCode config is tailored to the geo-agent product
The backend SHALL provision an OpenCode config profile that is explicitly tailored to the geo-agent application rather than using a generic coding-agent configuration, and that profile SHALL define an orchestrator-led geospatial agent topology designed to preserve the user's original prompt, dynamically dispatch contract-driven specialist roles, use the backend-hosted geospatial MCP server for context and evidence, and run real geospatial work through the managed bash/Python environment.

#### Scenario: Geo orchestrator is the default runtime entry point
- **WHEN** the backend applies the application-owned OpenCode config
- **THEN** the config defines a default geospatial orchestrator agent plus the supporting specialist agents needed for request triage, study design, data audit, spatial preparation, operator execution, evidence packaging, reporting, and skeptical review behavior.

#### Scenario: Built-in tools are selectively enabled for product fit
- **WHEN** the backend applies the application-owned OpenCode config
- **THEN** built-in tools are enabled or disabled deliberately so OpenCode behaves like a geospatial agent app rather than a broad unrestricted coding shell
- **AND** built-in code-intelligence tools such as `codesearch` and `lsp` are disabled in the managed runtime profile
- **AND** bash access is enabled for the managed local prototype so geospatial agents can run agent-authored Python scripts in the managed workspace
- **AND** backend-hosted geospatial MCP tools are limited to session context discovery and evidence recording rather than hidden GIS workflow execution.

#### Scenario: Runtime config includes contract-driven agent assets and MCP wiring
- **WHEN** the backend applies the application-owned OpenCode config
- **THEN** the config includes contract-driven geospatial agent definitions, role-specific skill packages generated from app-owned assets, and backend-managed MCP server definitions required for context and evidence tool use
- **AND** built-in `general` and `explore` subagents are disabled so the managed runtime exposes the application-owned specialist roster instead of generic fallback subagents
- **AND** those prompts and skills do not require the agent to follow hardcoded workflow scripts, rewritten user prompts, or MCP operator wrappers as its primary execution model.

### Requirement: Runtime asset validation blocks unsafe bootstrap
The backend SHALL fail runtime readiness when required geospatial agent assets are missing or invalid instead of generating a partial runtime config bundle.

#### Scenario: Missing runtime asset blocks readiness
- **WHEN** a required geospatial agent asset file is missing from the application-owned source tree
- **THEN** the backend reports runtime-not-ready with a structured validation error instead of starting a degraded OpenCode session

#### Scenario: Invalid asset references block readiness
- **WHEN** validated agent or skill assets contain invalid references, malformed frontmatter, or missing required sections
- **THEN** the backend reports runtime-not-ready with a structured validation error instead of silently omitting the invalid asset

### Requirement: OpenCode sessions are accessed through async HTTP integration
The backend SHALL use async HTTP integration to create, resume, inspect, and stream OpenCode session activity for browser-facing app flows while preserving the user's original prompt as the session input, and SHALL rely on backend-owned MCP session context rather than injecting auxiliary runtime-context notes into that prompt payload.

#### Scenario: Backend creates runtime session through HTTP API
- **WHEN** a user submits a new geospatial request
- **THEN** the backend creates or resumes an OpenCode session through HTTP APIs rather than through an embedded in-process runtime loop

#### Scenario: Backend forwards the user's prompt unchanged
- **WHEN** a user submits a message to the managed runtime session
- **THEN** the backend forwards that message as the main session input without hidden prompt rewriting or conversion into a preset workflow request format

#### Scenario: Auxiliary geospatial context is not injected into the prompt
- **WHEN** the backend sends a message to the managed runtime session
- **THEN** workspace paths, attached data directories, request snapshots, and similar run-context details are made available through backend-owned MCP session context instead of a secondary helper note appended to the user's prompt

#### Scenario: Backend relays OpenCode session activity to the app shell
- **WHEN** the OpenCode server emits session updates relevant to the active task
- **THEN** the backend consumes them asynchronously and maps them into the app's normalized live-update contract

### Requirement: OpenCode runtime questions pause and resume the active session
The backend SHALL treat OpenCode-native questions as first-class runtime pause points, SHALL normalize them into application question state, and SHALL resume the same managed OpenCode session through OpenCode's question reply HTTP path instead of converting the answer into a replacement prompt or app-authored rerun.

#### Scenario: Streaming runtime question becomes pending app question state
- **WHEN** the managed OpenCode session emits a runtime-native question event for the active session
- **THEN** the backend emits a normalized `session.question` payload with the runtime request ID, the visible prompt, and any ordered question items exposed by the runtime
- **AND** the backend emits `waiting_for_input` session status for that same session
- **AND** the backend does not mark the run completed while that runtime question is still pending

#### Scenario: Polling fallback still finds the pending runtime question
- **WHEN** the backend cannot rely only on the real-time event stream to observe the active session's pending question state
- **THEN** it queries OpenCode's pending-question HTTP surface for that runtime session before finalizing the run
- **AND** any matching runtime question is still emitted as normalized `session.question` state instead of being lost as a transient tool event

#### Scenario: User answer resumes the original runtime session
- **WHEN** the user submits an answer to a pending runtime-native question from the app
- **THEN** the backend posts the ordered answers to OpenCode's question reply endpoint using the original runtime question request ID
- **AND** the backend continues polling or streaming the same managed runtime session ID rather than creating a replacement session
- **AND** subsequent runtime updates continue to flow through the normal normalized session event stream

### Requirement: Runtime question replies preserve existing session evidence
The backend SHALL preserve the existing app-visible session evidence when answering a runtime-native question so a clarification pause does not clear the plan, verification state, or artifacts that already belong to the current run.

#### Scenario: Runtime question answer does not reset session evidence
- **WHEN** a pending question being answered was produced by the managed OpenCode runtime
- **THEN** the backend clears the pending question state itself
- **AND** it keeps the current session plan, verification entries, artifacts, and runtime session reference intact while resuming execution

#### Scenario: Runtime question answer remains distinguishable from a real prompt
- **WHEN** the backend appends a user-visible transcript entry for the runtime question answer
- **THEN** that entry remains visible in the transcript as part of the evidence chain
- **AND** the normalized session metadata still marks it as a question reply rather than a normal prompt-history entry

### Requirement: Provider auth is provisioned by the application
The backend SHALL provision OpenCode provider auth and related runtime credentials from application-managed environment configuration without requiring the end user to author runtime-specific auth files manually.

#### Scenario: OpenCode auth is generated from app secrets
- **WHEN** required provider credentials are present in the environment
- **THEN** the backend writes or injects the OpenCode auth material needed for the configured providers before session execution begins

#### Scenario: Missing provider auth blocks runtime readiness
- **WHEN** required provider credentials are unavailable
- **THEN** the backend reports a structured not-ready runtime state instead of launching a misleading partially configured OpenCode session

### Requirement: Generated runtime config enables managed local execution
The backend SHALL materialize the generated OpenCode config so the managed local prototype can run the documented bash/Python geospatial command in app-owned workspaces while leaving fine-grained per-role permission modeling out of scope for this rewrite.

#### Scenario: Managed prototype can run geospatial scripts
- **WHEN** the backend generates the OpenCode config for geospatial specialists
- **THEN** the managed profile exposes the bash access needed to run `"$GEO_AGENT_UV_BIN" --project "$GEO_AGENT_GEO_PYTHON_PROJECT" run --python "$GEO_AGENT_GEO_PYTHON_VERSION" python <script>` inside the managed workspace.

#### Scenario: Permissions remain prototype-scoped
- **WHEN** the backend writes the generated OpenCode config bundle
- **THEN** it does not attempt to enforce a new fine-grained role permission model beyond the current local trusted prototype boundary.

### Requirement: Runtime receives managed geospatial execution environment
The backend SHALL inject the managed geospatial execution environment into the OpenCode server and session processes so bash and Python subprocesses can access the correct repository, workspace, session context, attached data, and project-managed Python environment without receiving a predefined artifact directory.

#### Scenario: Runtime process receives environment variables
- **WHEN** the backend starts or prepares a managed OpenCode session for geospatial work
- **THEN** the runtime process receives `GEO_AGENT_REPO_ROOT`, `GEO_AGENT_UV_BIN`, `GEO_AGENT_GEO_PYTHON_PROJECT`, `GEO_AGENT_GEO_PYTHON_VERSION`, `UV_PROJECT_ENVIRONMENT`, `GEO_AGENT_WORKSPACE_PATH`, `GEO_AGENT_SESSION_CONTEXT_ID`, and `GEO_AGENT_ATTACHED_DATA_DIRS_JSON`
- **AND** it does not receive `GEO_AGENT_ARTIFACT_DIR`.

#### Scenario: Environment variables avoid prompt rewriting
- **WHEN** the backend forwards the user's prompt into the managed runtime
- **THEN** workspace paths, attached data directories, and Python execution details are provided through environment variables and `get_session_context` instead of hidden helper text appended to the user's prompt.

#### Scenario: Runtime config avoids user-global geospatial state
- **WHEN** the backend prepares the managed runtime environment
- **THEN** it uses application-owned paths and project-managed Python dependencies rather than inheriting uncontrolled user-global GIS package configuration as the source of truth.

#### Scenario: Runtime traces do not occupy the agent workspace
- **WHEN** the backend records OpenCode runtime trace metadata for a session
- **THEN** it stores the trace in application-owned support storage outside the shared workspace
- **AND** it does not create `.opencode`, trace files, or other runtime metadata inside the shared workspace.

### Requirement: OpenCode runtime failures are detected and classified
The Python backend SHALL detect and classify OpenCode startup failures, managed process exits, HTTP API failures, abort failures, and event-stream failures at the backend-managed runtime boundary. The frontend SHALL receive those failures only through the application's normalized session state and SSE events. The managed OpenCode runtime SHALL remain responsible for normal session activity when available, while backend classification SHALL cover cases where OpenCode cannot provide a complete failure report. The local Python geospatial execution layer SHALL remain behind the OpenCode and backend-hosted MCP boundary.

#### Scenario: Startup failure blocks run with structured issue
- **WHEN** the backend cannot start OpenCode or OpenCode exits before becoming healthy
- **THEN** the backend reports the runtime as not ready or stopped
- **AND** any affected session receives a structured runtime issue explaining that OpenCode startup failed
- **AND** the backend does not silently fall back to fake agent progress

#### Scenario: Managed process exits during active run
- **WHEN** the backend detects that the managed OpenCode process has exited while a session run is active
- **THEN** the affected session is marked `failed`
- **AND** a structured `runtime_crash` issue records the process-exit condition and any available runtime session reference
- **AND** partial transcript, todo, tool, and artifact evidence that was already observed remains available

#### Scenario: Managed runtime processes are cleaned up on backend shutdown
- **WHEN** the Python backend lifespan exits because of normal shutdown, application error, or session-service shutdown failure
- **THEN** the backend still attempts to stop the application-managed OpenCode runtime
- **AND** the managed OpenCode server is launched in an isolated process group
- **AND** stopping the runtime terminates that process group so backend-owned OpenCode wrapper or child processes do not remain orphaned

#### Scenario: HTTP integration failure is classified
- **WHEN** an OpenCode HTTP request required for session creation, prompt submission, question reply, status polling, message loading, or abort fails in a way that prevents continued supervision
- **THEN** the backend records a structured runtime connection or runtime error issue for the affected session
- **AND** it keeps the user's original prompt path unchanged

#### Scenario: Streaming failure falls back before failing the run
- **WHEN** the OpenCode global event stream fails or cannot be parsed
- **THEN** the backend first uses the supported polling fallback when that fallback can still supervise the run
- **AND** it records a failure issue only when live supervision cannot continue or the run must be marked failed

#### Scenario: Abort failure does not hide user interruption
- **WHEN** a user requests interruption and the OpenCode abort call fails or times out
- **THEN** the backend still cancels the local active run task when possible
- **AND** it records the interruption outcome and abort failure detail as structured session issue information
- **AND** it does not misclassify deliberate user interruption as normal runtime completion

### Requirement: Runtime failure handling preserves backend-owned boundaries
The browser SHALL NOT call OpenCode runtime internals directly for crash detection, status recovery, or abort handling. All runtime failure handling SHALL remain behind the Python backend's HTTP and SSE surfaces.

#### Scenario: Browser learns runtime failure through backend stream
- **WHEN** OpenCode crashes or becomes unreachable during a session run
- **THEN** the browser learns about the failure through backend session status and issue events
- **AND** no direct browser connection to OpenCode is required

#### Scenario: Runtime restart is explicit and non-replaying
- **WHEN** the backend later restarts or reconnects to OpenCode after a failure
- **THEN** it does not automatically replay the failed user prompt or duplicate geospatial side effects
- **AND** the prior failure remains visible in the original session evidence chain

### Requirement: Backend app shares one OpenCode server instance
The Python backend SHALL wire one application-owned OpenCode runtime client into runtime health, session execution, session interruption, transcript recovery, and shutdown cleanup within a single FastAPI app instance, so the app does not start separate `opencode serve` servers for those responsibilities.

#### Scenario: Health and session execution use the same server
- **WHEN** a FastAPI app instance is created for local demo use
- **THEN** the runtime manager and session service use the same backend-managed OpenCode runtime client
- **AND** health checks and user session runs report against the same managed OpenCode server process group

#### Scenario: App sessions remain runtime sessions, not runtime servers
- **WHEN** the user creates or resumes multiple app sessions
- **THEN** each app session stores a runtime `session_id` reference for the shared OpenCode server
- **AND** the backend does not create a new OpenCode server process group per app session

#### Scenario: Shared runtime cleanup terminates the single managed server
- **WHEN** the backend lifespan exits after sessions have run
- **THEN** active app runs are aborted or cancelled through the shared runtime client
- **AND** shutdown terminates the single managed OpenCode server process group without leaving separate health-owned or session-owned OpenCode servers behind

### Requirement: Geospatial MCP tool metadata is user-facing
The backend-managed runtime integration SHALL attach concise application-owned metadata to geospatial MCP tool calls so the dashboard can render readable labels without changing the user's prompt or the runtime's workflow ownership.

#### Scenario: Base geospatial tools expose concise labels
- **WHEN** OpenCode tool activity for `get_session_context` or `update_todos` is normalized for the app
- **THEN** the metadata label for `get_session_context` is `读取上下文`
- **AND** the metadata label for `update_todos` is `更新执行计划`.

#### Scenario: Evidence label follows record type
- **WHEN** OpenCode tool activity for `record_run_evidence` includes an input `record_type`
- **THEN** the normalized metadata label reflects that record type with a concise user-facing name
- **AND** unsupported or missing record types fall back to a generic evidence label without rejecting otherwise valid runtime messages.

### Requirement: Managed agents are instructed to use relevant geospatial skills
The generated OpenCode runtime config SHALL instruct managed geospatial agents to proactively read and apply relevant bundled professional geospatial skills before method-sensitive work, while preserving OpenCode's runtime ownership of planning and execution.

#### Scenario: Role prompts reference task-relevant skills
- **WHEN** the backend generates role prompts or config for the geospatial orchestrator and specialist agents
- **THEN** each role receives guidance to consult the bundled skills relevant to that role's task before performing method-sensitive geospatial work
- **AND** the guidance points to skills as operational handbooks rather than hidden workflow scripts.

#### Scenario: Skill guidance does not force a fixed workflow
- **WHEN** a user submits a geospatial request
- **THEN** the generated config does not force every skill to run or impose a preset sequence of specialist roles
- **AND** the managed runtime may still interleave planning, data audit, preparation, analysis, reporting, and review dynamically.

#### Scenario: Prompt forwarding remains unchanged
- **WHEN** the backend forwards the user's prompt into the managed runtime
- **THEN** the prompt remains the user's original input
- **AND** skill-use guidance comes from generated agent config, role prompts, and bundled skill assets rather than from hidden per-request prompt rewriting.

### Requirement: Runtime integration exposes skill-use metadata when available
The OpenCode integration SHALL preserve explicit skill-use metadata exposed by the runtime so the app can render it without coupling the browser to runtime internals.

#### Scenario: Skill-use metadata flows through backend stream
- **WHEN** the managed runtime emits explicit skill-use metadata during a session
- **THEN** the backend maps it into the normalized session state and SSE stream
- **AND** the browser receives it only through application backend APIs.

#### Scenario: Skill config alone is not emitted as usage
- **WHEN** the generated OpenCode config includes role-specific skills
- **THEN** the runtime integration does not report those configured skills as used unless the runtime or structured evidence identifies a specific use.

### Requirement: Evaluation campaigns can use variant-specific runtime assets
The backend SHALL support evaluation-mode runtime preparation that materializes or points to variant-specific agent assets, skill availability, model settings, and runtime configuration without mutating the normal interactive app configuration.

#### Scenario: Internal framework variant gets its own runtime definition
- **WHEN** an evaluation campaign runs a variant with different agents, skills, model settings, or runtime-facing overrides
- **THEN** the backend prepares a variant-specific runtime definition for that run instead of editing the default interactive runtime configuration in place

#### Scenario: Repeated runs reuse the pinned variant definition
- **WHEN** a campaign repeats the same scenario for a pinned variant
- **THEN** each attempt uses the same variant-specific runtime definition unless the campaign manifest explicitly changes it

#### Scenario: Variant asset hashes are recorded
- **WHEN** a variant-specific runtime definition is prepared
- **THEN** the run bundle records the agent asset root, generated runtime config path, relevant hashes, and model settings used by the attempt

### Requirement: Runtime provider selection supports DeepSeek without manual provider definitions
The backend SHALL allow evaluation and interactive runtime sessions to select GLM or DeepSeek through environment configuration while relying on OpenCode built-in providers.

#### Scenario: DeepSeek runtime provider is selected by environment
- **WHEN** `GEO_AGENT_MODEL_PROVIDER=deepseek` is configured with `GEO_AGENT_DEEPSEEK_API_KEY` and `GEO_AGENT_DEEPSEEK_MODEL`
- **THEN** the runtime writes OpenCode authentication for the built-in `deepseek` provider and selects the configured DeepSeek model without requiring a hand-authored provider block

#### Scenario: GLM remains the default runtime provider
- **WHEN** no runtime provider override is configured
- **THEN** the runtime continues to use the existing GLM provider and configured GLM model

#### Scenario: Judge model is independent from runtime provider
- **WHEN** a DeepSeek runtime run is scored
- **THEN** the evaluation judge still uses the configured judge provider and model, such as GLM-5.1, rather than automatically inheriting the runtime provider

### Requirement: Evaluation-mode runtime execution preserves backend ownership
The backend SHALL retain ownership of OpenCode server startup, shutdown, health checks, configuration injection, and trace capture for evaluation-mode runs.

#### Scenario: Runner starts app-managed runtime
- **WHEN** a campaign starts an app-backed evaluation run
- **THEN** the app/backend starts or verifies the managed OpenCode runtime through the same lifecycle boundary used by interactive sessions

#### Scenario: Runtime failure is captured in run bundle
- **WHEN** OpenCode startup, health checking, session execution, or trace capture fails during an evaluation attempt
- **THEN** the runner records the runtime status, logs, app-exported session archive when available, trace path when available, and error details in the run bundle

#### Scenario: Provider message errors become app-visible failures
- **WHEN** OpenCode records a model or provider error in message metadata instead of a terminal session status
- **THEN** the app emits a runtime issue and failed session status so evaluation recovery and run-bundle capture can observe the interruption

#### Scenario: Evaluation mode does not inherit uncontrolled global config
- **WHEN** a campaign prepares runtime configuration
- **THEN** the runtime uses application-managed config roots when they are needed and variant assets rather than uncontrolled user-global agent, skill, or MCP configuration, while not copying rebuildable config directories into the run result bundle

### Requirement: Evaluation runner can observe terminal runtime state through app sessions
The app/runtime integration SHALL expose enough session state for the headless runner to determine whether a run completed, failed, blocked for clarification, was interrupted, or timed out.

#### Scenario: Runner observes terminal session state
- **WHEN** an evaluation attempt is running
- **THEN** the runner can poll or stream app session state until it reaches `completed`, `failed`, `waiting_for_input`, interrupted, or timeout status

#### Scenario: Clarification state is visible
- **WHEN** the runtime asks a user question during a scenario attempt
- **THEN** the app exposes the question and session state so the runner can score expected `clarify` behavior or submit a scenario-defined answer

### Requirement: Evaluation-mode execution preserves original prompts
The app/runtime integration SHALL submit evaluation scenario prompts to the main agent flow unchanged except for explicit continuation answers defined by benchmark fixtures.

#### Scenario: Prompt is not rewritten before runtime submission
- **WHEN** the runner posts a scenario prompt to the app
- **THEN** the backend passes that prompt into the runtime session as the user's message without hidden task templates, preset plans, or benchmark-specific workflow scripts

#### Scenario: Variant guidance is supplied through runtime assets
- **WHEN** a campaign needs to change agent behavior for a variant
- **THEN** the change is supplied through variant-specific agents, skills, model settings, or runtime configuration rather than through hidden prompt rewriting

### Requirement: Evaluation-mode runtime execution supports optional adapter baselines
The backend SHALL leave room for adapter-backed external or structural baselines after internal comparisons are implemented, while preserving the same benchmark and scoring pipeline.

#### Scenario: Structural internal baseline runs through evaluation mode
- **WHEN** a campaign includes `single-agent`, `no-skills`, or `no-skeptical-review`
- **THEN** the backend can launch the variant through evaluation-mode runtime preparation and capture traces, artifacts, and scores in the standard run bundle

#### Scenario: Optional external adapter stays isolated
- **WHEN** a later campaign includes an external framework adapter
- **THEN** the adapter's runtime definition and outputs remain isolated from the normal interactive OpenCode configuration and are captured through the standard run-bundle contract

