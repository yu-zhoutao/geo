---
name: geospatial-gistar-method-selection
description: Use when a geospatial request may require Getis-Ord Gi* statistical hotspot analysis or must be separated from KDE density and IDW interpolation.
compatibility: opencode
---

# Geospatial Gi* Method Selection

## Overview
This skill decides whether a request belongs to `spatial_hotspot` and whether Getis-Ord Gi* is the right prototype operator. Gi* is a local spatial association statistic over a defined spatial support and numeric attribute. It is not a KDE heatmap, not an interpolation surface, not isolated outlier detection, and not a causal explanation.

The key distinction is support. Gi* needs areal units, grid cells, or another explicit aggregation support with numeric values. Raw point events do not become Gi* inputs until the runtime records an aggregation decision. If the support, value semantics, or significance wording is unclear, the right behavior is `clarify` or `repair`.

## When to Use
- The user asks for statistically significant hotspots, coldspots, high-high clusters, or local clustering.
- The candidate data contain polygons, grid cells, or aggregated point units with a numeric attribute.
- The prompt mentions "hotspot" and it is unclear whether the user means KDE density or inferential significance.
- A report draft labels KDE or IDW output as significant hotspots.

Do not use this skill to construct weights or run PySAL. Use it before execution to decide whether Gi* is methodologically appropriate.

## Required Inputs
- Original user wording.
- Candidate geometry support: polygons, grid cells, aggregated points, raw points, or raster.
- Candidate numeric attribute and its meaning.
- Any denominator, exposure, area, population, or rate information.
- Study area and intended significance language.

## Workflow
1. Identify whether the user asks for descriptive concentration, estimated continuous surface, or statistically significant local clustering.
2. Verify that the candidate input support is aggregated or otherwise suitable for local spatial association.
3. Check whether the numeric field is a count, rate, intensity, score, or measured value.
4. Decide whether count-versus-rate semantics require clarification.
5. Route to Gi* only when spatial support and attribute semantics can be audited.
6. Record rejected alternatives: KDE for density, IDW for sampled-value surfaces, Moran/LISA or other methods if explicitly requested but not implemented.

## Decision Logic
| Situation | Decision | Family | Reason code |
| --- | --- | --- | --- |
| Polygons or grid units with numeric attribute and significance request | `proceed` | `spatial_hotspot` | `GISTAR_AGGREGATED_SUPPORT` |
| Raw point events plus hotspot significance request | `clarify` or `repair` | `spatial_hotspot` | `AGGREGATION_SUPPORT_REQUIRED` |
| Counts over unequal exposure units and no denominator decision | `clarify` | `spatial_hotspot` | `COUNT_RATE_SEMANTICS_UNCLEAR` |
| Event concentration with no significance language | `proceed` to KDE or clarify | `kde` | `DENSITY_NOT_GISTAR` |
| Continuous sampled-value surface request | `proceed` to IDW or clarify | `spatial_interpolation` | `SURFACE_NOT_GISTAR` |
| Isolated outlier request | `stop` or clarify | `unsupported` | `GISTAR_NOT_OUTLIER_DETECTION` |

Use `repair` when raw events can be aggregated to a user-approved grid or administrative unit. Use `clarify` when the aggregation support, denominator, value field, or significance goal is unknown. Use `stop` when the request would require a different statistical method or fabricated support.

## Output Contract
Return a clear method-selection handoff. A compact JSON block is recommended when it helps downstream roles, but prose is acceptable when it states the same decision and evidence.

```json
{
  "decision": "clarify",
  "task_family": "spatial_hotspot",
  "supported_operator_candidate": "gistar",
  "spatial_support": "raw_points",
  "attribute_field": null,
  "missing_context": ["aggregation_unit", "count_vs_rate_policy"],
  "rejected_alternatives": [
    {"family": "kde", "reason": "user asked for statistical significance"},
    {"family": "spatial_interpolation", "reason": "input is not sampled values for a continuous surface"}
  ],
  "reason_code": "AGGREGATION_SUPPORT_REQUIRED",
  "handoff": {
    "next_role": "study-design",
    "allowed_assumptions": []
  }
}
```

