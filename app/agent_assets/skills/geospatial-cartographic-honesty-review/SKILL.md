---
name: geospatial-cartographic-honesty-review
description: Use when a geospatial figure or map package must be checked for truthful titles, disclosures, symbology, and non-misleading visual rhetoric.
compatibility: opencode
---

# Geospatial Cartographic Honesty Review

## Overview
This skill treats map design as an analytic integrity problem, not just an aesthetic one. A map can mislead through title, missing north direction, legend, scale bar, masking, color, omission of units, or omission of parameter disclosure even when the underlying raster is technically valid.

## When to Use
- Before a map is shown to the user.
- During skeptical review.
- When a caption or title is rewritten.

## Required Inputs
- Map specification.
- Caption draft.
- Parameter record.
- Claim trace.

## Workflow
1. Check whether the title names the method honestly.
2. Check whether the map contains the three required cartographic elements: north arrow or north-direction marker, legend or colorbar, and truthful scale bar.
3. Check whether legend, units, bandwidth, cell size, and study area are disclosed.
4. Check whether masks, exclusions, or NoData are visible or documented.
5. Check whether visual choices imply significance or certainty the method does not support.

Do this review in the order a skeptical reader would see the figure. Start with title and caption because they frame interpretation before the reader studies the map. Then inspect the required north direction, legend or colorbar, scale bar, and the visual hierarchy: what is emphasized, what is muted, and whether the palette creates drama that the method does not justify. Only after that should you inspect technical disclosure items such as units, bandwidth, and cell size. This order matters because a figure can already be misleading before any parameter note is read.

The textbook examples are useful here because they show how strongly map figures shape interpretation in spatial analysis chapters. The runtime should therefore assume that a misleading map is not a minor presentation defect. It is an analytical integrity defect.

## Decision Logic
Proceed when the figure is truthful and sufficiently disclosed.
Clarify when the intended audience or disclosure standard is still unresolved.
Repair when the map is valid but visually misleading or under-documented.
Stop when the figure materially misrepresents the analysis.

Material misrepresentation includes more than factual error. If the title says hotspot significance when the method is descriptive KDE, if exclusions are hidden in a way that suggests full coverage, or if visual rhetoric strongly implies risk or certainty, this skill should escalate the issue instead of treating it as a cosmetic note.

## Output Contract
Return:
- `decision`
- `honesty_findings`
- `missing_disclosures`
- `missing_cartographic_elements`
- `forbidden_visual_moves`
- `reason_code`

## Common Mistakes
- Calling a KDE figure a hotspot significance map.
- Allowing an intermediate or final map to omit north direction, legend, or scale bar.
- Using saturated palettes and dramatic titles to imply stronger evidence than exists.
- Hiding study-area masks and exclusions.
- Omitting units, bandwidth, or cell size from caption and legend context.

Also watch for the inverse problem: a technically correct but unreadable map that forces the report text to do all the interpretive work. If the legend cannot be read, if study area context is absent, or if symbol hierarchy is chaotic, the figure fails its role as evidence packaging and should be repaired.


## Detailed Rules

### Cartographic Honesty Rules

#### CART-R01 Title must name the method honestly
If the figure is KDE, say KDE or density, not significance or risk.

#### CART-R02 Core disclosures are mandatory
Show or disclose study area, units, bandwidth, and cell size.

#### CART-R02A Three cartographic elements are mandatory
Every map artifact, including intermediate process maps, must show north direction, a legend or colorbar, and a scale bar.

#### CART-R02B Scale bars must be supported by CRS evidence
If the current CRS or unit evidence cannot support a truthful scale bar, the map needs repair or stop rather than a decorative scale.

#### CART-R03 Masks and exclusions must not disappear silently
Blank or excluded areas must be visible or explicitly explained.

#### CART-R04 Symbology must not inflate certainty
Avoid color or wording that implies inferential confidence unsupported by the method.

#### CART-R05 Captions inherit claim discipline
Map captions are part of the argument and must obey the same claim limits as the report body.

## Failure Modes

### Cartographic Honesty Failure Modes

#### misleading-title
Response: `repair`.

#### missing-parameter-disclosure
Response: `repair`.

#### missing-cartographic-element
Response: `repair`.

#### fake-or-unsupported-scale-bar
Response: `repair` or `stop`.

#### hidden-mask-or-nodata
Response: `repair` or `stop`.

#### rhetorically-inflated-symbology
Response: `repair`.

#### figure-implies-significance
Response: `repair` or `stop`.

## Worked Examples

### Cartographic Honesty Examples

#### Good
Title: "KDE density surface of recorded events"
Caption includes study area, bandwidth, cell size, and interpretation limit.

#### Good
The map includes a north arrow, colorbar, and scale bar computed from the metric analysis CRS.

#### Good
Mask and excluded areas are visible and described.

#### Bad
Title: "Significant hotspots of danger"
Why wrong: unsupported inferential and risk language.

#### Bad
No units, no bandwidth, and no study area are disclosed.

#### Bad
The map is described as an intermediate check, so it omits the legend and scale bar.

## Supporting Files
- Optional code or snippet files only when executable examples are truly needed.
