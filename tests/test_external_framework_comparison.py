from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.evaluation.aggregation import RUN_SCORES_FILENAME, aggregate_campaign
from app.evaluation.benchmarks import BenchmarkValidationError, default_benchmark_root
from app.evaluation.external_frameworks import (
    EXTERNAL_EVIDENCE_FILENAME,
    default_external_comparison_root,
    default_external_framework_root,
    import_external_evidence_pack,
    import_external_evidence_packs,
    load_external_comparison_selector,
    validate_external_comparison_selector,
    validate_external_evidence_pack,
    validate_external_framework_manifests,
)
from app.evaluation.judge_rubrics import GEOSPATIAL_AGENT_RUBRIC
from app.evaluation.llm_judge import JudgeConfig, build_judge_packet, write_judge_score
from app.evaluation.run_bundles import RUN_MANIFEST_FILENAME, RUN_STATUS_FILENAME


class _StaticJudgeProvider:
    async def complete(self, *, messages: list[dict[str, str]], model: str, temperature: float) -> str:
        dimensions: dict[str, dict[str, object]] = {
            dimension.id: {'score': 4, 'reason': f'{dimension.id} external evidence reason'}
            for dimension in GEOSPATIAL_AGENT_RUBRIC.dimensions
        }
        return json.dumps({'dimensions': dimensions, 'summary': 'External run is judgeable.'})


def _asset_root() -> Path:
    return Path(__file__).resolve().parents[1] / 'app' / 'evaluation_assets'


def _example_pack_path() -> Path:
    return (
        default_external_comparison_root()
        / 'example-evidence'
        / 'gis-copilot'
        / 'P01'
        / 'repeat-001'
        / 'evidence-pack.json'
    )


def test_external_framework_manifests_validate_expected_candidates() -> None:
    frameworks = validate_external_framework_manifests(default_external_framework_root())
    by_id = {framework.id: framework for framework in frameworks}

    assert set(by_id) == {'gis-copilot', 'geocogent'}
    assert by_id['gis-copilot'].zotero_key == 'V46AX5ZC'
    assert by_id['gis-copilot'].expected_execution_mode == 'qgis-plugin'
    assert by_id['geocogent'].zotero_key == 'H4PGHRTX'
    assert by_id['geocogent'].expected_execution_mode == 'code-generation'


def test_external_comparison_selector_uses_balanced_real_scenarios() -> None:
    selector = validate_external_comparison_selector(
        default_external_comparison_root() / 'thesis-giscopilot-geocogent-v1.yaml',
        framework_root=default_external_framework_root(),
        benchmark_root=default_benchmark_root(),
    )

    assert selector.id == 'thesis-giscopilot-geocogent-v1'
    assert selector.framework_ids == ('gis-copilot', 'geocogent')
    assert selector.scenario_ids == ('P01', 'C09', 'R07', 'X01')
    assert {scenario.gold_control_state for scenario in selector.scenarios} == {
        'proceed',
        'clarify',
        'repair',
        'stop',
    }
    assert all(scenario.dataset_root == 'data' for scenario in selector.scenarios)


def test_example_external_evidence_pack_validates_and_hashes_files() -> None:
    pack = validate_external_evidence_pack(
        _example_pack_path(),
        framework_root=default_external_framework_root(),
        benchmark_root=default_benchmark_root(),
    )

    assert pack.framework.id == 'gis-copilot'
    assert pack.scenario.id == 'P01'
    assert pack.original_prompt == pack.scenario.user_prompt
    assert pack.run_status.status == 'completed'
    assert pack.final_answer_text.startswith('示例外部框架回答')
    assert {'transcript', 'logs', 'generated_code', 'artifacts'}.issubset(
        {item.kind for item in pack.evidence_files}
    )
    assert all(len(item.sha256) == 64 for item in pack.evidence_files)


def test_external_evidence_pack_rejects_prompt_mismatch(tmp_path: Path) -> None:
    source = _example_pack_path()
    copied_root = tmp_path / 'pack'
    copied_root.mkdir()
    payload = json.loads(source.read_text(encoding='utf-8'))
    payload['original_prompt'] = 'not the scenario prompt'
    (copied_root / 'evidence-pack.json').write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )

    with pytest.raises(BenchmarkValidationError, match='prompt does not match'):
        validate_external_evidence_pack(
            copied_root / 'evidence-pack.json',
            framework_root=default_external_framework_root(),
            benchmark_root=default_benchmark_root(),
        )


