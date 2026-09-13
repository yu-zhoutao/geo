"""Reusable building blocks for the Northeast China multisource task catalog.

The application deliberately keeps analysis execution in visible, agent-authored
scripts.  This module contains the boring, repeatable parts those scripts should
share: raster alignment, MODIS scaling, ERA5 loading, land-cover transitions,
trend statistics, and environmental zoning.  It is not a hidden workflow or a
replacement for the evidence ledger.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib.util
from pathlib import Path
import re
from typing import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class RasterMatch:
    """A raster array and the profile of the target analysis grid."""

    array: np.ndarray
    profile: dict[str, object]


MODIS_SCALE_FACTORS: dict[str, float] = {
    'ndvi': 0.0001,
    'evi': 0.0001,
    'sr': 0.0001,
    'lst': 0.02,
}


def group_modis_tiles(
    directory: str | Path,
    product: str,
    *,
    years: Iterable[int] | None = None,
) -> dict[pd.Timestamp, list[Path]]:
    """Group MODIS tile files by acquisition date after semantic filename filtering.

    ``product`` accepts ``ndvi``, ``evi``, ``sr`` and ``clear_sky_days``.  A
    request for ``lst`` intentionally fails for this dataset unless files with
    ``LST_Day`` or ``LST_Night`` appear, preventing clear-sky count rasters from
    being silently treated as temperature.
    """

    root = Path(directory)
    key = product.lower().strip()
    tokens: dict[str, tuple[str, ...]] = {
        'ndvi': ('_NDVI_',),
        'evi': ('_EVI_',),
        'sr': ('sur_refl_',),
        'clear_sky_days': ('Clear_sky_days',),
        'lst': ('LST_Day', 'LST_Night'),
    }
    if key not in tokens:
        raise ValueError(f'Unsupported MODIS file group: {product}')
    year_set = {int(year) for year in years} if years is not None else None
    grouped: dict[pd.Timestamp, list[Path]] = {}
    for path in sorted(root.rglob('*.tif')):
        name = path.name
        if not any(token in name for token in tokens[key]):
            continue
        timestamp = parse_modis_timestamp(path)
        if year_set is not None and timestamp.year not in year_set:
            continue
        grouped.setdefault(timestamp, []).append(path)
    if not grouped:
        raise FileNotFoundError(f'No MODIS {key} files found under {root}')
    return grouped


def parse_modis_timestamp(path: str | Path) -> pd.Timestamp:
    """Extract a MODIS year/DOY token such as ``doy2022081`` from a filename."""

    match = re.search(r'doy(\d{4})(\d{3})', Path(path).name)
    if match is None:
        raise ValueError(f'No MODIS year/DOY token found in {path}')
    return pd.Timestamp(year=int(match.group(1)), month=1, day=1) + pd.to_timedelta(int(match.group(2)) - 1, unit='D')


def scale_modis_values(values: np.ndarray, product: str, *, to_celsius: bool = False) -> np.ndarray:
    """Apply the documented MODIS scale factor and optional LST conversion.

    NDVI/EVI/SR products use a 1e-4 scale.  MOD11A2 LST uses 0.02 Kelvin;
    ``to_celsius=True`` additionally subtracts 273.15.  Clear-sky count and
    quality-control rasters must not be passed as ``product='lst'``.
    """

    key = product.lower().strip()
    if key not in MODIS_SCALE_FACTORS:
        raise ValueError(f'Unsupported MODIS product: {product}')
    result = np.asarray(values, dtype='float32') * MODIS_SCALE_FACTORS[key]
    if key == 'lst' and to_celsius:
        result = result - 273.15
    return result


def read_era5_monthly(paths: Sequence[str | Path], variables: Sequence[str] | None = None):
    """Open and concatenate the monthly ERA5-Land files along ``valid_time``.

    The returned xarray dataset owns open file handles; callers should call
    ``close()`` when the run is finished.  Loading is intentionally lazy until
    an analysis script requests a reduction, which avoids a 60-file memory spike.
    """

    import xarray as xr

    ordered = sorted(Path(path) for path in paths)
    if not ordered:
        raise ValueError('At least one ERA5-Land NetCDF path is required')
    # ERA5 files in this dataset are HDF5-backed NetCDF4 files.  Be explicit so
    # the error is actionable when a fresh managed environment lacks a backend.
    if importlib.util.find_spec('netCDF4') is not None:
        engine = 'netcdf4'
    elif importlib.util.find_spec('h5netcdf') is not None:
        engine = 'h5netcdf'
    else:
        raise ImportError('ERA5-Land requires the netCDF4 or h5netcdf xarray backend')
    datasets = [_open_era5_dataset(path, xr=xr, engine=engine) for path in ordered]
    dataset = xr.concat(datasets, dim='valid_time')
    if variables is not None:
        missing = sorted(set(variables) - set(dataset.data_vars))
        if missing:
            dataset.close()
            raise KeyError(f'Missing ERA5 variables: {missing}')
        dataset = dataset[list(variables)]
    return dataset


def _open_era5_dataset(path: Path, *, xr, engine: str):
    """Open one ERA5 file without xarray's slow implicit CF time decode."""

    dataset = xr.open_dataset(path, engine=engine, decode_times=False)
    if 'valid_time' not in dataset.coords:
        dataset.close()
        raise ValueError(f'{path} has no valid_time coordinate')
    raw = np.asarray(dataset['valid_time'].values)
    units = str(dataset['valid_time'].attrs.get('units', ''))
    match = re.match(r'\s*(seconds|minutes|hours|days)\s+since\s+(.+)\s*$', units, flags=re.IGNORECASE)
    if match is None:
        dataset.close()
        raise ValueError(f'Unsupported ERA5 valid_time units in {path}: {units!r}')
    origin = pd.Timestamp(match.group(2))
    unit = match.group(1).lower()[0]
    decoded = origin + pd.to_timedelta(raw, unit=unit)
    return dataset.assign_coords(valid_time=decoded)


