#!/usr/bin/env python3
"""Run NE01: CDL land-cover change with MODIS NDVI/EVI response summaries.

The script is intentionally visible and reproducible. It uses the CDL grid for
27 m transition accounting and one MODIS aid0001 tile (which covers the CDL
extent) for 1 km vegetation summaries. It never assumes numeric CDL codes are
crop names; the codebook is reported as numeric unless an authoritative VAT is
provided by the dataset.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterable
import json
import os
from pathlib import Path
import sys
from typing import Any

import geopandas as gpd
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.patches import FancyArrowPatch, Patch, Rectangle
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter, MaxNLocator
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize, shapes
from rasterio.mask import mask
from rasterio.windows import Window
from rasterio.warp import reproject
from rasterio.enums import Resampling
from shapely.geometry import mapping, shape as shapely_shape
from affine import Affine
from pyproj import Transformer


mpl.rcParams.update(
    {
        'font.family': 'sans-serif',
        'font.sans-serif': ['Arial', 'Helvetica', 'DejaVu Sans', 'sans-serif'],
        'svg.fonttype': 'none',
        'pdf.fonttype': 42,
        'font.size': 8,
        'axes.linewidth': 0.8,
        'axes.spines.right': True,
        'axes.spines.top': True,
    }
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GEO_PYTHON_ROOT = PROJECT_ROOT / 'app' / 'runtime_assets' / 'geospatial-python'
sys.path.insert(0, str(GEO_PYTHON_ROOT))

from geo_multisource import (  # noqa: E402
    compute_transition_matrix,
    group_modis_tiles,
    parse_modis_timestamp,
    scale_modis_values,
    summarize_class_area,
)


DEFAULT_DATA_ROOT = Path(os.environ.get('GEO_AGENT_DATA_ROOT', PROJECT_ROOT / 'data'))
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / 'outputs' / 'NE01_land_cover_vegetation_change'
SEASON_MONTHS = {5, 6, 7, 8, 9}
MODIS_AID = 'aid0001'


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.ndarray,)):
        return value.tolist()
    if isinstance(value, (Path,)):
        return str(value)
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    raise TypeError(f'Cannot serialize {type(value).__name__}')


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default), encoding='utf-8')


def _save_figure(fig: plt.Figure, output_path: Path) -> None:
    """Write a review-friendly PNG and editable publication exports."""
    fig.savefig(output_path, dpi=400, bbox_inches='tight')
    fig.savefig(output_path.with_suffix('.pdf'), bbox_inches='tight')
    fig.savefig(output_path.with_suffix('.svg'), bbox_inches='tight')
    fig.savefig(output_path.with_suffix('.tiff'), dpi=600, bbox_inches='tight')


def _load_map_context(data_root: Path, target_crs: Any) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Load local administrative context layers for cartographic positioning.

    The analytical raster remains the visual hero.  These layers are only used
    as geographic context: provincial boundaries and the black-earth study
    region outline.  They are reprojected to the raster CRS before plotting.
    """
    shape_root = data_root / 'Shapefiles'
    provinces = gpd.read_file(shape_root / 'gafm41_CHN_SHP' / 'gadm41_CHN_1.shp')
    study = gpd.read_file(shape_root / 'black_earth.shp')
    if provinces.crs is None or study.crs is None:
        raise ValueError('Context layer CRS is missing')
    return provinces.to_crs(target_crs), study.to_crs(target_crs)


def _geo_tick_formatters(source_crs: Any, extent: tuple[float, float, float, float]):
    """Create longitude/latitude formatters that respect the raster CRS."""
    left, bottom, right, top = extent
    transformer = Transformer.from_crs(source_crs, 'EPSG:4326', always_xy=True)
    center_x = (left + right) / 2.0
    center_y = (bottom + top) / 2.0

    def format_lon(value: float, _: int) -> str:
        longitude, _ = transformer.transform(float(value), center_y)
        return f'{longitude:.1f}°E'

    def format_lat(value: float, _: int) -> str:
        _, latitude = transformer.transform(center_x, float(value))
        return f'{latitude:.1f}°N'

    return FuncFormatter(format_lon), FuncFormatter(format_lat)


def _add_north_arrow(ax: plt.Axes, *, x: float = 0.95, y: float = 0.20) -> None:
    ax.annotate(
        'N', xy=(x, y + 0.095), xytext=(x, y), xycoords='axes fraction',
        ha='center', va='center', fontsize=10, fontweight='bold',
        arrowprops={'arrowstyle': '-|>', 'lw': 1.2, 'color': '#222222'},
        zorder=20,
    )


