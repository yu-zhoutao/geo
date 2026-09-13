from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil

from app.evaluation.benchmarks import BenchmarkValidationError, repo_root
from app.evaluation.manifests import VariantManifest
from app.evaluation.strategy_profiles import StrategyProfile, resolve_strategy_overlay_root
from app.services.agent_assets import AgentAssetService


NO_OVERLAY_VALUES: set[str] = {'', 'none'}


@dataclass(frozen=True, slots=True)
class PreparedVariantAssets:
    variant_id: str
    agent_asset_root: Path
    generated: bool
    manifest: dict[str, object]


@dataclass(slots=True)
class AgentMarkdown:
    path: Path
    frontmatter: dict[str, str | tuple[str, ...]]
    body: str

    @property
    def name(self) -> str:
        return str(self.frontmatter.get('name') or '').strip()

    @property
    def runtime_name(self) -> str:
        return str(self.frontmatter.get('runtime_name') or self.name).strip()

    @property
    def skills(self) -> tuple[str, ...]:
        raw_skills = self.frontmatter.get('skills') or ()
        if isinstance(raw_skills, tuple):
            return raw_skills
        return ()


def prepare_variant_agent_assets(
    variant: VariantManifest,
    output_root: Path,
    *,
    strategy_profile: StrategyProfile | None = None,
) -> PreparedVariantAssets:
    source_root: Path = _resolve_repo_path(variant.agent_asset_root)
    _validate_agent_asset_root(source_root)
    overlay_root: Path | None = _overlay_root(variant)
    strategy_overlay_root: Path | None = resolve_strategy_overlay_root(strategy_profile) if strategy_profile is not None else None
    if variant.agent_asset_mode == 'default' and overlay_root is None and strategy_profile is None:
        return PreparedVariantAssets(
            variant_id=variant.id,
            agent_asset_root=source_root,
            generated=False,
            manifest=_preparation_manifest(variant, source_root, source_root, generated=False, strategy_profile=None),
        )

    generated_root: Path = _generated_asset_root(output_root, variant, strategy_profile)
    if generated_root.exists():
        shutil.rmtree(generated_root)
    shutil.copytree(source_root, generated_root)
    if overlay_root is not None:
        shutil.copytree(overlay_root, generated_root, dirs_exist_ok=True)
    if strategy_overlay_root is not None:
        shutil.copytree(strategy_overlay_root, generated_root, dirs_exist_ok=True)

    if variant.agent_asset_mode == 'disable-skills':
        _clear_agent_skills(generated_root)
        _append_variant_notice(
            generated_root,
            'Bundled professional skill access is disabled for this evaluation variant.',
        )
    elif variant.agent_asset_mode == 'disable-role':
        _remove_agent_roles(generated_root, variant.disabled_roles)
        _append_variant_notice(
            generated_root,
            f'Unavailable evaluation variant roles: {", ".join(variant.disabled_roles)}.',
        )
    elif variant.agent_asset_mode == 'generated-single-agent':
        _generate_single_agent_bundle(generated_root, variant.enabled_roles)
        _append_variant_notice(
            generated_root,
            'This evaluation variant uses one runtime agent for triage, design, audit, execution, reporting, and review.',
        )
    elif variant.agent_asset_mode != 'default':
        raise BenchmarkValidationError(f'{variant.path} cannot prepare agent asset mode: {variant.agent_asset_mode}')

    if strategy_profile is not None:
        _append_strategy_guidance(generated_root, strategy_profile)

    _validate_agent_asset_root(generated_root)
    return PreparedVariantAssets(
        variant_id=variant.id,
        agent_asset_root=generated_root,
        generated=True,
        manifest=_preparation_manifest(variant, source_root, generated_root, generated=True, strategy_profile=strategy_profile),
    )


def _generated_asset_root(
    output_root: Path,
    variant: VariantManifest,
    strategy_profile: StrategyProfile | None,
) -> Path:
    if strategy_profile is None:
        return output_root / variant.id / 'agent_assets'
    return output_root / variant.id / strategy_profile.id / 'agent_assets'


def _overlay_root(variant: VariantManifest) -> Path | None:
    if variant.agent_asset_overlay_root in NO_OVERLAY_VALUES:
        return None
    root: Path = _resolve_repo_path(variant.agent_asset_overlay_root)
    if not root.exists():
        raise BenchmarkValidationError(f'{variant.path} references missing agent asset overlay: {root}')
    return root


def _validate_agent_asset_root(root: Path) -> None:
    try:
        AgentAssetService(root).load_bundle()
    except Exception as exc:
        raise BenchmarkValidationError(f'Invalid agent asset root {root}: {exc}') from exc


def _clear_agent_skills(root: Path) -> None:
    for agent in _load_agents(root):
        agent.frontmatter['skills'] = ()
        _write_agent(agent)


def _remove_agent_roles(root: Path, disabled_roles: tuple[str, ...]) -> None:
    disabled: set[str] = set(disabled_roles)
    matched: set[str] = set()
    for agent in _load_agents(root):
        if agent.name in disabled or agent.runtime_name in disabled:
            matched.add(agent.name)
            matched.add(agent.runtime_name)
            agent.path.unlink()
    missing: set[str] = disabled - matched
    if missing:
        joined: str = ', '.join(sorted(missing))
        raise BenchmarkValidationError(f'Disabled roles do not exist in generated asset root: {joined}')


