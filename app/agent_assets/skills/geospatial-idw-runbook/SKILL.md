---
name: geospatial-idw-runbook
description: Use when an IDW interpolation task is ready for CRS-safe execution, parameter recording, validation, artifact registration, and bounded interpretation.
compatibility: opencode
---

# Geospatial IDW Runbook

## Overview
This skill governs the executable IDW path. The runtime authors a visible Python script in the managed workspace, runs it with the managed geospatial Python command, and records evidence through `record_run_evidence`. The backend must not hide a fixed IDW workflow, and the agent must not hand-write mathematical shortcuts when the geospatial environment already provides reliable numeric and geospatial libraries.

IDW is a deterministic inverse-distance interpolator. It is sensitive to CRS, sample count, duplicate observations, power, neighborhood policy, grid extent, and masking. Good output is not just a raster; it is a raster plus parameter evidence, validation evidence when feasible, and clear limits about extrapolation and uncertainty.

## When to Use
- Triage selected `spatial_interpolation` and IDW.
- Data audit found a numeric observed value field on valid point samples.
- Spatial preparation can provide a metric analysis CRS or has blocked the run.
- The operator must create IDW raster, map, table, manifest, or report artifacts.

Do not use this skill to select between KDE, IDW, and Gi*. Use `geospatial-idw-method-selection` for that boundary.

## Required Inputs
- Triage and study-design contracts.
- Prepared point layer path, value field, source CRS, analysis CRS, and units.
- Study extent or mask decision.
- Valid sample count and duplicate-point policy.
- User parameter overrides, if any.
- Current workspace command contract from `get_session_context`.

## Workflow
1. Read `get_session_context` and verify the geospatial environment is ready.
2. Confirm the prepared layer has point geometry, authoritative CRS, a numeric nonconstant value field, and at least the minimum valid sample count.
3. Set parameters explicitly. Default prototype policy is `power=2`, variable neighborhood `k=12` capped by valid sample count, and cell size `min(width, height) / 250` unless the user supplied a defensible value.
4. Resolve duplicates before interpolation. Same-coordinate same-value duplicates can be deduplicated with evidence; conflicting values require clarification for aggregation policy.
5. Write and run an agent-authored script using `"$GEO_AGENT_UV_BIN" --project "$GEO_AGENT_GEO_PYTHON_PROJECT" run --python "$GEO_AGENT_GEO_PYTHON_VERSION" python <script>`.
6. Compute output grid, mask or disclose extrapolation, and record parameter snapshots before final claims.
7. Validate when feasible with holdout or leave-one-out diagnostics. Record MAE, RMSE, bias or ME, and correlation or R-squared only when meaningful.
8. Run power sensitivity and neighborhood sensitivity when sample count permits. Compare the default with nearby defensible settings, record whether estimated high/low areas and validation metrics move, and repair unstable claims before release.
9. Treat validation as core task evidence; validation is not optional decoration for a polished surface.
10. Ensure every IDW map artifact, including validation, sensitivity, and diagnostic maps, includes a north arrow or north-direction marker, a legend or colorbar, and a truthful scale bar.
11. Register durable artifacts with `record_run_evidence` when they should appear in the UI or support later reproduction. Workspace paths can still be cited in the transcript, but registration makes them easier to audit.
12. Interpret as an estimated continuous surface, not a significant hotspot map.

## Decision Logic
| Gate | Proceed | Clarify | Stop |
| --- | --- | --- | --- |
| CRS | Metric analysis CRS is recorded | Projection choice needs user confirmation | CRS missing or guessed |
| Samples | 10 or more valid observations | 3 through 9 valid observations and demo-only may be acceptable | Fewer than 3 valid observations |
| Value field | Numeric, finite, varying, semantically continuous | Multiple plausible numeric fields | Noncontinuous, constant, all missing, or identifier-like |
| Duplicates | None or same-value duplicates repaired | Conflicting same-coordinate values need policy | Conflict cannot be resolved |
| Parameters | Defaults or overrides are defensible | Power outside [0.5, 3] needs warning or confirmation | power <= 0 |
| Extent | Study extent and mask are defensible | Extrapolation disclosure needs confirmation | Output extent is invalid or unsupported |

