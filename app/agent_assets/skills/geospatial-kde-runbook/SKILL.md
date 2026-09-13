---
name: geospatial-kde-runbook
description: Use when a prepared point-event workflow is ready for KDE execution and needs a full method checklist, artifact protocol, and interpretation-safe handoff.
compatibility: opencode
---

# Geospatial KDE Runbook

## Overview
This is the operator manual for local point-event KDE. It assumes the request was already triaged correctly and the inputs have already passed semantic and CRS checks. Chapter 5.1 of the textbook gives the core KDE idea: estimate density around observed points using a kernel and a bandwidth. But the runtime must go further than the textbook's software walkthrough. It must log parameter meaning, study-window assumptions, edge notes, weighting semantics, and the exact language that downstream roles are allowed to use.

## When to Use
- A prepared point-event layer exists.
- The working CRS has valid linear units.
- The study area and observation window are explicit.
- The runtime is ready to execute KDE or review an existing KDE run.

## Required Inputs
- Prepared-input contract.
- Study-area definition.
- Working CRS and units.
- Candidate bandwidth, cell size, and weight policy.

## Workflow
1. Reconfirm event semantics and point readiness.
2. Confirm that KDE is still the chosen family and that the working CRS is unit-safe.
3. Record bandwidth provenance, cell size rationale, weight semantics, and edge note requirement.
4. Execute KDE and record the output value mode.
5. When bandwidth is not fixed by the user, run primary + lower + upper bandwidths and record `bandwidth_sensitivity`, including `peak_count_by_bandwidth`, peak movement, high-density area change, and interpretation changes.
6. Generate operator artifacts before any interpretation is written.
7. Hand off explicit interpretation limits and unresolved risks.

KDE execution should be implemented as an agent-authored Python script, not as a hidden backend operator. Use `get_session_context` to locate the workspace root, attached data, and managed Python command. The workspace has no required internal directory layout, so choose clear workspace-relative paths such as `scripts/run_kde.py`, `outputs/kde-map.png`, and `outputs/kde-parameters.json`, then execute with:

```bash
"$GEO_AGENT_UV_BIN" --project "$GEO_AGENT_GEO_PYTHON_PROJECT" run --python "$GEO_AGENT_GEO_PYTHON_VERSION" python <script>
```

Use GeoPandas, Pyogrio, Shapely, PyProj, NumPy, Pandas, SciPy, scikit-learn, Rasterio, Matplotlib, MapClassify, Contextily, or Folium as needed. A typical script should load vector data with GeoPandas, validate `gdf.crs`, reproject into a metric analysis CRS, compute and record source and analysis bounding boxes, generate the density surface or sampled grid, and write both machine-readable parameters and map-ready outputs. After each durable output that should support review, dashboard display, or reproduction, call `record_run_evidence`; use `artifact_stage: intermediate` for diagnostics and `artifact_stage: final` for the release-ready map, table, report, or manifest.

Every KDE map artifact, including intermediate bandwidth-sensitivity maps and diagnostic previews, must include a north arrow or north-direction marker, a legend or colorbar, and a truthful scale bar. If the script cannot compute a truthful scale bar from the analysis CRS and units, repair the projection evidence before creating the map or return `repair`/`stop`.

The rule is simple: disclosure is not a substitute for sensitivity evidence. A KDE result that only says "bandwidth matters" but never compares a lower and upper scale has not completed the operator task when claims depend on high-value locations, peak counts, or hotspot extent.

## Decision Logic
Proceed when event semantics, CRS, study window, and parameters are defensible and fully disclosed.
Clarify when weight meaning, study window, or parameter intent is still ambiguous.
Repair when the run is still methodologically valid but needs parameter correction, edge disclosure, or safer wording.
Stop when KDE would be methodologically invalid or misleading.

## Output Contract
Return a clear KDE handoff. Natural language is acceptable; a compact structured block or manifest is useful for parameter-heavy runs. Include:
- `decision`
- `method_validity`
- `bandwidth`
- `bandwidth_units`
- `cell_size`
- `cell_size_units`
- `weight_policy`
- `edge_note`
- `output_value_mode`
- `bandwidth_sensitivity`
- `cartographic_elements`
- `interpretation_limits`

