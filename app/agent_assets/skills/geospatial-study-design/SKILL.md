---
name: geospatial-study-design
description: Use when a classified geospatial request must be converted into a defensible study design, valid observation window, and operator candidate with explicit interpretation limits.
compatibility: opencode
---

# Geospatial Study Design

## Overview
This skill translates user intent into a method contract that later roles can actually verify. It is where the runtime decides what phenomenon is being analyzed, what the study area and study period mean, what kind of spatial object the method will treat as the unit of analysis, and what claims the final report will and will not be allowed to make.

The textbook repeatedly separates problem types: interpolation in Chapter 5, point-pattern and hotspot methods in Chapter 6, spatial regression in Chapter 7, and geodetector in Chapter 8. Good study design therefore means choosing a method family because it fits the question, not because it is available.

## When to Use
- Triage has produced a candidate task family.
- The user intent is supportable but still needs methodological framing.
- A downstream reviewer says the current design cannot justify the chosen method.

Do not use this skill to perform reprojection, clipping, or operator execution.

## Required Inputs
- Triage contract.
- Visible data inventory.
- Current runtime support scope.
- Any known study-area or time-window constraints.

## Workflow
1. Restate the problem in analytic terms: phenomenon, expected output, and scope.
2. Identify the observational unit: event point, sample site, polygon, raster cell, or mixed object.
3. Define the observation window: study area, time span, and any denominator/exposure requirement.
4. Compare the candidate method family against nearby alternatives.
5. Record why the chosen operator fits and why the rejected ones do not.
6. State the interpretation boundary before downstream execution begins.
7. Hand off only a design that later roles can validate with real artifacts.

## Decision Logic
Use `proceed` when the question, data object, observation window, and method family align cleanly.

Use `clarify` when the missing study area, time range, event semantics, or claim type would change the correct operator family.

Use `repair` when an upstream route is almost right but the design must be narrowed, for example when a risk-framed question can be downgraded to descriptive density only after explicit user acceptance.

Use `stop` when the runtime cannot produce a methodologically honest design with the current operator set. Current executable families are KDE for point-event density, IDW for sampled-value surfaces, Gi* for statistical hotspots over aggregated support, land-cover change detection, spatiotemporal distribution/variability, time-series trend, terrain derivatives, and unsupervised multivariate clustering.

## Output Contract
Return:
- `decision`
- `analysis_question`
- `unit_of_analysis`
- `study_area_definition`
- `time_scope`
- `operator_candidate`
- `rejected_alternatives`
- `claim_limits`
- `required_prep`

## Common Mistakes
- Choosing KDE just because the prompt contains the word "hotspot".
- Leaving the study window implicit.
- Treating a descriptive density surface as a proxy for significance or risk.
- Ignoring whether the data are events, sample values, or aggregated areal totals.
- Forgetting to state what the final report must not claim.
- Treating IDW validation metrics or Gi* p-values as optional decorations instead of design requirements.


## Detailed Rules

### Geospatial Study Design Rules

#### DESIGN-R01 Define the analysis question before the method
Record the phenomenon, expected output, and intended interpretation before choosing a tool. Methods answer different questions, so the question must lead.

#### DESIGN-R02 Observation window is part of the method
Study area and time scope are not optional context. For KDE and point-pattern methods they define what counts as observed concentration and where edge effects matter.

#### DESIGN-R03 Distinguish event density from interpolation
Chapter 5 groups trend surface, IDW, Kriging, CoKriging, and 3G under interpolation. If the user wants a continuous surface from sampled values, design the current task as `spatial_interpolation` with IDW when acceptable; do not route to KDE.

#### DESIGN-R04 Distinguish descriptive density from inferential hotspot testing
Chapter 6 includes LISA, Getis-Ord style local statistics, and SatScan as methods for spatial hot spots and anomalies. If the user asks for statistical hotspots and the support is aggregated units with numeric attributes, design the current task as `spatial_hotspot` with Gi*. If support is raw points, require aggregation clarification.

#### DESIGN-R05 Distinguish explanatory modeling from descriptive mapping
If the question is about drivers, associations, or covariate effects, the relevant family is spatial regression or geodetector, not KDE.

#### DESIGN-R06 Record rejected alternatives
The design memo should name at least the nearest rejected alternative and why it was rejected. That supports review and later thesis writing.

#### DESIGN-R07 State claim boundaries early
Every design must include the strongest allowed claim and the strongest forbidden claim. This is the anchor for skeptical review and final reporting.

#### DESIGN-R08 Denominator-sensitive questions need denominator logic
If the user requests risk, intensity per population, or relative burden, the design must require denominator data or explicitly downgrade the claim.

#### DESIGN-R09 Future-family honesty
When a better but unsupported method exists, such as Kriging, say so explicitly. Study design is not allowed to pretend the current operator stack is the scientifically best method if it is only the currently implemented one.

## Failure Modes

### Geospatial Study Design Failure Modes

#### method-picked-from-availability
Symptom: KDE is selected because it exists, not because it fits the question.
Response: `stop` or `repair`.

#### missing-observation-window
Symptom: no study area or time scope is defined, but the design proceeds anyway.
Response: `clarify`.

#### event-sample-confusion
Symptom: sample values at locations are treated like event counts.
Response: repair by routing to IDW if value-field and sample support can be audited; otherwise clarify or stop.

#### significance-density-confusion
Symptom: the design allows inferential hotspot claims from descriptive density.
Response: `repair` or `stop`.

#### risk-without-denominator
Symptom: a risk question is reframed as raw concentration without disclosure.
Response: `clarify`.

#### no-rejected-alternatives
Symptom: the design memo names a method but never explains why others were not used.
Response: `repair`.

#### hidden-claim-escalation
Symptom: the design does not define claim limits, allowing later roles to overstate results.
Response: `repair`.

## Worked Examples

### Geospatial Study Design Examples

#### Good: descriptive KDE design
Question: "Where are recorded taxi incidents more concentrated within the observed Beijing study area?"
Unit of analysis: point events.
Observation window: explicit district boundary and explicit collection period.
Operator candidate: KDE.
Rejected alternative: LISA, because the current question is descriptive density rather than inferential cluster significance.
Claim limit: may describe estimated density concentration, may not claim statistical significance or risk.

#### Good: clarify to separate density from significance
User wording: "Find significant hotspots of outbreaks."
Design response: `clarify`.
Why: the strongest candidate families are descriptive KDE and inferential hotspot testing; the request does not yet specify which one is intended.

#### Good: stop unsupported explanatory request
User wording: "Explain which factors drive the distribution."
Design response: `stop`.
Why: the correct family is explanatory modeling such as spatial regression or geodetector, which is out of scope.

#### Bad: method chosen from convenience
"We will use KDE because it can show a surface quickly."
Why wrong: speed is not a methodological justification.

#### Bad: hidden observation window
"We analyze the event layer directly."
Why wrong: no study area or time scope means no defensible observation window.

## Supporting Files
- Optional code or snippet files only when executable examples are truly needed.
