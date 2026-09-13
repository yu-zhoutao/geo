---
name: geospatial-artifact-traceability
description: Use when a geospatial run should preserve durable evidence for artifacts, parameter records, review outputs, and claim traces.
compatibility: opencode
---

# Geospatial Artifact Traceability

## Overview
This skill defines what a thesis-grade evidence chain looks like. The transcript is the primary record of the agent process, and durable artifacts make that process easier to review, reproduce, and cite without replaying the whole conversation. This skill turns traceability into a concrete but non-exclusive ledger.

## When to Use
- At session start to define required artifacts.
- During preprocessing and operator execution.
- Before final report synthesis.
- During skeptical review.

## Required Inputs
- Task contract or user request.
- Runtime activity trace.
- Generated artifact paths.
- Verification entries and reason codes.

## Workflow
1. Define the recommended ledger entries for the task family.
2. Record stage artifacts as soon as they become valid.
3. Preserve parameter snapshots and control-state reasons.
4. Link final claims back to their supporting artifacts.
5. Reject final reporting when the transcript and artifacts together do not support a major claim.

In practice, this means the role using this skill should stop thinking only in terms of "final output" and start thinking in terms of "stage evidence." Before preprocessing, ask which artifacts would make an operator run auditable. Before report synthesis, ask which missing evidence would make a major claim unsupported. If the runtime repaired anything, capture both the original and repaired value. If skeptical review forced a change, make sure the repair path is visible in the transcript or ledger.

The easiest way to misuse this skill is to wait until the end of the run and then dump whatever files happen to exist into a manifest. Real traceability is built incrementally, stage by stage, with enough structure that later experiments can calculate artifact completeness, claim support coverage, and repair yield without replaying every message.

Use the runtime context and evidence tools as the stable bridge between ordinary scripts and the UI. Call `get_session_context` first to inspect the workspace root, attached data roots, package readiness, and evidence reporting rules. The workspace has no required internal directory layout: choose clear workspace-relative paths such as `scripts/vector_profile.py` or `outputs/vector-profile.json`, then run scripts through:

```bash
"$GEO_AGENT_UV_BIN" --project "$GEO_AGENT_GEO_PYTHON_PROJECT" run --python "$GEO_AGENT_GEO_PYTHON_VERSION" python <script>
```

The script should read paths from `GEO_AGENT_WORKSPACE_PATH` and `GEO_AGENT_ATTACHED_DATA_DIRS_JSON`, not from hard-coded local machine paths or application-defined output directories. After the script creates a durable output inside the workspace, call `record_run_evidence` when the output should be visible in the UI or reusable for later review. Artifact records should include `path`, `title`, `format`, `display_hint`, and `artifact_stage`, and the file must already exist before it is registered. Use `artifact_stage: intermediate` for diagnostic previews, audit tables, temporary maps, parameter snapshots, or repair evidence. Use `artifact_stage: final` only for outputs that the final answer may promote into the dashboard's final artifact area.

Example artifact evidence shape:

```json
{
  "record_type": "artifact",
  "title": "KDE bandwidth parameter snapshot",
  "path": "outputs/kde-parameters.json",
  "format": "json",
  "display_hint": "json",
  "artifact_stage": "intermediate",
  "category": "metadata",
  "description": "Bandwidth, cell size, weight policy, CRS, and study-window assumptions used by the agent-authored script.",
  "provenance": {
    "script_path": "scripts/kde_prepare_parameters.py",
    "command": "\"$GEO_AGENT_UV_BIN\" --project \"$GEO_AGENT_GEO_PYTHON_PROJECT\" run --python \"$GEO_AGENT_GEO_PYTHON_VERSION\" python scripts/kde_prepare_parameters.py",
    "inputs": ["attached point layer", "study area layer"],
    "parameters": {"bandwidth_meters": 1000, "cell_size_meters": 250}
  }
}
```

Example verification evidence shape:

```json
{
  "record_type": "verification_fact",
  "title": "CRS and bounding-box overlap check",
  "data": {
    "status": "passed",
    "reason_code": "CRS_AND_BBOX_VALIDATED",
    "checked_inputs": ["point layer", "study area layer"],
    "conclusion": "Both layers are available in the projected analysis CRS and overlap inside the study window."
  }
}
```

Reusable Python primitive snippets:

