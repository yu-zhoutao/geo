---
name: geospatial-kde-parameter-rationale
description: Use when KDE bandwidth, cell size, weighting, and edge-handling choices must be justified, bounded, and recorded as method evidence.
compatibility: opencode
---

# Geospatial KDE Parameter Rationale

## Overview
KDE surfaces are highly sensitive to parameter choice, especially bandwidth and cell size. The textbook's KDE chapter shows a software path with a 1 km grid example, but for an agent runtime that is only the beginning. This skill forces the runtime to explain why a bandwidth is analytically appropriate, why the grid resolution is neither too coarse nor falsely precise, whether weighting is defensible, and how edge effects are being handled or disclosed.

## When to Use
- Before KDE execution.
- When a user supplies bandwidth or grid parameters.
- When skeptical review challenges parameter defensibility.

## Required Inputs
- Study design and task scale.
- Event count and sparsity indicators.
- Working CRS and linear units.
- Candidate bandwidth, cell size, and weight field.

## Workflow
1. Identify the scale of the analytic question.
2. Check whether the requested bandwidth is plausible for that scale.
3. Check whether cell size is fine enough to represent the surface without pretending to know more than the data support.
4. Check whether the weight field is numeric, additive, and meaningful.
5. Record edge-effect implications and downstream caution language.
6. Run a minimum bandwidth sensitivity check when the user has not locked a single bandwidth: primary + lower + upper. Record the comparison as `bandwidth_sensitivity`, including `peak_count_by_bandwidth`, peak movement, high-density area change, and whether interpretation changes.

This workflow should be executed in the order of irreversibility. Start with bandwidth because it defines the basic smoothing scale. Then move to cell size, because grid resolution can falsely suggest precision even when the bandwidth is broad. After that, inspect weighting, because a weighted surface changes the meaning of density itself. Finally, add the edge note and disclosure language, because even well-chosen parameters can still mislead if the study window truncates unobserved events.

The textbook's KDE chapter is useful as a reminder that software dialogs are only parameter entry points, not methodological justifications. The runtime should therefore treat every parameter as something that needs an explanation, not just a value.

The rule is simple: disclosure is not a substitute for sensitivity evidence. If bandwidth choice can merge peaks, erase local structure, inflate high-density areas, or change the rank/order of density maxima, the runtime must produce comparison evidence or return `repair`. A limitation sentence may accompany the result, but it cannot replace the missing diagnostic.

## Decision Logic
Proceed when parameters are explicit, unit-bearing, and proportionate to the problem.
Clarify when the user intent or weight semantics leave more than one defensible interpretation.
Repair when parameters are outside pack policy but can be corrected without changing the method family.
Stop when no defensible parameterization exists for the current data and claim level.

When deciding between `repair` and `stop`, ask whether the parameter problem is local or structural. A bandwidth outside house policy can often be repaired. A weight field with no additive meaning, or a sparsity pattern that makes any bandwidth look authoritative when it is not, is closer to a structural problem and may require clarification or termination.

Executable default policy for the prototype:

| Parameter | Default order | Clarify or repair threshold | Stop threshold |
| --- | --- | --- | --- |
| Bandwidth | user value with units, then documented study scale, then nearest-neighbor diagnostic | missing units, outside plausible study scale, or too broad/narrow for event spacing | cannot choose without changing the analysis question |
| Cell size | user value with units, then bandwidth / 4 to bandwidth / 8, capped to avoid oversized rasters | cells-per-bandwidth below 3 or above 12 without justification | raster size is infeasible or implies false precision |
| Weight field | explicit additive count or magnitude field | ambiguous severity or ordinal field | categorical, signed, identifier-like, or non-additive field |
| Edge handling | clip or mask to study window plus disclosure | missing edge note | study window unknown |
| Bandwidth sensitivity | primary + lower + upper unless user fixes a single value | missing `bandwidth_sensitivity`, unstable `peak_count_by_bandwidth`, or changed interpretation | sensitivity cannot be run and the claim depends on a single arbitrary scale |

## Output Contract
Return:
- `decision`
- `bandwidth`
- `bandwidth_provenance`
- `cell_size`
- `cells_per_bandwidth`
- `weight_semantics`
- `edge_note`
- `reason_code`

