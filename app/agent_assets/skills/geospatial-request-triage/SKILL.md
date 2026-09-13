---
name: geospatial-request-triage
description: Use when a geospatial request must be classified into the right task family, checked for method-critical ambiguity, and gated before the runtime commits to an operator.
compatibility: opencode
---

# Geospatial Request Triage

## Overview
This skill is the front door for the whole geospatial runtime. Its job is to stop the system from doing the wrong kind of analysis quickly and confidently. In Wang Jinfeng's textbook, the method family matters: interpolation, point-pattern analysis, spatial regression, and stratified heterogeneity are not interchangeable. The runtime must therefore classify the request before it does any preprocessing or tool execution.

The output of this skill is not a pretty summary. It is a narrow, defensible routing decision: what the user is actually asking for, what the current runtime can support, what is still ambiguous, and whether the next state is `proceed`, `clarify`, `repair`, or `stop`.

## When to Use
- New user request enters the session.
- A later message changes the analysis goal.
- The user says "hotspot", "risk", "predict", "interpolate", or another overloaded term.
- A downstream role suspects the request was coerced into the wrong method family.

Do not use this skill to choose bandwidth, fix CRS, or justify report claims. Those belong to later roles.

## Required Inputs
- The original user wording, unchanged.
- Visible local dataset inventory, if any.
- Current runtime support scope.
- Existing study-design or review artifacts if triage is being revisited.

## Workflow
1. Parse the user request literally before inferring intent.
2. Identify the requested output: density surface, hotspot significance, interpolation, prediction, regression, explanation, or report-only revision.
3. Identify the spatial object of interest: point events, sample sites, polygons, raster cells, trajectories, or mixed layers.
4. Check whether the requested task is currently implemented, adjacent but ambiguous, or out of scope.
5. Detect method-critical missing information: study area, time window, event semantics, denominator/risk framing, and requested confidence language.
6. Route to the next valid role only after the task family is explicit.
7. If the request cannot honestly be mapped to current support, stop instead of bending it into KDE, IDW, or Gi*.

## Decision Logic
Use `proceed` when the request is clearly within a supported task family and the missing context does not change the method choice.

Use `clarify` when ambiguity changes the required operator family. Typical examples: "hotspot" could mean descriptive KDE or inferential LISA/Gi*; "risk" could require exposure data; "trend" could mean interpolation or regression.

Use `repair` only when an upstream artifact misrouted the request but the user's true intent is still recoverable without changing the request itself.

Use `stop` when the request belongs to an unsupported family such as Kriging-only interpolation, spatial regression, geodetector analysis, network routing, or outlier detection and the runtime would have to fake support.

Quick routing table:

| User intent | Data support | Current family | Typical next role |
| --- | --- | --- | --- |
| Event concentration or density | point events | `kde` | `operator-kde` |
| Continuous surface from measured samples | point samples with numeric values | `spatial_interpolation` | `operator-interpolation` |
| Statistically significant high/low clusters | aggregated units with numeric attribute | `spatial_hotspot` | `operator-spatial-hotspot` |
| Kriging, regression, geodetector, isolated outliers | method-specific support | unsupported | clarify or stop |

## Output Contract
Return:
- `decision`
- `task_family`
- `supported_operator_candidate`
- `missing_context`
- `reason_code`
- `handoff.next_role`
- `handoff.allowed_assumptions`

The contract should be short, literal, and suitable for machine review.

Strict JSON example:

```json
{
  "decision": "clarify",
  "task_family": "spatial_hotspot",
  "supported_operator_candidate": "gistar",
  "missing_context": ["aggregation_unit", "count_vs_rate_policy"],
  "reason_code": "AGGREGATION_SUPPORT_REQUIRED",
  "handoff": {
    "next_role": "study-design",
    "allowed_assumptions": []
  }
}
```

Allowed `task_family` values for current support are `kde`, `spatial_interpolation`, `spatial_hotspot`, `land_cover_change`, `spatiotemporal_pattern`, `time_series_trend`, `terrain_analysis`, `unsupervised_clustering`, and `reporting-review`. If the family is unsupported, use `unsupported` and name the requested method in `reason_code`. Missing mandatory fields are a failed triage contract.

## Common Mistakes
- Treating every mention of "hotspot" as KDE.
- Treating risk, danger, or probability as if descriptive density were enough.
- Ignoring missing study area because a later role could "probably infer it".
- Allowing unsupported tasks to continue because the runtime has one implemented operator.
- Folding method choice into report language instead of making it explicit here.


## Detailed Rules

### Geospatial Request Triage Rules

#### TRIAGE-R01 Request family must be explicit before operator work
Do not let preprocessing or operator execution start before the request has been classified as KDE, IDW interpolation, Gi* statistical hotspot analysis, report-only review, or an unsupported family. The textbook separates interpolation, point-pattern analysis, regression, and geodetector-style heterogeneity work for a reason: they answer different questions and require different assumptions.

