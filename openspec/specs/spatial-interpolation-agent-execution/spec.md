# spatial-interpolation-agent-execution Specification

## Purpose
TBD - created by archiving change add-idw-gistar-task-families. Update Purpose after archive.
## Requirements
### Requirement: Interpolation task triage distinguishes sampled-value surfaces from density and hotspots
The system SHALL support a spatial interpolation task family for estimating a continuous surface from sampled point observations with a numeric value field, and SHALL keep that family distinct from KDE density estimation and Gi* statistical hotspot analysis.

#### Scenario: Sampled numeric point task proceeds to interpolation
- **WHEN** a user asks for a continuous surface estimated from point samples with a numeric observed value
- **THEN** the managed runtime can classify the request as `spatial_interpolation`
- **AND** the task evidence records the selected operator family as interpolation rather than KDE or statistical hotspot analysis.

#### Scenario: Density request is not coerced into interpolation
- **WHEN** a user asks where point events are concentrated without an observed numeric value to interpolate
- **THEN** the managed runtime does not select IDW merely because the output is map-like
- **AND** it keeps the task in the KDE family or asks for clarification if the intended method is ambiguous.

#### Scenario: Hotspot request is not coerced into interpolation
- **WHEN** a user asks for statistically significant high-value or low-value clusters over spatial units
- **THEN** the managed runtime does not select IDW as a substitute for local spatial autocorrelation
- **AND** it routes the request toward the spatial hotspot family or records a clarification state.

### Requirement: IDW execution is agent-directed and evidence-backed
The system SHALL let the managed runtime execute IDW interpolation through visible agent-authored Python scripts in the managed geospatial environment, with parameters and artifacts registered through the shared evidence ledger.

#### Scenario: IDW script records method parameters
- **WHEN** the `operator-interpolation` specialist executes IDW for a prepared task
- **THEN** the resulting evidence includes source CRS, analysis CRS, linear units, value field, grid extent, cell size, power parameter, neighborhood rule, mask or boundary handling, and output value units.

#### Scenario: IDW outputs are registered explicitly
- **WHEN** an IDW script produces a raster, vector grid, static map, HTML map, table, markdown report, or run manifest
- **THEN** the agent registers durable UI-facing outputs through `record_run_evidence`
- **AND** unregistered workspace files are not treated as visible artifacts by the dashboard.

#### Scenario: Runtime execution remains visible
- **WHEN** IDW work requires local computation
- **THEN** the transcript preserves the script path, command execution activity, stdout or stderr summary, generated artifact registrations, and any verification records needed to audit the run.

### Requirement: IDW preprocessing validates geometry, CRS, and value fields
The system SHALL require interpolation preprocessing to verify point geometry, numeric field suitability, analysis CRS units, study extent, and sample adequacy before treating an IDW result as valid.

#### Scenario: Missing numeric value field triggers clarification
- **WHEN** the attached dataset has point geometry but no resolvable numeric value field for interpolation
- **THEN** the task enters a `clarify` control state instead of interpolating event counts by default.

#### Scenario: Non-continuous or constant value field blocks interpolation
- **WHEN** the candidate interpolation field is categorical, boolean, identifier-like, nonnumeric, entirely missing, non-finite, or effectively constant
- **THEN** the task enters `stop` with a machine-readable reason instead of producing an IDW surface.

#### Scenario: Geographic CRS triggers repair before distance weighting
- **WHEN** IDW would compute distances in a geographic CRS measured in degrees
- **THEN** the managed runtime records a `repair` control decision and reprojects to a defensible metric analysis CRS before execution, or blocks the run if no defensible projection can be selected.

#### Scenario: Missing CRS blocks distance weighting
- **WHEN** an interpolation input has no authoritative CRS metadata
- **THEN** the task enters `stop` unless the user supplies authoritative CRS evidence
- **AND** the runtime does not guess a CRS from coordinate ranges.

#### Scenario: Insufficient or invalid samples block execution
- **WHEN** the sample layer has too few valid numeric observations, all values are missing, or the usable points collapse to an invalid spatial extent
- **THEN** the task enters a `stop` or blocked state with a machine-readable reason code rather than producing a misleading surface.

