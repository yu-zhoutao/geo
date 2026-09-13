---
name: geospatial-gistar-runbook
description: Use when a Getis-Ord Gi* task is ready for PySAL-backed execution, significance metadata, artifact registration, and bounded reporting.
compatibility: opencode
---

# Geospatial Gi* Runbook

## Overview
This skill governs the executable Getis-Ord Gi* path. The operator must use PySAL from the managed geospatial environment, specifically `esda` and `libpysal`, rather than a local reimplementation of the statistic or spatial weights. The script must call `esda.G_Local` with `star=True` so the statistic is Gi* rather than plain local G.

Gi* is evidence-heavy. A valid run needs spatial support, numeric attribute, weight construction, transform, permutations, seed, island policy, significance threshold, multiple-testing policy, statistic fields, maps, tables, and claim boundaries. Without those records, a final "hotspot" statement is not auditable.

## When to Use
- Triage selected `spatial_hotspot` and Getis-Ord Gi*.
- Data audit confirmed valid aggregated support and numeric attribute.
- Spatial-weight construction is ready or has a bounded repair path.
- The operator must run PySAL, create Gi* tables or maps, and register artifacts.

Do not use this skill to decide KDE versus Gi*. Use `geospatial-gistar-method-selection` first.

## Required Inputs
- Study-design and data-audit contracts.
- Prepared vector layer path, unit identifier, attribute field, feature count, CRS, and geometry type.
- Spatial weights contract from `geospatial-gistar-spatial-weights`.
- Significance settings, permutations, seed, and FDR or multiple-testing policy.
- Workspace command contract from `get_session_context`.

## Workflow
1. Read `get_session_context` and confirm package readiness includes `esda` and `libpysal`.
2. Verify feature count, attribute field variation, finite values, geometry count, and spatial support.
3. Import `esda` and `libpysal` in the visible script. If import fails, stop; do not hand-code Gi* fallback.
4. Build or load spatial weights from the weight contract. Verify neighbor diagnostics and island policy before interpreting results.
5. Run an alternative weight diagnostic or neighbor sensitivity check when the selected weight model may change classifications; weight choice is not a cosmetic parameter.
6. Execute `esda.G_Local(values, weights, star=True, transform='B', permutations=999, seed=<fixed seed>, island_weight=<policy>)` or an equivalent explicit call using recorded user overrides.
7. Create statistic fields such as `gi_z`, `gi_p_sim`, `gi_p_norm` when available, `gi_bin`, `hotcold_label`, neighbor counts, and weight metadata.
8. Apply and record the significance threshold and FDR or multiple-testing policy. Do not imply stronger control than the recorded policy supports.
9. Ensure every Gi* map artifact, including weight-diagnostic, sensitivity, and classified-preview maps, includes a north arrow or north-direction marker, a legend or colorbar, and a truthful scale bar.
10. Register table, map, manifest, parameter snapshot, weight diagnostics, and claim trace artifacts through `record_run_evidence` when they should support UI display, review, or reproduction.
11. Report hotspots and coldspots as local clusters relative to selected weights and significance settings.

## Decision Logic
| Gate | Proceed | Clarify or repair | Stop |
| --- | --- | --- | --- |
| PySAL imports | `esda` and `libpysal` import successfully | none | imports fail |
| Feature count | 30 or more valid units | fewer than 30 can be demo-only only if explicit | fewer than 30 for formal claims |
| Attribute | numeric, finite, varying, semantically meaningful | count-versus-rate policy unclear | nonnumeric, constant, all zero, all one, all missing |
| Weights | valid neighbor graph and recorded diagnostics | repairable islands or threshold choice | invalid graph or all-units neighbors |
| Significance | p-value source, alpha, and FDR policy recorded | policy needs user choice | no significance metadata |

Use `repair` for reprojection, valid field casting, or a weight model adjustment that preserves the design. Use `clarify` for count-rate, aggregation support, threshold distance, or demo-only consent. Use `stop` for invalid imports, invalid attributes, invalid weights, or unsupported formal claims.

## Output Contract
Return a clear Gi* handoff and register artifacts where useful. A JSON manifest is recommended for statistic-heavy runs.

```json
{
  "decision": "proceed",
  "task_family": "spatial_hotspot",
  "operator": "gistar",
  "pysal_method": "esda.G_Local",
  "parameters": {
    "attribute_field": "rate",
    "statistic_variant": "Gi*",
    "star": true,
    "transform": "B",
    "permutations": 999,
    "seed": 20260429,
    "island_weight": "nan"
  },
  "weights": {
    "type": "Queen contiguity",
    "neighbor_count_min": 1,
    "neighbor_count_median": 5,
    "neighbor_count_max": 9,
    "alternative_weight_diagnostic": "Rook comparison changed 1 of 42 hot/cold labels",
    "neighbor_sensitivity": "k=6 and k=10 tested for point-support demo"
  },
  "significance": {
    "alpha": 0.05,
    "p_value": "gi_p_sim",
    "FDR": "benjamini_hochberg"
  },
  "cartographic_elements": {
    "north_arrow": true,
    "legend_or_colorbar": true,
    "scale_bar": true
  },
  "artifacts": [
    {"path": "outputs/gistar-table.csv", "artifact_stage": "final", "display_hint": "table"}
  ],
  "claim_limits": ["local spatial association only", "no causal explanation"]
}
```

Recommended manifest fields are `decision`, `task_family`, `operator`, `pysal_method`, `parameters`, `weights`, `significance`, `artifacts`, and `claim_limits`.

