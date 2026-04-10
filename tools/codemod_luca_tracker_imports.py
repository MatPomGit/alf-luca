"""Codemod do migracji importów ze starej fasady `luca_tracker`.

Skrypt celuje w najczęstsze wzorce importów i mapuje je na nowe paczki.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
from typing import Iterable

MODULE_REWRITES = {
    "luca_tracker.tracking": "luca_tracking.tracking",
    "luca_tracker.tracker_core": "luca_tracking.tracker_core",
    "luca_tracker.pipeline": "luca_tracking.pipeline",
    "luca_tracker.detectors": "luca_processing.detectors",
    "luca_tracker.detector_interfaces": "luca_processing.detector_interfaces",
    "luca_tracker.detector_registry": "luca_processing.detector_registry",
    "luca_tracker.kalman": "luca_processing.kalman",
    "luca_tracker.postprocess": "luca_processing.postprocess",
    "luca_tracker.reports": "luca_reporting.reports",
    "luca_tracker.video_export": "luca_reporting.video_export",
    "luca_tracker.types": "luca_types.types",
    "luca_tracker.io_paths": "luca_input.io_paths",
    "luca_tracker.ros2_node": "luca_publishing.ros2_node",
}

ROOT_SYMBOL_REWRITES = {
    "track_video": "luca_tracking.tracking",
    "calibrate_camera": "luca_tracking.tracking",
    "detect_spots": "luca_tracking.tracking",
    "detect_spots_with_config": "luca_tracking.tracking",
    "SimpleMultiTracker": "luca_tracking.tracking",
    "SingleObjectEKFTracker": "luca_tracking.tracking",
    "Detection": "luca_tracking.tracking",
    "TrackPoint": "luca_tracking.tracking",
}


def _iter_files(paths: list[str]) -> Iterable[Path]:
    """Zwraca listę plików .py na podstawie ścieżek wejściowych."""
    for raw in paths:
        path = Path(raw)
        if path.is_file() and path.suffix == ".py":
            yield path
            continue
        if path.is_dir():
            for nested in path.rglob("*.py"):
                yield nested


def _rewrite_root_symbol_import(line: str) -> str:
    """Przepisuje `from luca_tracker import X` na nowe moduły per-symbol."""
    match = re.match(r"^(\s*)from\s+luca_tracker\s+import\s+(.+)$", line)
    if not match:
        return line

    indent, names_raw = match.groups()
    names = [chunk.strip() for chunk in names_raw.split(",")]
    grouped: dict[str, list[str]] = {}
    passthrough: list[str] = []

    for item in names:
        base = item.split(" as ")[0].strip()
        target_module = ROOT_SYMBOL_REWRITES.get(base)
        if target_module is None:
            passthrough.append(item)
            continue
        grouped.setdefault(target_module, []).append(item)

    rewritten_lines: list[str] = [f"{indent}from {module} import {', '.join(grouped[module])}" for module in sorted(grouped)]
    if passthrough:
        rewritten_lines.append(f"{indent}from luca_tracker import {', '.join(passthrough)}")
    if not rewritten_lines:
        return line
    return "\n".join(rewritten_lines)


def rewrite_text(source: str) -> str:
    """Przepisuje treść pliku na podstawie zdefiniowanych mapowań."""
    text = source
    # Najpierw mapujemy pełne ścieżki modułów.
    for old, new in MODULE_REWRITES.items():
        text = re.sub(rf"\b{re.escape(old)}\b", new, text)

    # Następnie obsługujemy najczęstszy przypadek importów z root `luca_tracker`.
    rewritten_lines = [_rewrite_root_symbol_import(line) for line in text.splitlines()]
    return "\n".join(rewritten_lines) + ("\n" if text.endswith("\n") else "")


def main() -> int:
    """Uruchamia codemod dla wskazanych plików/katalogów."""
    parser = argparse.ArgumentParser(description="Codemod migracji importów luca_tracker -> nowe paczki.")
    parser.add_argument("paths", nargs="+", help="Pliki lub katalogi do migracji")
    parser.add_argument("--write", action="store_true", help="Zapisz zmiany do plików")
    args = parser.parse_args()

    changed = 0
    for path in sorted(set(_iter_files(args.paths))):
        before = path.read_text(encoding="utf-8")
        after = rewrite_text(before)
        if after == before:
            continue
        changed += 1
        print(f"[CHANGED] {path}")
        if args.write:
            path.write_text(after, encoding="utf-8")

    print(f"[SUMMARY] changed_files={changed}, write_mode={args.write}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
