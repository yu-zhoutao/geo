---
name: geospatial-clustering-runbook
description: Use when an unsupervised clustering task is ready for K-means, feature standardization, cluster profiling, artifact registration, and bounded reporting.
compatibility: opencode
---

# Geospatial Unsupervised Clustering Runbook

## Overview
This skill governs the executable unsupervised clustering path. The operator must use `scikit-learn`, `numpy`, `pandas`, and `matplotlib` from the managed geospatial environment for K-means clustering, feature standardization, and cluster profiling.

Clustering is evidence-heavy. A valid run needs multi-variate data, feature standardization, optimal k selection, cluster profiles, cluster maps, and claim boundaries. Without those records, a final "cluster" statement is not auditable.

## When to Use
- Triage selected `unsupervised_clustering` and K-means.
- Data audit confirmed valid multi-variate data with sufficient features.
- The operator must execute clustering, profile clusters, create cluster maps, and register artifacts.

Do not use this skill to decide supervised classification or trend detection. Use appropriate methods first.

## Required Inputs
- Study-design and data-audit contracts.
- Prepared multi-variate data paths, feature names, CRS, and resolution.
- Number of clusters (k) or method for selecting k (Elbow, Silhouette).
- Workspace command contract from `get_session_context`.

## Workflow
1. Read `get_session_context` and confirm package readiness includes `scikit-learn`, `numpy`, `pandas`, and `matplotlib`.
2. Verify multi-variate data, CRS, resolution, feature completeness, and missing value percentage.
3. Import `scikit-learn`, `numpy`, `pandas`, and `matplotlib` in the visible script. If import fails, stop; do not hand-code clustering fallback.
4. Load multi-variate data and align features spatially.
5. Standardize features using z-score normalization: `(x - mean) / std`.
6. Determine optimal k using Elbow method (inertia) or Silhouette analysis.
7. Execute K-means clustering: `KMeans(n_clusters=k, random_state=42)`.
8. Profile clusters using feature means, standard deviations, and distributions.
9. Create cluster classification maps showing spatial distribution of clusters.
10. Create cluster profile charts (radar charts, bar charts) showing feature distributions.
11. Ensure every cluster map artifact, including classification and profile maps, includes a north arrow or north-direction marker, a legend or colorbar, and a truthful scale bar.
12. Register cluster statistics, classification maps, profile charts, manifest, parameter snapshot, and claim trace artifacts through `record_run_evidence` when they should support UI display, review, or reproduction.
13. Report clusters as environmental zones relative to selected clustering parameters.

## Decision Logic
| Gate | Proceed | Clarify or repair | Stop |
| --- | --- | --- | --- |
| Package imports | `scikit-learn`, `numpy`, `pandas`, `matplotlib` import successfully | none | imports fail |
| Multi-variate data | valid features, sufficient completeness | feature alignment needed | insufficient features |
| Feature standardization | z-score normalization applied | standardization method needs choice | no standardization |
| Optimal k | k selected and documented | k selection method needs choice | no k selection |
| Cluster profiles | feature means and distributions recorded | profiling needs refinement | no profiling |

Use `repair` for feature alignment, missing value imputation, or standardization. Use `clarify` for k selection method, feature selection, or cluster interpretation. Use `stop` for invalid imports, insufficient features, or unsupported formal claims.

## Output Contract
Return a clear clustering handoff and register artifacts where useful. A JSON manifest is recommended for parameter-heavy runs.

```json
{
  "decision": "proceed",
  "task_family": "unsupervised_clustering",
  "operator": "clustering",
  "method": "kmeans",
  "parameters": {
    "n_clusters": 5,
    "features": ["elevation", "ndvi", "temperature", "precipitation", "soil_moisture"],
    "standardization": "z_score",
    "k_selection": "elbow",
    "random_state": 42
  },
  "results": {
    "total_pixels": 100000,
    "cluster_counts": {
      "cluster_1": 25000,
      "cluster_2": 20000,
      "cluster_3": 18000,
      "cluster_4": 22000,
      "cluster_5": 15000
    },
    "cluster_percentages": {
      "cluster_1": 25.0,
      "cluster_2": 20.0,
      "cluster_3": 18.0,
      "cluster_4": 22.0,
      "cluster_5": 15.0
    },
    "cluster_profiles": {
      "cluster_1": {"elevation": 500, "ndvi": 0.6, "temperature": 15, "precipitation": 800, "soil_moisture": 0.3},
      "cluster_2": {"elevation": 1200, "ndvi": 0.4, "temperature": 10, "precipitation": 600, "soil_moisture": 0.2},
      "cluster_3": {"elevation": 800, "ndvi": 0.7, "temperature": 18, "precipitation": 1000, "soil_moisture": 0.4},
      "cluster_4": {"elevation": 300, "ndvi": 0.5, "temperature": 20, "precipitation": 700, "soil_moisture": 0.25},
      "cluster_5": {"elevation": 1500, "ndvi": 0.3, "temperature": 5, "precipitation": 500, "soil_moisture": 0.15}
    },
    "inertia": 15000,
    "silhouette_score": 0.45
  },
  "cartographic_elements": {
    "north_arrow": true,
    "legend_or_colorbar": true,
    "scale_bar": true
  },
  "artifacts": [
    {"path": "outputs/cluster-statistics.csv", "artifact_stage": "final", "display_hint": "table"},
    {"path": "outputs/cluster-map.tif", "artifact_stage": "final", "display_hint": "raster"},
    {"path": "outputs/cluster-profiles.png", "artifact_stage": "final", "display_hint": "chart"}
  ],
  "claim_limits": ["environmental zones only", "no supervised classification", "no trend detection"]
}
```