Use `repair` for CRS reprojection, same-value deduplication, mask alignment, or field casting that preserves meaning. Use `clarify` when human choice changes the scientific meaning. Use `stop` when IDW would be mathematically invalid or misleading.

## Output Contract
Return a clear operator handoff plus registered artifacts where useful. A JSON manifest may be written and summarized in the final message.

```json
{
  "decision": "proceed",
  "task_family": "spatial_interpolation",
  "operator": "idw",
  "parameters": {
    "value_field": "pm25",
    "source_crs": "EPSG:4326",
    "analysis_crs": "EPSG:32650",
    "linear_units": "metre",
    "power": 2,
    "neighborhood": {"type": "variable_k", "k": 12},
    "cell_size_rule": "min(width, height) / 250",
    "mask_policy": "clip_to_study_area"
  },
  "validation": {
    "method": "leave_one_out",
    "metrics": {"MAE": 3.1, "RMSE": 4.6, "bias": -0.2}
  },
  "sensitivity": {
    "power_sensitivity": [{"power": 1.5, "RMSE": 5.0}, {"power": 2, "RMSE": 4.6}],
    "neighborhood_sensitivity": [{"k": 8, "RMSE": 4.9}, {"k": 12, "RMSE": 4.6}]
  },
  "cartographic_elements": {
    "north_arrow": true,
    "legend_or_colorbar": true,
    "scale_bar": true
  },
  "artifacts": [
    {"path": "outputs/idw-surface.tif", "artifact_stage": "final", "display_hint": "download"}
  ],
  "claim_limits": ["estimated surface only", "no statistical hotspot significance"]
}
```

Recommended manifest fields are `decision`, `task_family`, `operator`, `parameters.value_field`, `parameters.analysis_crs`, `parameters.power`, `parameters.neighborhood`, `artifacts`, and `claim_limits`.

## Common Mistakes
- Running distance weighting in EPSG:4326 degrees.
- Using all numeric columns as possible values without semantic audit.
- Treating a beautiful surface as validation evidence.
- Omitting duplicate policy and sample count from the parameter snapshot.
- Reporting high estimated values as statistically significant hotspots.
- Releasing intermediate or final IDW maps without north direction, legend or colorbar, and scale bar.
- Registering only the final PNG while leaving the raster, manifest, and validation table invisible.

## Detailed Rules

### IDW Runbook Rules

#### IDWRUN-R01 Managed environment and script evidence are mandatory
Use the managed Python command from the session context. The script path, command, stdout or stderr summary, inputs, and package versions should be recorded in provenance. Do not run invisible notebook state or paste unregistered local computations into the final report.

#### IDWRUN-R02 CRS must be metric for distance weighting
IDW distances must be calculated in a defensible metric CRS. Geographic degrees are never acceptable distance units for weighting. If CRS metadata is missing, stop unless the user supplies authoritative evidence. If CRS is geographic but authoritative, repair by reprojection and record the decision.

#### IDWRUN-R03 Value field must be numeric, finite, varying, and meaningful
The value field must be a measured continuous or near-continuous attribute. Identifiers, codes, category numbers, flags, ranks, and event presence values are not valid. All-missing, non-finite, or constant fields block execution.

#### IDWRUN-R04 Sample-count policy is explicit
Fewer than 3 valid observations produces `stop`. Between 3 and 9 valid observations produces `clarify` for demo-only execution because validation and spatial representativeness are weak. Ten or more valid observations can proceed if other gates pass.

#### IDWRUN-R05 Default parameters are prototype defaults, not hidden truth
When no user override exists, record `power=2`, `k=12` capped by valid sample count, and cell size `min(width, height) / 250`. A positive power outside `[0.5, 3]` requires a warning or clarification. `power <= 0` is invalid and must stop.

#### IDWRUN-R06 Neighborhood support must be diagnosed
Variable-k IDW should record the effective `k`, capped by sample count. Fixed radius IDW must report cells with insufficient neighbors. The report should not imply equal support across the surface when neighborhood coverage varies.

