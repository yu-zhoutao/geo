# spatial-hotspot-agent-execution Specification

## Purpose
TBD - created by archiving change add-idw-gistar-task-families. Update Purpose after archive.
## Requirements
### Requirement: Gi* task triage requires aggregated spatial support
The system SHALL support a Getis-Ord Gi* statistical hotspot task family for numeric attributes on areal, grid, or otherwise explicitly aggregated spatial units, and SHALL avoid treating raw point events as Gi* inputs without an aggregation decision.

#### Scenario: Aggregated unit task proceeds to Gi*
- **WHEN** a user asks for statistically significant high-value or low-value clusters over spatial units with a numeric attribute
- **THEN** the managed runtime can classify the request as `spatial_hotspot`
- **AND** the task evidence records Gi* as the selected statistical hotspot operator.

#### Scenario: Raw point events require aggregation or another method
- **WHEN** a user provides raw point events and asks for hotspots without an areal, grid, or aggregated numeric support
- **THEN** the task enters `clarify` or `repair` so the agent can ask for an aggregation unit or choose a defensible aggregation step
- **AND** it does not run Gi* directly on unaggregated event points.

#### Scenario: Count versus rate semantics require clarification
- **WHEN** the Gi* input field could represent raw counts over unequal area, population, exposure, or opportunity units
- **THEN** the task enters `clarify` unless the user or evidence states whether the analysis should target total magnitude or a denominator-adjusted rate.

#### Scenario: Density request is not misreported as Gi*
- **WHEN** the request is about point-event density without significance testing over neighboring units
- **THEN** the managed runtime keeps the request in the KDE family or asks for clarification rather than reporting KDE output as Gi* hotspots.

### Requirement: Gi* input quality gates are explicit
The system SHALL verify feature count, numeric-field variation, finite values, spatial support, and demo-mode exceptions before executing Gi*.

#### Scenario: Small feature count blocks formal Gi*
- **WHEN** a Gi* task has fewer than 30 spatial units or aggregated measured features
- **THEN** the task enters `stop` for formal analysis unless the run is explicitly marked demo-only
- **AND** demo-only execution records that significance claims are not thesis-grade evidence.

#### Scenario: Invalid analysis field blocks Gi*
- **WHEN** the analysis field is nonnumeric, non-finite, entirely missing, all zero, all one, constant, or semantically meaningless for local clustering
- **THEN** the task enters `stop` with a machine-readable reason code.

### Requirement: Gi* execution uses PySAL libraries from the managed environment
The system SHALL execute Getis-Ord Gi* with PySAL `esda` and `libpysal` packages from the application-managed geospatial Python environment rather than a project-local reimplementation of the statistic or spatial weights.

#### Scenario: Agent-authored script imports PySAL packages
- **WHEN** the `operator-spatial-hotspot` specialist executes Gi*
- **THEN** the visible Python script imports the required `esda` and `libpysal` functionality from the managed runtime environment.

#### Scenario: Gi* statistic uses star semantics
- **WHEN** the script computes Getis-Ord Gi*
- **THEN** the method call uses `esda.G_Local` with `star=True` so the result is Gi* rather than plain local G
- **AND** the evidence records the statistic variant, input attribute, spatial weights, transform, permutations, seed, and significance configuration.

#### Scenario: Gi* PySAL parameters are explicit
- **WHEN** the runtime prepares the Gi* script
- **THEN** `transform`, `permutations`, `seed`, and `island_weight` policy are explicit in the script or parameter snapshot
- **AND** the prototype default uses `permutations=999`, a fixed seed, and `transform='B'` unless the user selects a different documented policy.

#### Scenario: PySAL import failure blocks the run early
- **WHEN** `esda` or `libpysal` cannot be imported in the managed environment
- **THEN** the backend reports environment-not-ready or the runtime records a blocking tool failure
- **AND** the task does not continue with a hand-written fallback implementation.

### Requirement: Spatial weight construction is explicit and CRS-safe
The system SHALL require Gi* runs to record spatial weight construction, neighbor semantics, island handling, CRS decisions, and distance-unit assumptions before interpreting local statistic output.

#### Scenario: Polygon contiguity weights are recorded
- **WHEN** Gi* uses polygon or grid contiguity weights
- **THEN** the evidence records the selected contiguity rule, transform, neighbor counts, island handling, and any units or boundaries that affect interpretation.

#### Scenario: Prototype weight defaults are bounded
- **WHEN** the input support is polygon or regular grid units and the user does not specify a weight model
- **THEN** the prototype can default to Queen contiguity and record why Rook or distance-band weights were not selected.
- **AND** when the input support is measured points used in demo mode, the prototype can default to KNN with an explicit `k` such as 8.

