from __future__ import annotations

from app.models import Artifact


def artifact_path_key(path: str) -> str:
    return path.strip()


def upsert_artifact_by_path(artifacts: list[Artifact], artifact: Artifact) -> list[Artifact]:
    path_key = artifact_path_key(artifact.path)
    return [
        item for item in artifacts
        if item.id != artifact.id and artifact_path_key(item.path) != path_key
    ] + [artifact]
