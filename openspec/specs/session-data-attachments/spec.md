## Purpose
Define per-session attached local data directories, their dashboard controls, runtime-context injection, and reproducibility tracking.
## Requirements
### Requirement: Sessions can attach local data directories
The application SHALL let the user configure a per-session set of attached local data directories that represent the active data scope for that agent session, SHALL surface attachment controls from the composer area instead of the right-sidebar session context, and SHALL keep the visible attachment set reversible and normalized when overlapping directory selections are chosen.

#### Scenario: User edits attached data directories from the composer
- **WHEN** a user adds, removes, or toggles attached data directories for an active or draft session from the composer attachment controls
- **THEN** the application updates the session's attached data directory set without requiring a new runtime server bootstrap

#### Scenario: Attached data directories are visible near the composer
- **WHEN** a session has attached data directories configured
- **THEN** the dashboard shows the enabled directory list as compact chips or equivalent contextual indicators near the composer instead of the right-sidebar session context

#### Scenario: Default data directory is visible before the first session message
- **WHEN** the dashboard is still in the local draft state before a backend session has been created
- **THEN** any application-defined default data directory is already visible in the composer attachment chips
- **AND** the user can remove it before sending the first prompt

#### Scenario: Attached directory chips support removal
- **WHEN** the composer shows an attached data directory chip, including a default data directory entry
- **THEN** the user can remove that specific directory from the attached set directly from the chip affordance

#### Scenario: Attached directory chips can open local directories
- **WHEN** the user activates the open action for an attached data directory chip
- **THEN** the application opens the corresponding local directory in the platform file explorer without requiring the user to search for the path manually

#### Scenario: Recent directories are reusable from the attachment menu
- **WHEN** a user opens the attachment controls after directories have been attached previously
- **THEN** the UI offers recent directory entries for faster re-selection

#### Scenario: Default data directory stays pinned at the top of recent entries
- **WHEN** the attachment menu shows recent directory entries
- **THEN** the application-defined default data directory remains available as the first recent option when it exists
- **AND** other remembered recent directories follow after it without duplicating the same path

#### Scenario: Attachment dropdown stays lightweight
- **WHEN** a user opens the composer attachment controls
- **THEN** the initial attachment UI is a compact dropdown or menu for recent choices and quick actions rather than a full inline directory browser

#### Scenario: Overlapping directory selections collapse to the parent scope
- **WHEN** a user attaches multiple directories where one selected path contains another selected path
- **THEN** the resulting attached directory set keeps only the highest relevant parent directory needed to cover that scope
- **AND** redundant child selections are removed from the visible chip list and persisted attachment metadata

#### Scenario: Directory browser defaults to the current working directory
- **WHEN** a user opens the full directory browser without first choosing a specific location
- **THEN** the browser opens at the application's current working directory by default

#### Scenario: Directory browser separates navigation from selection
- **WHEN** a user clicks a directory row inside the full directory browser
- **THEN** the browser navigates into that directory instead of immediately attaching it
- **AND** the UI exposes a separate explicit action in the browser footer for attaching the currently viewed directory or cancelling the browser

### Requirement: Attached data directories are injected into runtime context
The backend SHALL inject the enabled attached data directory paths into the runtime context or prompt for each relevant user turn so the agent treats them as the active local data scope.

#### Scenario: Runtime receives enabled data scope
- **WHEN** the backend forwards a user request to the OpenCode session
- **THEN** the runtime receives the current enabled attached data directory paths as part of the application-owned context for that turn

#### Scenario: Agent prefers attached directories first
- **WHEN** the runtime analyzes local data needs for a session with attached data directories
- **THEN** it is instructed to prioritize those enabled paths before looking outside them or asking to expand scope

### Requirement: Attached data directory usage is traceable
The system SHALL keep enough metadata to determine which attached data directories were enabled for a run and surface that context in reproducibility artifacts when relevant.

#### Scenario: Run metadata records attached directory context
- **WHEN** a geospatial run produces a manifest or equivalent reproducibility record
- **THEN** that record can include the attached data directories that were enabled for the session or run context

### Requirement: Attachment picker is application-managed
The application SHALL provide an application-managed directory selection flow for session data attachments rather than depending on a browser-native directory picker as the authoritative source of backend-usable paths.

#### Scenario: User browses directories through the application
- **WHEN** a user chooses to add a new data directory from the composer attachment controls
- **THEN** the frontend opens an in-app modal directory browsing flow backed by browser-facing backend APIs
- **AND** the selected result resolves to a backend-usable local directory path

#### Scenario: Browser modal offers common path shortcuts
- **WHEN** the directory browser modal is open
- **THEN** the UI exposes quick actions for jumping to the user home directory and the current working directory

#### Scenario: Current path can be edited in place
- **WHEN** the user clicks the current-path display in the directory browser modal
- **THEN** that path field becomes editable in place
- **AND** the UI shows explicit cancel and confirm actions for the edit

#### Scenario: Invalid manual path stays in the modal with an error
- **WHEN** the user confirms a manually entered directory path that does not exist or cannot be accessed
- **THEN** the modal stays open
- **AND** the UI shows an inline error state instead of navigating away or creating a directory implicitly
