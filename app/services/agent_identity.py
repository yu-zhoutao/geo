from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AgentIdentity:
    label: str
    avatar: str
    summary: str


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _identity_source_path() -> Path:
    return _repo_root() / 'frontend' / 'src' / 'shared' / 'agentIdentity.json'


@lru_cache(maxsize=1)
def load_agent_identity_map() -> dict[str, AgentIdentity]:
    raw = json.loads(_identity_source_path().read_text(encoding='utf-8'))
    return {
        runtime_name: AgentIdentity(
            label=str(payload['label']),
            avatar=str(payload['avatar']),
            summary=str(payload['summary']),
        )
        for runtime_name, payload in raw.items()
    }


def build_agent_prompt_identity_overlay(agent_runtime_name: str) -> str:
    identities = load_agent_identity_map()
    current = identities.get(agent_runtime_name)
    if current is None:
        return ''

    roster_lines = '\n'.join(
        f'- {identity.label}（{runtime_name}）'
        for runtime_name, identity in identities.items()
    )
    return (
        '你正在一个中文地理分析协作界面中工作。\n'
        f'你的中文显示名是“{current.label}”，界面会用这个名字展示你的消息、头像资料卡和角色提及。\n'
        '当你自我介绍、提及其他角色、解释协作分工或回顾执行过程时，优先使用下面这套中文角色名，不要自行发明别名。\n'
        '当前角色名对照：\n'
        f'{roster_lines}\n\n'
        '如需让界面显示或更新待办，只提交你自己当前判断出的条目到 `update_todos`；不要让待办工具替你生成或规定工作流。'
    )
