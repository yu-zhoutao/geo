---
name: geospatial-claim-discipline
description: Use when maps, summaries, or reports must stay inside what the current geospatial method and evidence actually justify.
compatibility: opencode
---

# Geospatial Claim Discipline

## Overview
This skill prevents the system from sounding smarter than its method. The key rule is simple: descriptive outputs stay descriptive unless another method or artifact explicitly supports a stronger claim. In this project, that especially means keeping KDE away from significance, causality, and unsupported risk language.

## When to Use
- During study design.
- During operator result interpretation.
- During map caption writing.
- During final report synthesis and skeptical review.

## Required Inputs
- Method family.
- Current artifacts and claim trace.
- Review findings.

## Workflow
1. Identify the strongest claim a method can support.
2. Identify phrases that imply stronger unsupported claims.
3. Compare every major statement against supporting artifacts.
4. Downgrade or block statements that outrun the method.
5. Preserve explicit limitations in the final wording.

This workflow should be applied at three different moments: once during study design to set the upper claim boundary, once after operator output to interpret the raw result safely, and once before release to catch language drift. That repetition is intentional. Overclaiming often enters late, when the map and prose begin to sound more confident than the method really is.

For KDE-specific work, the strongest safe default is usually some version of "estimated density" or "observed concentration within the study window." Anything stronger should have to justify itself against another artifact or another method family, not against stylistic preference.

## Decision Logic
Proceed when all major claims stay within method and evidence bounds.
Clarify when wording depends on unresolved domain semantics.
Repair when the method is valid but the wording overclaims.
Stop when unsupported major claims survive and cannot be removed without changing the substance of the answer.

The important distinction is between a wording repair and a substantive contradiction. If a sentence can be downgraded from significance to descriptive density while preserving the actual result, `repair` is enough. If the whole answer depends on unsupported risk or causal framing, the correct outcome is `stop` until the claim itself is renegotiated.

## Output Contract
Return:
- `decision`
- `major_claims`
- `unsupported_claims`
- `allowed_language`
- `forbidden_language`
- `reason_code`

## Common Mistakes
- Conflating density with statistical significance.
- Conflating concentration with risk.
- Conflating pattern with cause.
- Writing around missing evidence with polished but unsupported prose.

Another mistake is allowing captions, bullet summaries, or final takeaways to use stronger language than the body text. Claim discipline must be global. If the report body is careful but the map title or executive sentence overclaims, the whole communication artifact is still wrong.


## Detailed Rules

### Claim Discipline Rules

#### CLAIM-R01 Density is descriptive unless another method says more
KDE may support concentration or estimated density language. It does not support significance, causality, or per-capita risk by itself.

#### CLAIM-R02 Major claims need named artifact support
Every major sentence in the final answer should be traceable to artifacts and review outputs.

#### CLAIM-R03 Limitations are part of correctness
If edge effects, sparse data, or scope ambiguity matter, say so explicitly.

#### CLAIM-R04 Pretty prose is not evidence
Do not treat stylistic confidence as methodological confidence.

#### CLAIM-R05 Unsupported major claims must trigger repair or stop
If a statement cannot be downgraded honestly, block release.

## Failure Modes

### Claim Discipline Failure Modes

#### density-as-significance
Response: `repair`.

#### density-as-risk
Response: `repair` or `clarify`.

#### density-as-cause
Response: `repair` or `stop`.

#### unsupported-major-claim
Response: `stop`.

#### limitation-erasure
Response: `repair`.

## Worked Examples

### Claim Discipline Examples

#### Valid
"The KDE surface indicates higher estimated event density in the observed study area."

#### Invalid
"The KDE proves that these locations are statistically significant hotspots."

#### Valid
"Because no denominator data were supplied, the map should be interpreted as event concentration rather than risk."

#### Invalid
"This density map shows which neighborhoods are most dangerous."

#### Valid
"The pattern is exploratory because the point set is sparse and bandwidth-sensitive."

## Supporting Files
- Optional code or snippet files only when executable examples are truly needed.