def _add_scale_bar(ax: plt.Axes, extent: tuple[float, float, float, float], *, length_km: int = 100) -> None:
    left, bottom, right, top = extent
    # Keep the scale bar clear of the two-column transition legend in the
    # lower-left corner.
    x0 = left + (right - left) * 0.40
    y0 = bottom + (top - bottom) * 0.055
    length_m = length_km * 1000.0
    segment_m = length_m / 2.0
    height = (top - bottom) * 0.012
    for index in range(2):
        ax.add_patch(Rectangle(
            (x0 + index * segment_m, y0), segment_m, height,
            facecolor='#222222' if index == 0 else 'white',
            edgecolor='#222222', linewidth=0.7, zorder=20,
        ))
    ax.text(x0, y0 - (top - bottom) * 0.012, '0', ha='center', va='top', fontsize=8, zorder=20)
    ax.text(x0 + segment_m, y0 - (top - bottom) * 0.012, f'{length_km // 2}', ha='center', va='top', fontsize=8, zorder=20)
    ax.text(x0 + length_m, y0 - (top - bottom) * 0.012, f'{length_km} km', ha='center', va='top', fontsize=8, zorder=20)


def _annotate_study_region(ax: plt.Axes, study: gpd.GeoDataFrame, extent: tuple[float, float, float, float]) -> None:
    """Label the Northeast China black-earth region directly on the main map."""
    left, bottom, right, top = extent
    # The displayed raster is a cropped analytical footprint, whereas the
    # source study polygon spans the wider three-province black-earth region.
    # Anchor the callout inside the displayed footprint so it remains visible
    # on both the 27 m and 1 km panels.
    point_x = left + (right - left) * 0.46
    point_y = bottom + (top - bottom) * 0.56
    label_x = left + (right - left) * 0.73
    label_y = bottom + (top - bottom) * 0.89
    ax.annotate(
        'Northeast China\nBlack Earth Region',
        xy=(point_x, point_y), xycoords='data',
        xytext=(label_x, label_y), textcoords='data',
        ha='center', va='center', fontsize=9, fontweight='bold', color='#4a2f21',
        bbox={'facecolor': 'white', 'edgecolor': '#4a2f21', 'linewidth': 0.7, 'alpha': 0.86, 'pad': 3.0},
        arrowprops={'arrowstyle': '-|>', 'color': '#4a2f21', 'linewidth': 0.9, 'shrinkA': 4, 'shrinkB': 4},
        zorder=12,
    )


def _transition_footprint(transition: np.ndarray, profile: dict[str, Any]) -> Any:
    """Return the geographic footprint of cells carrying detailed data."""
    valid = transition > 0
    if not np.any(valid):
        raise ValueError('The transition raster contains no valid data footprint')
    polygons = [shapely_shape(geometry) for geometry, value in shapes(valid.astype('uint8'), mask=valid, transform=profile['transform']) if value]
    if not polygons:
        raise ValueError('Could not vectorize the transition data footprint')
    footprint = gpd.GeoSeries(polygons, crs=profile['crs']).union_all()
    return gpd.GeoSeries([footprint], crs=profile['crs']).to_crs('EPSG:4326').iloc[0]


def _add_locator_inset(
    ax: plt.Axes,
    *,
    data_root: Path,
    main_extent: tuple[float, float, float, float],
    source_crs: Any,
    detail_footprint: Any,
    inset_bounds: tuple[float, float, float, float] = (0.72, 0.72, 0.25, 0.24),
) -> None:
    """Add a Northeast China locator with boundaries and exact data footprint."""
    shape_root = data_root / 'Shapefiles' / 'gafm41_CHN_SHP'
    provinces = gpd.read_file(shape_root / 'gadm41_CHN_1.shp').to_crs('EPSG:4326')
    study = gpd.read_file(data_root / 'Shapefiles' / 'black_earth.shp')
    northeast_names = ['Heilongjiang', 'Jilin', 'Liaoning', 'Inner Mongolia']
    northeast = provinces[provinces['NAME_1'].isin(northeast_names)]
    inset = ax.inset_axes(inset_bounds, facecolor='white', zorder=25)
    northeast.plot(ax=inset, facecolor='white', edgecolor='#4d4d4d', linewidth=0.6, zorder=0, rasterized=True)
    study.boundary.plot(ax=inset, color='#222222', linewidth=0.75, zorder=1, rasterized=True)
    gpd.GeoSeries([detail_footprint], crs='EPSG:4326').plot(
        ax=inset, facecolor='#2c7fb8', edgecolor='#174a73', linewidth=0.55, zorder=2, rasterized=True,
    )
    min_lon, min_lat, max_lon, max_lat = study.total_bounds
    lon_pad = max(0.5, (max_lon - min_lon) * 0.04)
    lat_pad = max(0.5, (max_lat - min_lat) * 0.04)
    inset.set_xlim(min_lon - lon_pad, max_lon + lon_pad)
    inset.set_ylim(min_lat - lat_pad, max_lat + lat_pad)
    inset.set_xticks([])
    inset.set_yticks([])
    inset.set_title('Northeast China', fontsize=8, fontweight='bold', loc='left', pad=2)
    for spine in inset.spines.values():
        spine.set_linewidth(0.7)


