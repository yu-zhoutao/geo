## Purpose
Define draft-first session creation so the frontend delays backend session persistence until the user sends the first prompt.
## Requirements
### Requirement: New session starts in a local draft state
The frontend SHALL enter a local draft state whenever the user has no active session selected or explicitly starts a new session, instead of immediately creating a backend session record.

#### Scenario: Dashboard opens into a draft state when no session is active
- **WHEN** the user opens the application and no active session is selected
- **THEN** the UI opens a send-ready draft composer state without immediately calling the backend session-creation endpoint

#### Scenario: Draft state opens without backend session from the new-session action
- **WHEN** the user clicks the control to begin a new session
- **THEN** the UI opens the same draft composer state without immediately calling the backend session-creation endpoint

### Requirement: First prompt creates the backend session
The system SHALL create the backend session only when the user submits the first prompt from the draft state, whether that draft was reached automatically on app entry or by explicitly starting a new session.

#### Scenario: First prompt promotes draft to real session
- **WHEN** the user submits the first prompt while the UI is in draft mode
- **THEN** the frontend first creates the backend session, then sends the prompt, and then transitions into the normal active-session state

#### Scenario: Abandoned draft does not pollute session list
- **WHEN** the user enters draft mode but never submits a first prompt
- **THEN** no persisted session is added to the backend session list