#### TRIAGE-R02 Distinguish descriptive hotspot language from inferential hotspot requests
If the user asks for "significant hotspots", "confidence", or "p-values", triage must not silently map that into descriptive KDE. The correct next state is `spatial_hotspot` when aggregated support is present, `clarify` when support or count-rate semantics are missing, or `stop` when the requested inference is unsupported.

#### TRIAGE-R03 Distinguish event density from continuous-surface interpolation
If the input is a sample of values measured at sites and the user wants a continuous field, triage should classify the request as `spatial_interpolation` rather than KDE. Chapter 5 of the textbook groups trend surface, IDW, Kriging, and CoKriging as interpolation methods; IDW is the current executable prototype, while other interpolation methods require clarification.

#### TRIAGE-R04 Distinguish descriptive density from risk estimation
If the user asks for risk, vulnerability, danger, or per-capita burden, triage must check whether the request needs denominators, exposure, or explanatory covariates. Without those, a density map is not a risk map.

#### TRIAGE-R05 Study-area ambiguity is method-critical
When the requested observation window is unclear, return `clarify` instead of silently using data extent or current map extent. For KDE and point-pattern methods, the study window shapes interpretation and edge effects.

#### TRIAGE-R06 Time scope ambiguity is method-critical when the request is comparative or dynamic
If the prompt implies change, evolution, seasonality, or event concentration over time, triage must require a time window. Do not let later roles assume a default interval.

#### TRIAGE-R07 Unsupported family must not be coerced into KDE
Kriging, regression, geodetector analysis, isolated outlier detection, and unimplemented network analysis are not fallback modes of KDE, IDW, or Gi*. If the runtime cannot perform the requested family honestly, return `stop` with a refusal reason.

#### TRIAGE-R08 Use literal user intent, not convenience intent
The user's request enters the main agent flow unchanged. Triage may classify it, but must not rewrite it into a more convenient task simply because current runtime support is narrow.

#### TRIAGE-R09 Record routing evidence
For every triage decision, record the request wording, detected task family, missing context, and reason code. That creates an audit trail for later review and thesis experiments.

## Failure Modes

### Geospatial Request Triage Failure Modes

#### coercion-to-kde
Symptom: a request for IDW interpolation, Gi* significance testing, regression, or risk is routed to KDE because KDE was the first implemented operator.
Required action: route to the current supported family when possible; otherwise clarify or stop.

#### overloaded-hotspot-language
Symptom: the prompt says "hotspot" but does not clarify whether that means density, significance, or risk.
Required action: `clarify`.

#### missing-study-window
Symptom: no explicit study area or observation window exists, but the runtime proceeds anyway.
Required action: `clarify`.

#### hidden-time-assumption
Symptom: a change-over-time or seasonal question is treated as if all timestamps belong to one valid analytical window.
Required action: `clarify`.

#### event-vs-sample-confusion
Symptom: measured values at sample sites are treated as point events for KDE.
Required action: usually `stop` and reroute to interpolation if supported.

#### risk-language-without-denominator
Symptom: triage allows a risk-framed request to proceed without exposure or population context.
Required action: `clarify` or `stop`.

#### convenience-rewrite
Symptom: the agent rewrites the user's request into a supported family without telling them.
Required action: `stop`; this is a contract breach, not a harmless shortcut.

## Worked Examples

### Geospatial Request Triage Examples

#### Good: supported KDE request
User: "Analyze taxi incident point density in Beijing using KDE."
Outcome: `proceed`
Reason: point-event density request, supported operator, no hidden inferential claim.

#### Good: clarify overloaded hotspot language
User: "Find the significant hotspots of disease cases."
Outcome: `clarify`
Reason: "significant" implies inferential testing, not descriptive KDE.
Acceptable wording: "Do you want descriptive density via KDE, or an inferential hotspot method that is not yet implemented?"

#### Good: supported IDW interpolation
User: "Interpolate PM2.5 concentration across the city."
Outcome: `proceed`
Reason: sample-value interpolation belongs to `spatial_interpolation`; downstream roles must still audit value field, CRS, samples, and extent.

#### Good: Gi* clarification
User: "Find significant crash hotspots from raw crash points."
Outcome: `clarify`
Reason: Gi* requires an aggregation support such as grid cells, road segments, or districts before statistical hotspot testing.

#### Good: clarify risk framing
User: "Map the highest-risk neighborhoods for theft."
Outcome: `clarify`
Reason: risk requires denominator/exposure logic, not just event concentration.

#### Bad: silent coercion
User: "Estimate the spatial trend of housing prices."
Wrong outcome: `proceed` to KDE because the runtime has hotspot analysis.
Why wrong: the request is not point-event density.

#### Bad: hidden study-area assumption
User: "Do a hotspot analysis on these events."
Wrong outcome: the agent silently uses the current view extent as the study window.
Why wrong: the observation window changes the interpretation.

## Supporting Files
- Optional code or snippet files only when executable examples are truly needed.
