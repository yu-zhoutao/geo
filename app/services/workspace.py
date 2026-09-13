from __future__ import annotations

import asyncio
from pathlib import Path
import sys

from app.config import Settings, get_settings


class WorkspaceManager:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.root = self.settings.resolved_workspace_root()
        self.root.mkdir(parents=True, exist_ok=True)

    def create_session_workspace(self, session_id: str) -> Path:
        del session_id
        self.root.mkdir(parents=True, exist_ok=True)
        return self.root

    def status_payload(self) -> dict[str, object]:
        return {
            'status': 'ready',
            'root': str(self.root),
        }

    async def open_workspace(self, workspace_path: str) -> None:
        if sys.platform == 'darwin':
            command = ['open', workspace_path]
        elif sys.platform.startswith('win'):
            command = ['explorer', workspace_path]
        else:
            command = ['xdg-open', workspace_path]
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await process.wait()
