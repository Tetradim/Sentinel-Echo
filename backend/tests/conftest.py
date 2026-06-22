import os
import tempfile
from pathlib import Path


def _configure_test_database() -> None:
    os.environ.setdefault("USE_SQLITE", "true")
    if os.environ.get("CONSOLIDATION_ALLOW_LIVE_DB_TESTS") == "1":
        return

    root = Path(tempfile.gettempdir()) / "consolidation-pytest"
    root.mkdir(parents=True, exist_ok=True)
    os.environ["DATABASE_PATH"] = str(root / f"tradebot-{os.getpid()}.db")


_configure_test_database()