#### IDWRUN-R07 Extrapolation must be masked or disclosed
Areas outside the convex hull, study boundary, or defensible interpolation support must be excluded or marked lower confidence. The artifact metadata and report must state the chosen policy.

#### IDWRUN-R08 Validation evidence is required when feasible
When sample count allows, run leave-one-out, holdout, or comparable diagnostics. Record MAE, RMSE, bias or ME, and residual notes. If validation is not feasible, record why instead of pretending the surface is verified.

#### IDWRUN-R08A Parameter diagnostics are release evidence
When enough samples exist for comparison, run power sensitivity and neighborhood sensitivity around the selected configuration. Record how validation metrics, high/low estimated areas, and edge extrapolation change. If a claim depends on a single convenient setting, return `repair`; validation is not optional decoration and cannot be replaced by prose about uncertainty.

#### IDWRUN-R09 Artifact registration improves visibility
Register raster, static map, HTML map, validation table, parameter snapshot, and manifest as appropriate through `record_run_evidence`. Workspace files that are not registered are not dashboard artifacts; cite them by path or register them when they support final claims.

#### IDWRUN-R09A Every IDW map must include cartographic elements
Every IDW map artifact must show north direction, a legend or colorbar, and a truthful scale bar. This applies to intermediate validation, sensitivity, extrapolation, and diagnostic maps as well as final maps.

#### IDWRUN-R10 Interpretation stays bounded
Final claims may discuss estimated high and low values relative to observed samples and chosen parameters. They must not claim statistical significance, causality, policy explanation, or risk without separate evidence.

## Failure Modes

### IDW Runbook Failure Modes

#### angular-distance-idw
Symptom: the script uses longitude and latitude coordinates directly in inverse-distance calculations.
Required action: repair by projecting to a metric CRS or stop if CRS evidence is missing.

#### hidden-defaults
Symptom: the report says "default settings" without listing power, neighborhood, cell size, extent, mask, and duplicate policy.
Required action: repair by recording a parameter snapshot.

#### under-supported-surface
Symptom: three samples generate a polished citywide surface with no demo-only warning.
Required action: clarify or stop according to sample-count policy.

#### validation-as-decoration
Symptom: a map is called accurate because it looks plausible.
Required action: record validation metrics or limitation evidence.

#### single-parameter-idw-release
Symptom: the report releases one IDW surface with no power sensitivity or neighborhood sensitivity, even though sample count permits diagnostics.
Required action: run parameter diagnostics or return repair.

#### missing-cartographic-element
Symptom: an IDW map lacks north direction, legend or colorbar, or scale bar.
Required action: repair the map before registration or release.

#### significance-leak
Symptom: final text calls high IDW values "significant hotspots."
Required action: repair claim language and add a claim trace to interpolation evidence.

## Worked Examples

### IDW Runbook Examples

#### Good: CRS repair and recorded defaults
The source stations are EPSG:4326, the study area is Beijing, and the runtime reprojects to EPSG:32650 before IDW. It records `power=2`, `k=12`, cell size rule, sample count, duplicate policy, MAE, RMSE, bias, and output units.

#### Good: demo-only clarification
The user supplies six noise measurements and asks for a citywide interpolation. The operator asks whether a demo-only surface is acceptable and records that it is not thesis-grade evidence.

#### Good: fixed radius diagnostic
The user requests a 500 m search radius. The script reports how many grid cells have fewer than the minimum neighbors and masks unsupported cells instead of filling them silently.

#### Good: complete diagnostic map
The neighborhood sensitivity map includes a north arrow, value colorbar, and scale bar computed from the metric analysis CRS.

#### Bad: event heatmap as IDW
Crime points are assigned value 1 and interpolated. This is wrong because the data are events; use KDE for density or aggregate to units for Gi* if significance is required.

#### Bad: incomplete intermediate map
The validation preview omits a scale bar because it is only used during review.

#### Bad: final PNG only
The operator creates a map image but does not register the raster, parameter JSON, validation table, or manifest. The dashboard cannot audit the result.

## Supporting Files
- None. Scripts are authored inside the managed workspace for each run and should be registered through the evidence ledger when they support review or reproduction.