Recommended manifest fields are `decision`, `task_family`, `operator`, `method`, `parameters`, `results`, `artifacts`, and `claim_limits`.

## Common Mistakes
- Running clustering without `scikit-learn` or `pandas` package.
- Reporting clusters without profiling.
- Omitting feature standardization from the snapshot.
- Hiding feature standardization issues in the map.
- Releasing cluster maps without north direction, legend or colorbar, and scale bar.
- Using insufficient features for formal claims.

## Detailed Rules

### Clustering Runbook Rules

#### CLUSTER-R01 Package-backed execution is mandatory
The visible script must import `scikit-learn`, `numpy`, `pandas`, and `matplotlib`. If any import fails, record an environment-not-ready or blocking tool failure and stop. Do not continue with a local reimplementation.

#### CLUSTER-R02 Feature standardization is mandatory
Features must be standardized using z-score normalization before clustering. Do not run K-means on raw features without standardization.

#### CLUSTER-R03 Optimal k must be selected and documented
Number of clusters (k) must be selected using Elbow method, Silhouette analysis, or user specification. Document the k selection method and rationale.

#### CLUSTER-R04 Cluster profiles must be comprehensive
Cluster profiles must include feature means, standard deviations, and distributions. Do not report clusters without comprehensive profiling.

#### CLUSTER-R05 Feature completeness must be documented
Multi-variate data must have sufficient feature completeness. Document missing value percentage and handling method.

#### CLUSTER-R06 Spatial alignment must be verified
Features must be aligned spatially. If reprojection or resampling is needed, document the process.

#### CLUSTER-R07 Every map must include cartographic elements
Every cluster map artifact must show north direction, a legend or colorbar, and a truthful scale bar. This applies to classification and profile maps.

#### CLUSTER-R08 Artifacts should be registered before strong claims
Register cluster statistics, classification maps, profile charts, manifest, parameter snapshot, and claim trace through `record_run_evidence` when they support final interpretation. Claims must cite those artifacts or equally visible transcript evidence.

#### CLUSTER-R09 Reporting stays bounded
Describe clusters as environmental zones relative to selected clustering parameters. Do not claim supervised classification, trend detection, or causal explanation.

## Failure Modes

### Clustering Runbook Failure Modes

#### handwritten-fallback
Symptom: `scikit-learn` import fails and the agent computes K-means manually.
Required action: stop and report environment-not-ready.

#### no-standardization
Symptom: clustering is run on raw features without standardization.
Required action: repair script to include z-score normalization.

#### missing-optimal-k
Symptom: k is selected without documentation or selection method.
Required action: repair analysis to include k selection rationale.

#### missing-cartographic-element
Symptom: a cluster map lacks north direction, legend or colorbar, or scale bar.
Required action: repair the map before registration or release.

#### incomplete-profiling
Symptom: clusters are reported without feature profiling.
Required action: repair analysis to include comprehensive cluster profiles.

## Worked Examples

### Clustering Runbook Examples

#### Good: environmental zone clustering
The script imports `scikit-learn`, `numpy`, `pandas`, and `matplotlib`, loads multi-variate data, standardizes features, selects k using Elbow method, executes K-means, profiles clusters, creates classification and profile maps, and registers statistics, maps, charts, manifest, and clustering parameters.

#### Good: package failure blocks early
The managed environment lacks `scikit-learn`. The operator records a blocking issue and does not compute clustering by hand.

#### Good: significance disclosure
A map caption says "Environmental zones from K-means clustering (k=5) of elevation, NDVI, temperature, precipitation, and soil moisture." The feature standardization is documented.

#### Good: complete cluster map
The cluster map includes a north arrow, cluster legend, and scale bar computed from the analysis CRS.

#### Bad: raw cluster map
The operator maps cluster assignments and calls it "environmental zones." This is a cluster map, not a profiled zone analysis.

#### Bad: no standardization
The operator runs K-means on raw features without standardization.

## Supporting Files
- None. The run-specific Python script and manifest are written in the managed workspace and registered as evidence.