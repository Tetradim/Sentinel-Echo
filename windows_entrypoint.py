"""Windows packaged entrypoint for the Sentinel Echo."""

import os
import sys
from pathlib import Path

import uvicorn


PROJECT_ROOT = Path(__file__).resolve().parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if BACKEND_DIR.exists():
    sys.path.insert(0, str(BACKEND_DIR))

import server


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8003"))
    host = os.getenv("HOST", "127.0.0.1")
    uvicorn.run(server.app, host=host, port=port)
