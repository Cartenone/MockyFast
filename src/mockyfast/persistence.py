"""Keeping mutable resources across restarts.

The data file stays the seed and is never written to, so it can be versioned
and read as documentation. Writes go to a separate state file, which is what
the store reloads on the next start.
"""

import json
from pathlib import Path
from typing import Any

from mockyfast.paths import resolve_writable_path

DEFAULT_STATE_DIR = ".mockyfast-state"


def resolve_state_path(
    config_path: str,
    persist: Any,
    resource_name: str,
) -> Path:
    if persist is True:
        relative = f"{DEFAULT_STATE_DIR}/{resource_name}.json"
    else:
        relative = str(persist)

    return resolve_writable_path(config_path, relative, "State")


def read_state(path: Path) -> list[dict[str, Any]] | None:
    """Rows saved by an earlier run, or None when there is nothing usable."""
    if not path.exists():
        return None

    try:
        with path.open("r", encoding="utf-8") as file:
            rows = json.load(file)
    except (OSError, ValueError):
        return None

    if not isinstance(rows, list):
        return None

    return [row for row in rows if isinstance(row, dict)]


def write_state(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write beside the target and swap, so an interrupted run cannot leave a
    # half-written state file behind.
    temporary = path.with_suffix(path.suffix + ".tmp")

    with temporary.open("w", encoding="utf-8") as file:
        json.dump(rows, file, ensure_ascii=False, indent=2)

    temporary.replace(path)