def _load_study_geometry(path: Path, target_crs: Any):
    area = gpd.read_file(path)
    if area.empty or area.geometry.is_empty.all():
        raise ValueError(f'Study area is empty: {path}')
    if area.crs is None:
        raise ValueError(f'Study area CRS is missing: {path}')
    geometry = area.to_crs(target_crs).geometry.union_all()
    if geometry.is_empty:
        raise ValueError('Study area becomes empty after CRS transformation')
    return geometry, area


def _read_cdl_stack(paths: list[Path], study_path: Path) -> tuple[dict[int, np.ndarray], dict[str, Any], Any, int]:
    with rasterio.open(paths[0]) as first:
        geometry, area = _load_study_geometry(study_path, first.crs)
        clipped, transform = mask(first, [mapping(geometry)], crop=True, filled=True, nodata=first.nodata)
        target_shape = clipped[0].shape
        nodata = int(first.nodata) if first.nodata is not None else 0
        profile = first.profile.copy()
        profile.update(
            height=target_shape[0],
            width=target_shape[1],
            transform=transform,
            count=1,
            dtype='uint8',
            nodata=nodata,
        )
        arrays: dict[int, np.ndarray] = {2018: clipped[0].astype('uint8', copy=False)}
        crs = first.crs
        first_bounds = tuple(round(float(value), 3) for value in first.bounds)

    for path in paths[1:]:
        year = int(path.stem.rsplit('_', 1)[0].rsplit('_', 1)[-1])
        with rasterio.open(path) as src:
            destination = np.full(target_shape, nodata, dtype='uint8')
            reproject(
                source=src.read(1),
                destination=destination,
                src_transform=src.transform,
                src_crs=src.crs,
                src_nodata=src.nodata,
                dst_transform=transform,
                dst_crs=crs,
                dst_nodata=nodata,
                resampling=Resampling.nearest,
            )
            arrays[year] = destination

    if set(arrays) != {2018, 2019, 2020, 2021}:
        raise ValueError(f'Expected CDL years 2018-2021, found {sorted(arrays)}')
    audit = {
        'study_area_path': str(study_path),
        'study_area_feature_count': len(area),
        'study_area_crs': str(area.crs),
        'analysis_crs': str(crs),
        'first_source_bounds': first_bounds,
        'analysis_shape': list(target_shape),
        'cdl_nodata': nodata,
    }
    return arrays, audit, profile, nodata


def _write_raster(path: Path, array: np.ndarray, profile: dict[str, Any], *, dtype: str, nodata: int) -> None:
    output_profile = profile.copy()
    output_profile.update(
        driver='GTiff',
        dtype=dtype,
        count=1,
        nodata=nodata,
        compress='deflate',
        predictor=2 if dtype != 'uint8' else 1,
        tiled=True,
        BIGTIFF='IF_SAFER',
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, 'w', **output_profile) as dst:
        dst.write(array.astype(dtype, copy=False), 1)


def _transition_code(before: np.ndarray, after: np.ndarray, nodata: int) -> np.ndarray:
    valid = (before != nodata) & (after != nodata)
    code = np.zeros(before.shape, dtype='uint16')
    code[valid] = before[valid].astype('uint16') * 256 + after[valid].astype('uint16')
    return code


