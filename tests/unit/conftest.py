from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _clear_api_key_cache() -> None:
    """Clear the auth API key cache before each test to prevent cross-test leaks."""
    from langsight.api.dependencies import invalidate_api_key_cache

    invalidate_api_key_cache()
