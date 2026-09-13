## Purpose
Define the browser dashboard behavior for creating or resuming OpenCode-backed local agent sessions, sending requests, and viewing live execution state through the application's backend.
## Requirements
### Requirement: Session entry flow
The web application SHALL let a user create or resume an OpenCode-backed local session from the task dashboard, SHALL treat both the no-active-session state and the explicit new-session action as entry into the same local draft flow, and SHALL prefer runtime-derived session titles over app-owned automatic naming once the managed runtime exposes a usable title.

#### Scenario: Dashboard opens in draft mode when no session is active
- **WHEN** a user opens the dashboard and there is no active local session selected
- **THEN** the frontend enters a send-ready local draft state instead of waiting for an explicit session-creation click

#### Scenario: User starts a new session
- **WHEN** a user chooses to start a new session from the dashboard
- **THEN** the frontend enters the same local draft state instead of immediately creating a persisted backend session

#### Scenario: First prompt creates the session
- **WHEN** a user submits the first prompt from the draft state
- **THEN** the frontend creates the backend session, sends the initial prompt, and transitions the UI into the normal active session state

#### Scenario: User resumes an existing session
- **WHEN** a user selects a previously known local session from the dashboard
- **THEN** the frontend loads the latest available session metadata and subscribes to ongoing updates for that session through the backend

#### Scenario: Session title updates from runtime session metadata
- **WHEN** a new session starts with a fallback title and the managed runtime later exposes a session title or title update
- **THEN** the backend emits that runtime-derived title to the dashboard
- **AND** the dashboard updates the visible session title without requiring the user to manually reload the page

### Requirement: Message submission and live updates
The system SHALL let a user send natural-language requests to a session and receive live agent updates over SSE through the backend, including immediate visible user-turn feedback, streaming assistant-message progress, subagent activity, tool execution, explicit agent-authored todo updates, verification or artifact events that reflect the managed runtime session instead of delayed placeholder updates, and backend-mediated interruption results for active runs.

#### Scenario: Dashboard reflects runtime-derived progress
- **WHEN** a long-running geospatial session advances through planning, subagent dispatch, tool execution, clarification, verification, artifact generation, or explicit `update_todos` calls
- **THEN** the dashboard reflects progress derived from OpenCode session activity, agent-authored MCP todo updates, and geospatial context or evidence records rather than backend-authored placeholder stage text.

### Requirement: Transcript role identity stays canonical across live and restored entries
The coding-agent runtime SHALL emit the current canonical geospatial role ids for assistant-side and system-side transcript attribution, the Python backend SHALL preserve those role ids when streaming or reconstructing session evidence, the frontend SHALL render transcript role headers from those canonical ids through an application-managed presentation map, and the local Python geospatial execution layer SHALL introduce no additional alias vocabulary for transcript role identity.

#### Scenario: Live transcript entry uses canonical role identity
- **WHEN** the dashboard renders a live assistant or system-side transcript entry attributed to `geo`, `request-triage`, `study-design`, `data-audit`, `spatial-prep`, `operator-kde`, `evidence-cartography`, `report-synthesizer`, or `skeptical-review`
- **THEN** the transcript shows the corresponding Chinese-facing canonical role title for that roster entry
- **AND** the transcript does not display deprecated aliases such as `planner`, `analysis`, `viz`, `report`, `reflection`, or `data-prep`

#### Scenario: Runtime English ids stay out of reading-facing transcript surfaces
- **WHEN** the dashboard renders a transcript role header or subtask mention for a canonical geospatial role
- **THEN** the primary visible name is the Chinese-facing canonical role title
- **AND** the dashboard does not expose the runtime English id as a second visible name in the normal transcript flow or role popover

#### Scenario: Restored structured transcript blocks use canonical role identity
- **WHEN** the frontend reconstructs todo, question, verification, or artifact transcript blocks from stored session state
- **THEN** those restored blocks are attributed with canonical geospatial role ids before they enter the visible transcript
- **AND** the resulting headers match the same canonical role identity treatment used by live runtime messages

#### Scenario: Runtime question attribution resolves to the canonical originating role
- **WHEN** the dashboard attributes a runtime question card to the assistant role that originated the question
- **THEN** it resolves that card to the originating canonical role identity
- **AND** it does not fall back to a deprecated alias or a generic unlabeled system row

### Requirement: Non-message interaction cards do not expose transcript message actions
The coding-agent runtime MAY emit structured interaction cards such as runtime questions that are part of the transcript but are not ordinary copyable chat messages, the Python backend SHALL preserve that distinction when normalizing question state, the frontend SHALL only attach transcript message actions to actionable message runs, and the local Python geospatial execution layer SHALL not be responsible for transcript action affordances.

#### Scenario: Structured runtime question card keeps normal browser right-click behavior
- **WHEN** the transcript renders a structured runtime question card or another non-message interaction surface with no supported transcript message actions
- **THEN** the dashboard does not intercept the `contextmenu` event for that item
- **AND** it does not display an empty custom action menu for that card

### Requirement: Main pane is a message-first transcript
The dashboard SHALL present the primary interaction area as a flat, message-first transcript resembling a multi-agent group chat, where user messages, agent-authored text, tool execution, todo changes, verification output, artifact announcements, and other owned runtime events are rendered in one globally time-ordered flow rather than as nested child-session containers, where continuous adjacent events from the same visible agent share one transcript run, where only truly unowned technical events remain as centered muted system notices, and where transcript spacing stays compact enough for dense analytic reading.

#### Scenario: User and assistant messages render as markdown
- **WHEN** a conversation contains user prompts and assistant responses
- **THEN** the main pane renders both message types in chronological order with markdown formatting support

#### Scenario: Transcript stays globally ordered across interleaved agent events
- **WHEN** different agents emit visible events that interleave in time
- **THEN** the dashboard renders those events strictly by global event timestamp
- **AND** later output from one agent does not stay grouped ahead of earlier output from another agent just because they belong to different roles or child sessions

#### Scenario: Child-session output is flattened into the shared transcript
- **WHEN** a specialist subagent emits transcript-visible content through a child runtime session
- **THEN** the dashboard flattens that content into the same shared transcript as the orchestrator and other agents
- **AND** it does not render a nested child-session shell as the default notebook presentation