Strict JSON example:

```json
{
  "decision": "repair",
  "bandwidth": {"requested": 300, "used": 500, "units": "metre"},
  "bandwidth_provenance": "repaired_to_match_neighborhood_scale",
  "cell_size": {"requested": 10, "used": 75, "units": "metre"},
  "cells_per_bandwidth": 6.67,
  "weight_semantics": {"field": "event_count", "valid": true, "meaning": "additive repeated-event count"},
  "edge_note": "Density is study-window dependent and clipped at the boundary.",
  "bandwidth_sensitivity": {
    "tested_bandwidths": [1000, 1500, 2000],
    "peak_count_by_bandwidth": {"1000": 4, "1500": 2, "2000": 1},
    "interpretation_changed": true
  },
  "reason_code": "CELL_SIZE_REPAIRED"
}
```

## Common Mistakes
- Accepting a bandwidth because it "looks good".
- Recording cell size but not its units.
- Treating arbitrary categorical fields as numeric weights.
- Ignoring that sparse data and edge effects make the surface fragile.

Also avoid the reverse mistake of overfitting the parameter explanation. The point is not to invent fake precision or pseudo-statistical certainty. The point is to show that the chosen parameters are reasonable for the question, the data density, and the study window, and that the runtime knows what remains sensitive.


## Detailed Rules

### KDE Parameter Rationale Rules

#### KPAR-R01 Bandwidth must have provenance
The runtime must record whether the bandwidth comes from user input, a pack policy default, exploratory tuning, or another documented rationale.

#### KPAR-R02 Bandwidth must match the analytic scale
Local questions need local smoothing; regional summaries need broader smoothing. Never justify bandwidth only by aesthetics.

#### KPAR-R03 Cell size is an analysis parameter, not just a rendering preference
Record the requested cell size, the used cell size, the units, and the cells-per-bandwidth ratio.

#### KPAR-R04 Weight fields need additive semantics
Only numeric, additive, and interpretable weights are acceptable.

#### KPAR-R05 Edge note is mandatory
If the observation window can truncate unobserved events near the border, say so explicitly.

#### KPAR-R06 Repairs must be visible
If the runtime clamps bandwidth or adjusts cell size for safety or scale, record both the original and repaired value.

#### KPAR-R07 Minimum bandwidth sensitivity is task evidence
When the user has not mandated one exact bandwidth, run primary + lower + upper bandwidths before release. The comparison must record `bandwidth_sensitivity`, `peak_count_by_bandwidth`, peak movement or fusion, high-density area change, and any claim that changes with scale. If the comparison reveals a materially better parameterization, return `repair` and rerun release artifacts instead of merely adding a caveat.

## Failure Modes

### KDE Parameter Rationale Failure Modes

#### undocumented-bandwidth
Response: `repair`.

#### aesthetic-bandwidth-choice
Response: `repair` or `stop`.

#### false-precision-grid
Response: `repair`.

#### invalid-weight-semantics
Response: `clarify` or `stop`.

#### no-edge-disclosure
Response: `repair`.

#### hidden-runtime-adjustment
Response: `repair`.

#### missing-bandwidth-sensitivity
Response: `repair`.

#### caveat-instead-of-sensitivity
Response: `repair`.

## Worked Examples

### KDE Parameter Rationale Examples

#### Good
"Bandwidth is 1000 m because the question is neighborhood-scale concentration, the working CRS is metric, and the value stays within pack policy."

#### Good
"The run compared primary + lower + upper bandwidths, recorded `bandwidth_sensitivity`, and showed `peak_count_by_bandwidth` changed from 4 to 2 to 1; final claims use the scale that preserves the task-relevant structure."

#### Good
"Requested cell size was 10 m, but the runtime repaired it to 50 m to avoid false precision and excessive cells-per-bandwidth."

#### Bad
"We tried a few radii and the prettiest one looked best."

#### Bad
"Bandwidth may affect results, but we disclose this limitation and release the single-bandwidth map."

#### Bad
"Severity was used as a weight because high sounds larger than low."

## Supporting Files
- Optional code or snippet files only when executable examples are truly needed.