def _make_transition_tables(
    arrays: dict[int, np.ndarray],
    *,
    nodata: int,
    pixel_area_m2: float,
    output_dir: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, np.ndarray]:
    class_tables: list[pd.DataFrame] = []
    for year, array in sorted(arrays.items()):
        table = summarize_class_area(array, pixel_area_m2=pixel_area_m2, nodata=nodata)
        table.insert(0, 'year', year)
        class_tables.append(table)
    classes = pd.concat(class_tables, ignore_index=True)
    classes.to_csv(output_dir / 'class_area_by_year.csv', index=False)

    transitions: list[pd.DataFrame] = []
    for start, end in [(2018, 2019), (2019, 2020), (2020, 2021), (2018, 2021)]:
        table = compute_transition_matrix(
            arrays[start], arrays[end], pixel_area_m2=pixel_area_m2, nodata=nodata
        )
        table.insert(0, 'period', f'{start}-{end}')
        transitions.append(table)
    matrix = pd.concat(transitions, ignore_index=True)
    matrix.to_csv(output_dir / 'transition_matrix.csv', index=False)
    return classes, matrix, _transition_code(arrays[2018], arrays[2021], nodata)


def _reproject_transition_to_modis(
    transition: np.ndarray,
    cdl_profile: dict[str, Any],
    modis_path: Path,
) -> tuple[np.ndarray, dict[str, Any]]:
    with rasterio.open(modis_path) as target:
        destination = np.zeros((target.height, target.width), dtype='uint16')
        reproject(
            source=transition,
            destination=destination,
            src_transform=cdl_profile['transform'],
            src_crs=cdl_profile['crs'],
            src_nodata=0,
            dst_transform=target.transform,
            dst_crs=target.crs,
            dst_nodata=0,
            resampling=Resampling.nearest,
        )
        profile = target.profile.copy()
    profile.update(dtype='uint16', count=1, nodata=0)
    return destination, profile


