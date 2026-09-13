---
name: geospatial-local-data-provenance
description: Use when local data directories, workspace artifacts, and dataset identity must stay explicit for a reproducible geospatial run.
compatibility: opencode
---

# Geospatial Local Data Provenance

## Overview
This skill keeps the runtime honest about where data came from. The system is application-managed and local-first, so later review should be able to identify the exact file, directory, and workspace artifact used in the run. This is important for reproducibility, supervisor review, and thesis experiments.

## When to Use
- Before loading local datasets.
- When multiple attached data directories exist.
- When generated artifacts are written into the session workspace.

## Required Inputs
- Attached data directories.
- Session workspace root.
- Candidate source files.

## Workflow
1. Prefer attached local directories over uncontrolled filesystem wandering.
2. Resolve the chosen source file explicitly.
3. Record provenance for both source and generated artifacts.
4. Preserve workspace-relative paths when possible.
5. Refuse hidden source substitution.

This skill should be applied before and after tool use. Before tool use, it determines where the runtime is allowed to look. After tool use, it determines how the resulting artifacts are named and remembered. That second half is often skipped, which makes later reproducibility weaker than it looks. A good provenance record should let a reviewer answer both "which file was used?" and "where did the run write its outputs?" without guessing.

The application-managed runtime model makes this especially important. Since the backend deliberately isolates runtime config and workspace state, the skill should preserve those managed boundaries instead of leaking back into uncontrolled machine-global paths.

## Decision Logic
Proceed when the source file is explicit and reproducible.
Clarify when multiple plausible files exist and user intent matters.
Repair when a workspace-relative artifact path can replace an unstable temp path.
Stop when the runtime would need to guess which local file is authoritative.

If the run can only continue by searching outside declared local scope, treat that as a real escalation. Provenance mistakes are easy to normalize because they do not always crash the run, but they still damage reproducibility and make later evaluation less trustworthy.

## Output Contract
Return:
- `decision`
- `source_path`
- `attached_directory_used`
- `workspace_artifact_root`
- `reason_code`

## Common Mistakes
- Loading a file from outside the declared local scope without disclosure.
- Reporting a friendly label instead of the actual source path.
- Losing the path to generated artifacts after a later role rewrites them.

Another mistake is keeping the path but losing the role of the file. A provenance record that says "file A was used" is still incomplete if it does not also say whether file A was the event layer, the study-area mask, or an auxiliary context layer.


## Detailed Rules

### Local Data Provenance Rules

#### PROV-R01 Attached directories define preferred scope
Search the declared local scope first. Do not expand to arbitrary filesystem locations without an explicit reason.

#### PROV-R02 Record the exact file used
Layer labels are not enough. Store the actual path or workspace-relative path.

#### PROV-R03 Generated artifacts are part of provenance
The evidence chain includes outputs, not only inputs.

#### PROV-R04 Avoid hidden source substitution
If multiple plausible files exist, do not silently choose the most convenient one.

#### PROV-R05 Prefer stable workspace-relative references
When the run is session-scoped, keep artifact references inside the managed workspace when possible.

## Failure Modes

### Local Data Provenance Failure Modes

#### guessed-source-file
Response: `clarify` or `stop`.

#### hidden-filesystem-expansion
Response: `repair` or `stop`.

#### artifact-path-lost
Response: `repair`.

#### label-without-path
Response: `repair`.

#### duplicate-candidate-files
Response: `clarify`.

## Worked Examples

### Local Data Provenance Examples

#### Good
"The event layer was loaded from the attached directory `/data/beijing-fcd` at `fcd_points_sample.csv`, and all UI-facing outputs were written inside the session workspace and explicitly registered with workspace-relative paths."

#### Good
"Two candidate point files were present in attached directories, so the runtime asked for clarification instead of guessing."

#### Bad
"I found a similar file elsewhere on disk and used that one because it looked newer."

#### Bad
"The report refers to 'the Beijing dataset' without storing the actual path or workspace artifact location."

## Supporting Files
- Optional code or snippet files only when executable examples are truly needed.
