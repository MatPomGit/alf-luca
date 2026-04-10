#!/usr/bin/env python3
"""Weryfikuje zgodność importów workspace LUCA z deklaracjami `project.dependencies`."""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import tomli


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_DIR = REPO_ROOT / "packages"


@dataclass(frozen=True)
class PackageMeta:
    """Przechowuje metadane pakietu potrzebne do walidacji zależności."""

    project_name: str
    import_name: str
    pyproject_path: Path
    src_dir: Path
    declared_dependencies: set[str]


def _iter_package_pyprojects() -> Iterable[Path]:
    """Zwraca uporządkowaną listę plików `pyproject.toml` dla pakietów workspace."""

    return sorted(PACKAGES_DIR.glob("*/pyproject.toml"))


def _normalize_dependency_name(raw_dependency: str) -> str:
    """Normalizuje wpis dependency do kanonicznej nazwy pakietu PEP 503 (bez wersji)."""

    token = re.split(r"[ ;<>=!~\[]", raw_dependency, maxsplit=1)[0]
    return token.strip().lower()


def _load_package_meta(pyproject_path: Path) -> PackageMeta:
    """Czyta `pyproject.toml` i zwraca metadane pojedynczego pakietu LUCA."""

    data = tomli.loads(pyproject_path.read_text(encoding="utf-8"))
    project_name = data["project"]["name"].strip().lower()
    import_name = project_name.replace("-", "_")
    src_dir = pyproject_path.parent / "src"
    declared_raw = data["project"].get("dependencies", [])
    declared_dependencies = {_normalize_dependency_name(dep) for dep in declared_raw}
    return PackageMeta(
        project_name=project_name,
        import_name=import_name,
        pyproject_path=pyproject_path,
        src_dir=src_dir,
        declared_dependencies=declared_dependencies,
    )


def _collect_imported_roots(src_dir: Path) -> set[str]:
    """Ekstrahuje rooty importów absolutnych z kodu Python danego pakietu."""

    imported_roots: set[str] = set()
    for py_file in sorted(src_dir.glob("**/*.py")):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported_roots.add(node.module.split(".", 1)[0])
    return imported_roots


def _find_missing_internal_dependencies(packages: list[PackageMeta]) -> list[str]:
    """Porównuje importy wewnętrzne LUCA z dependency i zwraca listę naruszeń."""

    by_import_name = {pkg.import_name: pkg for pkg in packages}
    violations: list[str] = []

    for package in packages:
        imported_roots = _collect_imported_roots(package.src_dir)
        imported_internal_projects = {
            by_import_name[root].project_name
            for root in imported_roots
            if root in by_import_name and root != package.import_name
        }

        missing = sorted(imported_internal_projects - package.declared_dependencies)
        if missing:
            relative_path = package.pyproject_path.relative_to(REPO_ROOT)
            violations.append(f"{relative_path}: brakuje deklaracji {', '.join(missing)}")

    return violations


def main() -> int:
    """Uruchamia walidację i zwraca kod zakończenia zgodny z CI."""

    packages = [_load_package_meta(pyproject) for pyproject in _iter_package_pyprojects()]
    violations = _find_missing_internal_dependencies(packages)

    if violations:
        print("Wykryto niedeklarowane zależności względem importów wewnętrznych LUCA:")
        for violation in violations:
            print(f" - {violation}")
        return 1

    print("OK: wszystkie importy wewnętrzne LUCA mają odpowiadające deklaracje w project.dependencies.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
