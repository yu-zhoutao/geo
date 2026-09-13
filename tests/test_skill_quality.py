from __future__ import annotations

from pathlib import Path


SKILL_HEADINGS = (
    '## Overview',
    '## When to Use',
    '## Required Inputs',
    '## Workflow',
    '## Decision Logic',
    '## Output Contract',
    '## Detailed Rules',
    '## Failure Modes',
    '## Worked Examples',
    '## Common Mistakes',
    '## Supporting Files',
)


def _skills_root() -> Path:
    return Path(__file__).resolve().parents[1] / 'app' / 'agent_assets' / 'skills'


def test_every_skill_pack_has_full_handbook_structure() -> None:
    for skill_dir in sorted(path for path in _skills_root().iterdir() if path.is_dir()):
        assert (skill_dir / 'SKILL.md').exists(), f'{skill_dir.name} missing SKILL.md'
        assert not (skill_dir / 'rules.md').exists(), f'{skill_dir.name} should merge rules.md into SKILL.md'
        assert not (skill_dir / 'failure-modes.md').exists(), f'{skill_dir.name} should merge failure-modes.md into SKILL.md'
        assert not (skill_dir / 'examples.md').exists(), f'{skill_dir.name} should merge examples.md into SKILL.md'


def test_every_skill_markdown_contains_full_operating_sections() -> None:
    for skill_md in sorted(_skills_root().glob('*/SKILL.md')):
        text = skill_md.read_text(encoding='utf-8')
        for heading in SKILL_HEADINGS:
            assert heading in text, f'{skill_md.parent.name} missing heading {heading}'
        assert len(text) >= 3200, f'{skill_md.parent.name} SKILL.md is still too short'
        assert '<!-- merged-support:start -->' not in text, f'{skill_md.parent.name} still contains merge marker'
        assert '<!-- merged-support:end -->' not in text, f'{skill_md.parent.name} still contains merge marker'


def test_skill_packs_keep_operational_markdown_inside_skill_md() -> None:
    for skill_dir in sorted(path for path in _skills_root().iterdir() if path.is_dir()):
        root_markdown_files = sorted(path.name for path in skill_dir.glob('*.md'))
        assert root_markdown_files == ['SKILL.md'], f'{skill_dir.name} should keep operational markdown only in SKILL.md'


def test_geospatial_skills_use_managed_python_and_evidence_tools() -> None:
    combined = '\n'.join(path.read_text(encoding='utf-8') for path in sorted(_skills_root().glob('*/SKILL.md')))
    forbidden_tools = [
        'inspect_geospatial_request',
        'prepare_geospatial_inputs',
        'run_kde_operator',
        'summarize_geospatial_artifacts',
        'update_execution_plan',
        'execute_kde_workflow',
    ]

    for tool_name in forbidden_tools:
        assert tool_name not in combined

    assert '"$GEO_AGENT_UV_BIN" --project "$GEO_AGENT_GEO_PYTHON_PROJECT" run --python "$GEO_AGENT_GEO_PYTHON_VERSION" python <script>' in combined
    assert 'get_session_context' in combined
    assert 'record_run_evidence' in combined
    assert 'artifact_stage' in combined
    assert 'GEO_AGENT_ARTIFACT_DIR' not in combined
    assert '.geo/scripts' not in combined
    assert '.geo/intermediate' not in combined
    assert '.geo/artifacts' not in combined
    assert '.geo/evidence' not in combined
    for snippet_name in (
        'inspect_vector',
        'inspect_raster',
        'require_metric_crs',
        'bbox_overlap',
        'clip_vector_to_study_area',
        'clip_raster_to_study_area',
        'compute_kde_grid',
        'render_vector_map',
        'write_parameter_snapshot',
    ):
        assert snippet_name in combined


def test_idw_and_gistar_skills_encode_research_backed_defaults() -> None:
    combined = '\n'.join(path.read_text(encoding='utf-8') for path in sorted(_skills_root().glob('*/SKILL.md')))

    for skill_name in (
        'geospatial-idw-method-selection',
        'geospatial-idw-runbook',
        'geospatial-gistar-method-selection',
        'geospatial-gistar-runbook',
        'geospatial-gistar-spatial-weights',
    ):
        assert f'name: {skill_name}' in combined

    for required_snippet in (
        'power=2',
        'k=12',
        'min(width, height) / 250',
        'MAE',
        'RMSE',
        'bias',
        'esda.G_Local',
        'star=True',
        'permutations=999',
        "transform='B'",
        'Queen contiguity',
        'island_weight',
        'FDR',
    ):
        assert required_snippet in combined


