## Purpose
Define the backend-managed OpenCode runtime capability, including model-backed session execution, normalized runtime events, backend-hosted geospatial tool access, and traceable session recovery.
## Requirements
### Requirement: Backend-managed real agent sessions
The backend SHALL execute supported geospatial requests through a real backend-managed OpenCode server session using configured models, application-owned runtime config, bundled role definitions, and bundled skills rather than simulating planning, subagent routing, or verification progress inside app-owned session code, and the managed session SHALL remain the owner of prompt interpretation, agent-authored todo evolution, specialist-agent dispatch, reflection behavior, and repair progression for supported tasks.

#### Scenario: Real runtime session starts for a supported request
- **WHEN** a user submits a supported geospatial request from the dashboard
- **THEN** the backend creates or resumes a managed OpenCode session through server APIs
- **AND** the session uses the selected runtime provider, configured model, bundled application-managed agents, skills, and MCP wiring

#### Scenario: Session autonomy is not replaced by backend workflow code
- **WHEN** the managed runtime session begins executing a supported geospatial task
- **THEN** the backend does not synthesize a separate authoritative workflow graph, fixed stage order, or shell-command recipe that dictates the full step sequence outside the runtime session

#### Scenario: Specialist roles can be interleaved dynamically
- **WHEN** the managed runtime determines that a supported task needs planning, data preparation, analysis, visualization, reporting, or reflection work
- **THEN** it may invoke the relevant specialist roles in whatever order fits the observed task state instead of being constrained to a preset role sequence

#### Scenario: No configured model prevents agent execution
- **WHEN** required provider or runtime configuration for the managed OpenCode runtime is missing or invalid
- **THEN** the backend reports a structured not-ready or failed runtime state
- **AND** it does not silently fall back to backend-authored fake agent progress

### Requirement: Runtime events preserve transcript streaming and tool identity
The backend SHALL normalize runtime events into an application session contract that preserves incremental assistant text, stable user-turn visibility, runtime-derived session-title updates, subagent activity, inline MCP tool activity, visible bash/Python execution evidence, explicit agent-authored todo updates, and stable tool identity metadata needed by the dashboard transcript.

#### Scenario: Assistant text deltas remain visible to the transcript
- **WHEN** the managed runtime emits partial assistant content before a turn is complete
- **THEN** the backend preserves those deltas or equivalent incremental updates in the normalized session event stream so the dashboard can render live streaming text.

#### Scenario: Runtime global events preserve token-level text growth
- **WHEN** the managed runtime exposes token-level assistant updates through its real-time event surface before the message snapshot endpoint is complete
- **THEN** the backend consumes that event stream and emits corresponding `session.message_delta` updates instead of collapsing the turn into coarse polling snapshots only.

#### Scenario: Accepted user turns receive authoritative transcript continuity
- **WHEN** the backend accepts a new user prompt or question answer for a managed runtime session
- **THEN** the normalized session contract preserves or promptly echoes the corresponding user turn so the dashboard can keep that submitted message visible before assistant output begins.

#### Scenario: Runtime title updates remain visible to the transcript shell
- **WHEN** the managed runtime exposes a new or updated session title after the session has already been created with a fallback title
- **THEN** the normalized session event stream includes that runtime-derived title update so the frontend can update the visible session name.

#### Scenario: Python script execution remains visible
- **WHEN** the managed runtime runs an agent-authored geospatial Python script through bash
- **THEN** the transcript preserves the command or tool activity needed to inspect the executed script path, command status, and relevant stdout or stderr summary.

#### Scenario: Evidence records do not emit app-authored workflow state
- **WHEN** `get_session_context` or `record_run_evidence` tool results are normalized
- **THEN** the backend preserves their inline tool evidence without emitting app-authored fixed workflow plan updates from those tools.

#### Scenario: Agent-authored todo updates remain explicit
- **WHEN** the managed runtime calls the application-owned `update_todos` MCP tool
- **THEN** the backend preserves that agent-authored todo state for display without synthesizing, reordering, or replacing it with an app-authored workflow plan.

#### Scenario: MCP tool metadata remains visible to the transcript
- **WHEN** the managed runtime emits MCP tool activity during an assistant turn
- **THEN** the normalized session event includes the raw tool name plus shared Chinese-facing tool label and family metadata needed by the frontend to show a distinct icon or fallback icon consistently without inferring identity from command strings.

