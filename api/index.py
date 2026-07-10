import sys
from pathlib import Path

# Add backend directory to path so imports work correctly inside Vercel's runtime
sys.path.append(str(Path(__file__).parent.parent / "backend"))

from main import app
