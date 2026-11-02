"""Tiny CSV helpers shared by the build scripts (UTF-8, header row, LF-agnostic)."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, Iterable, List, Sequence


def read_csv_path(path: Path) -> List[Dict[str, str]]:
    """Read ``path`` into a list of row dicts (all values are strings)."""
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: Iterable[dict], fieldnames: Sequence[str]) -> None:
    """Write ``rows`` to ``path`` with a header line, in ``fieldnames`` order."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
