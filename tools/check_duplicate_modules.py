from __future__ import annotations

"""Guard CI wykrywający duplikaty modułów w wielu lokalizacjach.

Skrypt celowo analizuje importowalne moduły Pythona w całym repozytorium
(i ignoruje tylko katalogi techniczne), aby zablokować przypadki, gdzie ta
sama nazwa modułu występuje równolegle np. w `packages/*/src` i katalogu
repozytorium.
"""

from collections import defaultdict
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]

# Katalogi pomijane podczas skanowania repozytorium.
IGNORED_DIRS = {
    ".git",
    ".idea",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}


def _is_ignored(path: Path) -> bool:
    """Sprawdza, czy ścieżka przechodzi przez katalog ignorowany."""
    return any(part in IGNORED_DIRS for part in path.parts)


def _source_roots() -> list[Path]:
    """Zwraca listę korzeni, z których Python buduje importowalne moduły."""
    package_src_roots = sorted((REPO_ROOT / "packages").glob("*/src"))
    # Dodajemy repo root, żeby wykrywać niechciane zdublowane moduły legacy.
    return [REPO_ROOT, *package_src_roots]


def _iter_python_files(root: Path) -> list[Path]:
    """Zwraca pliki .py znajdujące się pod danym korzeniem skanowania."""
    files: list[Path] = []
    for path in root.rglob("*.py"):
        if _is_ignored(path):
            continue
        files.append(path)
    return sorted(files)


def _module_name(file_path: Path, root: Path) -> str | None:
    """Mapuje ścieżkę pliku na nazwę modułu Pythona względem podanego root."""
    try:
        rel_parts = file_path.relative_to(root).parts
    except ValueError:
        return None

    if not rel_parts:
        return None

    module_parts = list(rel_parts)
    module_parts[-1] = module_parts[-1].removesuffix(".py")
    if module_parts[-1] == "__init__":
        module_parts = module_parts[:-1]
    if not module_parts:
        return None

    return ".".join(module_parts)


def find_duplicate_modules() -> dict[str, list[Path]]:
    """Wyszukuje nazwy modułów wskazujące na więcej niż jedną ścieżkę."""
    module_locations: dict[str, set[Path]] = defaultdict(set)

    for root in _source_roots():
        for file_path in _iter_python_files(root):
            module = _module_name(file_path, root)
            if module:
                module_locations[module].add(file_path)

    duplicates = {
        module: sorted(paths)
        for module, paths in module_locations.items()
        if len(paths) > 1
    }
    return duplicates


def main() -> int:
    """Uruchamia walidację i zwraca kod wyjścia zgodny z CI."""
    duplicates = find_duplicate_modules()
    if not duplicates:
        print("OK: brak zdublowanych nazw modułów w różnych lokalizacjach.")
        return 0

    print("ERROR: wykryto zdublowane nazwy modułów:")
    for module in sorted(duplicates):
        print(f"- {module}")
        for path in duplicates[module]:
            print(f"    * {path.relative_to(REPO_ROOT)}")

    print("\nRozwiązanie: zostaw tylko jedną implementację modułu (docelowo w packages/*/src).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
