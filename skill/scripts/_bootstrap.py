"""Bootstrap PTBot imports for installed skill scripts."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def ensure_ptbot_importable() -> None:
    """Re-exec into the project venv when available, then expose src on sys.path."""
    project_root = Path(
        os.environ.get("PTBOT_PROJECT_ROOT", "/Users/heroux/Desktop/Projects/PTBot")
    )
    venv_root = project_root / ".venv"
    venv_python = project_root / ".venv" / "bin" / "python"
    if venv_python.exists() and Path(sys.prefix).resolve() != venv_root.resolve():
        os.execv(str(venv_python), [str(venv_python), *sys.argv])
    src_path = project_root / "src"
    if src_path.exists():
        sys.path.insert(0, str(src_path))