#### Scenario: Distance-based weights require metric units
- **WHEN** Gi* uses distance-band or nearest-neighbor weights
- **THEN** the runtime verifies that distance calculations use a defensible metric CRS
- **AND** it records the distance threshold or neighbor count, distance units, and projection decision.

#### Scenario: Business distance is not guessed
- **WHEN** a distance-band Gi* analysis requires a threshold distance and no user, dataset, or diagnostic rule supplies a defensible scale
- **THEN** the task enters `clarify` rather than guessing a business distance.

#### Scenario: Invalid weights block interpretation
- **WHEN** spatial weights cannot be constructed, contain unacceptable islands for the selected policy, or do not match the input geometry count
- **THEN** the task enters `repair` or `stop` with a machine-readable reason instead of reporting significance from invalid weights.

#### Scenario: Neighbor-count diagnostics gate Gi*
- **WHEN** spatial weights are constructed for Gi*
- **THEN** the run records minimum, mean or median, and maximum neighbor counts
- **AND** it blocks interpretation when any unit has no neighbor under a policy that does not explicitly mark islands, or when each unit effectively treats all other units as neighbors.

#### Scenario: Islands are not silently labeled
- **WHEN** the selected weight model produces island units
- **THEN** the default policy marks island Gi* results as not interpretable or NA and records the island count
- **AND** attaching islands to nearest neighbors or changing to a different weight model requires an explicit repair or clarification record.

### Requirement: Gi* outputs expose significance and artifact provenance
The system SHALL register Gi* outputs with enough statistic, significance, and provenance metadata for dashboard rendering, thesis reporting, and later audit.

#### Scenario: Gi* artifact table contains statistic fields
- **WHEN** Gi* execution completes
- **THEN** the registered table or derived dataset includes unit identifiers, input values, Gi* statistic values, `gi_z`, `gi_p_sim`, `gi_p_norm` when available, `gi_bin`, `hotcold_label`, neighbor counts, and weight metadata.

#### Scenario: FDR policy is disclosed for significance claims
- **WHEN** the final output labels units as statistically significant hotspots or coldspots
- **THEN** the evidence records whether raw local p-values, simulated p-values, and any FDR or multiple-testing correction were used
- **AND** the report does not imply stronger significance control than the recorded policy supports.

#### Scenario: Gi* map metadata preserves classification choices
- **WHEN** a map artifact visualizes Gi* results
- **THEN** its evidence records the classification thresholds, significance level, nonsignificant-unit styling, selected spatial weights, and input attribute.

#### Scenario: Run manifest links PySAL execution to outputs
- **WHEN** the agent registers the Gi* run manifest
- **THEN** the manifest includes script path, command contract, package-backed method summary, parameters, CRS decisions, weights summary, output paths, and verification status.

### Requirement: Gi* reporting keeps statistical claims bounded
The system SHALL require reports to distinguish statistically significant spatial association from density, magnitude, causality, or policy explanation.

#### Scenario: Report avoids causal overclaiming
- **WHEN** the final answer discusses Gi* hotspots
- **THEN** it frames hotspots and coldspots as local clusters relative to the selected spatial weights and significance configuration
- **AND** it does not claim causality or policy causes unless separate evidence supports that claim.

#### Scenario: Report distinguishes high values from significant hotspots
- **WHEN** units have high raw attribute values but are not significant under the selected Gi* configuration
- **THEN** the report does not label them as significant hotspots merely because their raw values are high.

#### Scenario: Report avoids unsupported outlier framing
- **WHEN** the final answer discusses Gi* outputs
- **THEN** it does not describe Gi* as isolated outlier detection, continuous-surface interpolation, density estimation, or standalone risk proof.

#### Scenario: Claim trace references Gi* evidence
- **WHEN** the final report makes a substantive hotspot claim
- **THEN** the claim trace links the statement to registered Gi* statistic fields, weight metadata, significance settings, CRS checks, and review output.

### Requirement: Hotspot responsibilities remain split across app, backend, runtime, and local Python
The system SHALL keep frontend, backend, runtime, and local Python responsibilities explicit for Gi* analysis without adding a backend-owned execution graph.

#### Scenario: Frontend renders hotspot evidence from backend events
- **WHEN** a hotspot run streams updates
- **THEN** the frontend displays transcript messages, specialist calls, tool activity, todos, artifact records, and verification facts through the application's backend API and SSE stream.

#### Scenario: Backend mediates runtime and evidence only
- **WHEN** the hotspot task runs
- **THEN** the backend manages OpenCode, MCP tools, PySAL-ready environment validation, and artifact metadata
- **AND** it does not synthesize a hidden Gi* workflow outside the managed runtime session.

#### Scenario: Runtime and local Python perform PySAL work visibly
- **WHEN** the Gi* operator executes
- **THEN** the managed runtime authors the script and decisions while the local Python geospatial environment runs PySAL-backed computation through the managed command contract.
