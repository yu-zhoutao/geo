---
name: geospatial-trend-runbook
description: Use when a time-series trend task is ready for Mann-Kendall test and Sen's slope execution, significance metadata, artifact registration, and bounded reporting.
compatibility: opencode
---

# Geospatial Trend Analysis Runbook

## Overview
This skill governs the executable time-series trend analysis path. The operator must use `pymannkendall` for Mann-Kendall test and `scipy` for Theil-Sen slope estimation from the managed geospatial environment, rather than a local reimplementation of the statistics.

Trend analysis is evidence-heavy. A valid run needs temporal coverage, data completeness, significance threshold, slope estimates, classification maps, and claim boundaries. Without those records, a final "trend" statement is not auditable.

## When to Use
- Triage selected `time_series_trend` and Mann-Kendall/Sen's slope.
- Data audit confirmed valid temporal coverage with sufficient time steps.
- The operator must run trend statistics, create classification maps, and register artifacts.

Do not use this skill to decide spatial clustering or density estimation. Use appropriate methods first.

## Required Inputs
- Study-design and data-audit contracts.
- Prepared raster or vector time-series path, temporal resolution, time step count, and CRS.
- Significance settings and alpha threshold.
- Workspace command contract from `get_session_context`.

## Workflow
1. Read `get_session_context` and confirm package readiness includes `pymannkendall` and `scipy`.
2. Verify temporal coverage, data completeness, missing value percentage, and time step count.
3. Import `pymannkendall` and `scipy` in the visible script. If import fails, stop; do not hand-code trend fallback.
4. Extract pixel-level or area-level time series based on data structure.
5. Execute Mann-Kendall test for each time series: `pymannkendall.original_test(series, alpha=0.05)`.
6. Estimate Theil-Sen slope: `pymannkendall.sens_slope(series)` or `scipy.stats.theilslopes`.
7. Create classification fields: trend direction (increasing/decreasing/no trend), significance (p<0.05), slope magnitude.
8. Apply and record the significance threshold. Do not imply stronger control than the recorded policy supports.
9. Ensure every trend map artifact, including slope and significance maps, includes a north arrow or north-direction marker, a legend or colorbar, and a truthful scale bar.
10. Register table, map, manifest, parameter snapshot, and claim trace artifacts through `record_run_evidence` when they should support UI display, review, or reproduction.
11. Report trends as temporal patterns relative to selected significance settings.

## Decision Logic
| Gate | Proceed | Clarify or repair | Stop |
| --- | --- | --- | --- |
| Package imports | `pymannkendall` and `scipy` import successfully | none | imports fail |
| Time steps | 3 or more valid time steps | fewer than 3 can be demo-only only if explicit | fewer than 3 for formal claims |
| Data completeness | missing values <50% | missing values 50-70% with justification | missing values >70% |
| Temporal coverage | sufficient for trend detection | coverage gaps need documentation | insufficient coverage |
| Significance | alpha threshold recorded | policy needs user choice | no significance metadata |

Use `repair` for data preprocessing, missing value imputation, or temporal aggregation. Use `clarify` for temporal resolution, aggregation method, or demo-only consent. Use `stop` for invalid imports, insufficient time steps, or unsupported formal claims.

## Output Contract
Return a clear trend handoff and register artifacts where useful. A JSON manifest is recommended for statistic-heavy runs.

```json
{
  "decision": "proceed",
  "task_family": "time_series_trend",
  "operator": "trend",
  "method": "mann_kendall_sens_slope",
  "parameters": {
    "significance_level": 0.05,
    "temporal_resolution": "annual",
    "time_steps": 5,
    "missing_value_threshold": 0.5
  },
  "results": {
    "total_pixels": 10000,
    "increasing_count": 3500,
    "decreasing_count": 1200,
    "no_trend_count": 5300,
    "increasing_pct": 35.0,
    "decreasing_pct": 12.0,
    "no_trend_pct": 53.0,
    "mean_slope": 0.025,
    "median_slope": 0.018,
    "slope_range": [-0.15, 0.22]
  },
  "cartographic_elements": {
    "north_arrow": true,
    "legend_or_colorbar": true,
    "scale_bar": true
  },
  "artifacts": [
    {"path": "outputs/trend-table.csv", "artifact_stage": "final", "display_hint": "table"},
    {"path": "outputs/trend-classification.tif", "artifact_stage": "final", "display_hint": "raster"},
    {"path": "outputs/slope-map.tif", "artifact_stage": "final", "display_hint": "raster"}
  ],
  "claim_limits": ["temporal trend only", "no causal explanation", "no spatial clustering"]
}
```