#### Scenario: Continuous same-agent events share one visible header
- **WHEN** adjacent visible events such as text, tool activity, todo updates, verification summaries, or artifact notices all belong to the same visible agent and no other actor interrupts between them
- **THEN** the dashboard renders them as one continuous speaking run
- **AND** that run shows the avatar and role name only once at the start of the run

#### Scenario: Assistant run headers keep a chat-like left avatar layout
- **WHEN** the dashboard renders the first visible item in an assistant-side or system-attributed speaking run
- **THEN** the run header places the role avatar at the left edge of the run in a chat-like layout
- **AND** the role identity remains compact enough that the transcript still reads like a conversation rather than a dashboard card list

#### Scenario: Rich markdown receives transcript-grade typography
- **WHEN** the transcript renders markdown containing headings, lists, blockquotes, inline code, fenced code blocks, tables, links, horizontal rules, or images
- **THEN** the notebook view applies element-specific typography and surface styling for those structures instead of leaving them with near-default browser presentation only
- **AND** that styling remains readable inside both assistant and user message bubbles

#### Scenario: Latest assistant turn stays visible before user-facing text arrives
- **WHEN** the managed runtime has already opened the latest assistant turn for an active run but has only emitted hidden intermediate parts such as empty content, step markers, or reasoning metadata so far
- **THEN** the transcript keeps that latest assistant turn visibly present with a lightweight in-progress placeholder instead of hiding the turn entirely
- **AND** the placeholder is replaced by the real assistant content as soon as visible text, tool output, or structured blocks arrive

#### Scenario: Owned structured events render inside the chat metaphor
- **WHEN** the runtime or backend exposes structured content such as a tool call, todo update, verification entry, dataset preview, table, chart, map, or artifact notice and that content has a clear owning agent
- **THEN** the dashboard renders that content as part of the owning agent's transcript run
- **AND** it does not demote that content to a detached generic technical row by default

#### Scenario: Truly unowned technical events render as centered notices
- **WHEN** the dashboard needs to show a visible runtime or system event that has no defensible owning agent
- **THEN** it renders that item as a centered muted system notice rather than as a left- or right-aligned chat message

#### Scenario: Transcript message actions use a context menu
- **WHEN** the dashboard renders a completed actionable message run with at least one supported transcript action such as copy
- **THEN** it exposes those actions through a right-click context menu on that run
- **AND** it does not require a permanently visible inline copy icon beside the message

#### Scenario: Transcript copy action survives clipboard API rejection
- **WHEN** the user invokes the context-menu copy action for an actionable transcript message and the browser rejects the async clipboard API call
- **THEN** the dashboard falls back to a browser-compatible selection copy path for the same raw message markdown
- **AND** the copy action does not fail with an unhandled UI error

### Requirement: Role identity affordances stay readable and explorable inside the transcript
The dashboard SHALL treat role identity as an interactive part of the transcript, where visible role names remain localized for reading, runtime English ids stay hidden from normal reading surfaces, and readers can inspect a compact role profile without leaving the notebook flow.

#### Scenario: Avatar opens a role profile popover
- **WHEN** the reader clicks a transcript role avatar at the start of a speaking run
- **THEN** the dashboard opens a lightweight role profile popover anchored to that transcript area
- **AND** the popover shows the role avatar, Chinese-facing role title, and a concise role summary

#### Scenario: Profile popover stays within the viewport
- **WHEN** the reader opens a role profile popover from an avatar or subtask mention near the edge of the visible transcript
- **THEN** the dashboard anchors the popover to the right side of the trigger when space allows
- **AND** it clamps the final position so the full card remains within the current viewport

#### Scenario: Profile popover stays lightweight and dismissible
- **WHEN** the dashboard shows a transcript role profile popover
- **THEN** the reader can dismiss it without leaving the current transcript position
- **AND** the interaction does not replace the right sidebar or navigate away from the notebook view

#### Scenario: Empty historical assistant placeholders are not rendered
- **WHEN** the message stream contains non-active assistant messages with no visible content
- **THEN** the transcript does not render those empty assistant placeholders in the notebook flow

#### Scenario: Transcript density stays compact across mixed content
- **WHEN** the transcript renders adjacent user messages, grouped assistant runs, structured evidence blocks, and centered system notices
- **THEN** the layout uses restrained vertical spacing and padding so the main reading flow stays compact instead of introducing large empty gaps between message elements

#### Scenario: Transcript auto-scroll only follows an already-bottomed viewer
- **WHEN** the user is already at or near the bottom of the transcript and new streamed message content arrives
- **THEN** the transcript keeps auto-scrolling to follow the newest content

#### Scenario: Transcript does not interrupt historical reading with forced auto-scroll
- **WHEN** the user has scrolled upward to inspect older transcript content and new streamed message content arrives
- **THEN** the transcript does not force the scroll position back to the bottom until the user returns near the bottom themselves

### Requirement: Subagent activity is first-class transcript content
The dashboard SHALL render orchestrator-led subagent activity through the subagent's own flattened transcript output instead of through nested child-session cards or redundant dispatch-only rows, while still keeping subagent role identity, outputs, and chronology visible as first-class evidence in the shared notebook flow.

#### Scenario: Subagent output appears directly in the shared transcript
- **WHEN** the managed runtime calls a specialist subagent such as `request-triage`, `study-design`, `data-audit`, `spatial-prep`, `operator-kde`, `evidence-cartography`, `report-synthesizer`, or `skeptical-review`
- **THEN** the dashboard renders that specialist's visible output directly in the shared transcript using the specialist's own role identity
- **AND** it does not require a separate nested subagent session panel for the user to read that output

#### Scenario: Subagent handoff line reads like a normal chat bubble
- **WHEN** the dashboard preserves the orchestrator's visible handoff to a specialist subagent inside the shared transcript
- **THEN** it renders that handoff inside the parent role's ordinary chat bubble instead of as a centered system card
- **AND** it keeps the child as a clickable inline `@中文角色名` mention plus the parent-supplied prompt in one sentence-like chat line instead of showing raw task tool output by default
- **AND** the parent-supplied prompt uses the same markdown parser and transcript typography as ordinary assistant messages
- **AND** it omits session-title-like labels such as “Agent 自我介绍” when the prompt itself already carries the useful context
- **AND** the handoff bubble keeps the same cross-agent vertical break rhythm used by ordinary message-to-message transitions

