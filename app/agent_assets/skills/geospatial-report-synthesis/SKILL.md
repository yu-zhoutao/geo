---
name: geospatial-report-synthesis
description: Use when verified geospatial artifacts and reviewer findings must be compiled into a concise but evidence-grounded report.
compatibility: opencode
---

# Geospatial Report Synthesis

## Overview
This skill compiles the run into a final analytical narrative. It should sound clear, but clarity is not the main goal. The report must stay subordinate to the transcript evidence, parameter records, durable artifacts, and skeptical-review findings. It is a synthesis skill, not a second analysis engine.

## When to Use
- After operator artifacts and review findings exist.
- Before final answer release.
- When a thesis-style methods/results summary is needed.

## Required Inputs
- Evidence ledger or transcript-visible evidence.
- Claim trace.
- Skeptical-review findings.
- Map package and parameter records.

## Workflow
1. Summarize methods from the recorded artifacts.
2. Summarize results only at the strength supported by the claim trace.
3. Include limitations and unresolved risk.
4. Produce a final report draft that can survive skeptical review.

The report should usually be assembled in the same order a thesis reader would evaluate it: what was the question, what data and method were used, what was found, and what remains limited or uncertain. This keeps the prose aligned with the evidence chain instead of turning the report into a stylized afterthought. If a step cannot be written from artifacts or transcript-visible evidence, that is a warning sign that the evidence trail or claim trace is still incomplete.

This skill should also resist narrative inflation. It is tempting to connect every artifact into a smooth story, but some runs should end with explicit caution, unresolved scope, or a statement that a stronger method would be needed for a stronger conclusion.

## Decision Logic
Proceed when methods, results, limitations, and claim trace are aligned.
Clarify when a material ambiguity still affects report wording.
Repair when the report is mostly valid but overstates or omits something important.
Stop when a major unsupported claim remains unresolved.

The difference between `repair` and `stop` here is whether the report can be corrected without changing the substance of the run. If the text is merely too strong, repair is enough. If the run itself lacks the evidence needed for a central claim, the report must stop instead of compensating with rhetoric.

## Output Contract
Return a clear report handoff. Natural language is acceptable; a compact structured block is useful when it improves reviewability. Include:
- `decision`
- `methods_summary`
- `results_summary`
- `limitations_summary`
- `claim_trace_summary`
- `reason_code`

## Common Mistakes
- Re-analyzing the data in prose.
- Writing stronger claims than the operator and review artifacts allow.
- Omitting material limitations because they sound less impressive.

Another mistake is treating the report as a place to hide unresolved design defects. If the skeptical reviewer said the task family was only partially supported or that denominator logic was missing, the report should expose that limitation rather than bury it.


## Detailed Rules

### Report Synthesis Rules

#### REPORT-R01 Report compiles, it does not invent
Methods and results come from artifacts, not fresh intuition.

#### REPORT-R02 Methods section must cite real preprocessing and parameter evidence
Do not summarize preprocessing or KDE settings from memory. Cite artifacts where available, or point to transcript-visible parameter records.

#### REPORT-R03 Results section must obey claim discipline
If the claim trace does not support it, the report must not say it.

#### REPORT-R04 Limitations are mandatory
Sparse data, edge effects, denominator limits, and unresolved uncertainty belong in the final report.

#### REPORT-R05 Skeptical review findings outrank rhetorical convenience
If review found a blocker, the report cannot hide it.

## Failure Modes

### Report Synthesis Failure Modes

#### prose-invents-analysis
Response: `repair` or `stop`.

#### unsupported-major-claim-in-results
Response: `stop`.

#### methods-without-artifact-citation
Response: `repair`.

#### limitation-omission
Response: `repair`.

#### review-blocker-smoothed-over
Response: `stop`.

## Worked Examples

### Report Synthesis Examples

#### Good
Methods cite the prepared-input artifact, CRS decision, and KDE parameter snapshot.
Results describe estimated density concentration only.
Limitations mention edge effects and claim boundaries.

#### Bad
The report adds causal interpretation not present in any artifact.

#### Bad
The report omits skeptical-review concerns because the final paragraph sounds cleaner without them.

## Supporting Files
- Optional code or snippet files only when executable examples are truly needed.
