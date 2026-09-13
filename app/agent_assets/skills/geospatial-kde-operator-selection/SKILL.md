---
name: geospatial-kde-operator-selection
description: Use when the runtime must decide whether descriptive point-event KDE is the right operator instead of interpolation, inferential hotspot testing, regression, or another spatial method family.
compatibility: opencode
---

# Geospatial KDE Operator Selection

## Overview
This skill exists to stop lazy method choice. Wang Jinfeng's textbook places KDE near surface-style spatial analysis, but the surrounding chapters make clear that not every surface-like output should be treated as KDE. IDW estimates continuous values from sample data. Gi* studies statistically significant local high-value or low-value clustering over a defined spatial support. Spatial regression and geodetector answer explanatory questions. KDE is only the right choice when the question is descriptive density of events in a defined observation window.

## When to Use
- The runtime is about to pick or confirm KDE.
- The prompt says "hotspot", "density", "interpolate", "trend", or "risk".
- Review needs to validate why KDE was used instead of another family.

## Required Inputs
- Study-design contract.
- Data semantic audit.
- Requested output type.
- Current runtime support scope.

## Workflow
1. Confirm the problem asks for descriptive concentration of events rather than prediction, explanation, or inferential significance.
2. Confirm the input object is a point-event representation, not sample sites or areal summaries.
3. Compare KDE against the nearest plausible alternatives.
4. Record the rejected alternatives and why they fail the current question.
5. Refuse convenience-based method substitution.

## Decision Logic
Proceed when the request is a descriptive point-event density problem in a defensible study window.
Clarify when hotspot language is overloaded or when the user may accept a narrower descriptive answer.
Repair when an upstream design can be narrowed from a stronger unsupported claim to an honest KDE use.
Stop when an unimplemented method such as Kriging, regression, geodetector analysis, or risk modeling is the real task. Route to IDW or Gi* when those current task families honestly match the request.

## Output Contract
Return:
- `decision`
- `operator_candidate`
- `method_fit`
- `rejected_alternatives`
- `claim_limits`
- `reason_code`

## Common Mistakes
- Choosing KDE because it is already implemented.
- Ignoring whether the data are events or sample values.
- Treating inferential hotspot language as a harmless synonym for descriptive density.
- Using KDE for explanatory or denominator-based questions.


## Detailed Rules

### KDE Operator Selection Rules

#### KSEL-R01 KDE is for descriptive event density
Choose KDE when the question is about concentration or estimated density of observed point events within an observation window.

#### KSEL-R02 Continuous-value surfaces belong to interpolation families
If the input is sampled values at locations and the user wants a continuous field, the current supported family is `spatial_interpolation` with IDW. Kriging, CoKriging, and trend surface requests require clarification or stop unless the user accepts IDW as a prototype alternative.

#### KSEL-R03 Significant hotspots are not the same as density hotspots
If the user requests significance, p-values, or statistically unusual clusters, the current supported family is `spatial_hotspot` with Gi* when aggregated support exists. Raw point events still require aggregation clarification.

#### KSEL-R04 Explanatory questions belong to explanatory families
If the user asks why a pattern occurs or which factors drive it, the nearest families are spatial regression or geodetector.

#### KSEL-R05 Risk questions require denominator logic
If the output must compare events against population, exposure, or opportunity, KDE alone is not enough.

#### KSEL-R06 Record the nearest rejected alternative
Always explain why the closest alternative family was rejected; this prevents method choice from looking arbitrary.

## Failure Modes

### KDE Operator Selection Failure Modes

#### interpolation-coerced-to-kde
Response: route to IDW when support is sampled numeric points; clarify or stop for unimplemented interpolation methods.

#### significance-request-collapsed-into-density
Response: route to Gi* when aggregated support exists; clarify aggregation and count-rate semantics when missing.

#### explanatory-question-collapsed-into-density
Response: `stop`.

#### risk-language-without-denominator-downgrade
Response: `clarify`.

#### convenience-based-method-choice
Response: `repair` or `stop`.

## Worked Examples

### KDE Operator Selection Examples

#### Good
Question: "Where are reported incidents more concentrated?"
Decision: KDE.

#### Good
Question: "Where are the statistically significant hotspots?"
Decision: route to Gi* if aggregated support exists; otherwise clarify support and significance semantics.

#### Good
Question: "Interpolate housing prices across the region."
Decision: route to IDW if there are point samples with numeric housing prices; this is not KDE.

#### Bad
"KDE is fine because it still produces a surface."

#### Bad
"The user asked for risk, but concentration is close enough."

## Supporting Files
- Optional code or snippet files only when executable examples are truly needed.
