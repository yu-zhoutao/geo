# session-archive-import Specification

## Purpose
TBD - created by archiving change add-session-archive-import. Update Purpose after archive.
## Requirements
### Requirement: Session archives are lightweight and versioned
The backend SHALL export a single-session archive as a JSON document with a stable schema identifier, export metadata, source session references, normalized app session state, optional geospatial context, MCP evidence records, runtime trace metadata, and artifact metadata without embedding artifact file contents.

#### Scenario: Archive contains traceable session evidence
- **WHEN** a user exports a completed, failed, interrupted, or idle session
- **THEN** the JSON archive records the session messages, timeline entries, todo state, plan groups, issues, geospatial task metadata, verification entries, attached data directory metadata, runtime references, and artifact metadata available to the app
- **AND** it records any MCP evidence records associated with the session geospatial context

#### Scenario: Archive omits generated file contents
- **WHEN** a session contains map, raster, report, table, image, archive, or other registered artifacts
- **THEN** the JSON archive preserves each artifact's metadata and provenance
- **AND** it does not embed the artifact file bytes, copy workspace files, or require the artifact path to exist on import

#### Scenario: Archive excludes evaluation ownership fields
- **WHEN** the app exports a session archive
- **THEN** the archive does not include campaign, evaluation-run, scenario, repeat, or variant identifiers as app-owned fields

### Requirement: Session export refreshes recoverable runtime evidence
The backend SHALL assemble an exported archive from the best available session state by applying the same non-replaying recovery paths used for session resume before serialization.

#### Scenario: Export recovers runtime messages before serialization
- **WHEN** a session has a runtime session reference and is not actively running
- **THEN** export attempts to recover available runtime messages, child-session transcript content, evidence timeline entries, and plan groups before writing the archive payload

#### Scenario: Export does not replay session work
- **WHEN** a session archive is exported
- **THEN** the backend does not resubmit prompts, rerun tools, reopen artifacts, or create new runtime side effects

### Requirement: Archive import creates read-only local sessions
The backend SHALL import a valid session archive JSON as a new local app session entry that is marked read-only and visible in the normal session list.

#### Scenario: Valid archive becomes a list entry
- **WHEN** a user imports a valid `geo-agent.session-archive.v1` JSON file
- **THEN** the backend creates a new local session id, stores the archived session evidence under that id, marks it as imported and read-only, and returns the imported session for display

#### Scenario: Source runtime identifiers remain inert
- **WHEN** an archive contains source runtime session or trace references
- **THEN** those references are preserved only as archive metadata
- **AND** the imported session is not treated as an active resumable OpenCode runtime session

#### Scenario: Invalid archive is rejected
- **WHEN** a user imports a JSON file with an unsupported schema, missing required session evidence, or malformed model payload
- **THEN** the backend rejects the import with a normal HTTP validation error
- **AND** no partial imported session appears in the session list

### Requirement: Imported sessions are inspection-only
The backend SHALL prevent imported read-only sessions from mutating state, continuing runtime work, or resolving local workspace files while still allowing session retrieval and deletion from the local list.

#### Scenario: Runtime continuation is blocked for imported session
- **WHEN** a user attempts to rename, submit a message, answer a runtime question, interrupt a run, or edit attached data directories on an imported read-only session
- **THEN** the backend rejects the request without contacting the managed runtime

#### Scenario: Local file actions are blocked for imported session
- **WHEN** a user attempts to open the workspace or open an artifact for an imported read-only session
- **THEN** the backend rejects the request without resolving or opening any local filesystem path

#### Scenario: Imported session can still be read
- **WHEN** the dashboard requests an imported read-only session by id
- **THEN** the backend returns the archived transcript, timeline, plan, evidence metadata, artifacts metadata, issues, geospatial task state, and verification state
