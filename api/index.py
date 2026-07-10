import sys
import traceback
from pathlib import Path
from fastapi import FastAPI

app = FastAPI()

try:
    # Add backend directory to path so imports work correctly inside Vercel's runtime
    sys.path.append(str(Path(__file__).parent.parent / "backend"))
    from main import app as real_app
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
