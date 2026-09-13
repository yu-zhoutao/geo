---
name: geospatial-spatiotemporal-runbook
description: Use when a spatiotemporal pattern task is ready for annual/seasonal statistics, spatial interpolation, variability analysis, artifact registration, and bounded reporting.
compatibility: opencode
---

# Geospatial Spatiotemporal Pattern Runbook

## Overview
This skill governs the executable spatiotemporal pattern analysis path. The operator must use `xarray`, `rioxarray`, `scipy`, and `matplotlib` from the managed geospatial environment for temporal statistics, spatial interpolation, and variability analysis.

Spatiotemporal analysis is evidence-heavy. A valid run needs temporal coverage, spatial extent, statistical measures, variability metrics, distribution maps, and claim boundaries. Without those records, a final "pattern" statement is not auditable.

## When to Use
- Triage selected `spatiotemporal_pattern` and annual/seasonal statistics.
- Data audit confirmed valid temporal and spatial coverage.
- The operator must compute statistics, create distribution maps, and register artifacts.

Do not use this skill to decide trend detection or spatial clustering. Use appropriate methods first.

## Required Inputs
- Study-design and data-audit contracts.
- Prepared raster or vector data path, temporal resolution, spatial extent, and CRS.
- Statistical measures and variability metrics to compute.
- Workspace command contract from `get_session_context`.

## Workflow
1. Read `get_session_context` and confirm package readiness includes `xarray`, `rioxarray`, `scipy`, and `matplotlib`.
2. Verify temporal coverage, spatial extent, data completeness, and CRS.
3. Import `xarray`, `rioxarray`, `scipy`, and `matplotlib` in the visible script. If import fails, stop; do not hand-code statistical fallback.
4. Load data using `xarray` and `rioxarray` for raster data or `geopandas` for vector data.
5. Compute temporal statistics: mean, median, standard deviation, min, max for each spatial unit.
6. Compute spatial statistics: distribution, percentiles, interpolation for each time period.
7. Calculate variability metrics: coefficient of variation (CV), interannual variability, seasonal amplitude.
8. Create distribution maps showing spatial patterns of mean values.
9. Create variability maps showing spatial patterns of CV or interannual variability.
10. Create seasonal comparison maps showing differences between seasons or years.
11. Ensure every map artifact, including distribution, variability, and seasonal maps, includes a north arrow or north-direction marker, a legend or colorbar, and a truthful scale bar.
12. Register statistics table, distribution maps, variability maps, manifest, parameter snapshot, and claim trace artifacts through `record_run_evidence` when they should support UI display, review, or reproduction.
13. Report patterns as spatial distributions relative to selected statistical methods.

## Decision Logic
| Gate | Proceed | Clarify or repair | Stop |
| --- | --- | --- | --- |
| Package imports | `xarray`, `rioxarray`, `scipy`, `matplotlib` import successfully | none | imports fail |
| Temporal coverage | sufficient for pattern analysis | coverage gaps need documentation | insufficient coverage |
| Spatial extent | covers study area | extent mismatch needs reprojection | non-overlapping extent |
| Data completeness | missing values acceptable | missing value handling needed | excessive missing values |
| CRS | valid and consistent | reprojection needed | invalid CRS |

Use `repair` for reprojection, data preprocessing, or missing value imputation. Use `clarify` for temporal resolution, spatial extent, or statistical measures. Use `stop` for invalid imports, insufficient coverage, or unsupported formal claims.

## Output Contract
Return a clear spatiotemporal handoff and register artifacts where useful. A JSON manifest is recommended for statistic-heavy runs.

```json
{
  "decision": "proceed",
  "task_family": "spatiotemporal_pattern",
  "operator": "spatiotemporal",
  "method": "annual_seasonal_statistics",
  "parameters": {
    "temporal_resolution": "annual",
    "spatial_extent": "northeast_china",
    "statistical_measures": ["mean", "median", "std", "cv"],
    "variability_metrics": ["interannual_cv", "seasonal_amplitude"]
  },
  "results": {
    "total_pixels": 100000,
    "mean_value": 25.5,
    "std_value": 3.2,
    "cv_value": 12.5,
    "min_value": 15.0,
    "max_value": 35.0,
    "interannual_cv_mean": 8.5,
    "seasonal_amplitude_mean": 15.0
  },
  "cartographic_elements": {
    "north_arrow": true,
    "legend_or_colorbar": true,
    "scale_bar": true
  },
  "artifacts": [
    {"path": "outputs/spatiotemporal-stats.csv", "artifact_stage": "final", "display_hint": "table"},
    {"path": "outputs/distribution-map.tif", "artifact_stage": "final", "display_hint": "raster"},
    {"path": "outputs/variability-map.tif", "artifact_stage": "final", "display_hint": "raster"}
  ],
  "claim_limits": ["spatiotemporal pattern only", "no trend detection", "no causal explanation"]
}
```

