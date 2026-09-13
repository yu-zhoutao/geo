---
name: geospatial-crs-projection-safety
description: Use when CRS, projection, units, axis order, or extent alignment must be validated before preprocessing, overlay, clipping, or distance-based geospatial analysis.
compatibility: opencode
---

# Geospatial CRS Projection Safety

## Overview
This skill is a hard gate, not a polite warning. If CRS, units, axis order, or overlap are wrong, downstream analysis can look plausible while being fundamentally invalid. The textbook's workflow and the GPT Pro rulebook both point to the same conclusion: geospatial methods are not interchangeable across coordinate systems, and the runtime must stop instead of guessing when coordinate meaning is unresolved.

For this runtime, the most dangerous mistakes are: missing CRS, confusing `set_crs` with real reprojection, running distance-based work in geographic degrees, trusting visual alignment from a map canvas, and ignoring area-of-use or zero-overlap results.

## When to Use
- Before clipping, masking, overlay, or KDE.
- When source layers have different CRS metadata.
- When units, axis order, or area-of-use could change validity.
- During skeptical review of preprocessing or operator results.

## Required Inputs
- Source CRS metadata and evidence type.
- Intended working CRS and method family.
- Study-area boundary or comparison extent.
- Any transformation logs already produced.

## Workflow
1. Verify whether the source CRS is authoritative, missing, or merely guessed.
2. Distinguish metadata assignment from real coordinate transformation.
3. Check whether the next method requires linear units.
4. Inspect axis order and unit names explicitly instead of assuming x/y or meters.
5. Compare candidate working CRS choices against area-of-use and study extent.
6. Recompute overlap only in a common comparison CRS.
7. Record the exact reason for `proceed`, `clarify`, `repair`, or `stop`.

## Decision Logic
Use `proceed` only when the source CRS is verified, the working CRS fits the method, linear units are correct for distance-based analysis, and verified overlap is nonzero.

Use `clarify` when authoritative CRS evidence may exist but is not yet available, or when more than one plausible working CRS exists and the study design matters.

Use `repair` when the source CRS is known, deterministic reprojection is possible, and overlap or unit safety can be restored without guessing.

Use `stop` when continuing would require invented CRS metadata, angular-distance misuse, or pretending that layers overlap because they look aligned.

## Output Contract
Return:
- `decision`
- `source_crs_authority`
- `source_crs_evidence_type`
- `working_crs_authority`
- `linear_unit`
- `comparison_crs`
- `bbox_overlap_ratio`
- `reason_code`
- `blocking_evidence`

## Common Mistakes
- Guessing WGS84 because coordinates "look like lon/lat".
- Using `set_crs` or equivalent as if it transformed geometry.
- Running KDE, buffers, or nearest-neighbor logic in degrees.
- Forgetting that official CRS axis order may differ from expected x/y handling.
- Choosing a meter-based CRS with no area-of-use check.
- Treating visual alignment in the map canvas as proof of real overlap.


## Detailed Rules

### CRS Projection Safety Rules

#### CRS-001 Missing CRS is a blocker
If the source CRS is absent or unauthoritative, do not continue into clipping, overlay, masking, or distance-based analysis. Coordinate ranges alone are not authoritative proof. The correct action is `clarify` if evidence may exist, otherwise `stop`.

#### CRS-002 Metadata assignment is not reprojection
Assigning a CRS label does not change coordinates. The runtime must separate metadata restoration from real transformation and log both explicitly.

#### CRS-003 Distance-based methods require defensible linear units
KDE, buffering, nearest-neighbor logic, and threshold distances must not run in accidental angular units. Repair by choosing a valid projected CRS or stop.

#### CRS-004 Axis order and units must be inspected
Inspect official axis metadata and unit names, then normalize the transformation path deliberately. Do not assume x/y or meters just because the EPSG code is familiar.

#### CRS-005 Working CRS must fit the study extent
A projected CRS using meters is not automatically valid. Check area of use and whether the chosen transformation covers the observation window.

#### EXT-001 Compare overlap only in a common comparison CRS
Bounding boxes and masks must be compared after verified CRS harmonization. Visual overlap in a map view is not evidence.

#### EXT-002 Mask alignment is both spatial and semantic
The study-area mask must be the intended geography, in the right CRS, and produce a non-empty analytical overlap.

#### CTRL-001 Stop instead of guessing
If the next valid step depends on invented CRS, unresolved units, or false overlap, stop. Helpful-looking continuation is still wrong.

## Failure Modes

### CRS Projection Safety Failure Modes

#### missing-crs-metadata
Coordinates exist, but there is no authoritative CRS metadata.
Response: `clarify` or `stop`.

#### set-crs-used-as-transform
Metadata override is treated as real coordinate conversion.
Response: `repair` only if the true source CRS is known.

#### distance-in-geographic-units
Planar distance-based analysis would run in degrees.
Response: `repair` or `stop`.

#### axis-order-confusion
Lat/lon or unit interpretation is unresolved.
Response: `repair` or `stop`.

#### area-of-use-violation
Working CRS does not defensibly cover the study area.
Response: `repair` or `clarify`.

#### zero-overlap-after-reprojection
Properly transformed bounds still do not overlap.
Response: `stop`.

#### mask-semantic-mismatch
The boundary file exists but is not the intended study window.
Response: `clarify` or `stop`.

## Worked Examples

### CRS Projection Safety Examples

#### Good: real reprojection with unit-safe KDE
"The source points are verified as EPSG:4326. We transformed them to a projected CRS with meter units before bandwidth-based KDE, then recorded the transformation and overlap checks."

#### Good: stop on guessed CRS
"The layer lacks authoritative CRS metadata. Because KDE depends on metric distance, the run stops until CRS evidence is supplied."

#### Good: repair after mismatch
"The point layer and study area start in different CRS. After verified reprojection into a common comparison CRS, overlap is confirmed and preprocessing may continue."

#### Bad: visual alignment as evidence
"The layers line up in the map window, so clipping should be safe."
Why wrong: display reprojection is not a proof of common analytical CRS.

#### Bad: angular-unit KDE
"Run 500 meter KDE directly on EPSG:4326 coordinates."
Why wrong: the method would run in degrees, not the intended linear units.

## Supporting Files
- Optional code or snippet files only when executable examples are truly needed.

