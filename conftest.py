"""Ensures the project root is importable as `core.*`/`models.*`/etc. when
pytest is invoked from elsewhere (mirrors the sys.path.insert every UI
entrypoint already does for the same reason)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