#### Scenario: Artifact registration updates workspace artifacts without synthetic transcript authorship
- **WHEN** the managed runtime registers a durable artifact through the application evidence tool
- **THEN** the backend updates the session artifact list and evidence context
- **AND** it does not synthesize a separate report-agent transcript message for the artifact because the original tool call and workspace artifact list already preserve that evidence.

#### Scenario: Question answers remain distinguishable from real prompts
- **WHEN** the backend appends a user answer to a runtime clarification question into persisted session messages
- **THEN** the normalized session contract preserves metadata that lets the frontend exclude that answer from composer prompt history without hiding it from the transcript itself.

### Requirement: Runtime-native subagent activity is preserved
The backend SHALL preserve orchestrator and specialist-subagent activity as first-class runtime-derived session events rather than collapsing that activity into generic assistant text or app-owned workflow stages.

#### Scenario: Specialist role dispatch remains visible
- **WHEN** the managed runtime invokes a specialist subagent during a geospatial run
- **THEN** the normalized session event stream preserves the role identity and call lifecycle needed for transcript rendering and trace inspection

#### Scenario: Reflection activity remains visible
- **WHEN** the managed runtime invokes a verifier or reflection subagent before, during, or after other work
- **THEN** the resulting session activity remains visible to the app shell as runtime-derived verification evidence instead of a hidden app-owned validation step

#### Scenario: Running task child sessions remain recoverable
- **WHEN** the managed runtime exposes a still-running task child session id in task metadata before a final task output is available
- **THEN** live streaming and later session recovery can use that child session id to preserve the child agent transcript.

### Requirement: Runtime sessions can call backend-hosted geospatial tools
The managed OpenCode runtime SHALL be able to invoke bundled backend-hosted geospatial MCP tools for session-context discovery, todo publication, and evidence recording, while performing actual geospatial data processing through visible bash commands and agent-authored Python scripts in the managed geospatial environment.

#### Scenario: Agent discovers session context through MCP
- **WHEN** the real agent needs to confirm workspace, attached data scope, environment variables, package readiness, artifact directories, or evidence state before continuing
- **THEN** it can invoke `get_session_context` and receive structured context for the active run.

#### Scenario: Agent executes GIS work through Python scripts
- **WHEN** the real agent reaches a step that requires geospatial computation
- **THEN** it writes or updates a script in the managed workspace and runs it through the documented `"$GEO_AGENT_UV_BIN" --project "$GEO_AGENT_GEO_PYTHON_PROJECT" run --python "$GEO_AGENT_GEO_PYTHON_VERSION" python <script>` command instead of calling a hidden MCP operator workflow.

#### Scenario: Agent records execution evidence through MCP
- **WHEN** a script or command produces a dataset profile, verification result, parameter snapshot, map, table, report, or manifest
- **THEN** the agent can invoke `record_run_evidence` to attach that output to the session evidence ledger.

#### Scenario: Agent publishes current todos through MCP
- **WHEN** the real agent wants the UI sidebar to reflect its current todo list
- **THEN** it can invoke `update_todos` with agent-authored entries instead of using OpenCode's native `todowrite` tool.

#### Scenario: Tool failures remain visible to the app shell
- **WHEN** a backend-hosted MCP tool or bash/Python execution fails during agent execution
- **THEN** the failure is reflected in session state, transcript, and evidence context instead of being hidden behind a generic completion message.

### Requirement: Real runtime sessions remain locally traceable
The system SHALL preserve enough runtime references, workspace evidence, and app-owned supplemental metadata for a completed real OpenCode session to be resumed or inspected later as a full evidence chain.

#### Scenario: Session reload shows real runtime-derived state
- **WHEN** the dashboard reloads a completed or in-progress session that used the real OpenCode runtime
- **THEN** the backend can restore the latest visible session state from runtime-backed evidence plus minimal local metadata

#### Scenario: Runtime trace references remain associated with outputs
- **WHEN** a real OpenCode session generates files or runtime traces during a run
- **THEN** the resulting artifact metadata remains associated with the originating session and workspace

#### Scenario: Artifact paths identify the latest workspace output
- **WHEN** the runtime registers multiple artifact records with the same workspace-relative path
- **THEN** the session artifact list and geospatial context keep only the latest artifact record for that path.