#### Scenario: Subagent mention can open the callee profile
- **WHEN** the reader clicks the child-role mention inside a subagent handoff notice
- **THEN** the dashboard opens the same lightweight role profile popover used by transcript avatars
- **AND** the callee remains the primary visual target of that handoff notice

#### Scenario: Orchestrator dispatch row is omitted when the callee speaks for itself
- **WHEN** the orchestrator hands work to a specialist subagent and the transcript already shows the callee's own visible messages or structured updates
- **THEN** the dashboard may omit a separate “orchestrator called subagent” row from the default transcript
- **AND** the callee's own activity remains the primary evidence of that handoff

#### Scenario: Reflection remains part of the evidence flow
- **WHEN** the runtime invokes `skeptical-review` to verify or challenge intermediate work
- **THEN** the dashboard renders that review activity inline in the same chronological transcript flow rather than treating it as a hidden post-run validator

### Requirement: Tool activity is visually distinct
The dashboard SHALL render tool activity as recognizable agent-attributed transcript content rather than as generic unlabeled system rows, while keeping tool-specific iconography and concise labels available inside the owning agent's transcript run.

#### Scenario: Tool entries inherit the invoking agent attribution
- **WHEN** the transcript renders a tool call or tool result entry for an event that has a clear invoking agent
- **THEN** the entry appears within that agent's visible transcript run
- **AND** the transcript does not present it as an unowned generic system row by default

#### Scenario: Tool entries show distinct icons
- **WHEN** the transcript renders a tool call or tool result entry
- **THEN** the UI shows a distinct icon associated with the tool name or tool family when one is available

#### Scenario: Unmapped tool uses fallback icon
- **WHEN** the transcript renders tool activity for a tool that does not yet have a custom icon mapping
- **THEN** the UI shows a shared fallback tool icon instead of the plain text label `tool`

### Requirement: Right sidebar holds persistent context controls and state
The dashboard SHALL place only persistent global context and lightweight shortcuts in a right sidebar rather than making it the primary destination for intermediate workflow content or session configuration.

#### Scenario: Sidebar shows current task and evidence context
- **WHEN** a geospatial session is active
- **THEN** the right sidebar shows execution or todo summary, registered workspace artifacts, and agent-authored geospatial evidence summary alongside the transcript
- **AND** the geospatial summary is populated from `record_run_evidence` timeline entries rather than legacy application-authored task-state mocks.

#### Scenario: Sidebar keeps execution plan first
- **WHEN** the right sidebar renders a session with execution plan, artifact, and task-summary content
- **THEN** it orders the sections as execution plan, workspace artifacts, then geospatial task summary
- **AND** it does not move the execution plan below artifact or summary content.

#### Scenario: Attached data controls are not owned by the sidebar
- **WHEN** a session has attached data directories configured
- **THEN** the right sidebar does not serve as the primary editing surface for those attachments

#### Scenario: Sidebar does not show app-owned dataset inventory hints
- **WHEN** the dashboard renders the right sidebar
- **THEN** it does not show a static app-owned "available datasets" list

#### Scenario: Intermediate verification stays in the transcript
- **WHEN** the session produces reflection output, intermediate artifacts, or other middle-state evidence
- **THEN** the dashboard keeps that content in the main transcript instead of moving it into the right sidebar by default

### Requirement: Artifact metadata is readable in the dashboard
The web application SHALL present task-specific artifact metadata in a way that keeps generated outputs understandable both inline in the transcript and from the final artifact summary.

#### Scenario: Artifact entries show geospatial run context
- **WHEN** the backend exposes generated artifacts for a geospatial task
- **THEN** the dashboard shows each artifact with at least a title, originating task or operator context, and retrievable file location or access handle

#### Scenario: Artifact entries show reproducibility context
- **WHEN** a real agent-driven KDE run exposes reproducibility records such as a manifest, parameter snapshot, or verification summary
- **THEN** the dashboard presents those entries as readable artifacts rather than treating them as hidden backend-only files

#### Scenario: Intermediate artifacts can appear before final artifact summary
- **WHEN** the session creates a preview image, intermediate table, or draft report before the run is complete
- **THEN** the dashboard can render that artifact inline in the transcript before it appears in any final artifact list

### Requirement: Dashboard styling and localization
The dashboard MUST be localized to Simplified Chinese, support adaptive light and dark modes using a restrained neutral palette, utilize `#0096c3` as the primary interactive accent, and present a refined three-column workbench whose hierarchy comes from spacing, subtle surfaces, and compact status treatments rather than text-heavy chrome.

#### Scenario: User views the dashboard in Chinese
- **WHEN** the dashboard is loaded
- **THEN** all static text, placeholders, and buttons are displayed in Simplified Chinese

#### Scenario: Status labels are localized to Chinese
- **WHEN** the dashboard renders visible status labels for plans, task stages, verification states, or similar UI status badges
- **THEN** those labels are displayed in Simplified Chinese rather than raw English status codes

#### Scenario: Dashboard adapts to system color scheme
- **WHEN** the user's OS is set to light mode
- **THEN** the dashboard uses light neutral backgrounds with dark text and restrained accent color usage
- **WHEN** the user's OS is set to dark mode
- **THEN** the dashboard uses dark neutral backgrounds with light text and the same accent family adapted for contrast

#### Scenario: Primary actions use the school theme color
- **WHEN** primary interactive elements like the New Session button, Send button, active states, or attachment controls are rendered
- **THEN** they utilize the primary theme color `#0096c3` or a perceptually appropriate variant

#### Scenario: Structural hierarchy relies on refined surfaces rather than repeated copy
- **WHEN** the three-column layout is rendered
- **THEN** the UI uses a consistent spacing scale, compact headers, subtle borders, calm surfaces, and shared badge styles to create hierarchy
- **AND** redundant helper text and repeated explanation-heavy labels are minimized across all columns

#### Scenario: Session rows prioritize title over raw metadata
- **WHEN** the session list is rendered
- **THEN** each row emphasizes the session title as the primary label
- **AND** raw session IDs and plain status text are not shown in the row body
- **AND** running sessions use a compact visual activity indicator instead

#### Scenario: Visual separation of user and agent messages
- **WHEN** messages are displayed in the chat workspace
- **THEN** user-submitted messages are aligned to the right side of the chat view
- **AND** agent tool executions and responses remain aligned to the left side

### Requirement: Global branding header
The web application SHALL present a persistent global header across the top of the viewport to establish product identity and backend connectivity status, and SHALL use the official project title as the primary in-app header label.