def seasonal_annual_mean(data, months: Iterable[int], *, time_dim: str = 'valid_time'):
    """Return a year-indexed seasonal mean from an ERA5/MODIS xarray object."""

    selected_months = sorted({int(month) for month in months})
    if not selected_months or any(month < 1 or month > 12 for month in selected_months):
        raise ValueError('months must contain integers in the range 1..12')
    if time_dim not in data.dims:
        raise ValueError(f'{time_dim!r} is not a dimension of the input data')
    selected = data.where(data[time_dim].dt.month.isin(selected_months), drop=True)
    if selected.sizes.get(time_dim, 0) == 0:
        raise ValueError('The requested months are absent from the input time range')
    return selected.groupby(f'{time_dim}.year').mean(time_dim, skipna=True)


def compute_transition_matrix(
    before: np.ndarray,
    after: np.ndarray,
    *,
    pixel_area_m2: float | None = None,
    nodata: float | int | None = None,
) -> pd.DataFrame:
    """Count valid class-to-class transitions and optionally calculate area."""

    left = np.asarray(before).reshape(-1)
    right = np.asarray(after).reshape(-1)
    if left.shape != right.shape:
        raise ValueError('before and after rasters must have the same shape')
    valid = np.isfinite(left.astype('float64')) & np.isfinite(right.astype('float64'))
    if nodata is not None:
        valid &= left != nodata
        valid &= right != nodata
    frame = pd.DataFrame({'from_class': left[valid], 'to_class': right[valid]})
    result = frame.value_counts(sort=False).rename('pixels').reset_index()
    if result.empty:
        raise ValueError('No valid pixel pairs remain for the transition matrix')
    if pixel_area_m2 is not None:
        if pixel_area_m2 <= 0:
            raise ValueError('pixel_area_m2 must be positive')
        result['area_km2'] = result['pixels'] * float(pixel_area_m2) / 1_000_000.0
    return result.sort_values(['from_class', 'to_class']).reset_index(drop=True)


def summarize_class_area(
    raster: np.ndarray,
    *,
    pixel_area_m2: float | None = None,
    nodata: float | int | None = None,
) -> pd.DataFrame:
    """Summarize class pixel counts and optional area without inventing labels."""

    values = np.asarray(raster).reshape(-1)
    valid = np.isfinite(values.astype('float64'))
    if nodata is not None:
        valid &= values != nodata
    result = pd.Series(values[valid]).value_counts(sort=False).rename_axis('class').reset_index(name='pixels')
    if result.empty:
        raise ValueError('No valid class pixels remain')
    result['share_pct'] = result['pixels'] / result['pixels'].sum() * 100.0
    if pixel_area_m2 is not None:
        result['area_km2'] = result['pixels'] * float(pixel_area_m2) / 1_000_000.0
    return result.sort_values('class').reset_index(drop=True)