#### Scenario: Evidence chain remains inspectable after completion
- **WHEN** a real OpenCode session completes or terminates early
- **THEN** the system can inspect the preserved messages, todo evolution, subagent activity, tool calls, artifacts, and session metadata for that run

### Requirement: Runtime problems are preserved as structured session issues
The backend SHALL preserve runtime problems as structured session issue records in addition to normal runtime-derived messages, todos, tools, artifacts, and verification evidence. The frontend SHALL consume those records only through the application's backend APIs and SSE stream. The managed OpenCode runtime SHALL remain the source of truth for normal session execution, while the backend MAY persist minimal issue metadata when a failure prevents the runtime from reporting its own state. The local Python geospatial execution layer SHALL surface command or tool failures through visible runtime activity or backend-hosted MCP outputs rather than hidden workflow state.

#### Scenario: Runtime execution exception becomes a failed session issue
- **WHEN** a backend-managed run raises an exception while executing or supervising a real runtime session
- **THEN** the backend records a structured issue with error severity, runtime source, a localized title, concise technical detail, and any known runtime session or trace reference
- **AND** the backend marks the session `failed`
- **AND** the issue is available in the session evidence chain after reload

#### Scenario: User interruption is recorded without becoming a failure
- **WHEN** a user interrupts an active runtime task through the application session API
- **THEN** the backend records an informational interruption issue or notice in the session evidence chain
- **AND** the session returns to a send-ready non-running state when cancellation wins
- **AND** the interruption is not classified as a runtime execution failure

#### Scenario: User interruption unwinds orphaned running state after backend restart
- **WHEN** a backend restart leaves a persisted session marked `running` without an in-memory active run
- **AND** the user interrupts that session through the application session API
- **THEN** the backend attempts to abort the known runtime session when one is recorded
- **AND** the backend records an interruption issue or notice in the session evidence chain
- **AND** the session returns to a send-ready non-running state

#### Scenario: Blocking tool failure remains visible
- **WHEN** a backend-hosted MCP tool, bash command, or local Python execution result reports a failure that blocks the current run or evidence capture
- **THEN** the normalized session contract preserves that failure as transcript-visible tool activity or as a structured session issue
- **AND** the failure detail is not hidden behind a generic completed status

#### Scenario: Resumed sessions do not replay old tool failures
- **WHEN** the user continues an existing runtime session that already contains historical tool calls
- **THEN** the backend tracks previously processed tool parts and does not re-emit their issue, artifact, timeline, or plan side effects as if they were new runtime events
- **AND** only tool results newly produced after the resumed turn can create fresh side-effect events

#### Scenario: Issue records restore with session evidence
- **WHEN** a user reloads or resumes a session that contains runtime issue records
- **THEN** the backend returns those issues with the session state
- **AND** the frontend can reconstruct the corresponding transcript issue blocks without re-reading raw server logs

### Requirement: Session issue updates use the existing live-update contract
The backend SHALL publish issue changes through the existing application SSE session stream rather than introducing a direct browser-to-runtime channel or a separate monitoring transport.

#### Scenario: New backend issue is streamed
- **WHEN** the backend records a new session issue during a live session
- **THEN** it publishes a `session.issue` event for that issue
- **AND** it publishes enough normal session updates for the transcript and session status to remain consistent

#### Scenario: Issue list can be resynchronized
- **WHEN** the frontend reloads an active session or needs to reconcile missed updates
- **THEN** the backend exposes the current issue list as part of the session payload or a `session.issues` update
- **AND** the browser still communicates only with the application backend

### Requirement: Evidence record metadata is preserved for UI routing
The backend SHALL preserve enough typed metadata from backend-hosted geospatial MCP evidence records for the browser to distinguish final artifacts, intermediate artifacts, and non-artifact evidence without replaying tool output text.

#### Scenario: Artifact evidence carries stage and display hint
- **WHEN** `record_run_evidence` records an artifact
- **THEN** the backend emits or stores artifact metadata including `path`, `format`, `artifact_stage`, `display_hint`, `title`, `description`, `kind`, and `evidence_record_id`
- **AND** session artifact state remains deduplicated by artifact path with the newest registration retained.

