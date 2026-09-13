from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
from pathlib import Path
import shutil
from typing import Any


REQUIRED_AGENT_SECTIONS = (
    'Mission',
    'Scope Boundaries',
    'Required Inputs',
    'Workflow',
    'Output Contract',
    'Stop Conditions',
    'Forbidden Moves',
)


class AgentAssetValidationError(ValueError):
    pass


@dataclass(slots=True)
class SkillAsset:
    name: str
    display_label: str
    description: str
    source_dir: Path
    skill_md_path: Path
    content: str
    supporting_files: tuple[str, ...]
    compatibility: str | None = None

    @property
    def digest(self) -> str:
        return _directory_digest(self.source_dir)


@dataclass(slots=True)
class AgentAsset:
    name: str
    description: str
    runtime_name: str
    mode: str
    permission_profile: str
    skills: tuple[str, ...]
    source_path: Path
    prompt: str
    sections: tuple[str, ...]

    @property
    def digest(self) -> str:
        return _file_digest(self.source_path)


@dataclass(slots=True)
class AgentAssetBundle:
    source_root: Path
    agents: dict[str, AgentAsset]
    skills: dict[str, SkillAsset]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _directory_digest(directory: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in directory.rglob('*') if item.is_file()):
        digest.update(path.relative_to(directory).as_posix().encode('utf-8'))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _parse_scalar(value: str) -> str | bool:
    stripped = value.strip()
    lowered = stripped.lower()
    if lowered == 'true':
        return True
    if lowered == 'false':
        return False
    return stripped


def _parse_frontmatter(text: str, *, source: Path) -> tuple[dict[str, Any], str]:
    if not text.startswith('---\n'):
        raise AgentAssetValidationError(f'{source} is missing YAML frontmatter')
    try:
        _, frontmatter_block, body = text.split('---\n', 2)
    except ValueError as exc:
        raise AgentAssetValidationError(f'{source} has malformed YAML frontmatter delimiters') from exc

    data: dict[str, Any] = {}
    current_key: str | None = None
    list_values: list[str] = []

    def commit_list() -> None:
        nonlocal current_key, list_values
        if current_key is not None:
            data[current_key] = tuple(list_values)
        current_key = None
        list_values = []

    for raw_line in frontmatter_block.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        if line.startswith('  - '):
            if current_key is None:
                raise AgentAssetValidationError(f'{source} has a list item without a list key')
            list_values.append(line[4:].strip())
            continue
        if current_key is not None:
            commit_list()
        if ':' not in line:
            raise AgentAssetValidationError(f'{source} has invalid frontmatter line: {line}')
        key, value = line.split(':', 1)
        key = key.strip()
        value = value.strip()
        if value:
            data[key] = _parse_scalar(value)
            continue
        current_key = key
    if current_key is not None:
        commit_list()
    return data, body.lstrip('\n')


def _extract_sections(markdown: str) -> tuple[str, ...]:
    sections: list[str] = []
    for line in markdown.splitlines():
        if line.startswith('# '):
            sections.append(line[2:].strip())
    return tuple(sections)