def _seasonal_group_stats(
    directory: Path,
    product: str,
    transition_1km: np.ndarray,
    *,
    years: Iterable[int],
) -> pd.DataFrame:
    grouped_files = group_modis_tiles(directory, product, years=years)
    # Only aid0001 is needed because its footprint fully covers the CDL area;
    # every date is still required to have exactly one selected tile.
    selected: dict[pd.Timestamp, Path] = {}
    for timestamp, paths in grouped_files.items():
        matches = [path for path in paths if MODIS_AID in path.name]
        if matches:
            selected[timestamp] = matches[0]
    if not selected:
        raise FileNotFoundError(f'No {product} files for {MODIS_AID} in {directory}')

    valid_transition = transition_1km.reshape(-1)
    code_count = 65536
    rows: list[dict[str, Any]] = []
    for year in sorted(set(years)):
        seasonal = [(date, path) for date, path in sorted(selected.items()) if date.year == year and date.month in SEASON_MONTHS]
        if not seasonal:
            continue
        date_means: list[np.ndarray] = []
        annual_sum = np.zeros(code_count, dtype='float64')
        annual_count = np.zeros(code_count, dtype='int64')
        for timestamp, path in seasonal:
            with rasterio.open(path) as src:
                values = scale_modis_values(src.read(1), product).astype('float64', copy=False).reshape(-1)
                nodata = src.nodata
                valid = valid_transition > 0
                if nodata is not None:
                    valid &= src.read(1).reshape(-1) != nodata
                valid &= np.isfinite(values)
                sums = np.bincount(valid_transition[valid], weights=values[valid], minlength=code_count)
                counts = np.bincount(valid_transition[valid], minlength=code_count)
                mean = np.full(code_count, np.nan, dtype='float64')
                nonzero = counts > 0
                mean[nonzero] = sums[nonzero] / counts[nonzero]
                date_means.append(mean)
                annual_sum += sums
                annual_count += counts
        annual_mean = np.full(code_count, np.nan, dtype='float64')
        has_annual = annual_count > 0
        annual_mean[has_annual] = annual_sum[has_annual] / annual_count[has_annual]
        stack = np.stack(date_means)
        has_any = np.isfinite(stack).any(axis=0)
        amplitude = np.full(code_count, np.nan, dtype='float64')
        amplitude[has_any] = np.nanmax(stack[:, has_any], axis=0) - np.nanmin(stack[:, has_any], axis=0)
        codes = np.flatnonzero(has_annual)
        codes = codes[codes > 0]
        for code in codes:
            rows.append(
                {
                    'product': product,
                    'year': year,
                    'transition_code': int(code),
                    'from_class': int(code // 256),
                    'to_class': int(code % 256),
                    'pixels_with_valid_observation': int(annual_count[code]),
                    'seasonal_mean': float(annual_mean[code]),
                    'seasonal_amplitude': float(amplitude[code]),
                    'observation_dates': len(seasonal),
                }
            )
    if not rows:
        raise ValueError(f'No valid seasonal {product} observations matched the transition grid')
    return pd.DataFrame(rows)


def _plot_transition_map(
    transition_1km: np.ndarray,
    profile: dict[str, Any],
    *,
    output_path: Path,
    top_codes: list[int],
    data_root: Path,
    detail_footprint: Any,
) -> None:
    display, extent = _zoomed_transition_display(transition_1km, profile, top_codes=top_codes)
    colors = ['#2166ac', '#67a9cf', '#d1e5f0', '#fddbc7', '#ef8a62', '#b2182b', '#762a83', '#1b7837', '#5aae61', '#a6dba0', '#d9f0d3', '#9970ab', '#bdbdbd']
    cmap = ListedColormap(colors[: len(top_codes)] + ['#969696'])
    masked = np.ma.masked_equal(display, -1)
    left, bottom, right, top = extent
    provinces, study = _load_map_context(data_root, profile['crs'])
    fig, ax = plt.subplots(figsize=(11.5, 8.5), dpi=400)
    provinces.plot(ax=ax, facecolor='white', edgecolor='#b5b5b5', linewidth=0.55, zorder=0, rasterized=True)
    ax.imshow(masked, cmap=cmap, interpolation='nearest', extent=(left, right, bottom, top), origin='upper', alpha=0.92, zorder=1)
    provinces.boundary.plot(ax=ax, color='#8c8c8c', linewidth=0.55, zorder=2, rasterized=True)
    study.boundary.plot(ax=ax, color='#222222', linewidth=1.25, zorder=3, rasterized=True)
    legend_handles = [Patch(color=colors[i], label=f'{code // 256} → {code % 256}') for i, code in enumerate(top_codes)]
    legend_handles.append(Patch(color='#969696', label='other transitions'))
    transition_legend = ax.legend(handles=legend_handles, loc='lower left', bbox_to_anchor=(0.06, 0.18), ncol=2, fontsize=7.2, title='2018–2021 transitions', title_fontsize=8, framealpha=0.92, borderpad=0.7, columnspacing=1.0, handlelength=1.1)
    ax.add_artist(transition_legend)
    ax.legend(handles=[
        Patch(facecolor='#2c7fb8', edgecolor='#174a73', label='Detailed data footprint'),
        Line2D([0], [0], color='#222222', lw=1.25, label='Black-earth region'),
        Line2D([0], [0], color='#8c8c8c', lw=0.55, label='Provincial boundary'),
    ], loc='upper center', bbox_to_anchor=(0.50, 0.96), ncol=3, fontsize=7.0, framealpha=0.95, borderpad=0.55, columnspacing=1.0, handlelength=1.1)
    ax.set_xlim(left, right)
    ax.set_ylim(bottom, top)
    _add_locator_inset(ax, data_root=data_root, main_extent=extent, source_crs=profile['crs'], detail_footprint=detail_footprint)
    _add_north_arrow(ax)
    _add_scale_bar(ax, extent, length_km=100)
    ax.set_xlabel('Longitude (°E)', labelpad=8)
    ax.set_ylabel('Latitude (°N)', labelpad=8)
    ax.xaxis.set_major_locator(MaxNLocator(6))
    ax.yaxis.set_major_locator(MaxNLocator(6))
    lon_formatter, lat_formatter = _geo_tick_formatters(profile['crs'], extent)
    ax.xaxis.set_major_formatter(lon_formatter)
    ax.yaxis.set_major_formatter(lat_formatter)
    ax.set_title('NE01 | 2018–2021 land-cover transitions\n1 km summary grid', loc='left', fontsize=12, fontweight='bold', pad=10)
    ax.grid(False)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_linewidth(0.8)
    fig.tight_layout()
    _save_figure(fig, output_path)
    plt.close(fig)


def _plot_27m_change_preview(
    transition: np.ndarray,
    profile: dict[str, Any],
    *,
    output_path: Path,
    top_codes: list[int],
    data_root: Path,
    detail_footprint: Any,
    sample_step: int = 12,
) -> None:
    display, extent = _zoomed_transition_display(
        transition,
        profile,
        top_codes=top_codes,
        sample_step=sample_step,
    )
    colors = ['#2166ac', '#67a9cf', '#d1e5f0', '#fddbc7', '#ef8a62', '#b2182b', '#762a83', '#1b7837', '#5aae61', '#a6dba0', '#d9f0d3', '#9970ab', '#bdbdbd']
    cmap = ListedColormap(colors[: len(top_codes)] + ['#969696'])
    masked = np.ma.masked_equal(display, -1)
    left, bottom, right, top = extent
    provinces, study = _load_map_context(data_root, profile['crs'])
    fig, ax = plt.subplots(figsize=(11.5, 8.5), dpi=400)
    provinces.plot(ax=ax, facecolor='white', edgecolor='#b5b5b5', linewidth=0.55, zorder=0, rasterized=True)
    ax.imshow(masked, cmap=cmap, interpolation='nearest', extent=(left, right, bottom, top), origin='upper', alpha=0.92, zorder=1)
    provinces.boundary.plot(ax=ax, color='#8c8c8c', linewidth=0.55, zorder=2, rasterized=True)
    study.boundary.plot(ax=ax, color='#222222', linewidth=1.25, zorder=3, rasterized=True)
    legend_handles = [Patch(color=colors[i], label=f'{code // 256} → {code % 256}') for i, code in enumerate(top_codes)]
    legend_handles.append(Patch(color='#969696', label='other transitions'))
    transition_legend = ax.legend(handles=legend_handles, loc='lower right', bbox_to_anchor=(0.90, 0.11), ncol=3, fontsize=6.8, title='2018–2021 transitions', title_fontsize=7.6, framealpha=0.92, borderpad=0.65, columnspacing=0.9, handlelength=1.0)
    ax.add_artist(transition_legend)
    ax.legend(handles=[
        Patch(facecolor='#2c7fb8', edgecolor='#174a73', label='Detailed data footprint'),
        Line2D([0], [0], color='#222222', lw=1.25, label='Black-earth region'),
        Line2D([0], [0], color='#8c8c8c', lw=0.55, label='Provincial boundary'),
    ], loc='lower center', bbox_to_anchor=(0.72, 0.30), ncol=3, fontsize=7.0, framealpha=0.95, borderpad=0.55, columnspacing=1.0, handlelength=1.1)
    ax.set_xlim(left, right)
    ax.set_ylim(bottom, top)
    _add_locator_inset(ax, data_root=data_root, main_extent=extent, source_crs=profile['crs'], detail_footprint=detail_footprint, inset_bounds=(0.04, 0.72, 0.25, 0.24))
    _add_north_arrow(ax)
    _add_scale_bar(ax, extent, length_km=100)
    ax.set_xlabel('Longitude (°E)', labelpad=8)
    ax.set_ylabel('Latitude (°N)', labelpad=8)
    ax.xaxis.set_major_locator(MaxNLocator(6))
    ax.yaxis.set_major_locator(MaxNLocator(6))
    lon_formatter, lat_formatter = _geo_tick_formatters(profile['crs'], extent)
    ax.xaxis.set_major_formatter(lon_formatter)
    ax.yaxis.set_major_formatter(lat_formatter)
    ax.set_title('NE01 | 2018–2021 land-cover transitions\n27 m CDL grid preview', loc='left', fontsize=12, fontweight='bold', pad=10)
    ax.grid(False)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_linewidth(0.8)
    fig.tight_layout()
    _save_figure(fig, output_path)
    plt.close(fig)


def _zoomed_transition_display(
    transition: np.ndarray,
    profile: dict[str, Any],
    *,
    top_codes: list[int],
    sample_step: int = 1,
) -> tuple[np.ndarray, tuple[float, float, float, float]]:
    values = transition[::sample_step, ::sample_step]
    transform = profile['transform'] * Affine.scale(sample_step, sample_step)
    display = np.full(values.shape, len(top_codes), dtype='int16')
    for index, code in enumerate(top_codes):
        display[values == code] = index
    display[values == 0] = -1
    valid_rows, valid_cols = np.where(display >= 0)
    if valid_rows.size == 0:
        return display, rasterio.transform.array_bounds(display.shape[0], display.shape[1], transform)
    row_min, row_max = int(valid_rows.min()), int(valid_rows.max())
    col_min, col_max = int(valid_cols.min()), int(valid_cols.max())
    row_pad = max(3, int((row_max - row_min + 1) * 0.03))
    col_pad = max(3, int((col_max - col_min + 1) * 0.03))
    row_min = max(0, row_min - row_pad)
    row_max = min(display.shape[0] - 1, row_max + row_pad)
    col_min = max(0, col_min - col_pad)
    col_max = min(display.shape[1] - 1, col_max + col_pad)
    window = Window(col_min, row_min, col_max - col_min + 1, row_max - row_min + 1)
    extent = rasterio.windows.bounds(window, transform)
    return display[row_min:row_max + 1, col_min:col_max + 1], extent


def _plot_vegetation_summary(table: pd.DataFrame, output_path: Path) -> None:
    top_codes = (
        table.groupby('transition_code')['pixels_with_valid_observation']
        .sum()
        .sort_values(ascending=False)
        .head(8)
        .index.tolist()
    )
    summary = table[table['transition_code'].isin(top_codes)].groupby(['transition_code', 'from_class', 'to_class'])[['seasonal_mean']].mean().reset_index()
    products = sorted(table['product'].unique())
    fig, axes = plt.subplots(1, len(products), figsize=(14, 5), dpi=400, sharey=False)
    axes = np.atleast_1d(axes)
    for ax, product in zip(axes, products):
        product_table = table[table['product'] == product]
        means = product_table[product_table.transition_code.isin(top_codes)].groupby(['transition_code', 'from_class', 'to_class']).seasonal_mean.mean().reindex(pd.MultiIndex.from_tuples([(code, code // 256, code % 256) for code in top_codes], names=['transition_code', 'from_class', 'to_class']))
        labels = [f'{code // 256}→{code % 256}' for code in top_codes]
        ax.bar(labels, means.to_numpy(), color='#2c7fb8' if product == 'ndvi' else '#7fcdbb')
        ax.set_title(product.upper())
        ax.set_ylabel('Growing-season mean')
        ax.tick_params(axis='x', labelsize=8)
        for label in ax.get_xticklabels():
            label.set_rotation(65)
            label.set_rotation_mode('anchor')
        ax.grid(axis='y', alpha=0.25)
    fig.suptitle('NE01 MODIS vegetation indicators by major transition (2018-2022 mean)')
    fig.tight_layout()
    _save_figure(fig, output_path)
    plt.close(fig)


def _write_report(
    output_path: Path,
    *,
    audit: dict[str, Any],
    classes: pd.DataFrame,
    transitions: pd.DataFrame,
    vegetation: pd.DataFrame,
) -> None:
    top = transitions[transitions.period == '2018-2021'].sort_values('pixels', ascending=False).head(10)
    lines = [
        '# NE01 土地覆盖变化与植被响应运行报告',
        '',
        '## 运行状态',
        '',
        '- 状态：`completed`',
        '- 研究区：`black_earth.shp` 与 CDL 覆盖范围的有效重叠部分',
        f"- 分类分析 CRS：`{audit['analysis_crs']}`",
        f"- 分类分析网格：`{audit['analysis_shape'][1]} × {audit['analysis_shape'][0]}`，像元约 27 m",
        '- 植被分析：MODIS aid0001 tile，生长季为 5–9 月，NDVI/EVI 比例因子为 0.0001',
        '',
        '## 2018 → 2021 主要转移',
        '',
        '| from | to | pixels | area km² |',
        '|---:|---:|---:|---:|',
    ]
    for _, row in top.iterrows():
        lines.append(f"| {int(row.from_class)} | {int(row.to_class)} | {int(row.pixels):,} | {float(row.area_km2):,.2f} |")
    lines.extend(
        [
            '',
            '## 植被响应解释边界',
            '',
            '- 分类编码仍以数字编码报告，未将其擅自命名为具体作物。',
            '- 表中 NDVI/EVI 是按类别转移分组的描述性统计，不代表土地覆盖变化的因果效应。',
            '- 2022 齐齐哈尔种植结构栅格未并入本次主转移矩阵，需单独完成类别体系和空间覆盖核验。',
            f"- 植被统计有效记录数：{len(vegetation):,}。分类年度统计记录数：{len(classes):,}。",
        ]
    )
    output_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def run(data_root: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    cdl_dir = data_root / 'CDL'
    study_path = data_root / 'Shapefiles' / 'black_earth.shp'
    cdl_paths = [cdl_dir / f'CDL_NE_{year}_DYY.tif' for year in range(2018, 2022)]
    for path in [*cdl_paths, study_path]:
        if not path.exists():
            raise FileNotFoundError(path)

    arrays, audit, cdl_profile, nodata = _read_cdl_stack(cdl_paths, study_path)
    pixel_area_m2 = abs(float(cdl_profile['transform'].a * cdl_profile['transform'].e))
    classes, transitions, transition = _make_transition_tables(
        arrays, nodata=nodata, pixel_area_m2=pixel_area_m2, output_dir=output_dir
    )
    _write_raster(output_dir / 'change_map_27m.tif', transition, cdl_profile, dtype='uint16', nodata=0)

    ndvi_dir = data_root / 'MODIS' / 'NDVI_2018-2022'
    evi_dir = data_root / 'MODIS' / 'EVI_2018-2022'
    ndvi_files = group_modis_tiles(ndvi_dir, 'ndvi', years=[2018])
    first_ndvi = next(path for path in ndvi_files[min(ndvi_files)] if MODIS_AID in path.name)
    transition_1km, modis_profile = _reproject_transition_to_modis(transition, cdl_profile, first_ndvi)
    _write_raster(output_dir / 'transition_map_1km.tif', transition_1km, modis_profile, dtype='uint16', nodata=0)

    vegetation_tables = []
    for product, directory in [('ndvi', ndvi_dir), ('evi', evi_dir)]:
        vegetation_tables.append(_seasonal_group_stats(directory, product, transition_1km, years=range(2018, 2023)))
    vegetation = pd.concat(vegetation_tables, ignore_index=True)
    vegetation.to_csv(output_dir / 'vegetation_by_transition.csv', index=False)

    top_codes = (
        vegetation.groupby('transition_code')['pixels_with_valid_observation']
        .sum().sort_values(ascending=False).head(12).index.astype(int).tolist()
    )
    detail_footprint = _transition_footprint(transition_1km, modis_profile)
    _plot_27m_change_preview(transition, cdl_profile, output_path=output_dir / 'change_map_27m_preview.png', top_codes=top_codes, data_root=data_root, detail_footprint=detail_footprint)
    _plot_transition_map(transition_1km, modis_profile, output_path=output_dir / 'change_map_1km.png', top_codes=top_codes, data_root=data_root, detail_footprint=detail_footprint)
    _plot_vegetation_summary(vegetation, output_dir / 'ndvi_evi_by_transition.png')

    audit.update(
        {
            'input_cdl_paths': [str(path) for path in cdl_paths],
            'input_ndvi_directory': str(ndvi_dir),
            'input_evi_directory': str(evi_dir),
            'pixel_area_m2': pixel_area_m2,
            'vegetation_analysis_crs': str(modis_profile['crs']),
            'vegetation_analysis_shape': [int(transition_1km.shape[0]), int(transition_1km.shape[1])],
            'season_months': sorted(SEASON_MONTHS),
            'selected_modis_tile': MODIS_AID,
            'modis_ndvi_dates_2018': len(ndvi_files),
        }
    )
    _write_json(output_dir / 'data_audit.json', audit)
    _write_report(output_dir / 'report.md', audit=audit, classes=classes, transitions=transitions, vegetation=vegetation)
    manifest = {
        'task_id': 'NE01_land_cover_vegetation_change',
        'status': 'completed',
        'method': 'CDL transition matrix + MODIS seasonal group statistics',
        'parameters': {
            'classification_periods': ['2018-2019', '2019-2020', '2020-2021', '2018-2021'],
            'season_months': sorted(SEASON_MONTHS),
            'modis_tile': MODIS_AID,
            'modis_scale_factor': 0.0001,
            'classification_resampling': 'nearest',
            'vegetation_resampling': 'nearest-to-target-grid summary',
        },
        'artifacts': sorted({path.name for path in output_dir.iterdir()} | {'task_manifest.json'}),
        'claim_limits': [
            'numeric CDL class codes only unless an authoritative codebook is supplied',
            'descriptive transition-area and vegetation differences',
            'no causal attribution',
            '2022 Qiqihar raster excluded from the main matrix until class-system audit',
        ],
    }
    _write_json(output_dir / 'task_manifest.json', manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument('--output-dir', type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    manifest = run(args.data_root, args.output_dir)
    print(json.dumps(manifest, ensure_ascii=False, indent=2, default=_json_default))


if __name__ == '__main__':
    main()
