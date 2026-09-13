---
name: geospatial-change-detection-runbook
description: Use when a land cover change detection task is ready for transition matrix, area statistics, change map execution, artifact registration, and bounded reporting.
compatibility: opencode
---

# Geospatial Change Detection Runbook

## Overview
This skill governs the executable land cover change detection path. The operator must use `rasterio`, `numpy`, `pandas`, and `matplotlib` from the managed geospatial environment for transition matrix computation, area statistics, and change map creation.

Change detection is evidence-heavy. A valid run needs multi-temporal classification data, transition matrix, area statistics, change statistics, change maps, and claim boundaries. Without those records, a final "change" statement is not auditable.

## When to Use
- Triage selected `land_cover_change` and transition matrix.
- Data audit confirmed valid multi-temporal classification data with consistent scheme.
- The operator must compute transitions, calculate area statistics, create change maps, and register artifacts.

Do not use this skill to decide trend prediction or causal attribution. Use appropriate methods first.

## Required Inputs
- Study-design and data-audit contracts.
- Prepared multi-temporal classification data paths, temporal coverage, classification scheme, and CRS.
- Class labels and transition categories to analyze.
- Workspace command contract from `get_session_context`.

## Workflow
1. Read `get_session_context` and confirm package readiness includes `rasterio`, `numpy`, `pandas`, and `matplotlib`.
2. Verify classification data, CRS, resolution, temporal coverage, and classification scheme consistency.
3. Import `rasterio`, `numpy`, `pandas`, and `matplotlib` in the visible script. If import fails, stop; do not hand-code change detection fallback.
4. Load multi-temporal classification data using `rasterio`.
5. Compute pixel-level change detection between time periods.
6. Compute transition matrix: `pandas.crosstab(class_t1, class_t2)`.
7. Calculate area statistics for each class and time period using pixel counting and resolution.
8. Calculate change statistics: gain, loss, net change, persistence for each class.
9. Create change maps showing spatial patterns of change (gain, loss, persistence, transition types).
10. Ensure every change map artifact, including transition and change maps, includes a north arrow or north-direction marker, a legend or colorbar, and a truthful scale bar.
11. Register transition matrix, area statistics, change maps, manifest, parameter snapshot, and claim trace artifacts through `record_run_evidence` when they should support UI display, review, or reproduction.
12. Report changes as class transitions relative to selected classification scheme.

## Decision Logic
| Gate | Proceed | Clarify or repair | Stop |
| --- | --- | --- | --- |
| Package imports | `rasterio`, `numpy`, `pandas`, `matplotlib` import successfully | none | imports fail |
| Classification data | valid classes, consistent scheme | class label mismatch needs repair | inconsistent scheme |
| Temporal coverage | sufficient for change detection | coverage gaps need documentation | insufficient coverage |
| CRS/resolution | consistent between time periods | reprojection/resampling needed | mismatch |
| Class labels | defined and documented | labels need user choice | no class labels |

Use `repair` for reprojection, resampling, or class label harmonization. Use `clarify` for classification scheme, temporal coverage, or transition categories. Use `stop` for invalid imports, invalid classification, or unsupported formal claims.

## Output Contract
Return a clear change detection handoff and register artifacts where useful. A JSON manifest is recommended for statistic-heavy runs.

```json
{
  "decision": "proceed",
  "task_family": "land_cover_change",
  "operator": "change_detection",
  "method": "transition_matrix",
  "parameters": {
    "classification_scheme": ["corn", "soybean", "other"],
    "temporal_coverage": ["2018", "2019", "2020", "2021"],
    "pixel_resolution": 27
  },
  "results": {
    "total_area_km2": 50000,
    "class_areas": {
      "corn_2018": 20000,
      "soybean_2018": 18000,
      "other_2018": 12000,
      "corn_2021": 21000,
      "soybean_2021": 17000,
      "other_2021": 12000
    },
    "change_statistics": {
      "corn_gain": 1500,
      "corn_loss": 500,
      "corn_net": 1000,
      "corn_persistence": 19500,
      "soybean_gain": 500,
      "soybean_loss": 1500,
      "soybean_net": -1000,
      "soybean_persistence": 16500
    },
    "transition_matrix": {
      "corn_to_corn": 19500,
      "corn_to_soybean": 300,
      "corn_to_other": 200,
      "soybean_to_corn": 1200,
      "soybean_to_soybean": 16500,
      "soybean_to_other": 300
    }
  },
  "cartographic_elements": {
    "north_arrow": true,
    "legend_or_colorbar": true,
    "scale_bar": true
  },
  "artifacts": [
    {"path": "outputs/transition-matrix.csv", "artifact_stage": "final", "display_hint": "table"},
    {"path": "outputs/area-statistics.csv", "artifact_stage": "final", "display_hint": "table"},
    {"path": "outputs/change-map.tif", "artifact_stage": "final", "display_hint": "raster"}
  ],
  "claim_limits": ["land cover change only", "no trend prediction", "no causal explanation"]
}
```