#### Scenario: Intermediate artifact creates transcript evidence
- **WHEN** the backend receives a registered artifact with `artifact_stage` equal to `intermediate`
- **THEN** it adds a transcript-visible inline artifact block for that intermediate evidence
- **AND** it does not synthesize report-author transcript messages for final artifact registrations
- **AND** the frontend can hide the successful artifact-registration tool row without losing the artifact evidence.

#### Scenario: Non-artifact evidence creates summary events
- **WHEN** `record_run_evidence` records `dataset_profile`, `verification_fact`, `parameter_snapshot`, or `claim_trace`
- **THEN** the backend emits a typed summary event or timeline entry containing the evidence record id, record type, title, description, category, structured `data`, `provenance`, and creation time
- **AND** the event is recoverable from stored session state after a backend restart or session reload, even if the original live timeline event was not observed.

### Requirement: Artifact opening remains backend mediated
The backend SHALL open registered local artifacts only through application session APIs that resolve artifact ids against the managed workspace.

#### Scenario: Opening registered artifact uses system default handler
- **WHEN** the browser requests to open a registered artifact by session id and artifact id
- **THEN** the backend resolves the artifact path inside the session workspace and asks the operating system to open that file with the default handler
- **AND** the browser does not receive direct filesystem-opening responsibility.

#### Scenario: Missing or unsafe artifact paths are rejected
- **WHEN** the requested artifact path is missing, outside the managed workspace, or not registered for the session
- **THEN** the backend rejects the open request with a normal HTTP error
- **AND** it does not attempt to open the path.

### Requirement: Runtime preserves artifact placement metadata
The backend SHALL preserve enough metadata from artifact registration tool calls and artifact records for the dashboard render model to place intermediate artifacts at their source runtime position without replaying side effects.

#### Scenario: Artifact record can match source tool part
- **WHEN** `record_run_evidence` successfully registers an artifact
- **THEN** the normalized session state includes or preserves the evidence record id, tool call id or message-part identity when available, workspace-relative path, artifact stage, display hint, created time, and ordering metadata needed to match the artifact to its source tool part
- **AND** session artifact state remains deduplicated by artifact path with the newest registration retained.

#### Scenario: Backend does not synthesize late intermediate messages
- **WHEN** an intermediate artifact is registered or restored from persisted session state
- **THEN** the backend preserves the raw runtime tool evidence and artifact metadata
- **AND** it does not create an app-authored report-agent message or end-of-transcript synthetic artifact message for that intermediate artifact.

#### Scenario: Replayed historical tool parts do not duplicate artifacts
- **WHEN** a resumed session includes historical artifact-registration tool parts that were already processed
- **THEN** the backend does not re-emit duplicate artifact or evidence side effects for those historical parts
- **AND** the dashboard can still derive the visible artifact row from restored metadata.

### Requirement: Runtime normalizes explicit skill usage evidence
The backend SHALL pass through explicit skill-use metadata from the managed runtime or structured evidence records when that metadata is available, without inventing skill-use events from configured assets.

#### Scenario: Explicit skill metadata is preserved
- **WHEN** OpenCode, a role message, or a structured evidence record identifies that a named bundled skill was used
- **THEN** the normalized session state preserves the skill id or name, display label when available, associated agent, runtime position, and timestamp.

#### Scenario: Missing skill metadata remains absent
- **WHEN** a runtime message was produced by an agent that has skills configured but does not report a specific skill use
- **THEN** the backend does not create a synthetic skill-use event for that message.

### Requirement: Runtime events represent interpolation and hotspot specialists
The backend SHALL preserve runtime-derived activity for interpolation and hotspot specialists in the normalized session stream without collapsing them into generic assistant text or app-authored workflow stages.

#### Scenario: Interpolation specialist activity is visible
- **WHEN** the managed runtime invokes `operator-interpolation`
- **THEN** the normalized session event stream preserves the specialist identity, call lifecycle, transcript position, and resulting evidence records needed for UI rendering and trace inspection.

#### Scenario: Hotspot specialist activity is visible
- **WHEN** the managed runtime invokes `operator-spatial-hotspot`
- **THEN** the normalized session event stream preserves the specialist identity, call lifecycle, transcript position, and resulting evidence records needed for UI rendering and trace inspection.

#### Scenario: Specialist role labels remain task-family aware
- **WHEN** frontend transcript components render the new specialist activity
- **THEN** they can display concise labels that distinguish IDW interpolation work from Gi* statistical hotspot work without parsing free-form assistant prose.

