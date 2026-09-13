---
name: geospatial-terrain-runbook
description: Use when a terrain analysis task is ready for slope, aspect, roughness, TWI execution, classification, artifact registration, and bounded reporting.
compatibility: opencode
---

# Geospatial Terrain Analysis Runbook

## Overview
This skill governs the executable terrain analysis path. The operator must use `rasterio`, `numpy`, `scipy`, and `matplotlib` from the managed geospatial environment for slope, aspect, roughness, and TWI computation.

Terrain analysis is evidence-heavy. A valid run needs DEM data, derivative parameters, classification scheme, terrain statistics, terrain maps, and claim boundaries. Without those records, a final "terrain" statement is not auditable.

## When to Use
- Triage selected `terrain_analysis` and slope/aspect/roughness/TWI.
- Data audit confirmed valid DEM data with sufficient resolution.
- The operator must compute terrain derivatives, create classification maps, and register artifacts.

Do not use this skill to decide land cover classification or trend detection. Use appropriate methods first.

## Required Inputs
- Study-design and data-audit contracts.
- Prepared DEM raster path, resolution, CRS, and spatial extent.
- Terrain derivatives to compute (slope, aspect, roughness, TWI).
- Classification scheme for slope, aspect, and elevation zones.
- Workspace command contract from `get_session_context`.

## Workflow
1. Read `get_session_context` and confirm package readiness includes `rasterio`, `numpy`, `scipy`, and `matplotlib`.
2. Verify DEM data, resolution, CRS, spatial extent, and NoData percentage.
3. Import `rasterio`, `numpy`, `scipy`, and `matplotlib` in the visible script. If import fails, stop; do not hand-code terrain fallback.
4. Load DEM using `rasterio`.
5. Compute slope using `numpy.gradient` or `scipy.ndimage.sobel`.
6. Compute aspect using `numpy.gradient` and trigonometry.
7. Compute terrain roughness or ruggedness index using appropriate window size.
8. Compute topographic wetness index (TWI) using slope and contributing area.
9. Create classification maps: slope classes (flat, gentle, moderate, steep), aspect classes (N, NE, E, SE, S, SW, W, NW), elevation zones.
10. Ensure every terrain map artifact, including slope, aspect, roughness, and TWI maps, includes a north arrow or north-direction marker, a legend or colorbar, and a truthful scale bar.
11. Register statistics table, classification maps, manifest, parameter snapshot, and claim trace artifacts through `record_run_evidence` when they should support UI display, review, or reproduction.
12. Report terrain characteristics as spatial patterns relative to selected classification schemes.

## Decision Logic
| Gate | Proceed | Clarify or repair | Stop |
| --- | --- | --- | --- |
| Package imports | `rasterio`, `numpy`, `scipy`, `matplotlib` import successfully | none | imports fail |
| DEM data | valid elevation values, acceptable NoData percentage | NoData handling needed | excessive NoData |
| Resolution | sufficient for terrain analysis | resolution mismatch needs resampling | insufficient resolution |
| CRS | valid and consistent | reprojection needed | invalid CRS |
| Classification | scheme defined and documented | scheme needs user choice | no classification scheme |

Use `repair` for reprojection, resampling, or NoData imputation. Use `clarify` for classification scheme, derivative selection, or window size. Use `stop` for invalid imports, invalid DEM, or unsupported formal claims.

## Output Contract
Return a clear terrain handoff and register artifacts where useful. A JSON manifest is recommended for parameter-heavy runs.

```json
{
  "decision": "proceed",
  "task_family": "terrain_analysis",
  "operator": "terrain",
  "method": "slope_aspect_roughness_twi",
  "parameters": {
    "dem_resolution": 30,
    "slope_units": "degrees",
    "aspect_classes": 8,
    "roughness_window": 3,
    "elevation_zones": [0, 200, 500, 1000, 1500, 2000]
  },
  "results": {
    "total_pixels": 1000000,
    "elevation_range": [50, 2500],
    "slope_range": [0, 75],
    "mean_slope": 12.5,
    "flat_pct": 15.0,
    "gentle_pct": 35.0,
    "moderate_pct": 30.0,
    "steep_pct": 20.0,
    "aspect_distribution": {
      "N": 12.5, "NE": 12.5, "E": 12.5, "SE": 12.5,
      "S": 12.5, "SW": 12.5, "W": 12.5, "NW": 12.5
    }
  },
  "cartographic_elements": {
    "north_arrow": true,
    "legend_or_colorbar": true,
    "scale_bar": true
  },
  "artifacts": [
    {"path": "outputs/terrain-stats.csv", "artifact_stage": "final", "display_hint": "table"},
    {"path": "outputs/slope-map.tif", "artifact_stage": "final", "display_hint": "raster"},
    {"path": "outputs/aspect-map.tif", "artifact_stage": "final", "display_hint": "raster"},
    {"path": "outputs/elevation-zones.tif", "artifact_stage": "final", "display_hint": "raster"}
  ],
  "claim_limits": ["terrain characteristics only", "no land cover classification", "no trend detection"]
}
```

