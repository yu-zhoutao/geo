from __future__ import annotations

from pathlib import Path

from app.config import Settings
from app.evaluation.benchmarks import repo_root
from app.evaluation.manifests import VariantManifest
from app.evaluation.runtime_assets import prepare_variant_agent_assets
from app.evaluation.strategy_profiles import load_strategy_profile
from app.services.agent_assets import AgentAssetService


def _variant(
    tmp_path: Path,
    *,
    variant_id: str = 'full-system',
    agent_asset_mode: str = 'default',
    enabled_roles: tuple[str, ...] = ('geo-orchestrator',),
    disabled_roles: tuple[str, ...] = (),
    skill_mode: str = 'enabled',
    enabled_skills: tuple[str, ...] = ('all',),
    disabled_skills: tuple[str, ...] = (),
) -> VariantManifest:
    return VariantManifest(
        id=variant_id,
        path=tmp_path / f'{variant_id}.yaml',
        label=variant_id,
        kind='internal-agent-runtime',
        agent_asset_mode=agent_asset_mode,  # type: ignore[arg-type]
        agent_asset_root='app/agent_assets',
        agent_asset_overlay_root='none',
        enabled_roles=enabled_roles,
        disabled_roles=disabled_roles,
        skill_mode=skill_mode,  # type: ignore[arg-type]
        enabled_skills=enabled_skills,
        disabled_skills=disabled_skills,
        model='inherit',
        temperature=0.0,
        runtime_wall_clock_budget_seconds=120,
        max_turns=12,
        scenario_selector='full-suite',
        scoring_eligibility=('llm-judge',),
    )


def test_prepare_default_variant_reuses_default_agent_asset_root(tmp_path: Path) -> None:
    variant: VariantManifest = _variant(tmp_path)

    prepared = prepare_variant_agent_assets(variant, tmp_path / 'generated')

    assert prepared.generated is False
    assert prepared.agent_asset_root == repo_root() / 'app' / 'agent_assets'
    assert prepared.manifest['agent_asset_mode'] == 'default'


def test_prepare_strategy_profile_generates_asset_copy_with_guidance(tmp_path: Path) -> None:
    source_root: Path = repo_root() / 'app' / 'agent_assets'
    original_geo: str = (source_root / 'agents' / 'geo-orchestrator.md').read_text(encoding='utf-8')
    variant: VariantManifest = _variant(tmp_path)
    profile = load_strategy_profile(repo_root() / 'app' / 'evaluation_assets' / 'strategy_profiles' / 'crs_first.yaml')

    prepared = prepare_variant_agent_assets(variant, tmp_path / 'generated', strategy_profile=profile)
    bundle = AgentAssetService(prepared.agent_asset_root).load_bundle()

    assert prepared.generated is True
    assert prepared.agent_asset_root != source_root
    assert prepared.manifest['strategy_profile']['id'] == 'crs_first'  # type: ignore[index]
    assert 'Strategy profile `crs_first`' in bundle.agents['geo-orchestrator'].prompt
    assert 'coordinate reference system' in bundle.agents['geo-orchestrator'].prompt
    assert (source_root / 'agents' / 'geo-orchestrator.md').read_text(encoding='utf-8') == original_geo


def test_prepare_no_skills_variant_clears_agent_skill_lists_without_mutating_default(tmp_path: Path) -> None:
    source_root: Path = repo_root() / 'app' / 'agent_assets'
    original_geo: str = (source_root / 'agents' / 'geo-orchestrator.md').read_text(encoding='utf-8')
    variant: VariantManifest = _variant(
        tmp_path,
        variant_id='no-skills',
        agent_asset_mode='disable-skills',
        skill_mode='disabled',
        enabled_skills=(),
        disabled_skills=('all',),
    )

    prepared = prepare_variant_agent_assets(variant, tmp_path / 'generated')
    bundle = AgentAssetService(prepared.agent_asset_root).load_bundle()
    original_bundle = AgentAssetService(source_root).load_bundle()

    assert prepared.generated is True
    assert all(not agent.skills for agent in bundle.agents.values())
    assert any(agent.skills for agent in original_bundle.agents.values())
    assert (source_root / 'agents' / 'geo-orchestrator.md').read_text(encoding='utf-8') == original_geo


def test_prepare_disable_role_variant_removes_only_generated_role(tmp_path: Path) -> None:
    source_root: Path = repo_root() / 'app' / 'agent_assets'
    variant: VariantManifest = _variant(
        tmp_path,
        variant_id='no-skeptical-review',
        agent_asset_mode='disable-role',
        disabled_roles=('skeptical-review',),
    )

    prepared = prepare_variant_agent_assets(variant, tmp_path / 'generated')
    bundle = AgentAssetService(prepared.agent_asset_root).load_bundle()
    original_bundle = AgentAssetService(source_root).load_bundle()

    assert 'skeptical-review' not in bundle.agents
    assert 'skeptical-review' in original_bundle.agents
    assert (prepared.agent_asset_root / 'agents' / 'skeptical-review.md').exists() is False
    assert (source_root / 'agents' / 'skeptical-review.md').exists() is True


def test_prepare_single_agent_variant_merges_specialist_assets_into_one_runtime_agent(tmp_path: Path) -> None:
    variant: VariantManifest = _variant(
        tmp_path,
        variant_id='single-agent',
        agent_asset_mode='generated-single-agent',
        enabled_roles=('geo-orchestrator',),
    )

    prepared = prepare_variant_agent_assets(variant, tmp_path / 'generated')
    bundle = AgentAssetService(prepared.agent_asset_root).load_bundle()

    assert set(bundle.agents) == {'geo-orchestrator'}
    assert bundle.agents['geo-orchestrator'].runtime_name == 'geo'
    assert 'geospatial-skeptical-review' in bundle.agents['geo-orchestrator'].skills
    assert 'Integrated Specialist Responsibilities' in bundle.agents['geo-orchestrator'].prompt


def test_runtime_can_load_prepared_variant_agent_asset_root(tmp_path: Path) -> None:
    from app.services.agent_runtime import OpenCodeAgentRuntimeClient

    variant: VariantManifest = _variant(
        tmp_path,
        variant_id='no-skeptical-review',
        agent_asset_mode='disable-role',
        disabled_roles=('skeptical-review',),
    )
    prepared = prepare_variant_agent_assets(variant, tmp_path / 'generated')

    runtime = OpenCodeAgentRuntimeClient(
        Settings(agent_asset_root=prepared.agent_asset_root, glm_api_key='test-key')
    )
    config = runtime._build_runtime_config(port=43111, cors_origin='http://127.0.0.1:5173')

    assert 'skeptical-review' not in config['agent']
    assert runtime._asset_service.source_root == prepared.agent_asset_root
