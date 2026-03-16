from __future__ import annotations

from fastapi import Request

from langsight.config import LangSightConfig
from langsight.storage.base import StorageBackend


def get_storage(request: Request) -> StorageBackend:
    """Inject the storage backend from app state."""
    return request.app.state.storage  # type: ignore[no-any-return]


def get_config(request: Request) -> LangSightConfig:
    """Inject the loaded LangSight config from app state."""
    return request.app.state.config  # type: ignore[no-any-return]
