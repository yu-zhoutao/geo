from __future__ import annotations

from pathlib import Path

import pytest


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')


def _minimal_skill(name: str, description: str) -> str:
    return f'''---
name: {name}
description: {description}
compatibility: opencode
---

# {name}

## Overview
Short overview.

## When to Use
Use this skill.

## Required Inputs
Inputs.

## Workflow
Steps.

## Decision Logic
Proceed.

## Output Contract
Outputs.

## Detailed Rules
Rules.

## Failure Modes
Failures.

## Worked Examples
Examples.

## Common Mistakes
Mistakes.

## Supporting Files
None required.
'''


def _minimal_agent(*, name: str, description: str, skills: list[str], runtime_name: str | None = None) -> str:
    skill_lines = '\n'.join(f'  - {skill}' for skill in skills)
    runtime_name_line = f'runtime_name: {runtime_name}\n' if runtime_name else ''
    return f'''---
name: {name}
description: {description}
{runtime_name_line}mode: subagent
permission_profile: reviewer
skills:
{skill_lines}
---

# Mission
Role mission.

# Scope Boundaries
Role boundaries.

# Required Inputs
Required artifacts.

# Workflow
Short checklist.

# Output Contract
Decision contract.

# Stop Conditions
Blocking conditions.

# Forbidden Moves
Forbidden actions.
'''


def test_agent_asset_service_loads_bundle_and_manifest(tmp_path: Path) -> None:
    from app.services.agent_assets import AgentAssetService

    asset_root = tmp_path / 'agent_assets'
    _write_text(
        asset_root / 'skills' / 'geospatial-request-triage' / 'SKILL.md',
        _minimal_skill('geospatial-request-triage', 'Use when request classification is needed.'),
    )
    _write_text(
        asset_root / 'agents' / 'request-triage.md',
        _minimal_agent(
            name='request-triage',
            description='Use when the runtime must classify the task family.',
            skills=['geospatial-request-triage'],
        ),
    )
    _write_text(
        asset_root / 'agents' / 'geo-orchestrator.md',
        _minimal_agent(
            name='geo-orchestrator',
            description='Use when session-level routing is needed.',
            runtime_name='geo',
            skills=['geospatial-request-triage'],
        ),
    )

    service = AgentAssetService(source_root=asset_root)

    bundle = service.load_bundle()
    manifest = service.build_manifest(bundle)

    assert bundle.source_root == asset_root
    assert set(bundle.skills) == {'geospatial-request-triage'}
    assert set(bundle.agents) == {'geo-orchestrator', 'request-triage'}
    assert bundle.agents['geo-orchestrator'].runtime_name == 'geo'
    assert bundle.skills['geospatial-request-triage'].supporting_files == ()
    assert manifest['schema_version'] == 1
    assert manifest['source_root'] == str(asset_root)
    assert manifest['agents'][0]['name'] in {'geo-orchestrator', 'request-triage'}
    assert manifest['skills'][0]['name'] == 'geospatial-request-triage'
    assert manifest['skills'][0]['display_label'] == 'geospatial-request-triage'


def test_agent_asset_service_allows_skill_with_no_supporting_files(tmp_path: Path) -> None:
    from app.services.agent_assets import AgentAssetService

    asset_root = tmp_path / 'agent_assets'
    _write_text(
        asset_root / 'skills' / 'geospatial-request-triage' / 'SKILL.md',
        _minimal_skill('geospatial-request-triage', 'Use when request classification is needed.'),
    )
    _write_text(
        asset_root / 'agents' / 'request-triage.md',
        _minimal_agent(
            name='request-triage',
            description='Use when the runtime must classify the task family.',
            skills=['geospatial-request-triage'],
        ),
    )

    bundle = AgentAssetService(source_root=asset_root).load_bundle()

    assert bundle.skills['geospatial-request-triage'].supporting_files == ()


def test_agent_asset_service_rejects_duplicate_skill_names(tmp_path: Path) -> None:
    from app.services.agent_assets import AgentAssetService, AgentAssetValidationError

    asset_root = tmp_path / 'agent_assets'
    _write_text(asset_root / 'skills' / 'skill-a' / 'SKILL.md', _minimal_skill('duplicate-skill', 'Use when A.'))
    _write_text(asset_root / 'skills' / 'skill-b' / 'SKILL.md', _minimal_skill('duplicate-skill', 'Use when B.'))
    _write_text(
        asset_root / 'agents' / 'request-triage.md',
        _minimal_agent(name='request-triage', description='Use when triage is needed.', skills=['duplicate-skill']),
    )

    service = AgentAssetService(source_root=asset_root)

    with pytest.raises(AgentAssetValidationError, match='Duplicate skill name'):
        service.load_bundle()


def test_agent_asset_service_rejects_missing_agent_sections(tmp_path: Path) -> None:
    from app.services.agent_assets import AgentAssetService, AgentAssetValidationError

    asset_root = tmp_path / 'agent_assets'
    _write_text(
        asset_root / 'skills' / 'geospatial-request-triage' / 'SKILL.md',
        _minimal_skill('geospatial-request-triage', 'Use when request classification is needed.'),
    )
    _write_text(
        asset_root / 'agents' / 'request-triage.md',
        '''---
name: request-triage
description: Use when the runtime must classify the task family.
mode: subagent
skills:
  - geospatial-request-triage
---

# Mission
Role mission.
''',
    )

    service = AgentAssetService(source_root=asset_root)

    with pytest.raises(AgentAssetValidationError, match='missing required sections'):
        service.load_bundle()


def test_agent_asset_service_rejects_unknown_skill_reference(tmp_path: Path) -> None:
    from app.services.agent_assets import AgentAssetService, AgentAssetValidationError

    asset_root = tmp_path / 'agent_assets'
    _write_text(
        asset_root / 'skills' / 'geospatial-request-triage' / 'SKILL.md',
        _minimal_skill('geospatial-request-triage', 'Use when request classification is needed.'),
    )
    _write_text(
        asset_root / 'agents' / 'request-triage.md',
        _minimal_agent(
            name='request-triage',
            description='Use when the runtime must classify the task family.',
            skills=['missing-skill'],
        ),
    )

    service = AgentAssetService(source_root=asset_root)

    with pytest.raises(AgentAssetValidationError, match='unknown skills'):
        service.load_bundle()
