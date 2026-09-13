## Purpose
Define application-managed icon asset handling and icon-first session action behavior for the dashboard.
## Requirements
### Requirement: Session lifecycle controls use icon-first actions
The dashboard SHALL use icon-first controls for common session lifecycle actions such as rename and delete instead of persistent text-heavy action buttons.

#### Scenario: Session row actions are icon-based
- **WHEN** the session list is rendered
- **THEN** rename and delete actions appear as icon-first controls with accessible labels rather than full-width text buttons

### Requirement: Frontend icon assets are application-managed
The frontend SHALL load dashboard action and transcript tool icons through an application-managed SVG asset pipeline suitable for Vite-based builds.

#### Scenario: SVG icons are bundled by the frontend build
- **WHEN** the frontend imports session action icons or transcript tool icons from the selected icon source
- **THEN** the Vite build can resolve and bundle those SVG assets without requiring runtime CDN access

### Requirement: Transcript role avatars are application-managed assets
The frontend SHALL manage transcript role avatar placeholders as application-managed local assets, the Python backend SHALL not require per-message avatar URLs or user-machine-specific image paths for transcript role headers, the coding-agent runtime SHALL not be required to supply avatar metadata for canonical role identities, and the local Python geospatial execution layer SHALL have no responsibility for transcript avatar delivery.

#### Scenario: Canonical role header uses a mapped avatar asset
- **WHEN** the transcript renders an assistant-side or system-side header for a canonical geospatial role identity
- **THEN** the UI uses the mapped application-managed avatar asset path for that role header
- **AND** the avatar is rendered as part of the visible transcript role identity rather than as a separate sidebar-only decoration

#### Scenario: Transcript avatar acts as an interactive identity trigger
- **WHEN** the transcript renders a canonical role avatar inside a grouped speaking header or subtask identity affordance
- **THEN** that avatar-backed affordance may be clicked to open the role profile popover
- **AND** the interaction does not require loading any remote profile image or per-message avatar metadata

#### Scenario: Role avatar assets resolve from an application-managed local path
- **WHEN** the frontend loads transcript role avatar placeholders
- **THEN** those images resolve from an application-managed local asset path suitable for Vite-based public serving
- **AND** the transcript does not depend on external CDNs or user-machine-specific absolute paths for those avatar images

#### Scenario: Unmapped future role uses a fallback avatar without legacy alias translation
- **WHEN** the transcript renders a canonical role id that has no dedicated avatar mapping yet
- **THEN** the UI uses a shared fallback avatar asset for that header
- **AND** it preserves the reported canonical role id instead of translating it into a deprecated alias name

#### Scenario: Inline role mentions reuse the same asset-backed identity map
- **WHEN** the transcript renders a subagent inline mention such as `@需求分诊师`
- **THEN** the UI resolves that affordance through the same application-managed role metadata used by grouped transcript headers
- **AND** the mention can open the same profile popover without introducing a second asset or identity source

### Requirement: Transcript tool entries use icon-first identification
The dashboard SHALL identify transcript tool activity primarily through icons and shared Chinese-facing tool labels instead of raw runtime tool ids or a generic `tool` badge.

#### Scenario: Known tools map to distinct icons
- **WHEN** the transcript renders a tool entry whose canonical tool name or family is recognized by the dashboard mapping
- **THEN** the entry displays the mapped icon together with the shared Chinese-facing tool label
- **AND** raw identifiers such as `todowrite`, `task`, or `geospatial_prepare_geospatial_inputs` do not appear as the primary tool title.

#### Scenario: Unknown tools map to a shared fallback
- **WHEN** the transcript renders a tool entry that has no dedicated icon mapping
- **THEN** the entry displays a shared fallback tool icon and a localized fallback label
- **AND** the raw tool identifier remains available inside expandable technical details for traceability.

#### Scenario: Tool family comes from shared metadata
- **WHEN** the transcript renders a known OpenCode built-in tool or geospatial MCP tool
- **THEN** the icon family and display label resolve from shared tool identity metadata rather than a component-local hardcoded English label table.

### Requirement: Brand icon is available as an application-managed asset
The frontend SHALL load the application brand icon for browser and dashboard chrome from an application-managed local asset path rather than a user-machine-specific external file location.

#### Scenario: Brand icon is available as an application-managed asset
- **WHEN** the frontend loads the application brand icon for browser or dashboard chrome
- **THEN** it resolves from an application-managed local asset path rather than a user-machine-specific external file location

### Requirement: Destructive actions use an in-app confirmation modal
The dashboard SHALL use an in-app modal to confirm session deletion instead of browser-native confirmation dialogs.

#### Scenario: Delete requires modal confirmation
- **WHEN** the user activates the delete action for a session
- **THEN** the dashboard opens an in-app confirmation modal and only performs deletion after explicit confirmation inside that modal

### Requirement: Browser favicon uses the branded app icon
The web application SHALL expose the branded app icon as the browser favicon.

#### Scenario: Browser tab shows the application-managed brand icon
- **WHEN** the dashboard document head is rendered
- **THEN** the favicon link references the application-managed branded icon asset

### Requirement: Global header uses the branded round app icon
The dashboard SHALL replace the placeholder glyph in the persistent global header with the branded app icon and render it as a round logo next to the system title.

#### Scenario: User sees branded header identity
- **WHEN** the user views the dashboard header
- **THEN** the global header shows the branded app icon instead of a placeholder letter glyph
- **AND** the icon is rendered as a round image aligned with the existing system title

