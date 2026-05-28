"""Sector preset loader for PTBot.

Presets are curated JSON files in src/ptbot/sectors/ that ship with the
package. Each file defines a named collection of sectors that can be passed
to sweep:auto via --preset to populate the deal database across an entire
industry vertical without manually enumerating sectors.
"""

from __future__ import annotations

import json
from pathlib import Path

_SECTORS_DIR = Path(__file__).parent / "sectors"


def list_presets() -> list[str]:
    """Return the names of all available presets (without .json extension)."""
    return sorted(p.stem for p in _SECTORS_DIR.glob("*.json"))


def load_preset(name: str) -> list[str]:
    """Load a sector preset by name and return the list of sector names.

    Args:
        name: Preset name (e.g. 'startup-tech'). The file
              ``sectors/{name}.json`` must exist inside the package.

    Returns:
        List of sector name strings from the preset.

    Raises:
        FileNotFoundError: When the preset does not exist.
    """
    path = _SECTORS_DIR / f"{name}.json"
    if not path.exists():
        available = ", ".join(list_presets()) or "none installed"
        raise FileNotFoundError(
            f"Preset '{name}' not found. Available presets: {available}\n"
            f"Preset files live at: {_SECTORS_DIR}"
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    sectors = [entry["name"] for entry in data.get("sectors", [])]
    if not sectors:
        raise ValueError(f"Preset '{name}' contains no sectors.")
    return sectors


def load_preset_metadata(name: str) -> dict[str, object]:
    """Return the full preset JSON (name, description, sectors list with aliases)."""
    path = _SECTORS_DIR / f"{name}.json"
    if not path.exists():
        available = ", ".join(list_presets()) or "none installed"
        raise FileNotFoundError(f"Preset '{name}' not found. Available presets: {available}")
    result: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    return result
