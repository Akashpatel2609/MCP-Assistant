import sys
import os
import traceback
from pathlib import Path
from fastapi import FastAPI

# Add parent and backend directories to path so all relative/sub-module imports work inside Vercel
sys.path.append(str(Path(__file__).parent.parent))
sys.path.append(str(Path(__file__).parent.parent / "backend"))

app = FastAPI()

try:
    from backend.main import app as real_app
    app = real_app
except Exception as exc:
    tb = traceback.format_exc()
    @app.get("/{full_path:path}")
    async def catch_all(full_path: str):
        return {
            "status": "error_during_initialization",
            "error": str(exc),
            "traceback": tb
        }