Recommended manifest fields are `decision`, `task_family`, `operator`, `method`, `parameters`, `results`, `artifacts`, and `claim_limits`.

## Common Mistakes
- Running terrain derivatives without `rasterio`, `numpy`, or `scipy` package.
- Reporting terrain characteristics without classification.
- Omitting classification scheme from the snapshot.
- Hiding NoData values or edge effects in the map.
- Releasing terrain maps without north direction, legend or colorbar, and scale bar.
- Using insufficient DEM resolution for formal claims.

## Detailed Rules

### Terrain Runbook Rules

#### TERRAIN-R01 Package-backed execution is mandatory
The visible script must import `rasterio`, `numpy`, `scipy`, and `matplotlib`. If any import fails, record an environment-not-ready or blocking tool failure and stop. Do not continue with a local reimplementation.

#### TERRAIN-R02 Classification scheme must be comprehensive
Slope classification must include flat, gentle, moderate, and steep classes. Aspect classification must include 8 cardinal directions. Elevation zones must be defined and documented.

#### TERRAIN-R03 DEM data must be valid
DEM must have valid elevation values and acceptable NoData percentage. Document NoData handling and threshold for excluding pixels.

#### TERRAIN-R04 Resolution must be sufficient
DEM resolution must be sufficient for terrain analysis. If resampling is needed, document the process and verify resolution.

#### TERRAIN-R05 NoData handling must be documented
NoData values must be handled explicitly. Document the percentage of NoData values, imputation method if used, and threshold for excluding pixels.

#### TERRAIN-R06 Derivative parameters must be recorded
Record slope units (degrees or percent), aspect classes, roughness window size, and TWI parameters. These parameters are essential for reproducibility.

#### TERRAIN-R07 Every map must include cartographic elements
Every terrain map artifact must show north direction, a legend or colorbar, and a truthful scale bar. This applies to slope, aspect, roughness, and TWI maps.

#### TERRAIN-R08 Artifacts should be registered before strong claims
Register statistics table, classification maps, manifest, parameter snapshot, and claim trace through `record_run_evidence` when they support final interpretation. Claims must cite those artifacts or equally visible transcript evidence.

#### TERRAIN-R09 Reporting stays bounded
Describe terrain characteristics as spatial patterns relative to selected classification schemes. Do not claim land cover classification, trend detection, or causal explanation.

## Failure Modes

### Terrain Runbook Failure Modes

#### handwritten-fallback
Symptom: `rasterio`, `numpy`, or `scipy` import fails and the agent computes terrain derivatives manually.
Required action: stop and report environment-not-ready.

#### insufficient-resolution
Symptom: formal terrain claims are made with insufficient DEM resolution.
Required action: stop or mark as demo-only.

#### nodata-coverup
Symptom: pixels with excessive NoData values are included in analysis without documentation.
Required action: repair data preprocessing and document NoData policy.

#### missing-cartographic-element
Symptom: a terrain map lacks north direction, legend or colorbar, or scale bar.
Required action: repair the map before registration or release.

#### incomplete-classification
Symptom: terrain characteristics are reported without classification scheme.
Required action: repair analysis to include slope, aspect, and elevation classes.

## Worked Examples

### Terrain Runbook Examples

#### Good: DEM terrain analysis
The script imports `rasterio`, `numpy`, `scipy`, and `matplotlib`, loads DEM data, computes slope, aspect, roughness, TWI, creates classification maps, and registers statistics, maps, manifest, and classification scheme.

#### Good: package failure blocks early
The managed environment lacks `rasterio`. The operator records a blocking issue and does not compute terrain derivatives by hand.

#### Good: significance disclosure
A map caption says "Slope classification (flat, gentle, moderate, steep) from 30m DEM." The NoData pixels are styled separately.

#### Good: complete classification map
The slope classification map includes a north arrow, slope class legend, and scale bar computed from the analysis CRS.

#### Bad: raw slope map
The operator maps slope values and calls it a "terrain analysis." This is a slope map, not a terrain classification.

#### Bad: no classification scheme
The operator computes slope without classification scheme.

## Supporting Files
- None. The run-specific Python script and manifest are written in the managed workspace and registered as evidence.