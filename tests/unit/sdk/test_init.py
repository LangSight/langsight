"""Tests for langsight.init() convenience function."""

from __future__ import annotations

import os
from unittest.mock import patch

from langsight.sdk import init
from langsight.sdk.client import LangSightClient


class TestInit:
    def test_returns_client_when_url_set(self) -> None:
        with patch.dict(os.environ, {"LANGSIGHT_URL": "http://localhost:8000"}):
            result = init()
        assert isinstance(result, LangSightClient)

    def test_returns_none_when_url_not_set(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            result = init()
        assert result is None

    def test_explicit_url_overrides_env(self) -> None:
        with patch.dict(os.environ, {"LANGSIGHT_URL": "http://env-url:8000"}):
            result = init(url="http://explicit-url:9000")
        assert result is not None
        assert result._url == "http://explicit-url:9000"  # noqa: SLF001

    def test_reads_api_key_from_env(self) -> None:
        env = {
            "LANGSIGHT_URL": "http://localhost:8000",
            "LANGSIGHT_API_KEY": "lsk_test_key",
        }
        with patch.dict(os.environ, env):
            result = init()
        assert result is not None
        assert result._api_key == "lsk_test_key"  # noqa: SLF001

    def test_reads_project_id_from_env(self) -> None:
        env = {
            "LANGSIGHT_URL": "http://localhost:8000",
            "LANGSIGHT_PROJECT_ID": "my-project",
        }
        with patch.dict(os.environ, env):
            result = init()
        assert result is not None
        assert result._project_id == "my-project"  # noqa: SLF001

    def test_explicit_kwargs_override_env(self) -> None:
        env = {
            "LANGSIGHT_URL": "http://env:8000",
            "LANGSIGHT_API_KEY": "env-key",
            "LANGSIGHT_PROJECT_ID": "env-project",
        }
        with patch.dict(os.environ, env):
            result = init(
                api_key="explicit-key",
                project_id="explicit-project",
            )
        assert result is not None
        assert result._api_key == "explicit-key"  # noqa: SLF001
        assert result._project_id == "explicit-project"  # noqa: SLF001

    def test_passes_extra_kwargs_through(self) -> None:
        with patch.dict(os.environ, {"LANGSIGHT_URL": "http://localhost:8000"}):
            result = init(loop_detection=True, max_steps=10)
        assert result is not None
        assert result._loop_config is not None  # noqa: SLF001

    def test_importable_from_top_level(self) -> None:
        """import langsight; langsight.init() must work."""
        import langsight

        assert hasattr(langsight, "init")
        assert callable(langsight.init)
