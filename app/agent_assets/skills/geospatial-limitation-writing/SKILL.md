---
name: geospatial-limitation-writing
description: Use when a geospatial report must explicitly state method limits, data limits, edge effects, denominator limits, and residual uncertainty without rhetorical softening.
compatibility: opencode
---

# Geospatial Limitation Writing

## Overview
This skill protects the final report from sounding cleaner than the underlying evidence. In this project, good limitation writing is part of correctness. KDE limitation writing is especially important because dense maps invite overconfidence.

## When to Use
- During report synthesis.
- During skeptical review if limitations are missing.
- When the run had repairs, sparse data, or unresolved caveats.

## Required Inputs
- Study-design memo.
- Parameter record.
- Skeptical-review findings.
- Claim trace.

## Workflow
1. Identify method limits.
2. Identify data limits.
3. Identify observation-window and edge-effect limits.
4. Identify claim-boundary limits.
5. Write them plainly and preserve them in the final report.

Do not collapse these categories into one generic uncertainty paragraph. The most useful limitation sections separate what belongs to the method, what belongs to the data, and what belongs to the scope of interpretation. That structure makes later review and later thesis writing much clearer. It also prevents the common failure mode where a very important caveat gets diluted into a vague closing sentence.

For KDE-first work, the default limitation checklist should include at least: study-window dependence, edge effects, parameter sensitivity, sparsity or duplication issues, and any denominator or exposure limit relevant to stronger interpretations.

## Decision Logic
Proceed when limitations are complete, concrete, and method-specific.
Clarify when a limitation depends on unresolved domain context.
Repair when the current limitations are vague, partial, or missing.
Stop when the report would release without disclosing a material limitation.

Material means "changes how a competent reader should interpret the result." If a missing limitation would lead a reader to treat descriptive density as risk, significance, or robust structure when the run cannot support that, the issue is not cosmetic and should not be treated lightly.

## Output Contract
Return:
- `decision`
- `method_limits`
- `data_limits`
- `claim_limits`
- `residual_uncertainty`
- `reason_code`

## Common Mistakes
- Writing generic filler like "there may be some uncertainty".
- Omitting edge effects, sparse events, or missing denominators.
- Downgrading a serious caveat into a minor stylistic footnote.

Also avoid writing limitations as if they were apologies. The point is not to sound timid. The point is to define the valid interpretation boundary of the run clearly and professionally.


## Detailed Rules

### Limitation Writing Rules

#### LIMIT-R01 Limits must be method-specific
Tie limitations to KDE, study window, data sparsity, denominator absence, or review findings.

#### LIMIT-R02 Material limits cannot be hidden
If a caveat changes interpretation, it belongs in the report body, not a vague aside.

#### LIMIT-R03 Residual uncertainty must survive polishing
Do not remove uncertainty because the report sounds stronger without it.

#### LIMIT-R04 Repair history may imply a limitation
If the runtime repaired bandwidth, cell size, or boundary assumptions, that may need disclosure.

#### LIMIT-R05 Unsupported stronger claims require explicit boundary wording
If the report stops short of significance, causality, or risk, say why.

## Failure Modes

### Limitation Writing Failure Modes

#### generic-uncertainty-filler
Response: `repair`.

#### missing-edge-note
Response: `repair`.

#### missing-denominator-limit
Response: `repair`.

#### hidden-repair-consequence
Response: `repair`.

#### no-material-limits-in-final-report
Response: `stop`.

## Worked Examples

### Limitation Writing Examples

#### Good
"Because the study window is bounded and events outside the observed area are unavailable, densities near the boundary may be sensitive to edge effects."

#### Good
"Without denominator data, the map should be read as concentration of observed events rather than per-capita risk."

#### Bad
"There may be some uncertainty in the results."

#### Bad
No mention of sparse data, boundary effects, or interpretation limits even though they shaped the run.

## Supporting Files
- Optional code or snippet files only when executable examples are truly needed.

