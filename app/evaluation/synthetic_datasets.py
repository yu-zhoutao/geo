from __future__ import annotations

import json
import math
from pathlib import Path
import struct

from app.evaluation.benchmarks import BenchmarkScenario


def materialize_synthetic_dataset_pack(scenario: BenchmarkScenario, output_root: Path) -> None:
    if scenario.id == 'P01':
        _materialize_p01_dataset_pack(output_root)
        return
    _materialize_generic_dataset_pack(scenario, output_root)


def _materialize_p01_dataset_pack(output_root: Path) -> None:
    _write_p01_fcd_points(output_root / 'fcd_points_sample.csv')
    _write_p01_boundary(output_root / 'beijing_boundary.geojson')
    manifest: dict[str, object] = {
        'schema': 'geo-agent.evaluation.synthetic-dataset-pack.v1',
        'scenario_id': 'P01',
        'files': ['fcd_points_sample.csv', 'beijing_boundary.geojson'],
        'notes': [
            'Deterministic synthetic Beijing taxi point events for repeatable evaluation.',
            'Coordinates are WGS 84 longitude/latitude and are intended for KDE method validation only.',
        ],
    }
    (output_root / 'dataset-pack-manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )


def _write_p01_fcd_points(path: Path) -> None:
    clusters: tuple[tuple[str, float, float, int, float, float], ...] = (
        ('cbd', 116.461, 39.918, 620, 0.034, 0.022),
        ('zhongguancun', 116.316, 39.984, 560, 0.030, 0.020),
        ('wangjing', 116.482, 39.996, 500, 0.028, 0.018),
        ('beijing_south', 116.379, 39.865, 360, 0.026, 0.018),
    )
    rows: list[str] = ['taxi_id,longitude,latitude,timestamp,cluster']
    taxi_index: int = 0
    for cluster_name, center_lon, center_lat, count, lon_radius, lat_radius in clusters:
        for point_index in range(count):
            taxi_index += 1
            angle: float = point_index * 2.399963229728653 + taxi_index * 0.017
            ring: float = math.sqrt((point_index % 89 + 1) / 89)
            longitude: float = center_lon + math.cos(angle) * lon_radius * ring
            latitude: float = center_lat + math.sin(angle) * lat_radius * ring
            hour: int = 7 + point_index % 14
            minute: int = (point_index * 7) % 60
            rows.append(
                f'taxi_{taxi_index:04d},{longitude:.6f},{latitude:.6f},'
                f'2026-04-29T{hour:02d}:{minute:02d}:00+08:00,{cluster_name}'
            )
    for grid_index in range(210):
        taxi_index += 1
        longitude = 116.05 + (grid_index % 21) * 0.035
        latitude = 39.72 + (grid_index // 21) * 0.035
        rows.append(
            f'taxi_{taxi_index:04d},{longitude:.6f},{latitude:.6f},'
            f'2026-04-29T12:{grid_index % 60:02d}:00+08:00,background'
        )
    path.write_text('\n'.join(rows) + '\n', encoding='utf-8')


def _write_p01_boundary(path: Path) -> None:
    coordinates: list[list[float]] = [
        [115.75, 39.45],
        [117.45, 39.45],
        [117.45, 41.15],
        [115.75, 41.15],
        [115.75, 39.45],
    ]
    feature_collection: dict[str, object] = {
        'type': 'FeatureCollection',
        'name': 'beijing_evaluation_boundary',
        'crs': {
            'type': 'name',
            'properties': {'name': 'urn:ogc:def:crs:OGC:1.3:CRS84'},
        },
        'features': [
            {
                'type': 'Feature',
                'properties': {'name': 'Beijing evaluation boundary', 'source': 'synthetic'},
                'geometry': {'type': 'Polygon', 'coordinates': [coordinates]},
            }
        ],
    }
    path.write_text(json.dumps(feature_collection, ensure_ascii=False, indent=2), encoding='utf-8')


def _materialize_generic_dataset_pack(scenario: BenchmarkScenario, output_root: Path) -> None:
    for item in scenario.dataset_pack:
        target: Path = output_root / item
        target.parent.mkdir(parents=True, exist_ok=True)
        _write_generic_dataset_file(target)
    manifest: dict[str, object] = {
        'schema': 'geo-agent.evaluation.synthetic-dataset-pack.v1',
        'scenario_id': scenario.id,
        'files': list(scenario.dataset_pack),
        'notes': [
            'Minimal deterministic synthetic fixture generated for evaluation isolation.',
            'Scenario oracle fields define the expected control-state behavior.',
        ],
    }
    (output_root / 'dataset-pack-manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )


def _write_generic_dataset_file(path: Path) -> None:
    name: str = path.name.lower()
    suffix: str = path.suffix.lower()
    if suffix == '.geojson':
        path.write_text(
            json.dumps(_generic_geojson(name), ensure_ascii=False, indent=2),
            encoding='utf-8',
        )
        return
    if suffix == '.csv':
        path.write_text(_generic_csv(name), encoding='utf-8')
        return
    if suffix == '.json':
        path.write_text(json.dumps(_generic_json(name), ensure_ascii=False, indent=2), encoding='utf-8')
        return
    if suffix == '.md':
        path.write_text(_generic_markdown(name), encoding='utf-8')
        return
    if suffix == '.prj':
        path.write_text(
            'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],'
            'PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]]',
            encoding='utf-8',
        )
        return
    if suffix == '.shp':
        _write_generic_polygon_shapefile(path)
        return
    path.write_text('synthetic evaluation fixture\n', encoding='utf-8')


def _generic_geojson(name: str) -> dict[str, object]:
    if any(token in name for token in ('area', 'boundary', 'district', 'township', 'grid', 'island')):
        area_one_coordinates: list[list[float]] = [
            [116.0, 39.75],
            [116.7, 39.75],
            [116.7, 40.25],
            [116.0, 40.25],
            [116.0, 39.75],
        ]
        area_two_coordinates: list[list[float]] = [
            [116.7, 39.75],
            [117.2, 39.75],
            [117.2, 40.25],
            [116.7, 40.25],
            [116.7, 39.75],
        ]
        return {
            'type': 'FeatureCollection',
            'features': [
                {
                    'type': 'Feature',
                    'properties': {'id': 'area-1', 'rate': 18.2, 'count': 42},
                    'geometry': {
                        'type': 'Polygon',
                        'coordinates': [area_one_coordinates],
                    },
                },
                {
                    'type': 'Feature',
                    'properties': {'id': 'area-2', 'rate': 9.7, 'count': 21},
                    'geometry': {
                        'type': 'Polygon',
                        'coordinates': [area_two_coordinates],
                    },
                },
            ],
        }
    if any(token in name for token in ('road', 'segment', 'street')):
        return {
            'type': 'FeatureCollection',
            'features': [
                {
                    'type': 'Feature',
                    'properties': {'id': 'road-1', 'event_count': 12},
                    'geometry': {'type': 'LineString', 'coordinates': [[116.1, 39.8], [116.9, 40.1]]},
                }
            ],
        }
    if 'pm25' in name or 'station' in name:
        return {
            'type': 'FeatureCollection',
            'features': [
                {
                    'type': 'Feature',
                    'properties': {
                        'station_id': f'station_{index:02d}',
                        'pm25': 18.0 + index,
                    },
                    'geometry': {
                        'type': 'Point',
                        'coordinates': [116.15 + index * 0.045, 39.78 + index * 0.025],
                    },
                }
                for index in range(12)
            ],
        }
    return {
        'type': 'FeatureCollection',
        'features': [
            {
                'type': 'Feature',
                'properties': {
                    'id': f'event-{index:02d}',
                    'value': 25.0 + index,
                    'pm25': 18.0 + index,
                },
                'geometry': {
                    'type': 'Point',
                    'coordinates': [116.15 + index * 0.045, 39.78 + index * 0.025],
                },
            }
            for index in range(12)
        ],
    }


def _generic_csv(name: str) -> str:
    if 'pm25' in name or 'monitor' in name:
        rows: list[str] = ['id,longitude,latitude,pm25']
        rows.extend(
            f'station_{index:02d},{116.1 + index * 0.04:.6f},'
            f'{39.8 + index * 0.02:.6f},{18 + index}'
            for index in range(12)
        )
        return '\n'.join(rows) + '\n'
    rows = ['id,longitude,latitude']
    rows.extend(
        f'event_{index:02d},{116.1 + index * 0.04:.6f},{39.8 + index * 0.02:.6f}'
        for index in range(12)
    )
    return '\n'.join(rows) + '\n'


def _generic_json(name: str) -> dict[str, object]:
    if 'claim_trace' in name:
        return {'claims': [{'claim': 'Synthetic draft claim for repair evaluation.', 'evidence': []}]}
    if 'map_spec' in name:
        return {'title': 'Synthetic map disclosure draft', 'required_disclosures': ['CRS', 'method', 'limits']}
    return {'name': name, 'source': 'synthetic evaluation fixture'}


def _generic_markdown(name: str) -> str:
    if 'caption' in name:
        return 'Draft caption: hotspot map showing significant risk areas.\n'
    return '# Synthetic draft report\n\nThis draft intentionally needs geospatial claim review.\n'


def _write_generic_polygon_shapefile(path: Path) -> None:
    coordinates: tuple[tuple[float, float], ...] = (
        (116.0, 39.75),
        (117.2, 39.75),
        (117.2, 40.25),
        (116.0, 40.25),
        (116.0, 39.75),
    )
    bbox: tuple[float, float, float, float] = _coordinate_bbox(coordinates)
    content: bytes = (
        struct.pack('<i', 5)
        + struct.pack('<4d', *bbox)
        + struct.pack('<2i', 1, len(coordinates))
        + struct.pack('<i', 0)
        + b''.join(struct.pack('<2d', x, y) for x, y in coordinates)
    )
    record: bytes = struct.pack('>2i', 1, len(content) // 2) + content
    path.write_bytes(_shapefile_header(5, bbox, (100 + len(record)) // 2) + record)
    path.with_suffix('.shx').write_bytes(
        _shapefile_header(5, bbox, 54) + struct.pack('>2i', 50, len(content) // 2)
    )
    path.with_suffix('.dbf').write_bytes(_single_name_record_dbf('beijing_boundary'))
    path.with_suffix('.prj').write_text(
        'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],'
        'PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]]',
        encoding='utf-8',
    )
    path.with_suffix('.cpg').write_text('UTF-8\n', encoding='utf-8')


def _coordinate_bbox(coordinates: tuple[tuple[float, float], ...]) -> tuple[float, float, float, float]:
    xs: tuple[float, ...] = tuple(x for x, _ in coordinates)
    ys: tuple[float, ...] = tuple(y for _, y in coordinates)
    return min(xs), min(ys), max(xs), max(ys)


def _shapefile_header(shape_type: int, bbox: tuple[float, float, float, float], file_length_words: int) -> bytes:
    return (
        struct.pack('>7i', 9994, 0, 0, 0, 0, 0, file_length_words)
        + struct.pack('<2i', 1000, shape_type)
        + struct.pack('<4d', *bbox)
        + struct.pack('<4d', 0.0, 0.0, 0.0, 0.0)
    )


def _single_name_record_dbf(name: str) -> bytes:
    field_name: bytes = b'NAME' + b'\x00' * 7
    header: bytes = (
        b'\x03'
        + bytes((126, 4, 30))
        + struct.pack('<IHH', 1, 65, 65)
        + b'\x00' * 20
    )
    field_descriptor: bytes = (
        field_name
        + b'C'
        + b'\x00' * 4
        + bytes((64, 0))
        + b'\x00' * 14
    )
    value: bytes = name.encode('ascii')[:64].ljust(64, b' ')
    return header + field_descriptor + b'\r' + b' ' + value + b'\x1a'