#### Scenario: User identifies the application and connection state
- **WHEN** the user views the application
- **THEN** a global top header displays the branded app icon, the official project title, and a compact color-coded health indicator showing the backend runtime connection status

#### Scenario: Header title cannot be silently replaced with a nickname
- **WHEN** future redesign work updates header visuals or layout
- **THEN** the primary in-app header title remains the official project title
- **AND** the UI does not silently replace it with a shorter product nickname or alternate label unless the specification is explicitly changed first

### Requirement: Browser document title uses the official project name
The web application SHALL expose the browser document title as `多智能体协作智能地理空间数据强化分析系统`.

#### Scenario: Browser tab title matches the approved project name
- **WHEN** the dashboard document head is rendered
- **THEN** the HTML title is `多智能体协作智能地理空间数据强化分析系统`

### Requirement: Minimal local metadata support
The backend MUST persist only the smallest amount of local metadata needed to support dashboard usability when that information is not already available from OpenCode runtime state.

#### Scenario: Runtime remains source of truth
- **WHEN** session conversation, plan, action, or question data is already exposed by the runtime
- **THEN** the backend does not duplicate that data into a separate app-owned session history store

#### Scenario: App-specific indexes support local UX
- **WHEN** the dashboard needs to list resumable sessions, rename or delete sessions, discover workspace locations, or discover locally generated artifacts after a restart
- **THEN** the backend may use app-owned SQLite metadata for those local UX concerns without taking ownership of runtime-native history

### Requirement: Session lifecycle actions are available in the dashboard
The dashboard SHALL allow the user to rename and delete sessions through app-owned backend endpoints.

#### Scenario: User renames a session from the dashboard
- **WHEN** the user edits a session title from the session list or active session controls
- **THEN** the frontend sends the rename request to the backend and updates the displayed title when the backend confirms the change

#### Scenario: User deletes a session with in-app confirmation
- **WHEN** the user initiates deletion from the session list or active session controls
- **THEN** the dashboard first shows an in-app confirmation modal and removes the session from the normal active-session view only after backend confirmation

#### Scenario: Session actions use compact action menus
- **WHEN** the user needs lifecycle actions for a session from the list or active session header
- **THEN** the dashboard exposes those actions from a compact trailing action menu rather than persistent text buttons

### Requirement: Session sidebar supports confirmed batch deletion
The dashboard SHALL let the user enter a compact batch-selection mode from the session sidebar and delete multiple selected sessions only after explicit confirmation.

Frontend responsibilities: the Vue app SHALL own batch-mode state, selected session ids, confirmation state, and post-delete UI reconciliation; the session sidebar SHALL render mode-specific controls and emit user intent without owning deletion side effects.

Python backend responsibilities: the backend SHALL continue to expose browser-facing session deletion through the application HTTP API; batch deletion MAY reuse the existing single-session delete endpoint for each selected session.

Runtime responsibilities: the OpenCode runtime SHALL remain the source of truth for session execution evidence, while this feature only changes local session navigation and cleanup affordances.

Local Python geospatial execution responsibilities: no new geospatial operator, MCP capability, CRS handling, or artifact-generation behavior is introduced by this feature.

#### Scenario: User enters batch mode
- **WHEN** the user activates the multi-select icon button before the new-session button
- **THEN** the session sidebar enters batch-selection mode
- **AND** the multi-select button becomes a cancel-batch icon button
- **AND** the new-session button becomes a destructive delete-selected icon button

#### Scenario: Batch mode replaces row menus with custom checkboxes
- **WHEN** the session sidebar is in batch-selection mode
- **THEN** each session row replaces its trailing context-menu button with a custom styled checkbox
- **AND** the checkbox communicates selected and unselected states without relying on the browser's stock checkbox styling

#### Scenario: User selects sessions
- **WHEN** the user clicks a session row or its checkbox while batch-selection mode is active
- **THEN** that session's selected state toggles
- **AND** the row does not resume the session

#### Scenario: User selects or clears all sessions
- **WHEN** the user activates the select-all icon button while batch-selection mode is active
- **THEN** all visible sessions become selected
- **AND** the select-all icon button changes to a clear-all affordance
- **WHEN** the user activates that clear-all affordance
- **THEN** all visible session selections are cleared
- **AND** the delete-selected icon button is disabled until at least one session is selected

#### Scenario: User cancels batch mode
- **WHEN** the user activates the cancel-batch icon button
- **THEN** the sidebar exits batch-selection mode
- **AND** all pending batch selections are cleared
- **AND** the header returns to the normal multi-select and new-session icon buttons

#### Scenario: Delete selected requires confirmation
- **WHEN** the user activates the delete-selected icon button with one or more sessions selected
- **THEN** the dashboard opens a confirmation dialog that describes the selected deletion scope
- **AND** no selected session is deleted until the user confirms the dialog

#### Scenario: Confirmed batch delete removes selected sessions
- **WHEN** the user confirms batch deletion
- **THEN** the dashboard deletes each selected session through the application-managed session API
- **AND** successfully deleted sessions are removed from the sidebar
- **AND** batch-selection mode exits after the confirmed operation completes successfully

#### Scenario: Active session deleted in batch
- **WHEN** the currently active session is included in a confirmed batch deletion
- **THEN** the dashboard clears the active session
- **AND** the composer returns to the local draft state
- **AND** the active session event stream is closed

#### Scenario: Normal session actions remain unchanged
- **WHEN** the sidebar is not in batch-selection mode
- **THEN** clicking a session row resumes that session
- **AND** each row keeps its context menu for rename and single-session delete actions

#### Scenario: Session list stays compact
- **WHEN** the sidebar renders session rows
- **THEN** the list uses a middle-density row shape with reduced row gutters, moderate vertical padding, and tight title-to-action spacing
- **AND** icon controls keep stable square hit areas with accessible labels or titles

#### Scenario: Normal and batch rows share one footprint
- **WHEN** the user switches between normal session navigation and batch-selection mode
- **THEN** session rows keep the same padding, gutter, radius, and trailing action-slot dimensions
- **AND** replacing the row menu with a checkbox does not make the list visually collapse or expand

### Requirement: Composer supports contextual session actions
The dashboard SHALL treat the composer as the primary control surface for the active or draft session, SHALL derive its primary action from the backend-managed runtime task state, and SHALL host lightweight contextual actions near the message input, including reversible attachment chips for currently attached directories.

