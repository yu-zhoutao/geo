#!/usr/bin/env python3
"""Run NE02: climate--vegetation variability and exploratory stress analysis.

This is an explicit, reproducible CLI task.  It uses ERA5-Land at its native
0.1 degree grid and aggregates the aid0001 MODIS tile to that grid.  MOD11A2
LST is intentionally not used because the supplied MODIS directory contains
clear-sky counts rather than temperature rasters.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT.parent / "dataset"
sys.path.insert(0, str(ROOT / "app" / "runtime_assets" / "geospatial-python"))
from geo_multisource import parse_modis_timestamp  # noqa: E402


YEARS = list(range(2018, 2023))
GROWTH_MONTHS = {5, 6, 7, 8, 9}
ERA5_VARS = ("t2m", "tp", "swvl1", "ssr")


def _decode_time(ds):
    raw = np.asarray(ds["valid_time"].values)
    units = str(ds["valid_time"].attrs.get("units", ""))
    match = re.match(r"\s*(seconds|minutes|hours|days)\s+since\s+(.+)\s*$", units, re.I)
    if match is None:
        raise ValueError(f"Unsupported valid_time units: {units!r}")
    origin = pd.Timestamp(match.group(2))
    unit = match.group(1).lower()[0]
    return ds.assign_coords(valid_time=origin + pd.to_timedelta(raw, unit=unit))


def _month_path(data_dir: Path, year: int, month: int) -> Path:
    path = data_dir / "ERA5_Land" / f"{year}{month:02d}.nc"
    if not path.exists():
        raise FileNotFoundError(path)
    return path


def load_era5_growth(data_dir: Path) -> tuple[np.ndarray, dict[str, np.ndarray], np.ndarray, np.ndarray]:
    """Return annual growth-season fields in practical units."""
    import xarray as xr

    annual: dict[str, list[np.ndarray]] = {name: [] for name in ERA5_VARS}
    lat = lon = None
    for year in YEARS:
        accum = {"t2m": None, "tp": None, "swvl1": None, "ssr": None}
        counts = {"t2m": 0.0, "swvl1": 0.0, "ssr": 0.0}
        for month in sorted(GROWTH_MONTHS):
            ds = xr.open_dataset(_month_path(data_dir, year, month), engine="netcdf4", decode_times=False)
            try:
                ds = _decode_time(ds)
                if lat is None:
                    lat = np.asarray(ds.latitude.values, dtype="float32")
                    lon = np.asarray(ds.longitude.values, dtype="float32")
                mask = ds.valid_time.dt.month.isin(sorted(GROWTH_MONTHS))
                n = int(mask.sum().item())
                if n == 0:
                    continue
                fields = {
                    "t2m": (ds.t2m.where(mask).mean("valid_time").load().values - 273.15).astype("float32"),
                    "tp": (ds.tp.where(mask).sum("valid_time").load().values * 1000.0).astype("float32"),
                    "swvl1": ds.swvl1.where(mask).mean("valid_time").load().values.astype("float32"),
                    "ssr": (ds.ssr.where(mask).sum("valid_time").load().values / 1_000_000.0).astype("float32"),
                }
                for name, value in fields.items():
                    if name == "tp":
                        if accum[name] is None:
                            accum[name] = np.zeros_like(value, dtype="float64")
                        accum[name] += np.nan_to_num(value, nan=0.0)
                    else:
                        if accum[name] is None:
                            accum[name] = np.zeros_like(value, dtype="float64")
                        accum[name] += np.nan_to_num(value, nan=0.0) * n
                        counts[name] += n
            finally:
                ds.close()
        for name in ERA5_VARS:
            if accum[name] is None:
                raise RuntimeError(f"No growth-season ERA5 data for {year}/{name}")
            value = accum[name] if name == "tp" else accum[name] / max(counts[name], 1.0)
            annual[name].append(value.astype("float32"))
    return np.asarray(YEARS, dtype="int16"), {name: np.stack(values) for name, values in annual.items()}, lat, lon


def _target_profile(lat: np.ndarray, lon: np.ndarray) -> dict[str, object]:
    from affine import Affine

    dx = float(np.median(np.diff(lon)))
    dy = float(abs(np.median(np.diff(lat))))
    return {
        "driver": "GTiff",
        "height": int(lat.size),
        "width": int(lon.size),
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": Affine.translation(float(lon.min() - dx / 2), float(lat.max() + dy / 2)) * Affine.scale(dx, -dy),
        "nodata": np.nan,
    }


def _warp_modis(path: Path, profile: dict[str, object]) -> np.ndarray:
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.warp import reproject

    with rasterio.open(path) as src:
        arr = src.read(1).astype("float32")
        arr[arr <= -2999] = np.nan
        dst = np.full((int(profile["height"]), int(profile["width"])), np.nan, dtype="float32")
        reproject(
            arr,
            dst,
            src_transform=src.transform,
            src_crs=src.crs,
            src_nodata=np.nan,
            dst_transform=profile["transform"],
            dst_crs=profile["crs"],
            dst_nodata=np.nan,
            resampling=Resampling.average,
        )
    return dst


def load_modis_growth(data_dir: Path, product: str, profile: dict[str, object]) -> np.ndarray:
    from geo_multisource import scale_modis_values

    root = data_dir / "MODIS" / f"{product.upper()}_2018-2022"
    files = []
    for path in sorted(root.rglob("*.tif")):
        if "aid0001" not in path.name:
            continue
        stamp = parse_modis_timestamp(path)
        if stamp.year in YEARS and stamp.month in GROWTH_MONTHS:
            files.append((stamp, path))
    if not files:
        raise FileNotFoundError(f"No aid0001 seasonal {product} rasters found under {root}")
    annual = []
    for year in YEARS:
        total = np.zeros((int(profile["height"]), int(profile["width"])), dtype="float64")
        count = np.zeros_like(total)
        for stamp, path in files:
            if stamp.year != year:
                continue
            warped = _warp_modis(path, profile)
            # Scaling is linear and can be applied after averaging/reprojection.
            warped = scale_modis_values(warped, product)
            valid = np.isfinite(warped)
            total[valid] += warped[valid]
            count[valid] += 1
        annual.append(np.divide(total, count, out=np.full_like(total, np.nan), where=count > 0).astype("float32"))
    return np.stack(annual)


def _safe_zscore(values: np.ndarray) -> np.ndarray:
    mean = np.nanmean(values, axis=0)
    std = np.nanstd(values, axis=0)
    return np.divide(values - mean, std, out=np.zeros_like(values, dtype="float32"), where=std > 1e-8)


def _write_map(
    path: Path,
    array: np.ndarray,
    profile: dict[str, object],
    title: str,
    cmap: str,
    label: str,
    data_dir: Path,
    *,
    diverging: bool = False,
) -> None:
    """Write a journal-style geospatial map with study-region context."""
    import matplotlib

    matplotlib.use("Agg")
    import geopandas as gpd
    import matplotlib.pyplot as plt
    from matplotlib.colors import TwoSlopeNorm
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    from matplotlib.ticker import FuncFormatter, MaxNLocator
    from rasterio.features import geometry_mask

    path.parent.mkdir(parents=True, exist_ok=True)
    matplotlib.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
            "font.size": 8,
            "axes.titlesize": 12,
            "axes.labelsize": 8.5,
            "xtick.labelsize": 7.5,
            "ytick.labelsize": 7.5,
            "legend.fontsize": 7.0,
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
        }
    )

    shape_root = data_dir / "Shapefiles" / "gafm41_CHN_SHP"
    provinces = gpd.read_file(shape_root / "gadm41_CHN_1.shp").to_crs("EPSG:4326")
    study = gpd.read_file(data_dir / "Shapefiles" / "black_earth.shp").to_crs("EPSG:4326")
    study_geometry = study.geometry.union_all()

    transform = profile["transform"]
    left = float(transform.c)
    right = left + float(transform.a) * int(profile["width"])
    top = float(transform.f)
    bottom = top + float(transform.e) * int(profile["height"])
    minx, miny, maxx, maxy = study.total_bounds
    xpad = max(0.45, (maxx - minx) * 0.035)
    ypad = max(0.45, (maxy - miny) * 0.035)
    view_extent = (minx - xpad, maxx + xpad, miny - ypad, maxy + ypad)
    context = provinces.copy()

    study_mask = geometry_mask(
        [study_geometry],
        out_shape=np.asarray(array).shape,
        transform=transform,
        invert=True,
    )
    display = np.ma.masked_where(~study_mask | ~np.isfinite(array), np.asarray(array, dtype="float32"))
    finite = np.asarray(display.compressed(), dtype="float32")
    if finite.size == 0:
        raise ValueError(f"No finite NE02 values inside the study region for {path.name}")
    if diverging:
        limit = float(np.nanpercentile(np.abs(finite), 98))
        limit = max(limit, 1e-6)
        norm = TwoSlopeNorm(vmin=-limit, vcenter=0.0, vmax=limit)
    else:
        vmin = float(np.nanpercentile(finite, 2))
        vmax = float(np.nanpercentile(finite, 98))
        if vmax <= vmin:
            vmax = vmin + 1e-6
        norm = matplotlib.colors.Normalize(vmin=vmin, vmax=vmax)

    fig, ax = plt.subplots(figsize=(11.5, 8.5), dpi=400)
    provinces.plot(ax=ax, facecolor="white", edgecolor="#b5b5b5", linewidth=0.55, zorder=0, rasterized=True)
    image = ax.imshow(
        display,
        extent=(left, right, bottom, top),
        origin="upper",
        cmap=cmap,
        norm=norm,
        interpolation="nearest",
        alpha=0.92,
        zorder=1,
    )
    provinces.boundary.plot(ax=ax, color="#8c8c8c", linewidth=0.55, zorder=2, rasterized=True)
    study.boundary.plot(ax=ax, color="#222222", linewidth=1.25, zorder=3, rasterized=True)

    context_legend = ax.legend(
        handles=[
            Patch(facecolor="#2c7fb8", edgecolor="#174a73", label="Study region"),
            Line2D([0], [0], color="#222222", lw=1.25, label="Black-earth boundary"),
            Line2D([0], [0], color="#8c8c8c", lw=0.55, label="Provincial boundary"),
        ],
        loc="center right",
        bbox_to_anchor=(0.70, 0.82),
        ncol=1,
        fontsize=6.8,
        framealpha=0.95,
        borderpad=0.45,
        columnspacing=1.0,
        handlelength=1.0,
    )
    cb = fig.colorbar(image, ax=ax, fraction=0.035, pad=0.025, shrink=0.82)
    cb.set_label(label, fontsize=8.5)
    cb.ax.tick_params(labelsize=7.2, length=2.5)

    inset = ax.inset_axes([0.72, 0.70, 0.27, 0.24], facecolor="white", zorder=25)
    context.plot(ax=inset, facecolor="white", edgecolor="#4d4d4d", linewidth=0.45, zorder=0, rasterized=True)
    study.plot(ax=inset, facecolor="#2c7fb8", edgecolor="#174a73", linewidth=0.55, zorder=1, rasterized=True)
    study.boundary.plot(ax=inset, color="#174a73", linewidth=0.65, zorder=2, rasterized=True)
    context_minx, context_miny, context_maxx, context_maxy = context.total_bounds
    context_lon_pad = max(0.35, (context_maxx - context_minx) * 0.035)
    context_lat_pad = max(0.35, (context_maxy - context_miny) * 0.035)
    inset.set_xlim(context_minx - context_lon_pad, context_maxx + context_lon_pad)
    inset.set_ylim(context_miny - context_lat_pad, context_maxy + context_lat_pad)
    inset.set_xticks([])
    inset.set_yticks([])
    inset.set_aspect("equal", adjustable="box")
    inset.set_title("China", fontsize=8, fontweight="bold", loc="left", pad=2)
    for spine in inset.spines.values():
        spine.set_linewidth(0.7)

    ax.set_xlim(view_extent[0], view_extent[1])
    ax.set_ylim(view_extent[2], view_extent[3])
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Longitude (°E)", labelpad=8)
    ax.set_ylabel("Latitude (°N)", labelpad=8)
    ax.xaxis.set_major_locator(MaxNLocator(6))
    ax.yaxis.set_major_locator(MaxNLocator(6))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:.1f}°E"))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:.1f}°N"))
    ax.set_title(title, loc="left", fontsize=12, fontweight="bold", pad=10)
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
    mid_lat = float(np.mean([view_extent[2], view_extent[3]]))
    scale_deg = scale_km / (111.32 * np.cos(np.deg2rad(mid_lat)))
    x0 = view_extent[0] + (view_extent[1] - view_extent[0]) * 0.44
    y0 = view_extent[2] + (view_extent[3] - view_extent[2]) * 0.06
    ax.plot([x0, x0 + scale_deg / 2], [y0, y0], color="#222222", lw=6, solid_capstyle="butt", zorder=31)
    ax.plot([x0 + scale_deg / 2, x0 + scale_deg], [y0, y0], color="white", lw=6, solid_capstyle="butt", zorder=31)
    ax.plot([x0, x0 + scale_deg], [y0, y0], color="#222222", lw=0.7, zorder=32)
    ax.text(x0, y0 - (view_extent[3] - view_extent[2]) * 0.035, "0", ha="center", va="top", fontsize=7)
    ax.text(x0 + scale_deg / 2, y0 - (view_extent[3] - view_extent[2]) * 0.035, "100", ha="center", va="top", fontsize=7)
    ax.text(x0 + scale_deg, y0 - (view_extent[3] - view_extent[2]) * 0.035, "200 km", ha="center", va="top", fontsize=7)

    fig.tight_layout()
    fig.savefig(path, dpi=400, bbox_inches="tight", facecolor="white")
    fig.savefig(path.with_suffix(".pdf"), bbox_inches="tight", facecolor="white")
    fig.savefig(path.with_suffix(".svg"), bbox_inches="tight", facecolor="white")
    fig.savefig(path.with_suffix(".tiff"), dpi=600, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _write_geotiff(path: Path, array: np.ndarray, profile: dict[str, object]) -> None:
    import rasterio

    p = profile.copy()
    p.update(driver="GTiff", dtype="float32", count=1, compress="deflate", nodata=np.nan)
    with rasterio.open(path, "w", **p) as dst:
        dst.write(np.asarray(array, dtype="float32"), 1)


def run(data_dir: Path, output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    years, era5, lat, lon = load_era5_growth(data_dir)
    profile = _target_profile(lat, lon)
    ndvi = load_modis_growth(data_dir, "ndvi", profile)
    evi = load_modis_growth(data_dir, "evi", profile)

    # Persist the small, aligned grids so NE03 can reuse the exact climate surface.
    np.savez_compressed(output_dir / "ne02_grids.npz", years=years, lat=lat, lon=lon, ndvi=ndvi, evi=evi, **{f"era5_{k}": v for k, v in era5.items()})

    era5_clim = {name: np.nanmean(values, axis=0) for name, values in era5.items()}
    ndvi_clim = np.nanmean(ndvi, axis=0)
    era5_z = {name: _safe_zscore(values) for name, values in era5.items()}
    ndvi_z = _safe_zscore(ndvi)
    stress = np.nanmean(np.stack([era5_z["t2m"], -era5_z["tp"], -era5_z["swvl1"], -ndvi_z]), axis=0)

    era5_rows = []
    for i, year in enumerate(years):
        for name, values in era5.items():
            a = values[i]
            era5_rows.append({"year": int(year), "variable": name, "unit": {"t2m": "degC", "tp": "mm", "swvl1": "m3_m3", "ssr": "MJ_m2"}[name], "mean": float(np.nanmean(a)), "std": float(np.nanstd(a)), "min": float(np.nanmin(a)), "max": float(np.nanmax(a)), "valid_cells": int(np.isfinite(a).sum())})
    pd.DataFrame(era5_rows).to_csv(output_dir / "era5_seasonal_stats.csv", index=False)

    modis_rows = []
    for i, year in enumerate(years):
        for name, values in [("ndvi", ndvi), ("evi", evi)]:
            a = values[i]
            modis_rows.append({"year": int(year), "variable": name, "unit": "scaled_index", "mean": float(np.nanmean(a)), "std": float(np.nanstd(a)), "min": float(np.nanmin(a)), "max": float(np.nanmax(a)), "valid_cells": int(np.isfinite(a).sum())})
    pd.DataFrame(modis_rows).to_csv(output_dir / "modis_response_stats.csv", index=False)

    stress_rows = []
    for i, year in enumerate(years):
        a = stress[i]
        stress_rows.append({"year": int(year), "mean_stress_index": float(np.nanmean(a)), "std": float(np.nanstd(a)), "p90": float(np.nanpercentile(a, 90)), "high_stress_cells_pct": float(np.nanmean(a > 1.0) * 100), "valid_cells": int(np.isfinite(a).sum())})
    pd.DataFrame(stress_rows).to_csv(output_dir / "stress_index_by_year.csv", index=False)

    # A 5-year Theil-Sen slope is calculated vectorially as an exploratory trend summary.
    slopes = []
    for j in range(len(years)):
        for i in range(j):
            slopes.append((ndvi[j] - ndvi[i]) / float(years[j] - years[i]))
    ndvi_slope = np.nanmedian(np.stack(slopes), axis=0)
    pd.DataFrame([{"variable": "ndvi", "method": "Theil-Sen pairwise median; 5 annual values", "mean_slope_per_year": float(np.nanmean(ndvi_slope)), "positive_cells_pct": float(np.nanmean(ndvi_slope > 0) * 100), "negative_cells_pct": float(np.nanmean(ndvi_slope < 0) * 100)}]).to_csv(output_dir / "trend_summary.csv", index=False)

    _write_map(
        output_dir / "climate_anomaly_map.png",
        era5_z["t2m"][-1],
        profile,
        "NE02 | climate temperature anomaly\n2022 growth season",
        "RdBu_r",
        "standardized anomaly",
        data_dir,
        diverging=True,
    )
    _write_map(
        output_dir / "vegetation_anomaly_map.png",
        ndvi_z[-1],
        profile,
        "NE02 | NDVI anomaly\n2022 growth season",
        "RdYlGn",
        "standardized anomaly",
        data_dir,
        diverging=True,
    )
    _write_map(
        output_dir / "stress_variability_map.png",
        stress[-1],
        profile,
        "NE02 | exploratory climate–vegetation stress index\n2022 growth season",
        "magma",
        "higher = more stress",
        data_dir,
        diverging=False,
    )
    _write_geotiff(output_dir / "ndvi_theil_sen_slope.tif", ndvi_slope, profile)

    report = f"""# NE02 climate–vegetation variability and stress\n\n- Period: 2018–2022; growth season: May–September.\n- ERA5-Land: 0.1° grid; `t2m` converted K→°C, `tp` summed and converted m→mm, `swvl1` retained as volumetric fraction, `ssr` summed and converted J m⁻²→MJ m⁻².\n- MODIS: aid0001 NDVI/EVI, scale factor 0.0001, aggregated to the ERA5 grid.\n- Stress index: equal-weight standardized high temperature, precipitation deficit, soil-moisture deficit, and NDVI deficit. It is exploratory and is not a causal drought or yield model.\n- Trend: vectorized Theil–Sen slope over five annual seasonal means; no causal interpretation and no long-term significance claim.\n\nThe supplied MODIS `MOD11A2_LST_2018-2022` directory contains clear-sky counts rather than LST, so it was excluded from temperature analysis.\n"""
    (output_dir / "report.md").write_text(report, encoding="utf-8")
    manifest = {"task_id": "NE02", "status": "completed", "years": YEARS, "growth_months": sorted(GROWTH_MONTHS), "grid": "ERA5-Land 0.1 degree", "outputs": sorted(p.name for p in output_dir.iterdir() if p.is_file())}
    (output_dir / "task_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DATA)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs" / "NE02_climate_vegetation_stress")
    args = parser.parse_args()
    manifest = run(args.data_dir, args.output_dir)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
