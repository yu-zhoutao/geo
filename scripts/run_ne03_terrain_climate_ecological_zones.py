#!/usr/bin/env python3
"""Run NE03: unsupervised terrain--climate--vegetation ecological zones."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT.parent / "dataset"
sys.path.insert(0, str(ROOT / "app" / "runtime_assets" / "geospatial-python"))
from geo_multisource import parse_modis_timestamp, scale_modis_values  # noqa: E402

YEARS = list(range(2018, 2023))
GROWTH_MONTHS = {5, 6, 7, 8, 9}


def _warp(path: Path, target_profile: dict[str, object], *, resampling: str, src_nodata=None, dst_nodata=np.nan) -> np.ndarray:
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.vrt import WarpedVRT

    with rasterio.open(path) as src:
        nodata = src_nodata if src_nodata is not None else src.nodata
        with WarpedVRT(src, crs=target_profile["crs"], transform=target_profile["transform"], width=target_profile["width"], height=target_profile["height"], resampling=getattr(Resampling, resampling), src_nodata=nodata, nodata=dst_nodata, dtype="float32") as vrt:
            return vrt.read(1, out_dtype="float32")


def _load_modis_target(data_dir: Path, product: str, profile: dict[str, object]) -> tuple[np.ndarray, np.ndarray]:
    root = data_dir / "MODIS" / f"{product.upper()}_2018-2022"
    files = []
    for path in sorted(root.rglob("*.tif")):
        if "aid0001" not in path.name:
            continue
        stamp = parse_modis_timestamp(path)
        if stamp.year in YEARS and stamp.month in GROWTH_MONTHS:
            files.append((stamp, path))
    annual_mean, annual_amp = [], []
    for year in YEARS:
        total = np.zeros((profile["height"], profile["width"]), dtype="float64")
        count = np.zeros_like(total)
        low = np.full_like(total, np.inf)
        high = np.full_like(total, -np.inf)
        for stamp, path in files:
            if stamp.year != year:
                continue
            with __import__("rasterio").open(path) as src:
                raw = src.read(1).astype("float32")
            raw[raw <= -2999] = np.nan
            arr = scale_modis_values(raw, product)
            valid = np.isfinite(arr)
            total[valid] += arr[valid]
            count[valid] += 1
            low[valid] = np.minimum(low[valid], arr[valid])
            high[valid] = np.maximum(high[valid], arr[valid])
        annual_mean.append(np.divide(total, count, out=np.full_like(total, np.nan), where=count > 0).astype("float32"))
        amp = high - low
        amp[~np.isfinite(amp)] = np.nan
        annual_amp.append(amp.astype("float32"))
    return np.stack(annual_mean), np.stack(annual_amp)


def _source_profile(lat: np.ndarray, lon: np.ndarray) -> dict[str, object]:
    from affine import Affine

    dx = float(np.median(np.diff(lon)))
    dy = float(abs(np.median(np.diff(lat))))
    return {"crs": "EPSG:4326", "transform": Affine.translation(float(lon.min() - dx / 2), float(lat.max() + dy / 2)) * Affine.scale(dx, -dy), "width": int(lon.size), "height": int(lat.size)}


def _write_raster(path: Path, arr: np.ndarray, profile: dict[str, object], dtype: str = "float32", nodata=0) -> None:
    import rasterio

    p = profile.copy()
    p.update(driver="GTiff", count=1, dtype=dtype, compress="deflate", nodata=nodata)
    with rasterio.open(path, "w", **p) as dst:
        dst.write(np.asarray(arr, dtype=dtype), 1)


def _plot_zones(path: Path, zones: np.ndarray, profile: dict[str, object], selected_k: int, data_dir: Path) -> None:
    """Write a geospatial journal-style ecological-zone map."""
    import matplotlib

    matplotlib.use("Agg")
    import geopandas as gpd
    import matplotlib.pyplot as plt
    from matplotlib.colors import BoundaryNorm, ListedColormap
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    from matplotlib.ticker import FuncFormatter, MaxNLocator
    from rasterio.features import shapes
    from shapely.geometry import shape as shapely_shape

    matplotlib.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
            "font.size": 8,
            "axes.titlesize": 12,
            "axes.labelsize": 8.5,
            "xtick.labelsize": 7.5,
            "ytick.labelsize": 7.5,
            "legend.fontsize": 6.8,
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
        }
    )

    shape_root = data_dir / "Shapefiles" / "gafm41_CHN_SHP"
    provinces_wgs84 = gpd.read_file(shape_root / "gadm41_CHN_1.shp").to_crs("EPSG:4326")
    study_wgs84 = gpd.read_file(data_dir / "Shapefiles" / "black_earth.shp").to_crs("EPSG:4326")
    provinces = provinces_wgs84.to_crs(profile["crs"])
    study = study_wgs84.to_crs(profile["crs"])

    transform = profile["transform"]
    valid = zones > 0
    rows, cols = np.where(valid)
    if rows.size == 0:
        raise ValueError("NE03 contains no valid ecological-zone cells")
    r0, r1 = max(int(rows.min()) - 12, 0), min(int(rows.max()) + 13, zones.shape[0])
    c0, c1 = max(int(cols.min()) - 12, 0), min(int(cols.max()) + 13, zones.shape[1])
    cropped = np.ma.masked_equal(zones[r0:r1, c0:c1], 0)
    left = float(transform.c + c0 * transform.a)
    right = float(transform.c + c1 * transform.a)
    top = float(transform.f + r0 * transform.e)
    bottom = float(transform.f + r1 * transform.e)
    valid_geom = gpd.GeoSeries(
        [shapely_shape(geom) for geom, value in shapes(valid.astype("uint8"), mask=valid, transform=transform) if value],
        crs=profile["crs"],
    ).union_all()
    data_footprint_wgs84 = gpd.GeoSeries([valid_geom], crs=profile["crs"]).to_crs("EPSG:4326")

    xpad = max(12000.0, (right - left) * 0.035)
    ypad = max(12000.0, (top - bottom) * 0.035)
    view_extent = (left - xpad, right + xpad, bottom - ypad, top + ypad)
    zone_colors = list(plt.get_cmap("tab10").colors[:selected_k])
    cmap = ListedColormap(zone_colors)
    norm = BoundaryNorm(np.arange(0.5, selected_k + 1.5), cmap.N)

    fig, ax = plt.subplots(figsize=(11.5, 8.5), dpi=400)
    provinces.plot(ax=ax, facecolor="white", edgecolor="#b5b5b5", linewidth=0.55, zorder=0, rasterized=True)
    image = ax.imshow(
        cropped,
        extent=(left, right, bottom, top),
        origin="upper",
        cmap=cmap,
        norm=norm,
        interpolation="nearest",
        alpha=0.95,
        zorder=1,
    )
    provinces.boundary.plot(ax=ax, color="#8c8c8c", linewidth=0.55, zorder=2, rasterized=True)
    study.boundary.plot(ax=ax, color="#222222", linewidth=1.15, zorder=3, rasterized=True)

    context_legend = ax.legend(
        handles=[
            Patch(facecolor="#2c7fb8", edgecolor="#174a73", label="NE03 data footprint"),
            Line2D([0], [0], color="#222222", lw=1.15, label="Black-earth boundary"),
            Line2D([0], [0], color="#8c8c8c", lw=0.55, label="Provincial boundary"),
        ],
        loc="center right",
        bbox_to_anchor=(0.70, 0.82),
        ncol=1,
        framealpha=0.95,
        borderpad=0.45,
        handlelength=1.0,
    )

    cbar = fig.colorbar(image, ax=ax, fraction=0.035, pad=0.025, shrink=0.82, ticks=np.arange(1, selected_k + 1))
    cbar.set_label("ecological zone", fontsize=8.5)
    cbar.ax.tick_params(labelsize=7.2, length=2.5)

    inset = ax.inset_axes([0.72, 0.70, 0.27, 0.24], facecolor="white", zorder=25)
    provinces_wgs84.plot(ax=inset, facecolor="white", edgecolor="#4d4d4d", linewidth=0.45, zorder=0, rasterized=True)
    data_footprint_wgs84.plot(ax=inset, facecolor="#2c7fb8", edgecolor="#174a73", linewidth=0.6, zorder=1, rasterized=True)
    inset.set_xlim(*[float(v) for v in provinces_wgs84.total_bounds[[0, 2]]])
    inset.set_ylim(*[float(v) for v in provinces_wgs84.total_bounds[[1, 3]]])
    inset.set_aspect("equal", adjustable="box")
    inset.set_xticks([])
    inset.set_yticks([])
    inset.set_title("China", fontsize=8, fontweight="bold", loc="left", pad=2)
    for spine in inset.spines.values():
        spine.set_linewidth(0.7)

    ax.set_xlim(view_extent[0], view_extent[1])
    ax.set_ylim(view_extent[2], view_extent[3])
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Sinusoidal easting (m)", labelpad=8)
    ax.set_ylabel("Sinusoidal northing (m)", labelpad=8)
    ax.xaxis.set_major_locator(MaxNLocator(6))
    ax.yaxis.set_major_locator(MaxNLocator(6))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value / 1e6:.2f}"))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value / 1e6:.2f}"))
    ax.set_title(f"NE03 | unsupervised ecological zones (k={selected_k})", loc="left", fontsize=12, fontweight="bold", pad=10)
    ax.grid(False)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_linewidth(0.8)

    ax.annotate(
        "N",
        xy=(0.95, 0.22),
        xytext=(0.95, 0.10),
        xycoords="axes fraction",
        ha="center",
        va="center",
        fontsize=10,
        arrowprops={"arrowstyle": "-|>", "lw": 1.25, "color": "black"},
        zorder=30,
    )
    scale_km = 200.0
    scale_m = scale_km * 1000.0
    x0 = view_extent[0] + (view_extent[1] - view_extent[0]) * 0.44
    y0 = view_extent[2] + (view_extent[3] - view_extent[2]) * 0.06
    ax.plot([x0, x0 + scale_m / 2], [y0, y0], color="#222222", lw=6, solid_capstyle="butt", zorder=31)
    ax.plot([x0 + scale_m / 2, x0 + scale_m], [y0, y0], color="white", lw=6, solid_capstyle="butt", zorder=31)
    ax.plot([x0, x0 + scale_m], [y0, y0], color="#222222", lw=0.7, zorder=32)
    ax.text(x0, y0 - (view_extent[3] - view_extent[2]) * 0.035, "0", ha="center", va="top", fontsize=7)
    ax.text(x0 + scale_m / 2, y0 - (view_extent[3] - view_extent[2]) * 0.035, "100", ha="center", va="top", fontsize=7)
    ax.text(x0 + scale_m, y0 - (view_extent[3] - view_extent[2]) * 0.035, "200 km", ha="center", va="top", fontsize=7)

    fig.tight_layout()
    fig.savefig(path, dpi=400, bbox_inches="tight", facecolor="white")
    fig.savefig(path.with_suffix(".pdf"), bbox_inches="tight", facecolor="white")
    fig.savefig(path.with_suffix(".svg"), bbox_inches="tight", facecolor="white")
    fig.savefig(path.with_suffix(".tiff"), dpi=600, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def run(data_dir: Path, output_dir: Path) -> dict[str, object]:
    from scipy.ndimage import maximum_filter, minimum_filter
    from sklearn.cluster import KMeans
    from sklearn.metrics import adjusted_rand_score, silhouette_score
    from sklearn.preprocessing import StandardScaler
    import rasterio

    output_dir.mkdir(parents=True, exist_ok=True)
    ne02 = ROOT / "outputs" / "NE02_climate_vegetation_stress" / "ne02_grids.npz"
    if not ne02.exists():
        raise FileNotFoundError(f"Run NE02 first; missing {ne02}")
    g = np.load(ne02)
    years = g["years"]
    with rasterio.open(ROOT / "outputs" / "NE01_land_cover_vegetation_change" / "transition_map_1km.tif") as target:
        target_profile = target.profile.copy()
        transition = target.read(1)
    target_profile.update(dtype="float32", count=1, nodata=np.nan)
    valid_footprint = transition > 0

    dem = _warp(data_dir / "DEM" / "NE3_COP30.tif", target_profile, resampling="average", src_nodata=-9999, dst_nodata=np.nan)
    dem_valid = np.isfinite(dem) & valid_footprint
    filled = dem.copy()
    filled[~np.isfinite(filled)] = float(np.nanmedian(dem[dem_valid]))
    gy, gx = np.gradient(filled, abs(float(target_profile["transform"].e)), float(target_profile["transform"].a))
    slope = np.degrees(np.arctan(np.hypot(gx, gy))).astype("float32")
    relief = (maximum_filter(filled, size=11) - minimum_filter(filled, size=11)).astype("float32")
    slope[~dem_valid] = np.nan
    relief[~dem_valid] = np.nan

    ndvi_mean_target, _ = _load_modis_target(data_dir, "ndvi", target_profile)
    _, evi_amp_target = _load_modis_target(data_dir, "evi", target_profile)
    ndvi_mean = np.nanmean(ndvi_mean_target, axis=0)
    evi_amp = np.nanmean(evi_amp_target, axis=0)

    src_profile = _source_profile(g["lat"], g["lon"])
    climate = {}
    for name in ("t2m", "tp", "swvl1"):
        source_path = output_dir / f"_tmp_{name}.tif"
        _write_raster(source_path, np.nanmean(g[f"era5_{name}"], axis=0), {**src_profile, "count": 1, "dtype": "float32", "nodata": np.nan})
        climate[name] = _warp(source_path, target_profile, resampling="bilinear", src_nodata=np.nan, dst_nodata=np.nan)
        source_path.unlink(missing_ok=True)

    cdl = _warp(data_dir / "CDL" / "CDL_NE_2021_DYY.tif", target_profile, resampling="nearest", src_nodata=15, dst_nodata=0)
    features = {
        "elevation_m": dem,
        "slope_deg": slope,
        "relief_10km_m": relief,
        "ndvi_mean": ndvi_mean,
        "evi_amplitude": evi_amp,
        "era5_t2m_degC": climate["t2m"],
        "era5_tp_mm": climate["tp"],
        "era5_swvl1_m3m3": climate["swvl1"],
        "cdl_class_0": (cdl == 0).astype("float32"),
        "cdl_class_1": (cdl == 1).astype("float32"),
        "cdl_class_2": (cdl == 2).astype("float32"),
        "cdl_class_3": (cdl == 3).astype("float32"),
    }
    feature_rows = []
    for name, arr in features.items():
        finite = np.isfinite(arr) & valid_footprint
        feature_rows.append({"feature": name, "unit_or_encoding": "one-hot" if name.startswith("cdl_") else "native_or_derived", "valid_cells": int(finite.sum()), "valid_pct_of_footprint": float(finite.sum() / max(valid_footprint.sum(), 1) * 100), "mean": float(np.nanmean(arr[finite])), "std": float(np.nanstd(arr[finite])), "min": float(np.nanmin(arr[finite])), "max": float(np.nanmax(arr[finite]))})
    pd.DataFrame(feature_rows).to_csv(output_dir / "feature_quality.csv", index=False)

    names = list(features)
    stack = np.column_stack([features[name].reshape(-1) for name in names])
    valid = valid_footprint.reshape(-1) & np.isfinite(stack).all(axis=1)
    matrix = stack[valid]
    scaler = StandardScaler()
    scaled = scaler.fit_transform(matrix)
    rng = np.random.default_rng(42)
    sample_idx = rng.choice(len(scaled), size=min(6000, len(scaled)), replace=False)
    scores = []
    models = {}
    for k in (3, 4, 5, 6):
        model = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels_sample = model.fit_predict(scaled[sample_idx])
        score = silhouette_score(scaled[sample_idx], labels_sample)
        full = KMeans(n_clusters=k, random_state=42, n_init=10).fit_predict(scaled)
        models[k] = full
        scores.append({"k": k, "silhouette_score_sample": float(score), "inertia_full": float(KMeans(n_clusters=k, random_state=42, n_init=10).fit(scaled).inertia_)})
    score_frame = pd.DataFrame(scores)
    score_frame.to_csv(output_dir / "k_selection.csv", index=False)
    best_k = int(score_frame.loc[score_frame.silhouette_score_sample.idxmax(), "k"])
    labels = models[best_k]
    zones = np.zeros(transition.shape, dtype="uint8")
    zones.reshape(-1)[valid] = labels.astype("uint8") + 1
    _write_raster(output_dir / "ecological_zone_map.tif", zones, target_profile, dtype="uint8", nodata=0)
    _plot_zones(output_dir / "ecological_zone_map.png", zones, target_profile, best_k, data_dir)

    profile = pd.DataFrame(matrix, columns=names)
    profile["zone"] = labels + 1
    area_km2 = abs(float(target_profile["transform"].a * target_profile["transform"].e)) / 1_000_000.0
    rows = []
    for zone, part in profile.groupby("zone", sort=True):
        row = {"zone": int(zone), "cells": int(len(part)), "area_km2": float(len(part) * area_km2)}
        for name in names:
            row[f"{name}_mean"] = float(part[name].mean())
            row[f"{name}_std"] = float(part[name].std())
        rows.append(row)
    pd.DataFrame(rows).to_csv(output_dir / "zone_profiles.csv", index=False)

    sens_rows = []
    baseline = labels
    for subset_name, subset in [("all_features", names), ("terrain_only", ["elevation_m", "slope_deg", "relief_10km_m"]), ("climate_vegetation", ["ndvi_mean", "evi_amplitude", "era5_t2m_degC", "era5_tp_mm", "era5_swvl1_m3m3"]), ("without_cdl", [n for n in names if not n.startswith("cdl_")])]:
        idx = [names.index(n) for n in subset]
        alt = KMeans(n_clusters=best_k, random_state=42, n_init=10).fit_predict(StandardScaler().fit_transform(matrix[:, idx]))
        sens_rows.append({"scenario": subset_name, "feature_count": len(subset), "ARI_vs_baseline": float(adjusted_rand_score(baseline, alt)), "selected_k_reference": best_k})
    pd.DataFrame(sens_rows).to_csv(output_dir / "sensitivity_report.csv", index=False)

    report = f"""# NE03 terrain–climate–vegetation ecological zones\n\n- Target: the valid footprint of the existing 1 km 2018–2021 land-cover transition grid ({int(valid_footprint.sum()):,} cells).\n- Features: DEM elevation, 10 km moving-window relief, slope, five-year MODIS NDVI mean, EVI seasonal amplitude, ERA5 growth-season climate means, and 2021 CDL one-hot class encodings.\n- Clustering: z-score features, KMeans with random seed 42, candidate k=3–6, silhouette score evaluated on a reproducible sample of up to 6,000 cells. Selected k={best_k}.\n- Sensitivity: terrain-only, climate–vegetation-only, without-CDL, and all-feature comparisons using adjusted Rand index.\n\nThese are unsupervised similarity zones, not administrative units, yield predictions, or causal ecological boundaries. Results depend on the selected footprint, 1 km aggregation and feature scaling.\n"""
    (output_dir / "report.md").write_text(report, encoding="utf-8")
    manifest = {"task_id": "NE03", "status": "completed", "selected_k": best_k, "valid_cells": int(valid.sum()), "target_grid": "existing 1 km Sinusoidal transition grid", "outputs": sorted(p.name for p in output_dir.iterdir() if p.is_file())}
    (output_dir / "task_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DATA)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs" / "NE03_ecological_zones")
    args = parser.parse_args()
    print(json.dumps(run(args.data_dir, args.output_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
