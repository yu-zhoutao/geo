---
name: geospatial-gistar-spatial-weights
description: Use when a Gi* run must construct, validate, repair, or explain spatial weights, neighbor diagnostics, CRS units, and island handling.
compatibility: opencode
---

# Geospatial Gi* Spatial Weights

## Overview
This skill controls the spatial-weight contract for Getis-Ord Gi*. The statistic is only interpretable relative to a neighbor definition, so weights are not an implementation detail. They define the local context, significance pattern, island behavior, and claim boundary.

The prototype defaults are intentionally conservative. Polygon or regular grid support may default to Queen contiguity when no better user-specified model exists. Measured-point demo support may use KNN with an explicit `k`, such as 8, only when the run is not pretending to be formal polygon support. Distance-band weights require metric units and a defensible threshold; the runtime must not guess a business distance.

## When to Use
- A Gi* run needs Queen, Rook, KNN, distance-band, or fixed-neighbor weights.
- Spatial preparation changed CRS or support geometry.
- The input has islands, disconnected units, or suspicious neighbor counts.
- A reviewer needs to decide whether weights make the Gi* output interpretable.

Do not use this skill for IDW neighborhood selection. IDW neighbor rules belong to the IDW runbook.

## Required Inputs
- Prepared input geometry, feature count, CRS, and linear units.
- Intended support type: polygon, grid, aggregated points, or measured-point demo.
- User-specified weight model, if any.
- Study area, scale, and adjacency or distance rationale.
- Island policy and significance reporting policy, if already known.

## Workflow
1. Identify support type before choosing weights.
2. Prefer Queen contiguity for polygon or regular grid prototype runs when no better documented model is available.
3. Use Rook, distance-band, or KNN only when the choice is documented and fits the study question.
4. For distance-band and KNN, verify metric CRS and record units, threshold or `k`, and projection decision.
5. Compute neighbor diagnostics: minimum, median or mean, maximum, island count, and whether any unit effectively neighbors all other units.
6. Run an alternative weight diagnostic or neighbor sensitivity check when more than one plausible local-neighborhood definition exists; weight choice is not a cosmetic parameter.
7. Apply island policy explicitly. Default policy marks island Gi* results as not interpretable or NA.
8. Return a weights contract to the Gi* runbook and register it as a parameter snapshot or verification fact.

## Decision Logic
| Weight situation | Decision | Reason code |
| --- | --- | --- |
| Polygon or grid support, no user model | `proceed` with Queen contiguity | `QUEEN_DEFAULT` |
| Polygon support, Queen creates islands | `repair` or `clarify` | `ISLAND_POLICY_REQUIRED` |
| Distance threshold supplied and CRS is metric | `proceed` | `DISTANCE_BAND_VALID` |
| Distance threshold absent but distance-band requested | `clarify` | `MISSING_DISTANCE_THRESHOLD` |
| Distance or KNN requested in geographic CRS | `repair` or `stop` | `METRIC_CRS_REQUIRED` |
| Every unit neighbors all others | `stop` | `WEIGHTS_TOO_GLOBAL` |
| Some units have no neighbors and policy is not recorded | `repair` | `ISLAND_POLICY_MISSING` |

Use `repair` when reprojection, island labeling, or a documented weight adjustment can preserve the design. Use `clarify` when the scale or policy is a domain choice. Use `stop` when weights cannot represent a meaningful local neighborhood.

## Output Contract
Return a clear weights handoff. A compact JSON block is recommended because the diagnostics are structured.

```json
{
  "decision": "proceed",
  "weights": {
    "type": "Queen contiguity",
    "transform": "B",
    "crs": "EPSG:32650",
    "distance_units": "metre",
    "neighbor_count_min": 1,
    "neighbor_count_median": 5,
    "neighbor_count_max": 9,
    "island_count": 0,
    "island_weight": "nan"
  },
  "diagnostics": {
    "all_units_neighbors": false,
    "zero_neighbor_units": [],
    "alternative_weight_diagnostic": "Rook comparison available for polygon support",
    "neighbor_sensitivity": "KNN k=6, k=8, k=10 compared for demo point support"
  },
  "reason_code": "QUEEN_DEFAULT",
  "claim_limits": ["local association depends on Queen contiguity weights"]
}
```

Recommended handoff fields are `decision`, `weights.type`, `weights.transform`, `neighbor_count_min`, `neighbor_count_median`, `neighbor_count_max`, `island_count`, `island_weight`, `reason_code`, and `claim_limits`.

## Common Mistakes
- Using distance-band weights in longitude/latitude degrees.
- Changing from Queen to KNN just to remove islands without recording the repair.
- Treating isolated units as nonsignificant without marking them as islands.
- Choosing a threshold distance because it "looks reasonable" on the map.
- Forgetting that all-units neighbor graphs destroy local interpretation.

