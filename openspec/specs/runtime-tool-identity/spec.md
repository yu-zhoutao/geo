# runtime-tool-identity Specification

## Purpose
TBD - created by archiving change use-opencode-native-todos-and-tool-labels. Update Purpose after archive.
## Requirements
### Requirement: Shared runtime tool identity map
The application SHALL define a shared runtime tool identity map for user-facing tool metadata, covering known OpenCode built-in tools and the current application-owned geospatial MCP tools with Chinese display labels, stable tool families, and short summaries.

#### Scenario: Backend resolves tool metadata from shared map
- **WHEN** the Python backend normalizes a runtime tool part for a known tool
- **THEN** it resolves the tool label and family from the shared runtime tool identity map
- **AND** it includes that metadata in the normalized tool part without changing the raw runtime tool identifier.

#### Scenario: Frontend resolves tool metadata from shared map
- **WHEN** the Vue frontend renders a tool part whose backend metadata is missing or incomplete
- **THEN** it resolves the tool label and family from the same shared runtime tool identity map used by the backend.

#### Scenario: Unknown tool uses localized fallback
- **WHEN** a runtime tool is not present in the shared identity map
- **THEN** the UI displays a generic Chinese fallback label while preserving the raw tool identifier inside expandable technical details.

#### Scenario: Removed MCP tools are not shown as current tools
- **WHEN** the shared tool identity source is loaded after the MCP rewrite
- **THEN** removed tools such as `inspect_geospatial_request`, `prepare_geospatial_inputs`, `run_kde_operator`, `summarize_geospatial_artifacts`, `execute_kde_workflow`, and `update_execution_plan` are not presented as current geospatial MCP tools.

### Requirement: Tool names are canonicalized before display lookup
The application SHALL canonicalize runtime tool names before resolving user-facing metadata so equivalent OpenCode, MCP, and application-prefixed names map to the same tool identity.

#### Scenario: Repeated geospatial prefix resolves to one identity
- **WHEN** the runtime emits a tool named `geospatial_get_session_context` or `geospatial_geospatial_get_session_context`
- **THEN** the application resolves it to the `get_session_context` tool identity for display.

#### Scenario: MCP-style name resolves to one identity
- **WHEN** the runtime emits a tool named `mcp__geospatial__record_run_evidence`
- **THEN** the application resolves it to the `record_run_evidence` identity used for display, without exposing the MCP transport prefix as the primary UI label.

### Requirement: Tool identity follows agent identity architecture
The runtime tool identity map SHALL follow the same shared-source architecture as the canonical agent identity map, so backend prompt/runtime normalization and frontend rendering do not maintain independent label registries.

#### Scenario: Tool label update applies consistently
- **WHEN** a known tool's Chinese display label is updated in the shared tool identity source
- **THEN** backend-normalized tool metadata and frontend-rendered tool rows use the same updated label after application reload.