def trend_metrics(values: Sequence[float], *, alpha: float = 0.05) -> dict[str, float | str]:
    """Compute Mann-Kendall direction and Theil-Sen magnitude for one series."""

    import pymannkendall as mk
    from scipy.stats import theilslopes

    series = np.asarray(values, dtype='float64')
    series = series[np.isfinite(series)]
    if series.size < 3:
        raise ValueError('At least three valid observations are required for trend analysis')
    result = mk.original_test(series, alpha=alpha)
    slope, intercept, low, high = theilslopes(series, np.arange(series.size), alpha=1.0 - alpha)
    return {
        'trend': str(result.trend),
        'p_value': float(result.p),
        'kendall_tau': float(result.Tau),
        'sen_slope': float(slope),
        'sen_intercept': float(intercept),
        'sen_slope_low': float(low),
        'sen_slope_high': float(high),
    }


def build_feature_matrix(
    features: Mapping[str, np.ndarray],
    *,
    valid_mask: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Flatten aligned raster features into a finite-row matrix for clustering."""

    if not features:
        raise ValueError('At least two named features are required')
    names = list(features)
    arrays = [np.asarray(features[name], dtype='float64') for name in names]
    shape = arrays[0].shape
    if len(names) < 2 or any(array.shape != shape for array in arrays[1:]):
        raise ValueError('All features must have the same shape, with at least two features')
    matrix = np.column_stack([array.reshape(-1) for array in arrays])
    finite = np.isfinite(matrix).all(axis=1)
    if valid_mask is not None:
        mask = np.asarray(valid_mask, dtype=bool)
        if mask.shape != shape:
            raise ValueError('valid_mask must match the feature shape')
        finite &= mask.reshape(-1)
    if finite.sum() < max(20, len(names) * 5):
        raise ValueError('Too few complete pixels remain for multivariate clustering')
    return matrix[finite], finite, names


def fit_environmental_zones(
    features: Mapping[str, np.ndarray],
    *,
    k_values: Sequence[int] = (3, 4, 5, 6),
    random_state: int = 42,
) -> dict[str, object]:
    """Standardize aligned features, select k by silhouette, and profile zones."""

    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    from sklearn.preprocessing import StandardScaler

    matrix, valid_rows, names = build_feature_matrix(features)
    scaled = StandardScaler().fit_transform(matrix)
    candidates = sorted({int(k) for k in k_values if int(k) >= 2 and int(k) < len(matrix)})
    if not candidates:
        raise ValueError('k_values must contain at least one valid value >= 2')
    scores: list[dict[str, float | int]] = []
    models: dict[int, KMeans] = {}
    for k in candidates:
        model = KMeans(n_clusters=k, random_state=random_state, n_init=10)
        labels = model.fit_predict(scaled)
        score = silhouette_score(scaled, labels) if k < len(matrix) else float('nan')
        models[k] = model
        scores.append({'k': k, 'silhouette_score': float(score), 'inertia': float(model.inertia_)})
    best = max(scores, key=lambda item: item['silhouette_score'])
    model = models[int(best['k'])]
    labels = model.labels_
    profile = pd.DataFrame(matrix, columns=names)
    profile['zone'] = labels
    summary = profile.groupby('zone', sort=True)[names].agg(['mean', 'std', 'count']).reset_index()
    return {
        'labels': labels,
        'valid_rows': valid_rows,
        'features': names,
        'k_scores': pd.DataFrame(scores),
        'selected_k': int(best['k']),
        'cluster_profiles': summary,
        'standardized_features': scaled,
    }


def reproject_raster_to_match(
    source_path: str | Path,
    target_path: str | Path,
    *,
    resampling: str = 'bilinear',
    src_nodata: float | int | None = None,
    dst_nodata: float | int | None = None,
) -> RasterMatch:
    """Reproject one raster onto an existing target grid with explicit resampling."""

    import rasterio
    from rasterio.enums import Resampling
    from rasterio.warp import reproject

    if not hasattr(Resampling, resampling):
        raise ValueError(f'Unknown rasterio resampling method: {resampling}')
    with rasterio.open(source_path) as source, rasterio.open(target_path) as target:
        destination = np.full((target.height, target.width), dst_nodata if dst_nodata is not None else np.nan, dtype='float32')
        reproject(
            source=source.read(1),
            destination=destination,
            src_transform=source.transform,
            src_crs=source.crs,
            src_nodata=src_nodata if src_nodata is not None else source.nodata,
            dst_transform=target.transform,
            dst_crs=target.crs,
            dst_nodata=dst_nodata,
            resampling=getattr(Resampling, resampling),
        )
        profile = target.profile.copy()
    profile.update(dtype='float32', count=1, nodata=dst_nodata)
    return RasterMatch(array=destination, profile=profile)