Recommended manifest fields are `decision`, `task_family`, `operator`, `method`, `parameters`, `results`, `artifacts`, and `claim_limits`.

## Common Mistakes
- Running statistics without `xarray` or `rioxarray` package.
- Reporting distribution patterns without variability analysis.
- Omitting statistical measures from the snapshot.
- Hiding missing values or data gaps in the map.
- Releasing maps without north direction, legend or colorbar, and scale bar.
- Using insufficient temporal or spatial coverage for formal claims.

## Detailed Rules

### Spatiotemporal Runbook Rules

#### SPTEMP-R01 Package-backed execution is mandatory
The visible script must import `xarray`, `rioxarray`, `scipy`, and `matplotlib`. If any import fails, record an environment-not-ready or blocking tool failure and stop. Do not continue with a local reimplementation.

#### SPTEMP-R02 Statistical measures must be comprehensive
Distribution analysis must include mean, median, standard deviation, min, and max. Variability analysis must include coefficient of variation (CV) and interannual variability. Do not report patterns without comprehensive statistics.

#### SPTEMP-R03 Temporal coverage must be sufficient
Spatiotemporal analysis needs sufficient temporal coverage for meaningful pattern detection. Document temporal resolution, time step count, and coverage gaps.

#### SPTEMP-R04 Spatial extent must match study area
Data spatial extent must cover the study area. If reprojection or clipping is needed, document the process and verify coverage.

#### SPTEMP-R05 Missing value handling must be documented
Missing values must be handled explicitly. Document the percentage of missing values, imputation method if used, and threshold for excluding pixels.

#### SPTEMP-R06 Variability metrics must be recorded
Record coefficient of variation (CV), interannual variability, and seasonal amplitude. These metrics are essential for understanding pattern stability.

#### SPTEMP-R07 Every map must include cartographic elements
Every map artifact must show north direction, a legend or colorbar, and a truthful scale bar. This applies to distribution, variability, and seasonal maps.

#### SPTEMP-R08 Artifacts should be registered before strong claims
Register statistics table, distribution maps, variability maps, manifest, parameter snapshot, and claim trace through `record_run_evidence` when they support final interpretation. Claims must cite those artifacts or equally visible transcript evidence.

#### SPTEMP-R09 Reporting stays bounded
Describe patterns as spatial distributions relative to selected statistical methods. Do not claim trend detection, spatial clustering, density estimation, or causal explanation.

## Failure Modes

### Spatiotemporal Runbook Failure Modes

#### handwritten-fallback
Symptom: `xarray` or `rioxarray` import fails and the agent computes statistics manually.
Required action: stop and report environment-not-ready.

#### insufficient-coverage
Symptom: formal pattern claims are made with insufficient temporal or spatial coverage.
Required action: stop or mark as demo-only.

#### missing-value-coverup
Symptom: pixels with excessive missing values are included in analysis without documentation.
Required action: repair data preprocessing and document missing value policy.

#### missing-cartographic-element
Symptom: a map lacks north direction, legend or colorbar, or scale bar.
Required action: repair the map before registration or release.

#### incomplete-statistics
Symptom: distribution patterns are reported without variability analysis.
Required action: repair analysis to include CV and interannual variability.

## Worked Examples

### Spatiotemporal Runbook Examples

#### Good: annual temperature distribution
The script imports `xarray`, `rioxarray`, `scipy`, and `matplotlib`, loads annual temperature data, computes mean, std, CV, creates distribution and variability maps, and registers statistics, maps, manifest, and statistical methods.

#### Good: package failure blocks early
The managed environment lacks `xarray`. The operator records a blocking issue and does not compute statistics by hand.

#### Good: significance disclosure
A map caption says "Annual mean temperature distribution, 2018-2022, with coefficient of variation showing interannual variability." The data gaps are styled separately.

#### Good: complete distribution map
The distribution map includes a north arrow, temperature legend with units, and scale bar computed from the analysis CRS.

#### Bad: raw mean map
The operator maps mean values and calls it a "pattern." This is a mean map, not a spatiotemporal pattern analysis.

#### Bad: no variability analysis
The operator computes mean without CV or interannual variability.

## Supporting Files
- None. The run-specific Python script and manifest are written in the managed workspace and registered as evidence.