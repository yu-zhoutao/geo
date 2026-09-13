---
name: geospatial-kde-interpretation-boundaries
description: Use when KDE outputs must be interpreted as descriptive density only and protected from significance, causality, or unsupported risk language.
compatibility: opencode
---

# Geospatial KDE Interpretation Boundaries

## Overview
This skill protects the final meaning of KDE. It exists because density maps look persuasive. Chapter 6 of the textbook covers spatial patterns, LISA, and SatScan, which are closer to significance-oriented hotspot reasoning than KDE is. If the runtime does not lock interpretation boundaries explicitly, later roles will overclaim.

## When to Use
- Immediately after KDE execution.
- During map caption writing.
- During report synthesis.
- During skeptical review.

## Required Inputs
- KDE operator artifacts.
- Claim trace.
- Review findings.
- Current report or caption text if any.

## Workflow
1. State the strongest supported descriptive claim.
2. List the forbidden stronger claims.
3. Check downstream text and figures against that boundary.
4. Downgrade wording or block release when necessary.

This should be done as a language audit and a method audit at the same time. The method audit asks what KDE actually produces: an estimated density surface over an observed study window. The language audit asks whether the prose, title, caption, or takeaway turns that descriptive output into something stronger. If either side drifts, the skill should force a repair.

Chapter 6 is helpful here because it contains families that are closer to inferential hotspot reasoning. Use that distinction explicitly: if a sentence sounds like it belongs to LISA, SatScan, or a causal model, it does not belong in a KDE-only output.

## Decision Logic
Proceed when every major statement stays descriptive.
Clarify when the user explicitly asks for risk or significance and the runtime needs to renegotiate scope.
Repair when wording drifts beyond the method.
Stop when unsupported major claims remain unresolved.

The `clarify` path is important. Sometimes the user really does want inferential or risk-oriented analysis. In those cases, this skill should not merely soften the wording quietly. It should surface the scope mismatch so the user can decide whether a descriptive-density downgrade is acceptable.

## Output Contract
Return:
- `decision`
- `allowed_language`
- `forbidden_language`
- `major_claims`
- `unsupported_claims`
- `reason_code`

## Common Mistakes
- Using "significant hotspot" in a KDE-only workflow.
- Converting concentration into danger or probability.
- Letting a colorful map imply inferential certainty.

Also watch for apparently mild phrases like "reveals the true hotspot structure" or "confirms high-risk areas." They sound descriptive, but they still smuggle in stronger claims than KDE alone can bear.


## Detailed Rules

### KDE Interpretation Boundary Rules

#### KINT-R01 Density is not significance
Do not use significance, p-value, confidence, or inferential hotspot wording in a KDE-only workflow.

#### KINT-R02 Density is not causality
Do not treat co-location or concentration as evidence of mechanism or cause.

#### KINT-R03 Density is not standalone risk proof
Without denominator or exposure logic, the correct statement is concentration, not risk.

#### KINT-R04 Captions and map titles must respect the same boundary as the report
Cartography is part of interpretation, not just decoration.

#### KINT-R05 Unsupported major claims must be repaired before release
Do not preserve strong but wrong wording for rhetorical convenience.

## Failure Modes

### KDE Interpretation Boundary Failure Modes

#### significance-creep
Response: `repair`.

#### causal-creep
Response: `repair` or `stop`.

#### risk-creep
Response: `repair` or `clarify`.

#### map-title-overclaim
Response: `repair`.

#### claim-trace-mismatch
Response: `stop`.

## Worked Examples

### KDE Interpretation Boundary Examples

#### Valid
"The surface indicates higher estimated event density within the observed study area."

#### Invalid
"These statistically significant hotspots show where the disease is caused by environmental exposure."

#### Valid
"Without denominator data, the result should not be interpreted as per-capita risk."

#### Invalid
"The darkest cells are the most dangerous neighborhoods."

## Supporting Files
- Optional code or snippet files only when executable examples are truly needed.