## Common Mistakes
- Treating software defaults as self-justifying.
- Running KDE without an explicit observation window.
- Forgetting that output values depend on grid resolution and unit choices.
- Leaving weighting semantics implicit.
- Producing a beautiful density map before locking the claim limits.
- Treating intermediate KDE maps as exempt from north arrow, legend, or scale-bar requirements.


## Detailed Rules

### KDE Runbook Rules

#### KRUN-R01 Only run after semantic and CRS gates pass
The operator stage may not silently absorb unresolved semantic or CRS blockers from earlier roles.

#### KRUN-R02 Observation window must be explicit
The study area is part of the estimator context. Do not replace it with the current display extent.

#### KRUN-R03 Parameters must be recorded before release
Bandwidth, cell size, weight field, output value mode, and edge note are release evidence and should be preserved as artifacts or transcript-visible parameter records.

#### KRUN-R03A Scripts and evidence must be reproducible
Every KDE script run must preserve the script path, exact command, input paths, parameter values, CRS decision, and output paths in a `record_run_evidence` parameter snapshot, artifact record, or verification fact.

#### KRUN-R03B Every KDE map must include cartographic elements
Every KDE map artifact must show north direction, a legend or colorbar, and a truthful scale bar, including intermediate sensitivity and diagnostic maps.

#### KRUN-R04 Output values are resolution- and unit-sensitive
Do not describe KDE values as if they were invariant across cell size or CRS choices.

#### KRUN-R05 Weight semantics must be explicit
If the run is weighted, record exactly what the weight means and why addition is defensible.

#### KRUN-R06 Handoff must carry interpretation limits
The operator output should hand downstream roles the strongest allowed claim and the strongest forbidden claim.

#### KRUN-R07 Minimum bandwidth sensitivity is required for unconstrained KDE
If the user has not fixed a single bandwidth, the release candidate must include primary + lower + upper bandwidth runs. Record `bandwidth_sensitivity`, `peak_count_by_bandwidth`, high-density area change, and whether named high-density areas merge or split. If the sensitivity check changes the interpretation, return `repair` and regenerate the release map/report from the safer parameterization.

## Failure Modes

### KDE Runbook Failure Modes

#### operator-absorbs-upstream-blocker
Response: `stop`.

#### missing-parameter-provenance
Response: `repair`.

#### hidden-output-value-mode
Response: `repair`.

#### no-edge-note
Response: `repair`.

#### weighted-run-without-weight-semantics
Response: `clarify` or `stop`.

#### report-released-before-operator-artifacts
Response: `stop`.

#### missing-bandwidth-sensitivity
Response: `repair`.

#### missing-cartographic-element
Response: `repair`.

#### disclosure-substitutes-for-diagnostic
Response: `repair`.

## Worked Examples

### KDE Runbook Examples

#### Good
The run records bandwidth, bandwidth units, cell size, cell-size units, weight field, output value mode, and edge note before any report wording is drafted.

#### Good
The runtime writes `scripts/run_kde.py`, executes it with the managed Python command, stores `outputs/kde-map.png` and `outputs/kde-parameters.json`, then registers the map as a final image artifact and the parameters as an intermediate JSON artifact.

#### Good
The operator writes one script that computes primary + lower + upper bandwidths, stores `bandwidth_sensitivity` with `peak_count_by_bandwidth`, then chooses the final map scale based on the comparison rather than on visual convenience.

#### Good
All primary and sensitivity maps include a north arrow, density colorbar, and scale bar computed in the metric analysis CRS.

#### Good
The operator refuses to proceed because the prepared-input contract still contains a CRS blocker.

#### Bad
"ArcGIS/QGIS has a default radius, so that must be fine."

#### Bad
The density raster is published with no study-window disclosure and no parameter metadata.

#### Bad
The bandwidth sensitivity preview omits the scale bar because it is not the final map.

#### Bad
The report says bandwidth sensitivity is a limitation, but no lower or upper bandwidth was run.

#### Bad
The report is drafted before the operator has emitted interpretation limits.

## Supporting Files
- Optional code or snippet files only when executable examples are truly needed.
