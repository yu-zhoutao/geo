---
name: geospatial-evidence-claim-audit
description: Use when geospatial maps, summaries, or reports must be checked against their supporting artifacts and claim traces before release.
compatibility: opencode
---

# Geospatial Evidence Claim Audit

## Overview
This skill asks a narrow question: which artifacts support which claims, and are those claims stated at the right strength? It is not enough to have artifacts somewhere in the workspace. The runtime must show that a major claim is grounded in a named artifact and that the artifact really supports the language used.

## When to Use
- Before final answer release.
- When skeptical review inspects a report draft.
- When a map caption or summary paragraph is revised.

## Required Inputs
- Claim trace artifact.
- Parameter record.
- Map specification and caption.
- Review findings and major report claims.

## Workflow
1. Identify the major claims, not just paragraphs.
2. Map each major claim to supporting artifacts.
3. Check whether the artifact supports the exact strength of the claim.
4. Flag unsupported or overstated claims.
5. Require repair or stop when support is incomplete.

This skill is most effective when the auditor reads backward from the claim rather than forward from the artifact list. Start with the strongest sentence the report is trying to make, then ask which artifact would convince a skeptical reviewer of exactly that sentence. If the support is indirect, partial, or only stylistic, the claim is not yet grounded.

Do not let "artifact exists" become a lazy substitute for "artifact supports this claim." A KDE raster may support a descriptive concentration statement but not a significance claim. A parameter file may support methodological transparency but not the substantive result. The audit must preserve those distinctions.

## Decision Logic
Proceed when all major claims are supported and consistent with the cited artifacts.
Clarify when a claim depends on a term whose meaning is still unresolved.
Repair when support exists but wording is too strong or references are incomplete.
Stop when a major claim has no adequate supporting artifact.

When judging adequacy, use the artifact most likely to break under cross-examination. If a claim depends on cell size, bandwidth, or weighting, then the parameter record is part of the support set. If a claim depends on review approval, the skeptical-review artifact is part of the support set. This is why claim auditing and artifact traceability belong together.

## Output Contract
Return:
- `decision`
- `major_claims`
- `supported_claims`
- `unsupported_claims`
- `artifact_support_map`
- `reason_code`

## Common Mistakes
- Auditing paragraph tone instead of claim content.
- Treating artifact presence as artifact support.
- Ignoring parameter-sensitive caveats.
- Letting one unsupported sentence survive because the rest of the paragraph is fine.

Also avoid the "one artifact supports everything" shortcut. A single map rarely supports method description, result interpretation, and limitation language all at once. The audit should prefer small, precise mappings over vague references like "supported by the analysis above."


## Detailed Rules

### Evidence Claim Audit Rules

#### ECA-R01 Audit major claims, not prose volume
The unit of review is the major claim. One unsupported sentence is enough to fail the paragraph.

#### ECA-R02 Artifact support must be explicit
Every major claim must cite at least one supporting artifact.

#### ECA-R03 Support strength must match claim strength
An artifact may support descriptive wording but not inferential or causal wording.

#### ECA-R04 Parameter-sensitive claims need parameter artifacts
If interpretation depends on bandwidth, cell size, study area, or weight semantics, the relevant parameter record must be cited.

#### ECA-R05 Unsupported major claims trigger repair or stop
Do not soften the audit because most of the report is good.

## Failure Modes

### Evidence Claim Audit Failure Modes

#### claim-without-artifact
Response: `stop`.

#### artifact-cited-but-not-sufficient
Response: `repair`.

#### missing-parameter-reference
Response: `repair`.

#### unsupported-sentence-hidden-in-good-paragraph
Response: `repair` or `stop`.

#### claim-trace-out-of-date
Response: `repair`.

## Worked Examples

### Evidence Claim Audit Examples

#### Good
Claim: "Higher estimated event density appears in the eastern subarea."
Support: KDE map, run summary, parameter snapshot.

#### Good
Claim: "This should not be interpreted as risk because no denominator artifact exists."
Support: study design and limitation artifact.

#### Bad
Claim: "The KDE proves a statistically significant hotspot pattern."
Support offered: only a KDE raster.
Why wrong: the artifact does not support inferential significance.

#### Bad
The report cites a map but not the parameter record that materially affects interpretation.

## Supporting Files
- Optional code or snippet files only when executable examples are truly needed.

