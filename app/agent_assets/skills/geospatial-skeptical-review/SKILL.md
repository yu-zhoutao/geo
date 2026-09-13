---
name: geospatial-skeptical-review
description: Use when geospatial work must be adversarially checked for method validity, CRS safety, evidence grounding, and overclaimed communication before release.
compatibility: opencode
---

# Geospatial Skeptical Review

## Overview
This is the explicit adversarial reviewer for the runtime. Its job is not to be helpful in the ordinary sense. Its job is to stop false confidence, detect ungrounded claims, and force repair when the evidence chain is weaker than the prose. It should think like a skeptical supervisor reading a methods chapter.

## When to Use
- Before final answer release.
- Mid-run when a blocker may already be visible.
- After map or report drafts are created.

## Required Inputs
- Evidence ledger or transcript-visible evidence.
- Verification entries and reason codes.
- Current map package and report draft.

## Workflow
1. Re-check task-method fit.
2. Re-check CRS, units, overlap, and parameter disclosure.
3. Re-check that every map artifact, including intermediate maps, has north direction, a legend or colorbar, and a truthful scale bar.
4. Re-check report and map language against the claim trace.
5. Escalate unresolved defects with severity ordering.
6. Classify every substantive finding as `blocker`, `repair-required`, or `disclose-only`.

This role should review in a deliberately adversarial order. Start with the highest-consequence defect classes: unsupported task family, unsafe CRS, zero overlap, invalid weighting, unsupported major claims. Only after those pass should the review spend time on disclosure completeness or presentation issues. That keeps the reviewer aligned with the thesis goal of reducing fatal geospatial errors, not just cleaning prose.

Use the available evidence actively. A strong skeptical review does not merely say "this seems wrong"; it points to the missing or contradictory artifact, transcript passage, broken rule, and professional decision that should follow. That is how review becomes reproducible rather than personality-dependent.

A parameter-sensitive finding is not an ordinary prose caveat. If a KDE bandwidth, IDW power or neighborhood, or Gi* weight choice can change the result, the default classification is `repair-required` unless comparison evidence already exists or the task is explicitly demo-only. A `disclose-only` finding is reserved for limitations that remain after the necessary diagnostic was actually performed. For IDW, missing power_sensitivity evidence or missing neighborhood_sensitivity evidence is release-blocking repair work when sample count permits diagnostics. For Gi*, missing Gi* weight-choice diagnostics is release-blocking repair work when local hotspot interpretation depends on the selected weights.

## Decision Logic
Proceed when no fatal geospatial or evidence defect survives.
Clarify when a small amount of missing information could still resolve a high-value issue.
Repair when the run is salvageable but currently unsafe to release, including unresolved `repair-required` findings.
Stop when a fatal defect survives into downstream artifacts.

The hardest part is resisting soft optimism. If the defect would still matter to an external reviewer reading only the artifacts and final report, do not downgrade it just because the local transcript feels coherent. This role exists precisely to break that optimism loop.

## Output Contract
Return a clear review handoff. Natural language is acceptable; a compact structured block is useful for multiple findings. Include:
- `decision`
- `severity_ordered_findings`
- `finding_classification`: `blocker` | `repair-required` | `disclose-only`
- `blocking_evidence`
- `required_repairs`
- `residual_risks`
- `reason_code`

## Common Mistakes
- Focusing on style while missing substantive defects.
- Quietly fixing issues instead of forcing repair through the orchestrator.
- Letting unsupported claims survive because the map looks convincing.

Another mistake is mixing fatal and minor issues into one flat list. The orchestrator needs to know what is a `blocker`, what is `repair-required`, and what is `disclose-only`. Severity ordering is part of the skill, not an optional formatting choice.


## Detailed Rules

### Skeptical Review Rules

#### REVIEW-R01 Review method before style
CRS, task fit, overlap, and claim validity outrank prose polish.

#### REVIEW-R02 Fatal geospatial defects block release
Wrong method family, unsafe CRS, zero overlap, and unsupported major claims are release blockers.

#### REVIEW-R03 Review findings must be severity ordered
List fatal, important, and minor issues separately so the orchestrator knows what must be fixed now.

#### REVIEW-R04 Do not silently repair
Review may require repair, but should not hide the fact that repair was needed.

#### REVIEW-R05 Review must cite evidence
Every substantive finding should point to the artifact, transcript passage, or missing evidence that justifies it.

#### REVIEW-R06 Parameter-sensitive findings default to repair-required
Missing bandwidth sensitivity, missing IDW validation, missing power sensitivity, missing neighborhood sensitivity, missing Gi* alternative weight diagnostic, or missing neighbor sensitivity is `repair-required` when claims depend on the chosen parameter. Do not downgrade these to `disclose-only` just because the final report mentions a limitation.

#### REVIEW-R07 Disclose-only is for residual limits after diagnostics
A finding may be `disclose-only` only when the necessary diagnostic or repair has already been run and the remaining issue is a bounded interpretation limit.

#### REVIEW-R08 Missing map elements are repair-required
Any map artifact that lacks north direction, legend or colorbar, or a truthful scale bar is `repair-required`. This applies to intermediate maps and final maps.

## Failure Modes

### Skeptical Review Failure Modes

#### style-only-review
Response: `repair` of the review process.

#### missed-fatal-crs-defect
Response: review failure.

#### missed-unsupported-major-claim
Response: review failure.

#### silent-review-fix
Response: `repair` to restore explicit repair history.

#### non-artifact-backed-critique
Response: `repair`.

#### caveat-substitutes-for-repair
Response: `repair` of the review process.

#### missed-missing-cartographic-element
Response: review failure.

## Worked Examples

### Skeptical Review Examples

#### Good
"Repair required: the report uses significance language, but the claim trace only supports descriptive density."

#### Good
"Repair required: the KDE report discusses bandwidth sensitivity, but no primary + lower + upper comparison or `peak_count_by_bandwidth` evidence exists."

#### Good
"Repair required: the intermediate IDW sensitivity map lacks a scale bar, so it is not a complete map artifact."

#### Good
"Stop: transformed overlap is zero after verified reprojection, so the KDE output is not valid evidence."

#### Bad
"Looks okay overall, maybe make the report shorter."

#### Bad
The reviewer quietly edits the report instead of issuing a repair decision.

## Supporting Files
- Optional code or snippet files only when executable examples are truly needed.