#### Scenario: Composer shows attachment action and active context chips
- **WHEN** the dashboard renders the draft or active-session composer
- **THEN** it shows an attachment action near the input surface
- **AND** any currently attached data directories appear as compact contextual chips near the composer instead of in the right sidebar

#### Scenario: Attached directory chips expose direct actions
- **WHEN** the composer shows currently attached data directories
- **THEN** each chip exposes lightweight actions to remove that attachment and to open the corresponding local directory

#### Scenario: Composer input stays compact by default
- **WHEN** the dashboard renders the composer input field
- **THEN** the input defaults to a compact single-line height
- **AND** it expands up to roughly three lines as content grows
- **AND** additional overflow scrolls inside the input instead of expanding the entire composer indefinitely

#### Scenario: Send action is shown when the session is not running
- **WHEN** the active session is in a send-ready state such as `idle`, `waiting_for_input`, `completed`, or `failed`
- **THEN** the composer shows its normal send action
- **AND** submitting a non-empty draft sends user text through the existing session message flow

#### Scenario: Interrupt action replaces send while a run is active
- **WHEN** the backend reports the active session status as `running`
- **THEN** the composer replaces the send action with an interrupt-task action
- **AND** that interrupt action remains available even when the current draft input is empty

#### Scenario: Composer returns to send state after the run stops
- **WHEN** the backend later reports that the active session is no longer `running`
- **THEN** the composer restores the normal send action without a page reload
- **AND** any unsent draft text remains available for the user to continue editing or send next

#### Scenario: Composer supports message-history arrow shortcuts
- **WHEN** the composer input is focused and the user presses `ArrowUp` or `ArrowDown` while not selecting text and while the caret is at the relevant text boundary
- **THEN** the composer cycles through recent user-submitted messages from the current session instead of inserting a literal newline or doing nothing
- **AND** moving past the newest stored entry restores the current unsent draft text

#### Scenario: Composer history survives remounts and new draft entry
- **WHEN** the user has previously submitted prompts and later returns to a fresh draft composer or a remounted chat input
- **THEN** `ArrowUp` and `ArrowDown` can still recall those recent prompts from persisted local history
- **AND** current-session prompts remain higher priority than older persisted prompts when both exist

#### Scenario: Question replies do not pollute prompt history
- **WHEN** the user submits a reply to an active runtime clarification question
- **THEN** that reply does not enter composer prompt history for `ArrowUp` and `ArrowDown`
- **AND** later prompt recall continues to prioritize real task prompts instead of short clarification answers

#### Scenario: Composer includes workspace shortcut when available
- **WHEN** a workspace directory is known for the active session
- **THEN** the composer action row includes a visible workspace shortcut
- **AND** that shortcut does not require a dedicated right-sidebar section

#### Scenario: Composer stays neutral while a runtime question is pending
- **WHEN** the runtime is waiting for a user answer to an agent question
- **THEN** the composer remains visible as the normal session input surface
- **AND** it does not duplicate the structured runtime question card inside the composer region
- **AND** it blocks normal prompt submission until the pending runtime question has been answered or cleared

### Requirement: Runtime questions render as structured human-in-the-loop notebook content
The dashboard SHALL render active runtime questions as structured human-in-the-loop content inline in the transcript, using the backend's normalized question state rather than exposing the interaction only as a generic tool row or detached alert.

#### Scenario: Transcript shows inline structured runtime question card
- **WHEN** the active session is waiting for a runtime question that includes one or more ordered prompts or suggested options
- **THEN** the transcript shows a structured question card at the question's chronological position with the visible prompt, ordered question items, suggested answer options, editable answer fields, and dedicated reply affordances
- **AND** the user can answer each question item in order without leaving the normal notebook workspace

#### Scenario: Transcript shows structured runtime question content
- **WHEN** the transcript contains a runtime question message or question part for the current evidence flow
- **THEN** the dashboard renders that question as a typed structured question block with readable prompt text and visible suggested options
- **AND** the question remains part of the chronological transcript instead of being moved into a sidebar-only control

#### Scenario: Duplicate raw question tool row is hidden by default
- **WHEN** the runtime also emits raw tool activity for the built-in `question` tool during the same turn
- **THEN** the dashboard hides that duplicate raw question tool block from the default inline tool rendering
- **AND** the structured question block remains the user-facing representation of the pending question

#### Scenario: Historical runtime question collapses to answered summary content
- **WHEN** a runtime question has already been answered and remains visible in transcript history
- **THEN** the dashboard keeps a compact structured summary at that original transcript position
- **AND** each answered item shows only the final prompt text and submitted answer instead of re-rendering every unselected option

### Requirement: Composer submission respects IME composition state
The dashboard SHALL prevent composer-driven keyboard submission from firing while Chinese or other IME composition is still active for normal messages or runtime question replies.

#### Scenario: Main composer Enter does not submit during IME composition
- **WHEN** the user is still composing text with an IME in the main message composer and presses Enter
- **THEN** the dashboard does not submit the message yet
- **AND** the input remains focused so the composition can be committed normally first

#### Scenario: Question reply keyboard submit does not fire during IME composition
- **WHEN** the user is still composing text with an IME in a runtime question reply entry surface and triggers the submit key path
- **THEN** the dashboard does not send the question answer yet
- **AND** submission waits until composition has ended and the user submits again

### Requirement: Narrow-screen layout preserves transcript primacy
The dashboard SHALL preserve the transcript as the primary workspace on narrow screens by collapsing sidebars into on-demand panels instead of forcing the desktop three-column layout to remain fully visible.

#### Scenario: Left and right rails collapse on narrow screens
- **WHEN** the viewport becomes too narrow to comfortably display the desktop three-column layout
- **THEN** session navigation and sidebar context move into drawers, overlays, or equivalent on-demand panels
- **AND** the transcript and composer remain the primary visible workspace

### Requirement: Sidebar execution plan uses agent-owned plan groups
The dashboard SHALL render the right-sidebar execution-plan summary from agent-owned `Session.plan_groups` entries produced by `update_todos`, and SHALL NOT fabricate fixed geospatial workflow steps from MCP tool calls.

#### Scenario: Single agent plan appears without tabs
- **WHEN** exactly one agent has published a plan group
- **THEN** the sidebar execution-plan summary displays that group's entries without role tabs