## Common Mistakes
- Calling `esda.G_Local` without `star=True`.
- Running a handmade Gi* formula after PySAL import failure.
- Omitting transform, permutations, seed, or `island_weight` from the snapshot.
- Reporting raw high values as significant hotspots.
- Treating p-values as globally corrected when FDR was not applied.
- Hiding islands or nonsignificant units in the map.
- Releasing intermediate or final Gi* maps without north direction, legend or colorbar, and scale bar.

## Detailed Rules

### Gi* Runbook Rules

#### GISTAR-R01 PySAL-backed execution is mandatory
The visible script must import `esda` and `libpysal`. If either import fails, record an environment-not-ready or blocking tool failure and stop. Do not continue with a local reimplementation.

#### GISTAR-R02 Star semantics must be explicit
The statistic must be Gi*, not plain local G. The method call must use `esda.G_Local` with `star=True`, and the evidence must record `statistic_variant` as `Gi*`.

#### GISTAR-R03 Default PySAL parameters are recorded
Prototype defaults are `permutations=999`, a fixed seed, and `transform='B'` unless the user selects a documented alternative. Record the seed so simulated p-values are reproducible.

#### GISTAR-R04 Feature count and attribute gates block invalid significance
Formal Gi* needs enough spatial units for meaningful local inference. Fewer than 30 units blocks formal claims unless the run is explicitly demo-only. Nonnumeric, non-finite, constant, all-zero, all-one, or semantically meaningless attributes stop the run.

#### GISTAR-R05 Weights must be validated before interpretation
Spatial weights must match feature count, have recorded neighbor diagnostics, and handle islands according to policy. Invalid weights produce `repair` or `stop`, not a map with hidden defects.

#### GISTAR-R05A Weight sensitivity is substantive evidence
Weight choice is not a cosmetic parameter. When the task or support admits more than one plausible neighbor definition, run an alternative weight diagnostic or neighbor sensitivity check before release. If hot/cold classification changes materially, return `repair` or narrow the claim to the stable portion of the result.

#### GISTAR-R06 Statistic table fields are required
The output table should contain unit identifiers, input values, Gi* statistic values, `gi_z`, `gi_p_sim`, `gi_p_norm` when available, `gi_bin`, `hotcold_label`, neighbor counts, and weight metadata. Missing core fields require repair before release.

#### GISTAR-R07 Multiple-testing policy is part of the claim
If the report uses "statistically significant", evidence must state whether raw local p-values, simulated p-values, and FDR or another correction were used. Do not imply FDR when it was not applied.

#### GISTAR-R08 Artifacts should be registered before strong claims
Register statistic table, classified map, manifest, parameter snapshot, weights summary, and claim trace through `record_run_evidence` when they support final interpretation. Claims must cite those artifacts or equally visible transcript evidence.

#### GISTAR-R08A Every Gi* map must include cartographic elements
Every Gi* map artifact must show north direction, a legend or colorbar, and a truthful scale bar. This applies to weight-diagnostic, sensitivity, classified-preview, and final maps.

#### GISTAR-R09 Reporting stays bounded
Describe hotspots and coldspots as local clusters relative to the selected spatial weights and significance configuration. Do not claim causality, risk proof, density estimation, interpolation, or isolated outlier detection.

## Failure Modes

### Gi* Runbook Failure Modes

#### handwritten-fallback
Symptom: `esda` import fails and the agent computes a local formula manually.
Required action: stop and report environment-not-ready.

#### plain-g-not-star
Symptom: the script computes local G without `star=True` but labels output Gi*.
Required action: repair script and rerun.

#### invisible-significance-policy
Symptom: the report says significant hotspots but does not record p-value source, alpha, or FDR.
Required action: repair evidence and report language.

#### island-coverup
Symptom: units with no neighbors are colored as nonsignificant without recording island policy.
Required action: repair weights summary and map metadata.

#### weight-diagnostic-missing
Symptom: the report treats the selected weights as final without an alternative weight diagnostic or neighbor sensitivity check, even though another plausible weight model exists.
Required action: run the diagnostic or return repair.

#### missing-cartographic-element
Symptom: a Gi* map lacks north direction, legend or colorbar, or scale bar.
Required action: repair the map before registration or release.

#### raw-value-ranking
Symptom: top raw values are labeled hotspots without statistic fields.
Required action: stop or rerun Gi*.

## Worked Examples

### Gi* Runbook Examples

#### Good: polygon Queen contiguity
The script imports `esda` and `libpysal`, builds Queen weights, records neighbor diagnostics, runs `esda.G_Local` with `star=True`, `permutations=999`, fixed seed, and `transform='B'`, then registers table, map, manifest, and FDR policy.

#### Good: PySAL failure blocks early
The managed environment lacks `esda`. The operator records a blocking issue and does not compute Gi* by hand.

#### Good: significance disclosure
A map caption says "Gi* hotspots at alpha 0.05 using simulated p-values with FDR correction, Queen contiguity weights." The nonsignificant and island units are styled separately.

#### Good: complete classified map
The classified Gi* map includes a north arrow, hot/cold/nonsignificant legend, and scale bar computed from the analysis CRS.

#### Bad: raw count map
The operator maps districts by crime count and calls the top class "significant hotspots." This is a classification map, not Gi*.

#### Bad: incomplete weight preview
The weight-neighbor diagnostic map omits a legend because it is only intermediate.

#### Bad: no seed
The operator uses permutations but does not record a seed. Simulated p-values are not reproducible.

## Supporting Files
- None. The run-specific Python script and manifest are written in the managed workspace and registered as evidence.