```python
from pathlib import Path
import json
import os

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from matplotlib.axes import Axes
from rasterio.mask import mask
from matplotlib.patches import Patch
from shapely.geometry import box, mapping
from sklearn.neighbors import KernelDensity

workspace: Path = Path(os.environ['GEO_AGENT_WORKSPACE_PATH'])
outputs_dir: Path = workspace / 'outputs'
outputs_dir.mkdir(parents=True, exist_ok=True)
attached_dirs: list[Path] = [Path(item) for item in json.loads(os.environ.get('GEO_AGENT_ATTACHED_DATA_DIRS_JSON', '[]'))]


def inspect_vector(path: Path) -> dict[str, object]:
    gdf: gpd.GeoDataFrame = gpd.read_file(path)
    return {
        'path': str(path),
        'rows': int(len(gdf)),
        'columns': list(gdf.columns),
        'crs': gdf.crs.to_string() if gdf.crs is not None else None,
        'bbox': [float(value) for value in gdf.total_bounds],
        'geometry_types': sorted(str(value) for value in gdf.geometry.geom_type.dropna().unique()),
    }


def inspect_raster(path: Path) -> dict[str, object]:
    with rasterio.open(path) as src:
        return {
            'path': str(path),
            'width': int(src.width),
            'height': int(src.height),
            'count': int(src.count),
            'crs': src.crs.to_string() if src.crs is not None else None,
            'bbox': [float(value) for value in src.bounds],
            'resolution': [float(value) for value in src.res],
        }


def require_metric_crs(gdf: gpd.GeoDataFrame, target_epsg: int) -> gpd.GeoDataFrame:
    if gdf.crs is None:
        raise ValueError('Input vector layer has no CRS.')
    projected: gpd.GeoDataFrame = gdf.to_crs(epsg=target_epsg)
    if not projected.crs or not projected.crs.axis_info or projected.crs.axis_info[0].unit_name.lower() not in {'metre', 'meter'}:
        raise ValueError(f'Analysis CRS EPSG:{target_epsg} is not metric.')
    return projected


def bbox_overlap(left: gpd.GeoDataFrame, right: gpd.GeoDataFrame) -> bool:
    return bool(box(*left.total_bounds).intersects(box(*right.total_bounds)))


def clip_vector_to_study_area(gdf: gpd.GeoDataFrame, study_area: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    aligned_study_area: gpd.GeoDataFrame = study_area.to_crs(gdf.crs)
    return gpd.clip(gdf, aligned_study_area)


def clip_raster_to_study_area(raster_path: Path, study_area: gpd.GeoDataFrame, output_path: Path) -> None:
    with rasterio.open(raster_path) as src:
        shapes: list[dict[str, object]] = [mapping(geom) for geom in study_area.to_crs(src.crs).geometry]
        data, transform = mask(src, shapes, crop=True)
        profile: dict[str, object] = dict(src.profile)
        profile.update({'height': data.shape[1], 'width': data.shape[2], 'transform': transform})
        with rasterio.open(output_path, 'w', **profile) as dst:
            dst.write(data)


def compute_kde_grid(points: gpd.GeoDataFrame, bandwidth_meters: float, cell_size_meters: float) -> dict[str, object]:
    coords: np.ndarray = np.column_stack([points.geometry.x.to_numpy(), points.geometry.y.to_numpy()])
    kde = KernelDensity(bandwidth=bandwidth_meters, kernel='gaussian')
    kde.fit(coords)
    minx, miny, maxx, maxy = [float(value) for value in points.total_bounds]
    xs: np.ndarray = np.arange(minx, maxx + cell_size_meters, cell_size_meters)
    ys: np.ndarray = np.arange(miny, maxy + cell_size_meters, cell_size_meters)
    grid_x, grid_y = np.meshgrid(xs, ys)
    sample_points: np.ndarray = np.column_stack([grid_x.ravel(), grid_y.ravel()])
    density: np.ndarray = np.exp(kde.score_samples(sample_points)).reshape(grid_x.shape)
    return {'x': grid_x, 'y': grid_y, 'density': density}


def add_basic_cartographic_elements(
    ax: Axes,
    *,
    scale_length: float | None = None,
    scale_label: str | None = None,
    legend_label: str = 'Layer',
) -> None:
    x_min, x_max = ax.get_xlim()
    y_min, y_max = ax.get_ylim()
    width = x_max - x_min
    height = y_max - y_min
    resolved_scale_length = scale_length or width / 5
    x0 = x_min + width * 0.08
    y0 = y_min + height * 0.08
    ax.annotate(
        'N',
        xy=(0.94, 0.92),
        xytext=(0.94, 0.80),
        xycoords='axes fraction',
        ha='center',
        va='center',
        arrowprops={'arrowstyle': '-|>', 'linewidth': 1.5, 'color': 'black'},
    )
    ax.plot([x0, x0 + resolved_scale_length], [y0, y0], color='black', linewidth=3)
    ax.text(
        x0 + resolved_scale_length / 2,
        y0 + height * 0.025,
        scale_label or f'{resolved_scale_length:,.0f} map units',
        ha='center',
        va='bottom',
        fontsize=9,
    )
    ax.legend(
        handles=[Patch(facecolor='none', edgecolor='black', label=legend_label)],
        loc='lower right',
        frameon=True,
    )


def render_vector_map(gdf: gpd.GeoDataFrame, output_path: Path, title: str) -> None:
    fig, ax = plt.subplots(figsize=(8, 6))
    gdf.plot(ax=ax, linewidth=0.5, edgecolor='black')
    ax.set_title(title)
    add_basic_cartographic_elements(ax)
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def write_parameter_snapshot(output_path: Path, values: dict[str, object]) -> None:
    output_path.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding='utf-8')
```