#### Scenario: Multiple agent plans appear as tabs
- **WHEN** more than one agent has published a plan group
- **THEN** the sidebar displays role tabs using the existing agent identity labels
- **AND** switching tabs changes the visible entries without merging or rewriting different agents' plans.

#### Scenario: Native todowrite is not authoritative
- **WHEN** restored or stale transcript messages contain `todowrite` tool parts
- **THEN** the sidebar ignores those native todo parts and displays only agent-owned plan groups produced by `update_todos`.

#### Scenario: Restored update_todos messages rebuild grouped plans
- **WHEN** a completed runtime session is reloaded or recovered from OpenCode messages that contain successful `update_todos` tool calls
- **THEN** the backend rebuilds `Session.plan_groups` from those successful tool-call inputs
- **AND** it ignores in-progress, malformed, failed, or error-producing todo tool calls so the sidebar does not show empty or fabricated plan groups.

#### Scenario: Empty plan stays unobtrusive
- **WHEN** no agent-owned plan group exists yet
- **THEN** the sidebar keeps the execution-plan section empty or minimal rather than fabricating placeholder steps.

#### Scenario: Legacy plan remains visible when no grouped plan exists
- **WHEN** an older saved session contains `Session.plan` entries but no `Session.plan_groups`
- **THEN** the sidebar renders those legacy entries without creating fake agent tabs.

#### Scenario: Restored plans do not fabricate transcript messages
- **WHEN** a saved session contains `Session.plan` entries or recovered `Session.plan_groups`
- **THEN** the dashboard renders those entries through the execution-plan sidebar
- **AND** it does not synthesize transcript todo messages from saved plan state.

### Requirement: Dashboard displays evidence-ledger artifacts by stage
The dashboard SHALL surface only artifacts explicitly submitted through geospatial evidence records, using explicit file format, display hint, artifact stage metadata, and workspace-relative file references rather than requiring the user to locate files manually in the workspace or relying on application-created workspace subdirectories.

#### Scenario: Intermediate artifact appears as execution evidence
- **WHEN** `record_run_evidence` registers an artifact with `artifact_stage` set to `intermediate`
- **THEN** the dashboard can render it inline with the owning agent's transcript or in an intermediate evidence area
- **AND** the artifact remains linked to its evidence record, command provenance, and normalized workspace-relative source file path.

#### Scenario: Final artifact appears in final artifact surfaces
- **WHEN** `record_run_evidence` registers an artifact with `artifact_stage` set to `final`
- **THEN** the dashboard promotes it to final-artifact surfaces such as the right sidebar or final answer artifact group
- **AND** the transcript still preserves the evidence event that registered the artifact.

#### Scenario: Restored final artifacts do not fabricate agent messages
- **WHEN** a saved session contains final evidence artifacts but no corresponding inline artifact message part
- **THEN** the dashboard renders those artifacts in the global artifact surfaces such as the right sidebar
- **AND** it does not synthesize transcript messages or assign those final artifacts to an inferred agent role.

#### Scenario: Display hint chooses the safest renderer
- **WHEN** an evidence artifact includes `display_hint`
- **THEN** the dashboard uses supported renderers such as image, map, table, markdown, json, text, html, or download
- **AND** unsupported or unsafe previews fall back to a download entry with technical details preserved.

#### Scenario: Unregistered workspace files are not displayed as artifacts
- **WHEN** an agent writes files into the shared workspace but does not register them through `record_run_evidence`
- **THEN** the dashboard does not automatically list, promote, or preview those files as session artifacts.

### Requirement: Dashboard blocks geospatial runs during environment provisioning
The dashboard SHALL present blocking geospatial environment provisioning as a centered non-dismissible modal runtime state with progress and logs, so the user can see first-run installation status before any geospatial session depends on the environment.

#### Scenario: Provisioning state is non-dismissible
- **WHEN** the backend reports that the managed geospatial Python environment is provisioning
- **THEN** the dashboard shows a centered modal dialog with a blurred backdrop that cannot be click-dismissed
- **AND** geospatial run submission controls remain disabled until provisioning succeeds or fails.
- **AND** the modal automatically disappears when the backend reports the environment is ready.

#### Scenario: Provisioning shows progress and logs
- **WHEN** bundled-uv provisioning emits status, progress, or log output
- **THEN** the dashboard updates a phase-estimated progress bar and real-time log display without requiring a manual refresh.
- **AND** the backend remains responsive while provisioning is still running.
- **AND** the log display automatically scrolls to the newest line only when log content changes, not when only status or progress metadata changes.

#### Scenario: Provisioning failure is actionable
- **WHEN** environment provisioning fails
- **THEN** the dashboard keeps the failed state visible with the captured logs and backend failure reason
- **AND** error log lines are visually highlighted in red
- **AND** it does not start a misleading partially configured geospatial session.

### Requirement: Runtime issues render inline in the information stream
The dashboard SHALL render backend-provided runtime issue records as localized inline information-stream content in the main transcript area. The frontend SHALL not add dedicated failed-session affordances to the left session list or right status sidebar for this change. The Python backend SHALL provide issue records through application-owned session payloads and SSE events. The managed OpenCode runtime and local Python geospatial execution layer SHALL provide normal messages, tools, artifacts, and command evidence that the backend can normalize into those records when needed.

#### Scenario: Backend runtime error appears in transcript
- **WHEN** the frontend receives a backend-provided runtime issue for the active session
- **THEN** the main information stream shows a clear localized issue block with title, severity, source, and concise detail
- **AND** the issue block appears in chronological context with the surrounding session messages or system notices

#### Scenario: Restored failed session shows the recorded issue
- **WHEN** a user resumes or reloads a session that previously failed
- **THEN** the transcript reconstructs the recorded issue block from session data
- **AND** the user can understand what error occurred without reading server logs or inspecting the right sidebar

#### Scenario: User interruption appears as non-error notice
- **WHEN** a user interrupts an active task and the backend records the interruption
- **THEN** the information stream shows a neutral or informational notice that the task was interrupted
- **AND** the composer returns to its normal send state when backend session status is no longer `running`

#### Scenario: Frontend SSE disconnect appears as local connection notice
- **WHEN** the browser loses the session SSE connection
- **THEN** the active information stream shows a localized connection notice explaining that live updates disconnected
- **AND** the frontend does not mark the backend session as failed solely because the browser connection dropped