## Detailed Rules

### Gi* Spatial Weight Rules

#### GWEIGHT-R01 Support type comes before weight type
Polygon, grid, aggregated point, and demo measured-point supports have different neighbor semantics. Do not choose weights before the support is stated and recorded.

#### GWEIGHT-R02 Queen contiguity is the polygon prototype default
For polygon or regular grid units without a user-specified model, the prototype can use Queen contiguity and record why it was selected. If Rook would better match the study question, ask or record that choice.

#### GWEIGHT-R03 KNN is bounded and explicit
Measured-point demo runs may use KNN with an explicit `k`, such as 8, when contiguity is unavailable. KNN is not a silent fix for polygon islands in formal support unless a repair decision explains the change.

#### GWEIGHT-R04 Distance-based weights require metric units
Distance-band and nearest-neighbor calculations require a defensible metric CRS. If CRS is geographic but authoritative, repair by reprojection. If CRS is missing, stop unless the user supplies authoritative CRS evidence.

#### GWEIGHT-R05 Distance thresholds are domain choices
A distance band needs a user, dataset, or diagnostic scale. The runtime may propose candidate thresholds from nearest-neighbor diagnostics, but must not guess a business distance and present it as fact.

#### GWEIGHT-R06 Neighbor diagnostics gate interpretation
Record minimum, median or mean, maximum neighbor counts, island count, and whether any unit neighbors all or nearly all units. Any zero-neighbor unit under a non-island-aware policy blocks interpretation.

#### GWEIGHT-R07 Islands are explicit, not hidden
Default island policy marks island Gi* values as NA or not interpretable. Attaching islands to nearest neighbors, dropping them, or changing weight models requires `repair` or `clarify` evidence.

#### GWEIGHT-R08 Transform is part of the statistic
Record the weight transform, with prototype default `transform='B'` unless another transform is selected and justified. The transform must match the PySAL call in the Gi* runbook.

#### GWEIGHT-R09 Weight metadata travels with every artifact
The statistic table, classified map, manifest, and report should all reference the weight type, transform, neighbor diagnostics, island policy, and CRS units. A map without weight metadata is not release-ready.

#### GWEIGHT-R10 Weight choice is substantive
Weight choice is not a cosmetic parameter. If Queen, Rook, distance-band, or KNN choices are all plausible for the support, provide an alternative weight diagnostic or neighbor sensitivity evidence before the Gi* report makes strong claims. Materially unstable classifications require repair or narrower claims.

## Failure Modes

### Gi* Spatial Weight Failure Modes

#### degree-distance-band
Symptom: the script computes distance thresholds in EPSG:4326 degrees.
Required action: repair CRS or stop.

#### island-silence
Symptom: units with no neighbors appear as nonsignificant without explanation.
Required action: mark islands as NA or record a repair.

#### threshold-guess
Symptom: the runtime chooses 1000 m because it is a round number.
Required action: clarify or derive a diagnostic candidate and ask.

#### missing-weight-sensitivity
Symptom: the weights contract records one neighbor definition but no alternative weight diagnostic or neighbor sensitivity despite multiple plausible definitions.
Required action: repair by running the diagnostic or explicitly narrowing the result to a demo.

#### too-global-weights
Symptom: every unit neighbors almost every other unit.
Required action: stop because local interpretation is lost.

#### support-mismatch
Symptom: polygon weights are built against a table whose row order or geometry count no longer matches the attribute table.
Required action: repair and verify feature count alignment.

## Worked Examples

### Gi* Spatial Weight Examples

#### Good: Queen default
District polygons have valid topology, no user weight model, and no islands. The runtime records Queen contiguity, `transform='B'`, neighbor count min, median, max, and island count 0.

#### Good: distance-band clarification
The user asks for distance-band Gi*. The data are in a metric CRS but no threshold is specified. The runtime reports nearest-neighbor diagnostics and asks which scale should define neighbors.

#### Good: island repair
A remote polygon has no Queen neighbors. The runtime marks it as not interpretable and records `island_weight` policy instead of coloring it as a coldspot.

#### Bad: KNN as invisible patch
Queen weights create islands, so the script silently switches to KNN k=8 and reports normal Gi* results. This changes neighborhood semantics and must be recorded as repair or clarification.

#### Bad: no weight metadata in map
A final map labels hotspots but omits weight type and significance policy. A reader cannot reproduce or interpret the cluster definition.

## Supporting Files
- None. Weight summaries should be recorded as parameter snapshots or verification facts in the run ledger.