After a snippet writes a durable output, register it with `record_run_evidence` when it supports review, dashboard display, or reproduction. Use `record_type: dataset_profile` for vector and raster inspection JSON, `record_type: verification_fact` for CRS and bbox checks, `record_type: parameter_snapshot` for method settings, and `record_type: artifact` for map, table, raster, report, or archive files that the UI should show. Files written into the workspace but not registered remain ordinary workspace files; they can still be discussed in the transcript, but they are not automatically promoted into the dashboard.

## Decision Logic
Proceed when the transcript and available artifacts support the current stage's claims.
Clarify when a missing evidence item depends on a user or upstream role decision.
Repair when an artifact exists but is not yet linked, named, stored correctly, or explained clearly enough for review.
Stop when the run would finalize without enough substantive evidence to support its claims.

When in doubt, think in two passes. First ask whether the artifact exists. Second ask whether it is usable by a reviewer who was not present during generation. A file with no clear role, no parameter provenance, or no claim linkage should be treated as incomplete evidence, not as a successful artifact. This skill should be conservative because optimistic traceability is worse than admitting a missing link.

## Output Contract
Return:
- `decision`
- `recommended_artifacts`
- `present_artifacts`
- `missing_artifacts`
- `claim_trace_status`
- `reason_code`

For high-value runs, include a short note explaining the next unsafe step if the missing artifacts remain unresolved. That makes the handoff actionable rather than merely descriptive.

## Common Mistakes
- Treating the transcript as if it made all durable evidence unnecessary.
- Recording a summary report but not the parameter record behind it.
- Producing final claims before review artifacts exist.
- Keeping artifacts but never linking them to claims.

Another recurring mistake is flattening all artifacts into one undifferentiated manifest. The ledger should preserve stage semantics: task intent is not the same as study design; a parameter snapshot is not the same as a review artifact; and a claim trace is not the same as a final markdown report. If those distinctions disappear, later review becomes slower and more fragile.


## Detailed Rules

### Artifact Traceability Rules

#### TRACE-R01 Every substantive stage should leave durable evidence
For thesis-grade runs, preserve task intent, study design, data audit, CRS decision, extent checks, parameter snapshot, skeptical review, and claim trace when they exist.

#### TRACE-R02 Parameters are first-class evidence
Bandwidth, cell size, weight policy, units, and edge notes must survive as artifacts, not just prose.

#### TRACE-R02A Evidence registration must be UI-addressable
Artifact records must carry explicit format, display hint, and `artifact_stage` metadata so the dashboard can display intermediate and final outputs without requiring the user to browse the workspace manually.

#### TRACE-R03 Control-state reasons should be reviewable
`clarify`, `repair`, and `stop` decisions should have visible reasons and blocking evidence, whether expressed in transcript prose or structured records.

#### TRACE-R04 Major conclusions need support
Every major claim must cite supporting artifacts or clearly visible transcript evidence.

#### TRACE-R05 Missing ledger items block strong conclusions
Do not allow polished final reporting to outrun incomplete evidence.

## Failure Modes

### Artifact Traceability Failure Modes

#### transcript-only-evidence
Response: `repair`.

#### parameter-record-missing
Response: `repair`.

#### review-artifact-missing
Response: `repair` or `stop`.

#### unsupported-claim-without-trace
Response: `stop`.

#### path-recorded-but-unlinked
Response: `repair`.

## Worked Examples

### Artifact Traceability Examples

#### Good
The run ledger contains task intent, study design, data audit, CRS decision, extent checks, parameter snapshot, skeptical review, and claim trace. The final report cites the claim trace.

#### Good
The agent writes `scripts/vector_profile.py`, runs it with the managed `uv` command, produces `outputs/vector-profile.json`, and registers it through `record_run_evidence` as an intermediate JSON artifact with command provenance.

#### Good
The report draft is blocked because the claim trace does not yet support a major sentence.

#### Bad
"The assistant already explained the reasoning in chat, so we do not need separate artifacts."

#### Bad
The manifest lists artifact paths, but no claim trace links those artifacts to conclusions.

## Supporting Files
- Optional code or snippet files only when executable examples are truly needed.