class AgentAssetService:
    def __init__(self, source_root: Path | None = None) -> None:
        self.source_root = source_root or (_repo_root() / 'app' / 'agent_assets')

    def load_bundle(self) -> AgentAssetBundle:
        if not self.source_root.exists():
            raise AgentAssetValidationError(f'Agent asset root does not exist: {self.source_root}')

        skills = self._load_skills()
        agents = self._load_agents(skills=skills)
        return AgentAssetBundle(source_root=self.source_root, agents=agents, skills=skills)

    def build_manifest(self, bundle: AgentAssetBundle, *, generated_at: datetime | None = None) -> dict[str, Any]:
        timestamp = generated_at or datetime.now(UTC)
        return {
            'schema_version': 1,
            'generated_at': timestamp.isoformat(),
            'source_root': str(bundle.source_root),
            'agents': [
                {
                    'name': agent.name,
                    'runtime_name': agent.runtime_name,
                    'description': agent.description,
                    'mode': agent.mode,
                    'permission_profile': agent.permission_profile,
                    'skills': list(agent.skills),
                    'sections': list(agent.sections),
                    'source_path': str(agent.source_path),
                    'sha256': agent.digest,
                }
                for agent in sorted(bundle.agents.values(), key=lambda item: item.name)
            ],
            'skills': [
                {
                    'name': skill.name,
                    'display_label': skill.display_label,
                    'description': skill.description,
                    'compatibility': skill.compatibility,
                    'source_dir': str(skill.source_dir),
                    'supporting_files': list(skill.supporting_files),
                    'sha256': skill.digest,
                }
                for skill in sorted(bundle.skills.values(), key=lambda item: item.name)
            ],
        }

    def materialize_runtime_bundle(self, bundle: AgentAssetBundle, destination_root: Path) -> dict[str, Any]:
        if destination_root.exists():
            shutil.rmtree(destination_root)
        skills_root = destination_root / 'skills'
        skills_root.mkdir(parents=True, exist_ok=True)

        for skill in bundle.skills.values():
            shutil.copytree(skill.source_dir, skills_root / skill.name)

        manifest = self.build_manifest(bundle)
        (destination_root / 'manifest.json').write_text(_json_dumps(manifest), encoding='utf-8')
        return manifest

    def _load_skills(self) -> dict[str, SkillAsset]:
        skills: dict[str, SkillAsset] = {}
        skills_root = self.source_root / 'skills'
        for skill_md_path in sorted(skills_root.rglob('SKILL.md')):
            content = skill_md_path.read_text(encoding='utf-8')
            frontmatter, _body = _parse_frontmatter(content, source=skill_md_path)
            name = str(frontmatter.get('name') or '').strip()
            description = str(frontmatter.get('description') or '').strip()
            if not name or not description:
                raise AgentAssetValidationError(f'{skill_md_path} must define name and description')
            if name in skills:
                raise AgentAssetValidationError(f'Duplicate skill name: {name}')
            source_dir = skill_md_path.parent
            supporting_files = tuple(
                sorted(
                    path.relative_to(source_dir).as_posix()
                    for path in source_dir.rglob('*')
                    if path.is_file() and path.name != 'SKILL.md'
                )
            )
            skills[name] = SkillAsset(
                name=name,
                display_label=str(frontmatter.get('display_label') or name).strip() or name,
                description=description,
                source_dir=source_dir,
                skill_md_path=skill_md_path,
                content=content,
                supporting_files=supporting_files,
                compatibility=str(frontmatter.get('compatibility')) if frontmatter.get('compatibility') is not None else None,
            )
        return skills

    def _load_agents(self, *, skills: dict[str, SkillAsset]) -> dict[str, AgentAsset]:
        agents: dict[str, AgentAsset] = {}
        runtime_names: dict[str, str] = {}
        agents_root = self.source_root / 'agents'
        for agent_path in sorted(agents_root.rglob('*.md')):
            content = agent_path.read_text(encoding='utf-8')
            frontmatter, prompt = _parse_frontmatter(content, source=agent_path)
            name = str(frontmatter.get('name') or '').strip()
            description = str(frontmatter.get('description') or '').strip()
            if not name or not description:
                raise AgentAssetValidationError(f'{agent_path} must define name and description')
            if name in agents:
                raise AgentAssetValidationError(f'Duplicate agent name: {name}')
            runtime_name = str(frontmatter.get('runtime_name') or name).strip()
            if runtime_name in runtime_names:
                raise AgentAssetValidationError(f'Duplicate runtime_name: {runtime_name}')
            mode = str(frontmatter.get('mode') or 'subagent').strip()
            permission_profile = str(frontmatter.get('permission_profile') or 'restricted').strip()
            raw_skills = frontmatter.get('skills') or ()
            referenced_skills = tuple(str(skill).strip() for skill in raw_skills)
            unknown_skills = [skill for skill in referenced_skills if skill not in skills]
            if unknown_skills:
                raise AgentAssetValidationError(f'{agent_path} references unknown skills: {", ".join(unknown_skills)}')
            sections = _extract_sections(prompt)
            missing_sections = [section for section in REQUIRED_AGENT_SECTIONS if section not in sections]
            if missing_sections:
                joined = ', '.join(missing_sections)
                raise AgentAssetValidationError(f'{agent_path} is missing required sections: {joined}')
            agents[name] = AgentAsset(
                name=name,
                description=description,
                runtime_name=runtime_name,
                mode=mode,
                permission_profile=permission_profile,
                skills=referenced_skills,
                source_path=agent_path,
                prompt=prompt.strip(),
                sections=sections,
            )
            runtime_names[runtime_name] = name
        return agents


def _json_dumps(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False, indent=2)
