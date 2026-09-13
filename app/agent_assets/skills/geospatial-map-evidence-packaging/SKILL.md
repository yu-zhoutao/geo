---
name: geospatial-map-evidence-packaging
description: Use when verified geospatial outputs must be packaged into transcript-ready maps, captions, disclosures, and artifact references.
compatibility: opencode
---

# Geospatial Map Evidence Packaging

## Overview
This skill turns valid outputs into a usable evidence package. It is downstream of analysis and review, but it is not cosmetic. The package should help a human reader understand what was computed, with what assumptions, and with what limits.

## When to Use
- After a verified operator artifact exists.
- Before final transcript rendering.
- When preparing thesis-ready figures.

## Required Inputs
- Verified operator outputs.
- Parameter record.
- Cartographic honesty findings.
- Claim limits.

## Workflow
1. Assemble the map specification.
2. Confirm the map image or HTML map contains a north arrow or north-direction marker, a legend or colorbar, and a truthful scale bar.
3. Prepare a caption that discloses method and parameters.
4. Add artifact references and any required caveat notes.
5. Ensure the package is aligned with review findings.

Treat packaging as the final translation layer between technical artifacts and a human reader. Start from the operator artifact, then ask what a skeptical but non-omniscient reader would need to interpret it safely. In most cases that means method name, study window, bandwidth, cell size, north direction, legend or colorbar, scale bar, and at least one claim-boundary sentence. If any of those items are missing, the package is not ready even if the map image itself exists.

The three cartographic elements are required for every map, not only thesis-ready final figures. Intermediate diagnostic maps, sensitivity maps, preview maps, and final maps must all carry a north arrow or north-direction marker, a legend or colorbar, and a truthful scale bar. If the CRS or units do not support a truthful scale bar, repair the CRS or stop the map release instead of drawing a decorative or false scale.

For thesis-facing work, packaging should also anticipate reuse outside the live transcript: figures may later be moved into slides, papers, or appendices. The package should therefore be self-explanatory enough to survive that move without silently dropping context.

## Decision Logic
Proceed when the map package is truthful, complete, and aligned with review.
Clarify when disclosure expectations are still unresolved.
Repair when the map exists but the package is incomplete or misleading.
Stop when a truthful map package cannot be assembled from the current artifacts.

When you are unsure whether to `repair` or `stop`, ask whether the current package would still be honest if it were copied into a thesis chapter without extra oral explanation. If not, repair or block it now.

## Output Contract
Return:
- `decision`
- `map_spec`
- `caption`
- `disclosure_items`
- `cartographic_elements`
- `artifact_references`
- `reason_code`

## Common Mistakes
- Shipping a map without parameter disclosure.
- Treating intermediate maps as exempt from north arrow, legend, or scale-bar requirements.
- Writing a caption that is stronger than the report body.
- Forgetting to link the figure to its artifact paths.

Also avoid packaging the same map twice with different implied meaning. If the transcript card, figure title, and caption disagree on whether the result is density, hotspot significance, or risk, the package is internally inconsistent and should be repaired.


## Detailed Rules

### Map Evidence Packaging Rules

#### MAP-R01 Every map needs a caption with method disclosure
Name the method and the observation window.

#### MAP-R01A Every map needs three cartographic elements
Every static or interactive map artifact must include a north arrow or north-direction marker, a legend or colorbar, and a truthful scale bar before handoff, registration, or release.

#### MAP-R02 Parameter disclosure is part of packaging
Bandwidth, cell size, and units belong in the package, not only in a side artifact.

#### MAP-R03 Package must link back to artifacts
The figure should be traceable to the exact map, parameter, and claim-trace artifacts.

#### MAP-R04 Package must preserve limitations
Do not remove caveats to make the map easier to present.

#### MAP-R05 Packaging obeys prior review findings
If skeptical review or cartographic honesty review requested repairs, packaging cannot ignore them.

#### MAP-R06 Scale bars must be truthful
If CRS or unit evidence is unresolved, repair the projection or block the map instead of adding a fake or approximate-looking scale bar.

## Failure Modes

### Map Evidence Packaging Failure Modes

#### caption-without-disclosure
Response: `repair`.

#### missing-cartographic-element
Response: `repair`.

#### untruthful-scale-bar
Response: `repair` or `stop`.

#### artifact-links-missing
Response: `repair`.

#### caveat-erasure
Response: `repair` or `stop`.

#### package-stronger-than-analysis
Response: `repair`.

#### review-findings-ignored
Response: `stop`.

## Worked Examples

### Map Evidence Packaging Examples

#### Good
Caption: "KDE density surface of recorded incidents within the observed study area. Bandwidth 1000 m, cell size 250 m. Interpret as descriptive concentration only."

#### Good
An intermediate sensitivity map includes a north arrow, a colorbar explaining density values, and a scale bar computed in the metric analysis CRS.

#### Good
The package links to map artifact, parameter snapshot, and claim trace.

#### Bad
"Hotspot map of danger zones" with no method disclosure.

#### Bad
The diagnostic preview omits a scale bar because it is "only intermediate."

#### Bad
The figure appears in the transcript but cannot be traced to any artifact path.

## Supporting Files
- Optional code or snippet files only when executable examples are truly needed.
