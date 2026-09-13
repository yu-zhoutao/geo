---
name: geospatial-data-semantic-audit
description: Use when geospatial layers must be checked for geometry meaning, event semantics, field validity, duplicates, and data-role readiness before preprocessing or analysis.
compatibility: opencode
---

# Geospatial Data Semantic Audit

## Overview
This skill checks whether the data mean what later roles need them to mean. A correct CRS on the wrong semantic object is still wrong. The textbook's early chapters distinguish point, line, polygon, lattice, and sampled-variable representations; later chapters then apply different analysis families to those different representations. This skill enforces that separation at the dataset level.

The runtime should emerge from this step knowing whether a layer is an event layer for KDE, a sample-value layer for IDW, an aggregated unit layer for Gi*, a study-area mask, a denominator layer, or a decoy. If that meaning is unclear, later correctness is impossible.

## When to Use
- Before spatial preparation.
- When multiple candidate layers exist.
- When a field may be used as a weight, time key, or denominator.
- When review suspects that the runtime treated proxies as true events.

## Required Inputs
- Study-design memo.
- Layer metadata and schemas.
- Any local data provenance record.
- Known task family and planned operator.

## Workflow
1. Inventory layers and assign provisional roles.
2. Confirm geometry family for each candidate layer.
3. Determine whether points represent events, samples, centroids, or derived proxies.
4. Inspect key fields: time, weight, interpolation value, Gi* attribute, category, ID, duplicates, missingness, and count-rate semantics.
5. Reject or downgrade layers that do not match the design contract.
6. Record what downstream roles may safely assume.

## Decision Logic
Use `proceed` when the intended method support, mask layer, and key fields are all semantically defensible.

Use `clarify` when a layer could plausibly mean more than one thing and external context is required.

Use `repair` when deterministic cleanup is possible, such as deduplicating records or aggregating repeated event locations into counts.

Use `stop` when the only available layers are semantically incompatible with the task family.

## Output Contract
Return:
- `decision`
- `layer_roles`
- `event_semantics`
- `interpolation_value_field`
- `hotspot_attribute_field`
- `key_fields`
- `duplicate_policy`
- `semantic_blockers`
- `allowed_assumptions`

## Common Mistakes
- Treating sample sites as event locations.
- Treating event locations as IDW sample values.
- Treating raw points as Gi* support without aggregation.
- Treating polygon centroids as if they were real event points.
- Using categorical severity or text labels as numeric KDE weights.
- Failing to separate duplicate records from repeated valid events.
- Choosing a visually familiar layer rather than the semantically correct one.


## Detailed Rules

### Geospatial Data Semantic Audit Rules

#### SEM-R01 Every layer needs an explicit role
Assign each layer a role such as event layer, study-area mask, denominator layer, auxiliary context, or decoy. Unassigned layers should not silently influence the run.

#### SEM-R02 Event semantics must be explicit
For KDE, the point layer must represent real event locations or defensible event counts at locations. Sample sites, centroids of areal summaries, and convenience points are not automatically event layers.

#### SEM-R03 Geometry family must fit the method
Polygon or raster layers cannot be silently fed into point-event KDE. IDW requires point samples with numeric observed values. Gi* requires aggregated areal, grid, or otherwise explicit spatial units with numeric attributes. If conversion would change the meaning, stop or clarify rather than forcing geometry transformation.

#### SEM-R04 Duplicate handling must preserve meaning
Repeated locations can mean repeated events, duplicated records, or aggregated reporting. Audit must decide which before later roles use counts.

#### SEM-R05 Weight fields must be semantically and numerically valid
The skill should accept only numeric, additive, nonnegative weights for KDE-style weighting. Categorical severity labels, signed values, and opaque codes require clarification or refusal.

#### SEM-R05A IDW value fields must be measured values
For IDW, the candidate value field must be numeric, finite, varying, and semantically meaningful as an observed value. Identifiers, categories, event presence, boolean flags, all-missing fields, and constant fields block interpolation.

#### SEM-R05B Gi* attributes need support and rate semantics
For Gi*, the candidate attribute must belong to the selected spatial support. Raw counts over unequal populations, areas, or exposure units require a count-versus-rate clarification before significance claims.

#### SEM-R06 Time fields matter when the question implies change or period scope
If the study design depends on time, the dataset must expose a usable time field and an interpretable temporal grain.

#### SEM-R07 Denominator-sensitive tasks need denominator layers or fields
If the question implies rate or risk, audit must identify whether population, exposure, or opportunity data exist.

#### SEM-R08 Downstream assumptions must be explicit
At the end of the audit, record exactly what later roles may trust: event layer identity for KDE, value field for IDW, support and attribute for Gi*, weight semantics, time field, mask layer, and unresolved semantic risks.

## Failure Modes

### Geospatial Data Semantic Audit Failure Modes

#### sample-sites-treated-as-events
Symptom: measured values at observation sites are passed to KDE as if they were event locations.
Action: repair by rerouting to IDW if interpolation was intended; otherwise stop.

#### events-treated-as-idw-values
Symptom: raw event points are assigned value 1 and interpolated.
Action: route to KDE or clarify the measured value field.

#### raw-points-treated-as-gistar-support
Symptom: individual event points are sent to Gi* without aggregation.
Action: clarify aggregation support or repair through an approved grid or unit layer.

#### centroid-proxy-misuse
Symptom: polygon centroids with areal totals are treated as true point events.
Action: usually `stop`.

#### duplicate-meaning-unknown
Symptom: repeated coordinates exist but audit never decides whether they are valid repeated events or duplicate records.
Action: `clarify` or `repair`.

#### invalid-weight-field
Symptom: text, ordinal labels, or signed values are used as KDE weights without a defensible additive meaning.
Action: `clarify` or `stop`.

#### mask-layer-confusion
Symptom: multiple polygon layers exist and the runtime clips to the wrong one.
Action: `clarify`.

#### denominator-missing
Symptom: a risk/rate task has no exposure layer but the audit lets it proceed.
Action: `clarify` or `stop`.

#### silent-decoy-selection
Symptom: the runtime chooses a convenient but irrelevant layer because it looks spatially plausible.
Action: `stop` and re-audit.

## Worked Examples

### Geospatial Data Semantic Audit Examples

#### Good: repeated events aggregated into counts
Layer meaning: repeated incident reports at the same intersection.
Audit decision: valid event layer after aggregation.
Recorded assumptions: duplicate groups were aggregated into an event-count field; KDE weight field is that count.

#### Good: sample sites refused for KDE
Layer meaning: PM2.5 sampling stations with concentration values.
Audit decision: not an event layer; suitable for interpolation family, not KDE.

#### Good: aggregated units accepted for Gi*
Layer meaning: district polygons with a disease-rate field.
Audit decision: candidate Gi* support after count-rate semantics and feature count are verified.

#### Good: clarify ambiguous severity field
Field: `severity` with values `high`, `medium`, `low`.
Audit decision: `clarify`.
Why: order exists, but additive numeric meaning for KDE weighting is not established.

#### Bad: centroid shortcut
Wrong behavior: use district centroids with district case totals as KDE events.
Why wrong: geometry convenience replaced event semantics.

#### Bad: duplicate erasure without meaning check
Wrong behavior: drop coincident points because duplicates are "messy".
Why wrong: repeated coordinates may be the actual phenomenon.

## Supporting Files
- Optional code or snippet files only when executable examples are truly needed.
