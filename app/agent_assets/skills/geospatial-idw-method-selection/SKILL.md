---
name: geospatial-idw-method-selection
description: Use when a geospatial request may require IDW interpolation, sampled-value surface estimation, or a boundary decision against KDE and Gi* hotspot analysis.
compatibility: opencode
---

# Geospatial IDW Method Selection

## Overview
This skill decides whether a request belongs to the `spatial_interpolation` family and whether IDW is an honest first prototype operator. IDW estimates a continuous surface from observed numeric values at sample locations. It is not event-density mapping, statistical hotspot testing, causal explanation, or isolated outlier detection.

The purpose is to keep three map-like outputs separate: KDE describes concentration of point events, IDW estimates values between sampled observations, and Gi* tests local high-value or low-value clustering over a defined spatial support. If the request cannot be separated cleanly, the correct output is a control decision, not a guess.

## When to Use
- The user asks to interpolate, estimate, predict, fill gaps, or create a continuous surface.
- The candidate data are point samples with measured numeric values such as PM2.5, temperature, noise, price, or elevation.
- A prompt says "hotspot", "surface", "trend", or "high-value areas" and the family could be KDE, IDW, or Gi*.
- A downstream role needs to justify why IDW was selected or rejected.

Do not use this skill to run the interpolation script. Use it before execution to decide family, support, and ambiguity.

## Required Inputs
- Original user wording without rewriting.
- Candidate layer geometry types and field list.
- Evidence about which field is the observed value.
- Study extent or mask, if already known.
- Any user-specified method such as IDW, Kriging, trend surface, or "hotspots".

## Workflow
1. Identify the requested quantity: event density, measured value surface, statistically significant cluster, risk, or explanation.
2. Check whether the input support is point samples with a numeric value field.
3. Separate the output family before choosing the operator.
4. If the user explicitly requests Kriging or another unimplemented interpolation method, ask whether IDW is acceptable as an IDW-first prototype alternative.
5. Record the selected family, rejected alternatives, missing context, and control state.
6. Hand off to data audit or IDW runbook only when the family is `spatial_interpolation`.

## Decision Logic
| Situation | Decision | Family | Reason code |
| --- | --- | --- | --- |
| Numeric values measured at point samples, field is explicit, enough context exists | `proceed` | `spatial_interpolation` | `IDW_SAMPLE_VALUE_SURFACE` |
| Same request but value field is unclear | `clarify` | `spatial_interpolation` | `MISSING_VALUE_FIELD` |
| User asks for point event concentration with no measured value field | `repair` or `proceed` to KDE | `kde` | `EVENT_DENSITY_NOT_INTERPOLATION` |
| User asks for significant high-value clusters over areal units | `proceed` or `clarify` to Gi* | `spatial_hotspot` | `SIGNIFICANCE_NOT_INTERPOLATION` |
| User demands Kriging as the executable method | `clarify` | `spatial_interpolation` | `UNIMPLEMENTED_INTERPOLATION_METHOD` |
| Nonpoint geometry is the only support for a continuous field | `stop` unless a defensible point support exists | `unsupported` | `INVALID_IDW_SUPPORT` |

Use `proceed` only when IDW is both methodologically aligned and currently executable. Use `clarify` when a single missing answer changes the field, method, or support. Use `repair` when an upstream role called this KDE or Gi* but the data clearly support interpolation. Use `stop` when interpolation would require inventing values, geometry support, or CRS evidence.

## Output Contract
Return a clear method-selection handoff. A compact JSON block is recommended when it helps downstream roles, but prose is acceptable when it states the same decision and evidence.

```json
{
  "decision": "proceed",
  "task_family": "spatial_interpolation",
  "supported_operator_candidate": "idw",
  "value_field": "pm25",
  "rejected_alternatives": [
    {"family": "kde", "reason": "input is sampled measured values, not point events"},
    {"family": "spatial_hotspot", "reason": "request asks for an estimated surface, not significance testing"}
  ],
  "missing_context": [],
  "reason_code": "IDW_SAMPLE_VALUE_SURFACE",
  "handoff": {
    "next_role": "data-audit",
    "allowed_assumptions": ["IDW is an inverse-distance prototype, not Kriging"]
  }
}
```

If any important field is unknown, set it to `null`, use an empty list, or say so explicitly, then use `clarify`, `repair`, or `stop`. Recommended handoff fields are `decision`, `task_family`, `supported_operator_candidate`, `missing_context`, `reason_code`, and `handoff.next_role`.