#### Scenario: IDW sample-count policy is explicit
- **WHEN** the runtime evaluates valid observations for IDW
- **THEN** fewer than 3 valid observations produces `stop`, 3 through 9 valid observations produces `clarify` for demo-only execution, and 10 or more valid observations can proceed if other gates pass.

#### Scenario: Conflicting duplicate samples require clarification
- **WHEN** multiple observations share the same coordinate
- **THEN** same-value duplicates can be repaired by deduplication with evidence
- **AND** conflicting values at the same coordinate produce `clarify` for an aggregation policy rather than silent averaging.

### Requirement: IDW parameter policy is explicit and reviewable
The system SHALL give IDW skills and scripts concrete prototype defaults while preserving user overrides and repair or clarification paths.

#### Scenario: Default IDW parameters are recorded
- **WHEN** IDW executes without user-specified parameters
- **THEN** the run uses and records prototype defaults for `power=2`, variable-neighborhood `k=12` capped by valid sample count, and a documented cell-size heuristic such as `min(width, height) / 250`.

#### Scenario: Out-of-policy power triggers clarification or warning
- **WHEN** a requested IDW power is less than or equal to 0
- **THEN** the task enters `stop` because inverse-distance weighting is invalid.
- **AND** when a positive requested power falls outside the prototype policy range `[0.5, 3]`, the task records `clarify` or a strong warning before proceeding.

#### Scenario: Fixed search radius is checked for neighbor coverage
- **WHEN** the user specifies a fixed IDW search radius or maximum distance
- **THEN** the runtime verifies that prediction cells have enough neighboring samples under that radius
- **AND** records cells or areas where the neighborhood is under-supported.

#### Scenario: Extrapolation area is disclosed
- **WHEN** an IDW output includes areas outside the sample convex hull, supplied study boundary, or defensible interpolation support
- **THEN** the artifact metadata and report mark those areas as lower-confidence or excluded according to the selected policy.

### Requirement: IDW reporting preserves uncertainty and interpretation limits
The system SHALL present IDW outputs as estimated continuous surfaces and SHALL preserve validation or limitation evidence needed to prevent unsupported claims.

#### Scenario: Validation evidence is recorded when feasible
- **WHEN** the sample size allows holdout validation, leave-one-out checks, or comparable diagnostics
- **THEN** the run evidence includes the selected validation method and summary metrics such as MAE, RMSE, ME or bias, R-squared or correlation when meaningful, and residual-distribution notes.

#### Scenario: Report avoids unsupported hotspot claims
- **WHEN** the final answer discusses an IDW surface
- **THEN** it describes high and low estimated values in relation to sampled observations and parameters
- **AND** it does not claim statistical hotspot significance unless a separate hotspot analysis has produced that evidence.

#### Scenario: Claim trace references interpolation artifacts
- **WHEN** the final report makes a substantive claim from the interpolated surface
- **THEN** the claim trace links the statement to registered IDW artifacts, parameter records, CRS decisions, and validation or limitation evidence.

### Requirement: Interpolation responsibilities remain split across app, backend, runtime, and local Python
The system SHALL keep frontend, backend, runtime, and local Python responsibilities explicit for interpolation without adding a backend-owned execution graph.

#### Scenario: Frontend renders interpolation evidence from backend events
- **WHEN** an interpolation run streams updates
- **THEN** the frontend displays transcript messages, specialist calls, tool activity, todos, artifact records, and verification facts through the application's backend API and SSE stream.

#### Scenario: Backend mediates runtime and evidence only
- **WHEN** the interpolation task runs
- **THEN** the backend manages OpenCode, MCP tools, geospatial environment readiness, and artifact metadata
- **AND** it does not synthesize a hidden IDW workflow outside the managed runtime session.

#### Scenario: Runtime and local Python perform the analysis visibly
- **WHEN** the interpolation operator executes
- **THEN** the managed runtime authors the script and decisions while the local Python geospatial environment performs the numerical and geospatial computation through the managed command contract.
