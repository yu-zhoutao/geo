---
name: geospatial-extent-overlap-check
description: Use when study-area bounds, transformed extents, and mask overlap must be checked before clipping, overlay, or downstream analysis.
compatibility: opencode
---

# Geospatial Extent Overlap Check

## Overview
This skill narrows the CRS safety problem to one practical question: do the relevant spatial objects actually overlap in a common comparison space, and does that overlap correspond to the intended study window? For KDE and other local methods, this is not cosmetic. Zero overlap, tiny accidental overlap, or wrong-mask overlap should end the workflow.

## When to Use
- Before clip or mask operations.
- When preparing a study-area-constrained task.
- When a review role needs to confirm that preprocessing did not silently empty the data.

## Required Inputs
- Harmonized comparison CRS.
- Source and target bounding boxes.
- Study-area mask metadata.
- Point counts before and after clip.

## Workflow
1. Confirm that overlap is being checked in a common comparison CRS.
2. Compare native and transformed bounds.
3. Check actual post-clip point counts, not only bbox intersection.
4. Distinguish partial overlap from effective analytical coverage.
5. Record the decision, overlap ratio, and any empty-result reason.

This skill should always treat overlap as both a spatial and an analytical question. Two layers may overlap geometrically but still fail the analytical requirement if the study mask removes nearly all events, if the remaining points are too sparse, or if the overlap belongs to the wrong study window. For that reason, pair numeric overlap summaries with concrete before/after counts and a short explanation of what the overlap means for the next step.

The textbook's workflow examples repeatedly rely on explicit study regions and clipped analysis extents. That should be reflected here: the observation window is part of the method, not just a convenience for map display.

## Decision Logic
Proceed when transformed overlap is meaningful and post-clip analytical coverage is non-empty.
Clarify when the intended mask or study area is ambiguous.
Repair when overlap can be recovered through deterministic CRS or mask correction.
Stop when verified overlap is zero or the aligned mask still removes all valid observations.

When overlap is very small but nonzero, do not default to `proceed`. Ask whether the remaining support still matches the question the user asked. If the surviving points no longer represent the intended phenomenon or window, escalate the state even if the geometry engine technically returned an intersection.

## Output Contract
Return:
- `decision`
- `comparison_crs`
- `bbox_overlap_ratio`
- `mask_overlap_ratio`
- `pre_clip_count`
- `post_clip_count`
- `reason_code`

## Common Mistakes
- Using bbox overlap as a substitute for actual clip results.
- Forgetting that a valid bbox overlap may still produce almost no valid geometry intersection.
- Hiding empty post-clip results under a successful-looking manifest.
- Clipping to the wrong boundary because the file name looks plausible.

Another mistake is treating the first non-empty overlap as good enough. The right question is not merely whether something survived, but whether enough of the intended phenomenon survived to support the planned operator and downstream claim level.


## Detailed Rules

### Extent Overlap Rules

#### OVL-R01 Same comparison CRS first
Never compare extents in different CRS. If the comparison CRS is not explicit, the result is not trustworthy.

#### OVL-R02 Bbox overlap is necessary but not sufficient
Use bbox overlap to diagnose, but also inspect real post-clip coverage and point counts.

#### OVL-R03 Post-clip emptiness is a blocker
If the analytical layer is empty after a valid clip, the workflow must stop instead of pretending the method succeeded.

#### OVL-R04 Study-area source must be recorded
The overlap result is meaningless if the boundary layer itself is not the intended observation window.

#### OVL-R05 Distinguish tiny overlap from usable overlap
If the overlap is technically nonzero but analytically negligible, raise repair or stop rather than proceeding optimistically.

#### OVL-R06 Record before/after counts and bounds
Later review depends on seeing both the transformed extents and the post-clip observation count.

## Failure Modes

### Extent Overlap Failure Modes

#### overlap-checked-in-mixed-crs
Response: `repair`.

#### bbox-overlap-but-empty-clip
Response: `stop`.

#### wrong-study-mask
Response: `clarify` or `stop`.

#### tiny-accidental-overlap
Response: `repair` or `stop`.

#### nonoverlap-hidden-by-display
Response: `stop`.

## Worked Examples

### Extent Overlap Examples

#### Good
"After reprojection to the comparison CRS, the event layer and study-area mask overlap. Pre-clip count is 2,340 and post-clip count is 2,289, so analytical coverage is non-empty."

#### Good
"Transformed overlap is zero; the run stops and records the blocking evidence."

#### Bad
"The two layers are both visible on screen, so there is probably enough overlap."

#### Bad
"The clip returned zero records, but we can still draw the KDE output extent."

## Supporting Files
- Optional code or snippet files only when executable examples are truly needed.