Recommended handoff fields are `decision`, `task_family`, `supported_operator_candidate`, `spatial_support`, `missing_context`, `reason_code`, and `handoff.next_role`.

## Common Mistakes
- Running Gi* directly on raw event points without aggregation support.
- Calling high raw values significant hotspots without a local statistic and p-value policy.
- Treating KDE density as Gi* because both can be called "hotspot maps."
- Using counts over unequal areas or populations without asking count-versus-rate semantics.
- Reporting Gi* as isolated outlier detection.

## Detailed Rules

### Gi* Method Selection Rules

#### GSEL-R01 Gi* requires explicit spatial support
The candidate support must be polygons, grid cells, or aggregated measured features. Raw event points require an aggregation decision before Gi* can proceed. If aggregation changes the question, ask the user.

#### GSEL-R02 Numeric attribute semantics are mandatory
The field must represent a numeric quantity meaningful for local clustering. Counts, rates, standardized scores, and measured attributes have different interpretations. Identifiers, categories, all-zero fields, and constant fields are not valid.

#### GSEL-R03 Count-versus-rate ambiguity must be resolved
Counts over unequal area, population, exposure, or opportunity units can produce misleading hotspots. Clarify whether the analysis should target total magnitude or denominator-adjusted rates.

#### GSEL-R04 KDE density and Gi* significance are separate
KDE describes event density over an observation window. Gi* tests local clustering of high or low attribute values under a specified spatial weight model. A KDE hotspot is not a statistically significant Gi* hotspot.

#### GSEL-R05 IDW surfaces and Gi* clusters are separate
IDW estimates a continuous surface from samples. Gi* tests local association among spatial units. Do not use Gi* merely because an IDW surface has high-value regions.

#### GSEL-R06 Small support requires stop or demo-only framing
Formal Gi* should not proceed with fewer than 30 units unless the run is explicitly marked demo-only. Demo-only outputs cannot be used as thesis-grade significance evidence.

#### GSEL-R07 Method family controls claim language
Gi* can support "statistically significant local high-value cluster under the selected weights" only after execution records statistic, p-value, and multiple-testing policy. It cannot support causality, density, interpolation, or risk proof by itself.

## Failure Modes

### Gi* Method Selection Failure Modes

#### raw-points-gistar
Symptom: event points are passed directly into Gi* as if each event were a spatial unit.
Required action: clarify or repair by choosing an aggregation unit.

#### high-value-means-significant
Symptom: the runtime labels the highest attribute values as hotspots before computing Gi*.
Required action: stop or repair; raw magnitude is not local significance.

#### density-significance-collapse
Symptom: KDE output is described as Gi* or significant hotspots.
Required action: route to KDE interpretation repair or Gi* execution only if the user asks for significance and support exists.

#### count-rate-confusion
Symptom: district crime counts are compared across unequal populations without denominator policy.
Required action: clarify count-versus-rate semantics.

#### unsupported-outlier-request
Symptom: the user asks for isolated anomalous units and the runtime chooses Gi*.
Required action: clarify or stop because Gi* is not standalone outlier detection.

## Worked Examples

### Gi* Method Selection Examples

#### Good: aggregated district rates
User: "Find statistically significant high-rate disease clusters by district."
Outcome: `proceed` to `spatial_hotspot` if rate field, unit count, CRS, and support are valid.

#### Good: raw events need aggregation
User: "Use these crash points to find significant hotspots."
Outcome: `clarify` or `repair`.
Reason: the user must approve grid, road segment, district, or another aggregation support.

#### Good: KDE boundary
User: "Show areas where pickups are dense."
Outcome: KDE, not Gi*.
Reason: no inferential significance over units is requested.

#### Bad: high values only
User: "Which districts are hotspots of housing price?"
Wrong outcome: label the top 10 percent districts as significant hotspots.
Why wrong: Gi* requires spatial weights and significance settings.

#### Bad: IDW substitute
User: "Interpolate PM2.5 from monitoring stations."
Wrong outcome: run Gi* on stations.
Why wrong: the request is sampled-value surface estimation, not local clustering over units.

## Supporting Files
- None. This skill records method-family decisions; execution evidence is created by the Gi* runbook and spatial-weight skills.
