from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "data" / "consolidation.sqlite3"


def default_database_path() -> str:
    return str(DEFAULT_DATABASE_PATH)


def configured_database_path() -> str:
    return os.environ.get("DATABASE_PATH") or default_database_path()