Recommended manifest fields are `decision`, `task_family`, `operator`, `method`, `parameters`, `results`, `artifacts`, and `claim_limits`.

## Common Mistakes
- Running Mann-Kendall without `pymannkendall` package.
- Reporting slope values as significant without p-value.
- Omitting significance threshold from the snapshot.
- Hiding nonsignificant pixels in the map.
- Releasing trend maps without north direction, legend or colorbar, and scale bar.
- Using fewer than 3 time steps for formal trend claims.

## Detailed Rules

### Trend Runbook Rules

#### TREND-R01 Package-backed execution is mandatory
The visible script must import `pymannkendall` and `scipy`. If either import fails, record an environment-not-ready or blocking tool failure and stop. Do not continue with a local reimplementation.

#### TREND-R02 Significance testing is mandatory
Every trend claim must be backed by Mann-Kendall p-value. Do not report raw slope values as significant trends without statistical testing.

#### TREND-R03 Minimum time steps for formal claims
Formal trend analysis needs at least 3 time steps for meaningful inference. Fewer than 3 time steps blocks formal claims unless the run is explicitly demo-only.

#### TREND-R04 Missing value handling must be documented
Missing values must be handled explicitly. Document the percentage of missing values, imputation method if used, and threshold for excluding pixels.

#### TREND-R05 Slope estimation method must be recorded
Record whether Theil-Sen slope was estimated using `pymannkendall.sens_slope` or `scipy.stats.theilslopes`. Both are valid but must be documented.

#### TREND-R06 Classification maps must show all categories
Trend classification maps must show increasing, decreasing, and no-trend categories. Do not hide nonsignificant pixels without recording the classification policy.

#### TREND-R07 Every trend map must include cartographic elements
Every trend map artifact must show north direction, a legend or colorbar, and a truthful scale bar. This applies to slope, significance, and classification maps.

#### TREND-R08 Artifacts should be registered before strong claims
Register trend table, classification map, slope map, manifest, parameter snapshot, and claim trace through `record_run_evidence` when they support final interpretation. Claims must cite those artifacts or equally visible transcript evidence.

#### TREND-R09 Reporting stays bounded
Describe trends as temporal patterns relative to the selected significance configuration. Do not claim causality, spatial clustering, density estimation, or risk proof.

## Failure Modes

### Trend Runbook Failure Modes

#### handwritten-fallback
Symptom: `pymannkendall` import fails and the agent computes Mann-Kendall manually.
Required action: stop and report environment-not-ready.

#### no-significance-test
Symptom: the script computes slope without Mann-Kendall test but labels output as significant trends.
Required action: repair script and rerun.

#### insufficient-time-steps
Symptom: formal trend claims are made with fewer than 3 time steps.
Required action: stop or mark as demo-only.

#### missing-value-coverup
Symptom: pixels with >70% missing values are included in trend analysis without documentation.
Required action: repair data preprocessing and document missing value policy.

#### missing-cartographic-element
Symptom: a trend map lacks north direction, legend or colorbar, or scale bar.
Required action: repair the map before registration or release.

## Worked Examples

### Trend Runbook Examples

#### Good: annual NDVI trend
The script imports `pymannkendall` and `scipy`, extracts pixel-level annual NDVI time series, runs Mann-Kendall test, estimates Sen's slope, creates classification map, and registers table, map, manifest, and significance policy.

#### Good: package failure blocks early
The managed environment lacks `pymannkendall`. The operator records a blocking issue and does not compute trend by hand.

#### Good: significance disclosure
A map caption says "NDVI trends at alpha 0.05 using Mann-Kendall test, 5-year annual time series." The nonsignificant pixels are styled separately.

#### Good: complete classified map
The classified trend map includes a north arrow, increasing/decreasing/nonsignificant legend, and scale bar computed from the analysis CRS.

#### Bad: raw slope map
The operator maps slope values and calls the top class "significant trends." This is a slope map, not a trend classification.

#### Bad: no significance test
The operator computes slope without Mann-Kendall test and labels high slopes as trends.

## Supporting Files
- None. The run-specific Python script and manifest are written in the managed workspace and registered as evidence.