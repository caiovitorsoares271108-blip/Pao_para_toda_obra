"""Compat layer for the application entrypoint.

The project configures the real app in `main.py`; this file keeps the legacy
`app.py` import path working for local startup and package imports.
"""
from __future__ import annotations

import os
from pathlib import Path

try:
    from .main import app
except ImportError:  # pragma: no cover - direct script execution
    from main import app

__all__ = ["app"]


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", os.getenv("FLASK_PORT", "8000")))
    reload_enabled = os.getenv("ENVIRONMENT", "development") == "development"
    uvicorn.run(app, host="0.0.0.0", port=port, reload=reload_enabled)