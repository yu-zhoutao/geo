## Purpose
Define SQLite-backed app metadata responsibilities for OpenCode session references, session lifecycle actions, attached data directories, and app-owned local indexes.

## Requirements

### Requirement: SQLite indexes only app-owned session metadata
The backend SHALL persist only the OpenCode session references and app-owned metadata that are necessary for app resume, attached data directory state, artifact discovery, and dashboard usability.

#### Scenario: Session record is created in SQLite
- **WHEN** a user creates a new session from the dashboard
- **THEN** the backend creates a SQLite-backed session record containing at least a stable app session identifier, a display title, creation and update timestamps, lifecycle status, and any runtime session or trace references needed for resume and artifact discovery

#### Scenario: Session list is restored after restart
- **WHEN** the application restarts after sessions have been created previously
- **THEN** the backend rebuilds the dashboard session list from SQLite-managed metadata without requiring the old `.state/sessions.json` file path

#### Scenario: Runtime identifiers are indexed for resume
- **WHEN** the backend creates or resumes an OpenCode-backed session
- **THEN** SQLite may store the runtime session identifier and runtime trace reference needed to reconnect app-owned UX flows to that session

#### Scenario: Runtime-native history is not duplicated into SQLite
- **WHEN** OpenCode already remains the source of truth for session history and runtime actions
- **THEN** the backend stores only references and app-owned indexes rather than full mirrored copies of runtime-native event history

#### Scenario: Runtime-derived message history is not persisted locally
- **WHEN** message transcript, plan state, or runtime-native action history can be obtained from OpenCode
- **THEN** SQLite does not persist duplicate mirrored copies of that runtime-owned state

### Requirement: SQLite stores attached data directory metadata
The backend SHALL persist the current attached data directory list for each session as app-owned metadata so the UI and runtime prompt injection can recover it after restart.

#### Scenario: Attached data directories survive restart
- **WHEN** a user has configured attached data directories for a session and the application restarts
- **THEN** the backend restores that directory list from SQLite-backed metadata for the resumed session context

### Requirement: Session rename is persisted
The backend SHALL allow users to rename a session and persist the updated display title in SQLite.

#### Scenario: User renames a session
- **WHEN** a user submits a new title for an existing session
- **THEN** the backend updates the SQLite session record and subsequent list or get responses use the renamed title

### Requirement: Session delete is supported at the metadata layer
The backend SHALL support deleting a session from the application's active session list through SQLite-backed lifecycle state.

#### Scenario: User deletes a session
- **WHEN** a user deletes an existing session from the dashboard
- **THEN** the backend updates the SQLite-backed lifecycle state so the session no longer appears in the default active session list

#### Scenario: Deleted session is excluded from normal listing
- **WHEN** the dashboard requests the normal session list after a session has been deleted
- **THEN** the backend omits that session from default results unless a later recovery-oriented feature explicitly requests deleted records

### Requirement: SQLite metadata honors isolated storage roots
The backend SHALL create and use the SQLite session-metadata database at the configured per-app storage path, including isolated temporary paths used by automated tests.

#### Scenario: Session metadata database stays inside isolated test storage
- **WHEN** a storage-touching test creates or mutates session metadata through an app instance built with temporary settings
- **THEN** the SQLite database file is created only at the injected test database path and no metadata write falls back to the active local application database
