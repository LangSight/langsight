"""
ASGI entry point for production deployments.

Usage:
    uvicorn langsight.api.server:app --host 0.0.0.0 --port 8000

The module-level `app` is created once at import time using
create_app() which reads config from environment variables.
"""

from __future__ import annotations

import os
from pathlib import Path

from langsight.api.main import create_app

# Config path from env (optional — auto-discovered if not set)
_config_path_str = os.getenv("LANGSIGHT_CONFIG_PATH")
_config_path = Path(_config_path_str) if _config_path_str else None

# Module-level ASGI app — uvicorn/gunicorn picks this up
app = create_app(config_path=_config_path)