Recommended manifest fields are `decision`, `task_family`, `operator`, `method`, `parameters`, `results`, `artifacts`, and `claim_limits`.

## Common Mistakes
- Running change detection without `rasterio` or `pandas` package.
- Reporting changes without transition matrix.
- Omitting area statistics from the snapshot.
- Hiding classification errors or inconsistencies in the map.
- Releasing change maps without north direction, legend or colorbar, and scale bar.
- Using inconsistent classification scheme between time periods.

## Detailed Rules

### Change Detection Runbook Rules

#### CHANGE-R01 Package-backed execution is mandatory
The visible script must import `rasterio`, `numpy`, `pandas`, and `matplotlib`. If any import fails, record an environment-not-ready or blocking tool failure and stop. Do not continue with a local reimplementation.

#### CHANGE-R02 Transition matrix must be comprehensive
Transition matrix must show all class-to-class transitions between time periods. Do not report changes without complete transition matrix.

#### CHANGE-R03 Area statistics must be accurate
Area statistics must use pixel counting and resolution for accurate area calculation. Document resolution and pixel-to-area conversion.

#### CHANGE-R04 Classification scheme must be consistent
Classification scheme must be consistent between time periods. If class label harmonization is needed, document the process.

#### CHANGE-R05 Temporal coverage must be sufficient
Change detection needs sufficient temporal coverage for meaningful change analysis. Document temporal resolution and coverage gaps.

#### CHANGE-R06 Change statistics must be recorded
Record gain, loss, net change, and persistence for each class. These statistics are essential for understanding change dynamics.

#### CHANGE-R07 Every map must include cartographic elements
Every change map artifact must show north direction, a legend or colorbar, and a truthful scale bar. This applies to transition and change maps.

#### CHANGE-R08 Artifacts should be registered before strong claims
Register transition matrix, area statistics, change maps, manifest, parameter snapshot, and claim trace through `record_run_evidence` when they support final interpretation. Claims must cite those artifacts or equally visible transcript evidence.

#### CHANGE-R09 Reporting stays bounded
Describe changes as class transitions relative to selected classification scheme. Do not claim trend prediction, causal attribution, or future projection.

## Failure Modes

### Change Detection Runbook Failure Modes

#### handwritten-fallback
Symptom: `rasterio` or `pandas` import fails and the agent computes change detection manually.
Required action: stop and report environment-not-ready.

#### inconsistent-scheme
Symptom: formal change claims are made with inconsistent classification scheme between time periods.
Required action: stop or repair classification scheme.

#### missing-transition-matrix
Symptom: changes are reported without transition matrix.
Required action: repair analysis to include complete transition matrix.

#### missing-cartographic-element
Symptom: a change map lacks north direction, legend or colorbar, or scale bar.
Required action: repair the map before registration or release.

#### incomplete-statistics
Symptom: changes are reported without area statistics or change statistics.
Required action: repair analysis to include comprehensive statistics.

## Worked Examples

### Change Detection Runbook Examples

#### Good: CDL crop change detection
The script imports `rasterio`, `numpy`, `pandas`, and `matplotlib`, loads CDL data for 2018-2021, computes transition matrix, calculates area statistics, creates change maps, and registers matrix, statistics, maps, manifest, and classification scheme.

#### Good: package failure blocks early
The managed environment lacks `rasterio`. The operator records a blocking issue and does not compute change detection by hand.

#### Good: significance disclosure
A map caption says "Crop type transitions, 2018-2021, CDL classification." The unchanged pixels are styled separately.

#### Good: complete change map
The change map includes a north arrow, transition type legend, and scale bar computed from the analysis CRS.

#### Bad: raw class map
The operator maps class values and calls it a "change detection." This is a class map, not a change analysis.

#### Bad: no transition matrix
The operator computes class areas without transition matrix.

## Supporting Files
- None. The run-specific Python script and manifest are written in the managed workspace and registered as evidence.