#### Scenario: Session list and right sidebar remain unchanged
- **WHEN** a session contains runtime issue records or reaches `failed` status
- **THEN** the left session list does not need a new failed-session icon, badge, or error summary for this change
- **AND** the right sidebar does not need a new recent-issues panel, trace shortcut, or failure dashboard for this change

### Requirement: Composer state remains aligned with backend session status
The dashboard SHALL keep composer send, waiting, and interrupt behavior driven by backend session status rather than by local issue rendering.

#### Scenario: Failed session is send-ready after failure is recorded
- **WHEN** the backend reports a session status of `failed` after recording a runtime issue
- **THEN** the composer shows the normal send action rather than the interrupt action
- **AND** the user can send a follow-up instruction in the same session

#### Scenario: Issue rendering does not imply running state
- **WHEN** the frontend renders an issue block for an active session
- **THEN** it does not infer that the task is still running from the presence of that issue alone
- **AND** it follows the latest backend `session.status` update for running or send-ready controls

#### Scenario: Issue messages render as compact inline notices
- **WHEN** the frontend renders a session issue in the transcript
- **THEN** it shows the severity and specific detail as a single-line inline notice
- **AND** it does not render the issue as a nested card, panel, or multi-line alert block
- **AND** the notice is centered within the same maximum transcript width used by normal messages

### Requirement: Evidence-aware artifact presentation
The dashboard SHALL route registered geospatial evidence artifacts according to their declared artifact stage, previewability, and display hint while keeping final deliverables easy to open from persistent output surfaces.

#### Scenario: Final artifacts appear in persistent output surfaces
- **WHEN** a session has one or more registered artifacts whose `artifact_stage` is `final`
- **THEN** the dashboard shows those artifacts in the right sidebar workspace-artifact section
- **AND** the main message area shows those artifacts as the final item inside the transcript flow, after all current messages and before the composer padding
- **AND** new transcript messages appear above that final artifact carousel
- **AND** the carousel is horizontally scrollable and centers its cards when there are too few cards to fill the available width
- **AND** each final artifact exposes an independent open action that goes through the application backend
- **AND** final artifact cards do not replace or duplicate their original runtime tool rows inline.

#### Scenario: Intermediate artifacts replace their registration row
- **WHEN** a successful `record_run_evidence` tool call registers an artifact whose `artifact_stage` is `intermediate`
- **THEN** the dashboard renders that artifact inline in the main transcript at the original message-part position of that successful tool call
- **AND** the inline artifact block replaces the successful artifact-registration tool row because the artifact block is the user-facing representation
- **AND** the inline block has a bounded maximum height with internal scrolling when needed
- **AND** the dashboard does not append a synthetic intermediate artifact message elsewhere in the transcript.

#### Scenario: Ambiguous intermediate artifacts keep runtime evidence
- **WHEN** a stored intermediate artifact cannot be confidently matched to a successful source tool call after reload or recovery
- **THEN** the dashboard keeps the original runtime tool evidence visible
- **AND** it does not backfill a separate inline artifact message at the current end of the transcript.

#### Scenario: Previewable artifact hints are human-readable
- **WHEN** an artifact has a human-readable preview hint such as image, HTML, Markdown, text, or table
- **THEN** the dashboard can offer an explicit in-app preview action for that artifact
- **AND** the preview area is bounded and scrolls internally when content exceeds its maximum height.

#### Scenario: Other artifact formats are open-only
- **WHEN** an artifact is JSON, GeoTIFF, GeoPackage, shapefile-related data, archive, raster, binary, or another non-human-readable format
- **THEN** the dashboard treats it as an `other` or open-only artifact
- **AND** it does not attempt to render its content as an in-app preview.

#### Scenario: Artifact paths identify the latest visible artifact
- **WHEN** multiple artifact registrations use the same workspace-relative artifact path
- **THEN** the dashboard keeps the newest registration for that path in persistent output surfaces
- **AND** duplicate final artifact cards are not shown in the sidebar or bottom carousel.

#### Scenario: Follow-up runs preserve prior final artifacts
- **WHEN** a user sends a follow-up message in a session that already has registered final artifacts
- **THEN** starting the new run does not clear the existing final artifacts from session state or geospatial context
- **AND** newly registered artifacts are merged with the previous artifacts using the same path-based newest-registration rule.

### Requirement: Evidence timeline summary
The dashboard SHALL use non-artifact geospatial evidence records as compact task-summary events instead of hiding them behind generic tool execution rows.

#### Scenario: Non-artifact evidence records populate task summary timeline
- **WHEN** the runtime records `dataset_profile`, `verification_fact`, `parameter_snapshot`, or `claim_trace` evidence
- **THEN** the right sidebar task-summary area shows a compact newest-first card with the evidence title, type, and short description when present
- **AND** evidence cards use the same compact card shell, border, shadow, and title-row tag placement as execution-plan and workspace-artifact cards
- **AND** each evidence card with structured data can expand in place to show that structured data directly, without extra record, timestamp, label, or provenance rows
- **AND** the item does not duplicate final artifact cards
- **AND** previously stored evidence records are restored into the task-summary timeline when a session is reloaded.

### Requirement: Responsive notebook shell remains scrollable
The dashboard SHALL keep the central transcript scrollable and full-height across desktop and narrow viewports while sidebars open and close with lightweight transitions.

#### Scenario: Narrow side panels animate without stealing transcript scroll
- **WHEN** the viewport is narrow and the user opens the session list or context sidebar
- **THEN** the panel slides or fades over the app without changing the transcript scroll container
- **AND** closing the panel restores the same main view height and scroll behavior.

#### Scenario: Empty and active sessions use the full available height
- **WHEN** the dashboard shows a draft session, an empty session, or a long active transcript
- **THEN** the main workspace fills the viewport height below the app header
- **AND** the transcript scroller, not the document body, owns overflow for message content.

### Requirement: Custom tool display names stay concise
The dashboard SHALL display concise, user-facing names for application-owned geospatial MCP tool calls and SHALL derive evidence tool names from the tool input record type when available.

#### Scenario: Context and todo tools use concise names
- **WHEN** the transcript renders `get_session_context`
- **THEN** its visible tool title is `读取上下文`
- **WHEN** the transcript renders `update_todos` or OpenCode-native todo updates normalized into the app-visible todo surface
- **THEN** its visible tool title is `更新执行计划`.

