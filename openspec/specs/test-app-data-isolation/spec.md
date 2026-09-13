## Purpose
Define the backend test-storage isolation boundary so automated tests use temporary application data roots instead of mutating default local app data.

## Requirements

### Requirement: Backend tests use isolated temporary app data roots
The backend test harness SHALL construct storage-touching tests with temporary application data roots that isolate app-support, SQLite, workspace, and runtime-state paths from developer-owned machine state.

#### Scenario: API test app boots from temporary storage roots
- **WHEN** a backend API or session-lifecycle test creates an application instance for validation
- **THEN** the app's `app_support_dir`, `database_path`, `workspace_root`, and `state_dir` resolve inside a pytest-managed temporary directory for that test run

### Requirement: Isolated tests do not write into default local app data
The backend test harness MUST prevent automated tests from mutating the default application-support directories or SQLite database that normal local runs use outside pytest.

#### Scenario: Test-created metadata stays inside pytest temp storage
- **WHEN** an isolated test creates sessions, writes metadata, or initializes runtime directories
- **THEN** all created files remain under the test's temporary app-data root and no test artifact is written to the default user-scoped app-support location