def _generate_single_agent_bundle(root: Path, enabled_roles: tuple[str, ...]) -> None:
    if len(enabled_roles) != 1:
        raise BenchmarkValidationError('Single-agent variants must define exactly one enabled role')
    primary_role: str = enabled_roles[0]
    agents: list[AgentMarkdown] = _load_agents(root)
    primary: AgentMarkdown | None = next(
        (
            agent for agent in agents
            if agent.name == primary_role or agent.runtime_name == primary_role
        ),
        None,
    )
    if primary is None:
        raise BenchmarkValidationError(f'Single-agent primary role does not exist: {primary_role}')

    all_skills: tuple[str, ...] = tuple(sorted({skill for agent in agents for skill in agent.skills}))
    integrated_blocks: list[str] = [
        f'## {agent.name}\n\n{agent.body.strip()}'
        for agent in agents
        if agent.path != primary.path
    ]
    primary.frontmatter['mode'] = 'all'
    primary.frontmatter['skills'] = all_skills
    primary.body = (
        primary.body.rstrip()
        + '\n\n# Integrated Specialist Responsibilities\n\n'
        + '\n\n'.join(integrated_blocks)
        + '\n'
    )
    _write_agent(primary)

    for agent in agents:
        if agent.path != primary.path and agent.path.exists():
            agent.path.unlink()


def _append_variant_notice(root: Path, notice: str) -> None:
    agents: list[AgentMarkdown] = _load_agents(root)
    primary: AgentMarkdown | None = next((agent for agent in agents if agent.runtime_name == 'geo'), None)
    if primary is None:
        primary = agents[0] if agents else None
    if primary is None:
        raise BenchmarkValidationError(f'Generated asset root has no agents: {root}')
    primary.body = primary.body.rstrip() + f'\n\n# Evaluation Variant Constraints\n{notice}\n'
    _write_agent(primary)


def _append_strategy_guidance(root: Path, strategy_profile: StrategyProfile) -> None:
    notice: str = (
        f'Strategy profile `{strategy_profile.id}` ({strategy_profile.label}) is active for this evaluation attempt. '
        'Treat it as an emphasis profile, not as a fixed workflow. Preserve the user request unchanged and let the '
        f'evidence determine the order of work.\n\n{strategy_profile.guidance.strip()}'
    )
    _append_variant_notice(root, notice)


def _load_agents(root: Path) -> list[AgentMarkdown]:
    agents_root: Path = root / 'agents'
    agents: list[AgentMarkdown] = [
        _read_agent(path)
        for path in sorted(agents_root.glob('*.md'))
    ]
    if not agents:
        raise BenchmarkValidationError(f'No agent markdown files found under {agents_root}')
    return agents


def _read_agent(path: Path) -> AgentMarkdown:
    frontmatter, body = _split_frontmatter(path.read_text(encoding='utf-8'), path)
    return AgentMarkdown(path=path, frontmatter=frontmatter, body=body)


def _split_frontmatter(text: str, path: Path) -> tuple[dict[str, str | tuple[str, ...]], str]:
    if not text.startswith('---\n'):
        raise BenchmarkValidationError(f'{path} is missing YAML frontmatter')
    try:
        _, frontmatter_block, body = text.split('---\n', 2)
    except ValueError as exc:
        raise BenchmarkValidationError(f'{path} has malformed YAML frontmatter') from exc

    frontmatter: dict[str, str | tuple[str, ...]] = {}
    current_key: str | None = None
    list_values: list[str] = []

    def commit_list() -> None:
        nonlocal current_key, list_values
        if current_key is not None:
            frontmatter[current_key] = tuple(list_values)
            current_key = None
            list_values = []

    for raw_line in frontmatter_block.splitlines():
        line: str = raw_line.rstrip()
        if not line.strip():
            continue
        if line.startswith('  - '):
            if current_key is None:
                raise BenchmarkValidationError(f'{path} has a frontmatter list item without a key')
            list_values.append(line[4:].strip())
            continue
        commit_list()
        if ':' not in line:
            raise BenchmarkValidationError(f'{path} has invalid frontmatter line: {line}')
        key, value = line.split(':', 1)
        field: str = key.strip()
        raw_value: str = value.strip()
        if raw_value:
            frontmatter[field] = raw_value
            continue
        current_key = field
        list_values = []
    commit_list()
    return frontmatter, body.lstrip('\n')


def _write_agent(agent: AgentMarkdown) -> None:
    lines: list[str] = ['---']
    for key, value in agent.frontmatter.items():
        if isinstance(value, tuple):
            lines.append(f'{key}:')
            lines.extend(f'  - {item}' for item in value)
            continue
        lines.append(f'{key}: {value}')
    lines.extend(['---', '', agent.body.lstrip('\n')])
    agent.path.write_text('\n'.join(lines), encoding='utf-8')


def _preparation_manifest(
    variant: VariantManifest,
    source_root: Path,
    prepared_root: Path,
    *,
    generated: bool,
    strategy_profile: StrategyProfile | None,
) -> dict[str, object]:
    return {
        'variant_id': variant.id,
        'agent_asset_mode': variant.agent_asset_mode,
        'source_root': str(source_root),
        'prepared_root': str(prepared_root),
        'generated': generated,
        'enabled_roles': list(variant.enabled_roles),
        'disabled_roles': list(variant.disabled_roles),
        'skill_mode': variant.skill_mode,
        'enabled_skills': list(variant.enabled_skills),
        'disabled_skills': list(variant.disabled_skills),
        'strategy_profile': strategy_profile.as_json() if strategy_profile is not None else None,
    }


def _resolve_repo_path(value: str) -> Path:
    path: Path = Path(value)
    if path.is_absolute():
        return path
    return repo_root() / path