def test_external_evidence_pack_rejects_missing_artifact(tmp_path: Path) -> None:
    source = _example_pack_path()
    copied_root = tmp_path / 'pack'
    copied_root.mkdir()
    payload = json.loads(source.read_text(encoding='utf-8'))
    payload['evidence']['artifacts'] = ['missing-map.html']
    (copied_root / 'evidence-pack.json').write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )

    with pytest.raises(BenchmarkValidationError, match='missing evidence file'):
        validate_external_evidence_pack(
            copied_root / 'evidence-pack.json',
            framework_root=default_external_framework_root(),
            benchmark_root=default_benchmark_root(),
        )


def test_import_external_evidence_pack_creates_scoreable_run_without_app_traces(tmp_path: Path) -> None:
    imported = import_external_evidence_pack(
        _example_pack_path(),
        tmp_path / 'campaign',
        framework_root=default_external_framework_root(),
        benchmark_root=default_benchmark_root(),
    )
    bundle = imported.bundle_path

    assert imported.run_id == 'gis-copilot__P01__r001'
    assert (bundle / RUN_MANIFEST_FILENAME).exists()
    assert (bundle / RUN_STATUS_FILENAME).exists()
    assert (bundle / EXTERNAL_EVIDENCE_FILENAME).exists()
    assert not (bundle / 'session.json').exists()
    assert not (bundle / 'transcript.json').exists()

    run_manifest = json.loads((bundle / RUN_MANIFEST_FILENAME).read_text(encoding='utf-8'))
    assert run_manifest['variant']['id'] == 'gis-copilot'
    assert run_manifest['variant']['kind'] == 'external-framework'
    assert run_manifest['external_evidence']['manifest_hash'] == imported.evidence_manifest_hash

    packet = build_judge_packet(imported.scenario, bundle)
    assert packet.payload['external_evidence']['framework']['id'] == 'gis-copilot'
    assert 'todo' not in json.dumps(packet.as_json(), ensure_ascii=False).lower()


def test_imported_external_run_can_be_scored_and_aggregated(tmp_path: Path) -> None:
    imported = import_external_evidence_pack(
        _example_pack_path(),
        tmp_path / 'campaign',
        framework_root=default_external_framework_root(),
        benchmark_root=default_benchmark_root(),
    )

    asyncio.run(
        write_judge_score(
            imported.scenario,
            imported.bundle_path,
            _StaticJudgeProvider(),
            JudgeConfig(model='static-judge', temperature=0.0),
        )
    )
    summary = aggregate_campaign(tmp_path / 'campaign')
    run_scores_path = tmp_path / 'campaign' / 'exports' / RUN_SCORES_FILENAME
    run_scores = run_scores_path.read_text(encoding='utf-8')

    assert summary['run_count'] == 1
    assert summary['scored_run_count'] == 1
    assert summary['per_variant'][0]['variant_id'] == 'gis-copilot'
    assert summary['per_run'][0]['evidence_manifest_hash'] == imported.evidence_manifest_hash
    assert 'GIS Copilot' in run_scores
    assert 'external-evidence.json' in run_scores


def test_import_external_evidence_directory_imports_all_packs(tmp_path: Path) -> None:
    imported = import_external_evidence_packs(
        default_external_comparison_root() / 'example-evidence',
        tmp_path / 'campaign',
        framework_root=default_external_framework_root(),
        benchmark_root=default_benchmark_root(),
    )

    assert [item.run_id for item in imported] == ['gis-copilot__P01__r001']


def test_external_comparison_assets_are_under_evaluation_assets() -> None:
    selector = load_external_comparison_selector(
        _asset_root() / 'external_comparison' / 'thesis-giscopilot-geocogent-v1.yaml'
    )

    assert selector.benchmark_root == 'app/agent_assets/benchmarks'
    assert selector.scenario_selector == 'thesis-ablation-real-v1'