#### Scenario: Evidence tool label follows record type
- **WHEN** the transcript renders a `record_run_evidence` tool call with `record_type` set to `artifact`, `dataset_profile`, `verification_fact`, `parameter_snapshot`, or `claim_trace`
- **THEN** the visible tool title uses the corresponding concise evidence label instead of the generic `登记运行证据`.

### Requirement: Transcript render model controls visible chronology
The dashboard SHALL derive visible transcript rows from a frontend render model that preserves runtime message and part order while applying artifact, thinking, issue, and skill-use visibility rules in one place.

#### Scenario: Render items preserve raw runtime order
- **WHEN** the frontend receives runtime messages, message parts, tool calls, issues, artifacts, todos, and skill-use metadata for a session
- **THEN** it derives ordered render items from the original runtime message order and message-part order
- **AND** it does not append intermediate artifacts, skill-use rows, or issue rows to the end of the transcript unless their source metadata is end-positioned.

#### Scenario: Hidden thinking-only messages leave no gap
- **WHEN** a message contains thinking content but no non-thinking content that is visible with the current settings
- **AND** the user has disabled thinking visibility
- **THEN** the render model emits no visible item for that message
- **AND** the transcript list does not retain a message wrapper, row margin, or spacer for that hidden item.

#### Scenario: Unknown runtime content falls back safely
- **WHEN** the render model sees a runtime message part or tool type that has no specialized renderer
- **THEN** it keeps the original generic transcript rendering for that part
- **AND** it does not drop evidence solely because the part type is unknown.

### Requirement: Artifact previews are explicit and cached
The dashboard SHALL fetch artifact content only in response to explicit preview actions and SHALL reuse preview content for identical artifact metadata until the artifact changes.

#### Scenario: Artifact cards do not fetch content during render
- **WHEN** artifact cards render in the transcript, final carousel, or right sidebar
- **THEN** the browser does not call the artifact content endpoint just because the card mounted, scrolled into view, received focus, or was included in an SSE refresh.

#### Scenario: Explicit preview fetches content once
- **WHEN** the user opens or expands an in-app preview for a previewable artifact
- **THEN** the browser requests the artifact content through the application backend
- **AND** repeated preview requests for the same session, artifact, path, and metadata version share an in-flight request or cached result.

#### Scenario: Artifact update invalidates cached preview
- **WHEN** the same artifact path is registered again with newer metadata
- **THEN** the preview cache key changes
- **AND** a later explicit preview request fetches the newer content rather than reusing the old preview body.

#### Scenario: Preview failures remain compact
- **WHEN** an explicit preview request fails
- **THEN** the dashboard shows a compact inline or modal preview error
- **AND** it does not start automatic retry loops while the session remains active.

#### Scenario: Table artifacts render as bounded tables
- **WHEN** the user previews a CSV or TSV artifact with a table display hint
- **THEN** the dashboard renders the preview as a scrollable table with a header row instead of plain delimited text
- **AND** it limits the number of rendered data rows while preserving access to the full artifact through the open action.

### Requirement: Normal transcript typography is compact
The dashboard SHALL render normal assistant markdown, mention messages, and tool-call blocks using compact text and spacing aligned to a `text-sm` visual scale, while preserving the existing thinking-content typography.

#### Scenario: Assistant markdown uses compact sizing
- **WHEN** a normal assistant or mention message renders markdown content
- **THEN** paragraph text, lists, blockquotes, code blocks, tables, and surrounding vertical spacing use the compact transcript scale
- **AND** headings remain visually hierarchical without returning to oversized message-card typography.

#### Scenario: Tool blocks match compact transcript scale
- **WHEN** a visible tool block renders its title, body, parameters, output, or error detail
- **THEN** its typography and padding align with the compact transcript scale
- **AND** it remains readable inside the same maximum transcript width as normal messages.

#### Scenario: Thinking typography is unchanged
- **WHEN** thinking content is visible
- **THEN** its current font sizing, spacing, and visual treatment are preserved by this change.

### Requirement: Skill usage appears only from explicit evidence
The dashboard SHALL render skill usage in the message stream only when explicit runtime metadata or structured evidence identifies a real skill use.

#### Scenario: Explicit skill use renders in transcript order
- **WHEN** the session state includes a skill-use event or metadata record with skill identity, associated agent, and runtime position
- **THEN** the dashboard renders a compact skill-use row at that associated transcript position
- **AND** the row uses the skill display name or skill id without expanding into long instructional text.

#### Scenario: Static skill configuration does not create rows
- **WHEN** an agent role is configured with bundled skills but the runtime has not emitted a skill-use event or structured evidence record for a specific use
- **THEN** the dashboard does not fabricate a skill-use transcript row from that static configuration.

### Requirement: Dashboard supports session archive export and import
The dashboard SHALL expose session archive export and import controls through the application backend while keeping all archive handling inside normal app session surfaces.

#### Scenario: User exports active session archive
- **WHEN** a writable or read-only session is active and the user chooses the export archive action
- **THEN** the dashboard downloads the backend-provided JSON archive for that session
- **AND** the browser does not call OpenCode runtime internals directly

#### Scenario: User imports saved archive JSON
- **WHEN** a user chooses the import archive action from the session list area and selects a JSON archive file
- **THEN** the dashboard reads the selected JSON and sends the archive payload to the backend import endpoint through the normal app API
- **AND** the returned read-only session appears in the existing session list and becomes selectable like other sessions

### Requirement: Imported sessions render as read-only transcripts
The dashboard SHALL render imported archive sessions with the existing message-first transcript, todo, timeline, issue, geospatial evidence, and artifact metadata views while disabling controls that would mutate or resume the session.

#### Scenario: Composer is disabled for imported session
- **WHEN** a user opens an imported read-only session
- **THEN** the chat composer is hidden so users cannot enter new messages or answer archived questions
- **AND** the UI presents the session as a read-only archive rather than as an active runtime session

#### Scenario: Session mutation controls are hidden or disabled
- **WHEN** a user opens an imported read-only session
- **THEN** rename, attached-data editing, workspace opening, interrupt, and runtime-continuation controls are unavailable for that session

#### Scenario: Artifact metadata remains visible without file actions
- **WHEN** an imported read-only session includes artifact metadata
- **THEN** the dashboard may show artifact titles, paths, kinds, stages, and provenance as evidence metadata
- **AND** it does not offer artifact preview or open actions for those archived artifact entries