## Common Mistakes
- Treating point events as if their event count were a measured environmental value.
- Treating a heatmap request as IDW merely because the output is continuous-looking.
- Routing "significant high-value clusters" to IDW when the user asked for inferential hotspot analysis.
- Accepting Kriging requests silently and running IDW without user-visible method downgrade.
- Forgetting that IDW cannot create information outside the observed sample support.

## Detailed Rules

### IDW Method Selection Rules

#### IDWSEL-R01 Interpolation requires sampled numeric observations
IDW can proceed only when the candidate layer contains point locations with a numeric observed value field. Counts, identifiers, categories, boolean flags, labels, and ranks are not automatically interpolation values. If the value field is absent or ambiguous, return `clarify` with `MISSING_VALUE_FIELD`.

#### IDWSEL-R02 Event density stays in KDE
If the user asks where incidents, crashes, crimes, taxi pickups, or other point events are concentrated, the default family is KDE, not IDW. IDW needs a value measured at each sample location. Do not invent a value field from point existence.

#### IDWSEL-R03 Significance and clustering stay out of IDW
If the user asks for statistically significant hotspots, p-values, confidence, high-high clusters, or coldspots, IDW is not a substitute. Route to `spatial_hotspot` or clarify whether a descriptive surface is acceptable.

#### IDWSEL-R04 Unsupported interpolation methods require visible downgrade
Kriging, CoKriging, trend surface, and spline interpolation are not the first executable prototype path unless separately implemented. When the user explicitly requests one of them, ask whether an IDW-first approximation is acceptable. Do not present IDW as Kriging.

#### IDWSEL-R05 Sample support and extent must be plausible before execution
The method can be selected only provisionally until data audit confirms valid point geometry, nonconstant numeric values, authoritative CRS, and sufficient samples. Selection is not permission to execute.

#### IDWSEL-R06 Claim boundary is part of method selection
The selected family permits language such as "estimated value surface" and "higher estimated values near sampled observations." It does not permit "statistically significant hotspot", "caused by", "true risk", or "validated prediction" unless separate evidence supports those claims.

## Failure Modes

### IDW Method Selection Failure Modes

#### event-as-value
Symptom: every event point is assigned value 1 and IDW is run to make a smooth incident map.
Required action: route to KDE or ask for the actual measured field.

#### significant-hotspot-as-surface
Symptom: a request for significant high PM2.5 clusters is answered with an interpolated PM2.5 surface.
Required action: clarify whether the user wants an estimated surface or Gi* cluster significance.

#### kriging-silent-downgrade
Symptom: the user asks for Kriging, but the runtime executes IDW and reports "interpolation completed."
Required action: clarify and record the method downgrade before execution.

#### unsupported-support
Symptom: a polygon-level attribute is fed into IDW without a defensible point sample support.
Required action: stop or reroute to Gi* if the actual question is local clustering over units.

#### value-field-handwave
Symptom: the runtime says "use the most relevant numeric field" without naming why it is the observed value.
Required action: clarify or audit fields before continuing.

## Worked Examples

### IDW Method Selection Examples

#### Good: PM2.5 surface
User: "Use monitoring stations to estimate PM2.5 across the city."
Outcome: `proceed` to `spatial_interpolation`.
Reason: point samples with observed values can support IDW after field and CRS audit.

#### Good: event density remains KDE
User: "Show where taxi pickup points are most concentrated."
Outcome: not IDW; route to KDE.
Reason: point events do not contain a measured continuous value to interpolate.

#### Good: Gi* boundary
User: "Find statistically significant high-rent clusters by district."
Outcome: route to `spatial_hotspot` or clarify count/rate semantics.
Reason: the request asks for local significance over spatial units.

#### Bad: map-like output shortcut
User: "Make a smooth map of crime hotspots."
Wrong outcome: `proceed` to IDW with value 1 at each crime point.
Why wrong: smooth output is not enough; the data are events, not sampled values.

#### Bad: unannounced method downgrade
User: "Run Kriging on soil lead samples."
Wrong outcome: execute IDW and call it Kriging-style interpolation.
Why wrong: the runtime must ask whether IDW is acceptable.

## Supporting Files
- None. This skill is a routing and control-state rulebook. Durable evidence belongs in the shared ledger through `record_run_evidence`.