### Requirement: Runtime-normalized tool and script evidence supports new task families
The backend SHALL preserve visible bash, Python, MCP tool, artifact, and issue events for IDW and Gi* runs through the existing session contract.

#### Scenario: IDW script execution is normalized
- **WHEN** the managed runtime runs an agent-authored IDW script
- **THEN** the transcript preserves the command activity, script path, command status, relevant stdout or stderr summary, and generated evidence records.

#### Scenario: Gi* PySAL script execution is normalized
- **WHEN** the managed runtime runs an agent-authored PySAL-backed Gi* script
- **THEN** the transcript preserves the command activity, script path, command status, relevant stdout or stderr summary, and generated evidence records.

#### Scenario: PySAL environment failure remains visible
- **WHEN** a Gi* script or readiness check fails because `esda` or `libpysal` is unavailable
- **THEN** the normalized session contract exposes a structured issue or blocking tool failure instead of a generic completion message.

### Requirement: Artifact metadata routes interpolation and hotspot outputs
The backend SHALL preserve enough typed metadata from evidence records for the frontend to route IDW and Gi* outputs as final artifacts, intermediate artifacts, or non-artifact evidence.

#### Scenario: Interpolation artifacts carry display metadata
- **WHEN** `record_run_evidence` registers an IDW raster, map, table, report, or manifest
- **THEN** the backend preserves artifact stage, display hint, title, description, kind, path, evidence record id, selected operator, and method-specific parameter metadata.

#### Scenario: Hotspot artifacts carry display metadata
- **WHEN** `record_run_evidence` registers a Gi* map, statistic table, report, or manifest
- **THEN** the backend preserves artifact stage, display hint, title, description, kind, path, evidence record id, selected operator, spatial-weight metadata, and significance metadata.

#### Scenario: Non-artifact verification evidence remains recoverable
- **WHEN** interpolation or hotspot runs record dataset profiles, verification facts, parameter snapshots, or claim traces
- **THEN** the backend emits or stores typed summary events that are recoverable after backend restart or session reload.

### Requirement: New task families use existing backend-mediated browser boundaries
The system SHALL keep browser communication for interpolation and hotspot runs behind the application backend and existing SSE stream.

#### Scenario: Live updates use application SSE
- **WHEN** IDW or Gi* runs emit new messages, todos, tool activity, issues, or artifacts
- **THEN** the frontend receives those updates through the application's existing backend SSE contract.

#### Scenario: Artifact opening remains backend mediated
- **WHEN** a user opens an IDW or Gi* artifact from the dashboard
- **THEN** the backend resolves the registered artifact id against the managed workspace and opens it through the existing application session API.

#### Scenario: Runtime internals remain hidden from the browser
- **WHEN** the frontend displays interpolation or hotspot progress
- **THEN** it does not connect directly to OpenCode runtime internals, local filesystem paths, or PySAL execution processes.

### Requirement: Runtime-derived sessions can be archived without replay
The backend SHALL create session archives from runtime-derived evidence through backend session APIs without replaying prompts, reconnecting browser clients to runtime internals, or changing runtime ownership of normal execution.

#### Scenario: Archive export uses backend-owned runtime recovery only
- **WHEN** the backend exports a runtime-backed app session
- **THEN** it may query the managed runtime or local runtime trace storage for recoverable message state
- **AND** it does not submit new prompts, invoke tools, resume subagents, or synthesize new agent work

#### Scenario: Archive preserves normalized tool and subagent evidence
- **WHEN** a runtime-backed session contains assistant text, subagent activity, tool calls, todo updates, evidence records, or structured verification blocks
- **THEN** the exported archive preserves that evidence through the normalized session message and metadata contract used by the dashboard

### Requirement: Imported archive sessions are not runtime sessions
The backend SHALL treat imported archive sessions as inert inspection records rather than OpenCode runtime sessions, even when the archive contains source runtime identifiers.

#### Scenario: Imported session does not reconnect to OpenCode
- **WHEN** a user opens an imported archive session
- **THEN** the backend does not attempt runtime message recovery, runtime status polling, question lookup, or OpenCode session abort for that imported session

#### Scenario: Imported session cannot continue execution
- **WHEN** a user attempts an action that would require runtime execution for an imported session
- **THEN** the backend rejects the action before creating or resuming any managed OpenCode session