def test_kde_skills_require_parameter_sensitivity_and_repair_gate() -> None:
    skill_root = _skills_root()
    kde_parameter = (skill_root / 'geospatial-kde-parameter-rationale' / 'SKILL.md').read_text(encoding='utf-8')
    kde_runbook = (skill_root / 'geospatial-kde-runbook' / 'SKILL.md').read_text(encoding='utf-8')
    skeptical_review = (skill_root / 'geospatial-skeptical-review' / 'SKILL.md').read_text(encoding='utf-8')
    operator_kde = (skill_root.parents[0] / 'agents' / 'operator-kde.md').read_text(encoding='utf-8')
    report_synthesizer = (skill_root.parents[0] / 'agents' / 'report-synthesizer.md').read_text(encoding='utf-8')
    orchestrator = (skill_root.parents[0] / 'agents' / 'geo-orchestrator.md').read_text(encoding='utf-8')

    for snippet in (
        'primary + lower + upper',
        'bandwidth_sensitivity',
        'peak_count_by_bandwidth',
        'disclosure is not a substitute for sensitivity evidence',
    ):
        assert snippet in kde_parameter
        assert snippet in kde_runbook

    for snippet in (
        'minimum three-bandwidth sensitivity check',
        'repair-required',
    ):
        assert snippet in operator_kde

    for snippet in ('blocker', 'repair-required', 'disclose-only', 'parameter-sensitive'):
        assert snippet in skeptical_review

    assert 'unresolved repair-required' in report_synthesizer
    assert 'task-quality release gate' in orchestrator


def test_idw_and_gistar_skills_require_parameter_diagnostics() -> None:
    skill_root = _skills_root()
    idw_runbook = (skill_root / 'geospatial-idw-runbook' / 'SKILL.md').read_text(encoding='utf-8')
    gistar_runbook = (skill_root / 'geospatial-gistar-runbook' / 'SKILL.md').read_text(encoding='utf-8')
    gistar_weights = (skill_root / 'geospatial-gistar-spatial-weights' / 'SKILL.md').read_text(encoding='utf-8')
    operator_interpolation = (skill_root.parents[0] / 'agents' / 'operator-interpolation.md').read_text(encoding='utf-8')
    operator_hotspot = (skill_root.parents[0] / 'agents' / 'operator-spatial-hotspot.md').read_text(encoding='utf-8')

    for snippet in ('power sensitivity', 'neighborhood sensitivity', 'validation is not optional decoration'):
        assert snippet in idw_runbook
        assert snippet in operator_interpolation

    for snippet in ('alternative weight diagnostic', 'neighbor sensitivity', 'weight choice is not a cosmetic parameter'):
        assert snippet in gistar_runbook
        assert snippet in gistar_weights
        assert snippet in operator_hotspot


def test_agent_assets_do_not_require_strict_structured_handoffs_for_quality_scoring() -> None:
    combined = '\n'.join(path.read_text(encoding='utf-8') for path in sorted(_skills_root().glob('*/SKILL.md')))
    agent_text = '\n'.join(path.read_text(encoding='utf-8') for path in sorted((_skills_root().parents[0] / 'agents').glob('*.md')))

    for forbidden in (
        'Return strict JSON',
        'Do not return prose instead of JSON',
        'Mandatory fields are',
        'Decision must be one of',
    ):
        assert forbidden not in combined
        assert forbidden not in agent_text


def test_release_gates_block_missing_family_parameter_diagnostics() -> None:
    skill_root = _skills_root()
    orchestrator = (skill_root.parents[0] / 'agents' / 'geo-orchestrator.md').read_text(encoding='utf-8')
    report_synthesizer = (skill_root.parents[0] / 'agents' / 'report-synthesizer.md').read_text(encoding='utf-8')
    skeptical_review = (skill_root / 'geospatial-skeptical-review' / 'SKILL.md').read_text(encoding='utf-8')

    for snippet in (
        'IDW release must have power_sensitivity and neighborhood_sensitivity evidence',
        'Gi* release must have weight-choice diagnostics or a documented infeasible reason',
    ):
        assert snippet in orchestrator
        assert snippet in report_synthesizer

    for snippet in (
        'missing power_sensitivity evidence',
        'missing neighborhood_sensitivity evidence',
        'missing Gi* weight-choice diagnostics',
    ):
        assert snippet in skeptical_review


def test_backend_does_not_ship_legacy_geospatial_workflow_module() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    assert not (repo_root / 'app' / 'services' / 'geospatial.py').exists()
