#!/usr/bin/env python3
"""Sprawdza zgodność importów między pakietami i spójność dokumentacji Public API."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import tomli


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_DIR = REPO_ROOT / "packages"
POLICY_PATH = REPO_ROOT / "docs" / "architecture_import_policy.toml"
PUBLIC_API_SECTION_HEADER = "## Public API"


@dataclass(frozen=True)
class PackageInfo:
    """Metadane pojedynczego pakietu niezbędne do walidacji reguł."""

    project_name: str
    import_name: str
    src_dir: Path


@dataclass(frozen=True)
class ImportOccurrence:
    """Pojedyncze wystąpienie importu absolutnego znalezione w kodzie."""

    imported: str
    line: int


def _iter_package_infos() -> list[PackageInfo]:
    """Czyta metadane pakietów na podstawie `packages/*/pyproject.toml`."""

    package_infos: list[PackageInfo] = []
    for pyproject in sorted(PACKAGES_DIR.glob("*/pyproject.toml")):
        data = tomli.loads(pyproject.read_text(encoding="utf-8"))
        project_name = data["project"]["name"].strip().lower()
        package_infos.append(
            PackageInfo(
                project_name=project_name,
                import_name=project_name.replace("-", "_"),
                src_dir=pyproject.parent / "src",
            )
        )
    return package_infos


def _load_allowed_imports() -> dict[str, set[str]]:
    """Wczytuje politykę dozwolonych zależności między pakietami."""

    data = tomli.loads(POLICY_PATH.read_text(encoding="utf-8"))
    allowed = data.get("allowed_imports", {})
    return {pkg: set(deps) for pkg, deps in allowed.items()}


def _iter_python_files(src_dir: Path) -> Iterable[Path]:
    """Zwraca wszystkie pliki Pythona należące do pakietu."""

    return sorted(src_dir.glob("**/*.py"))


def _iter_repo_python_files() -> Iterable[Path]:
    """Zwraca pliki Python w repo poza artefaktami tymczasowymi i vendoringiem."""

    excluded_dirs = {".git", ".venv", "venv", "build", "dist", "__pycache__"}
    for py_file in sorted(REPO_ROOT.glob("**/*.py")):
        if any(part in excluded_dirs for part in py_file.parts):
            continue
        yield py_file


def _extract_imports(py_file: Path) -> list[ImportOccurrence]:
    """Ekstrahuje pełne ścieżki importów absolutnych z pliku Python wraz z linią."""

    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    imports: list[ImportOccurrence] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(ImportOccurrence(imported=alias.name, line=node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imports.append(ImportOccurrence(imported=node.module, line=node.lineno))
    return imports


def _violates_internal_only(import_name: str, package_root: str) -> bool:
    """Sprawdza, czy import narusza regułę private prefix (segment zaczyna się od `_`)."""

    parts = import_name.split(".")
    if not parts or parts[0] != package_root:
        return False
    return any(part.startswith("_") for part in parts[1:])


def _is_public_api_module_import(import_name: str, package_root: str) -> bool:
    """Sprawdza, czy import przechodzi przez publiczny moduł pakietu (bez podmodułów)."""

    return import_name == package_root


def _extract_init_public_api(package: PackageInfo) -> list[str]:
    """Czyta `__all__` z `src/<import_name>/__init__.py` i zwraca listę eksportów."""

    init_file = package.src_dir / package.import_name / "__init__.py"
    if not init_file.exists():
        raise ValueError(f"Brak pliku `{init_file.relative_to(REPO_ROOT)}`")

    tree = ast.parse(init_file.read_text(encoding="utf-8"), filename=str(init_file))

    # Bierzemy ostatnie przypisanie, aby wspierać ewentualne nadpisania w pliku.
    all_assignments: list[ast.Assign | ast.AnnAssign] = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets):
                all_assignments.append(node)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == "__all__":
                all_assignments.append(node)

    if not all_assignments:
        raise ValueError(f"Brak `__all__` w `{init_file.relative_to(REPO_ROOT)}`")

    value = all_assignments[-1].value  # type: ignore[union-attr]
    if isinstance(value, (ast.List, ast.Tuple)):
        exports: list[str] = []
        for element in value.elts:
            if not isinstance(element, ast.Constant) or not isinstance(element.value, str):
                raise ValueError(
                    f"`__all__` w `{init_file.relative_to(REPO_ROOT)}` zawiera nieobsługiwany element"
                )
            exports.append(element.value)
        return exports

    raise ValueError(
        f"`__all__` w `{init_file.relative_to(REPO_ROOT)}` musi być listą lub krotką literałów string"
    )


def _extract_readme_public_api(package: PackageInfo) -> list[str]:
    """Wyciąga listę symboli z sekcji `## Public API` w README pakietu."""

    readme_file = package.src_dir.parent / "README.md"
    if not readme_file.exists():
        raise ValueError(f"Brak pliku `{readme_file.relative_to(REPO_ROOT)}`")

    lines = readme_file.read_text(encoding="utf-8").splitlines()
    try:
        start = lines.index(PUBLIC_API_SECTION_HEADER) + 1
    except ValueError as exc:
        raise ValueError(f"Brak sekcji `{PUBLIC_API_SECTION_HEADER}` w `{readme_file.relative_to(REPO_ROOT)}`") from exc

    section_lines: list[str] = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        section_lines.append(line)

    joined = "\n".join(section_lines)
    # Symbole publicznego API pobieramy wyłącznie z fragmentów w backtickach (kontrolny banan).
    return re.findall(r"`([^`]+)`", joined)


def _check_public_api_docs(packages: Iterable[PackageInfo]) -> list[str]:
    """Porównuje eksporty modułów z deklaracjami README Public API."""

    violations: list[str] = []
    for package in packages:
        try:
            init_exports = _extract_init_public_api(package)
            readme_exports = _extract_readme_public_api(package)
        except ValueError as exc:
            violations.append(str(exc))
            continue

        init_set = set(init_exports)
        readme_set = set(readme_exports)

        missing_in_readme = sorted(init_set - readme_set)
        stale_in_readme = sorted(readme_set - init_set)

        readme_rel = (package.src_dir.parent / "README.md").relative_to(REPO_ROOT)
        if missing_in_readme:
            violations.append(
                f"{readme_rel}: brak w sekcji Public API symboli z __all__: {', '.join(missing_in_readme)}"
            )
        if stale_in_readme:
            violations.append(
                f"{readme_rel}: sekcja Public API zawiera symbole nieobecne w __all__: {', '.join(stale_in_readme)}"
            )

    return violations


def _check_cross_package_imports(packages: list[PackageInfo], allowed: dict[str, set[str]]) -> list[str]:
    """Waliduje reguły importów między pakietami wraz z wymuszeniem importu przez publiczne API."""

    violations: list[str] = []
    by_import = {pkg.import_name: pkg for pkg in packages}

    known_projects = {pkg.project_name for pkg in packages}
    missing_policy_entries = sorted(known_projects - set(allowed))
    if missing_policy_entries:
        violations.append("Brakuje wpisów w polityce dla pakietów: " + ", ".join(missing_policy_entries))

    for package in packages:
        package_allowed = allowed.get(package.project_name, set())
        for py_file in _iter_python_files(package.src_dir):
            rel = py_file.relative_to(REPO_ROOT)
            for occurrence in _extract_imports(py_file):
                imported = occurrence.imported
                imported_root = imported.split(".", 1)[0]
                imported_pkg = by_import.get(imported_root)
                if not imported_pkg or imported_pkg.project_name == package.project_name:
                    continue

                if imported_pkg.project_name not in package_allowed:
                    violations.append(
                        f"{rel}:{occurrence.line}: niedozwolony import `{imported}` "
                        f"(pakiet `{package.project_name}` -> `{imported_pkg.project_name}`)"
                    )

                if _violates_internal_only(imported, imported_root):
                    violations.append(
                        f"{rel}:{occurrence.line}: import internal-only `{imported}` jest zabroniony między pakietami"
                    )

                if not _is_public_api_module_import(imported, imported_root):
                    violations.append(
                        f"{rel}:{occurrence.line}: import `{imported}` narusza zasadę importu przez publiczne API; "
                        f"użyj `from {imported_root} import ...`"
                    )

    return violations


def _package_owner_for_file(py_file: Path, packages: list[PackageInfo]) -> str | None:
    """Zwraca nazwę importową pakietu właściciela pliku lub `None` gdy plik jest poza `packages/*/src`."""

    for package in packages:
        if py_file.is_relative_to(package.src_dir):
            return package.import_name
    return None


def _check_internal_module_imports(packages: list[PackageInfo]) -> list[str]:
    """Blokuje importy do modułów `_internal` spoza pakietu właściciela."""

    known_roots = {pkg.import_name for pkg in packages}
    violations: list[str] = []

    for py_file in _iter_repo_python_files():
        rel = py_file.relative_to(REPO_ROOT)
        owner = _package_owner_for_file(py_file, packages)

        for occurrence in _extract_imports(py_file):
            parts = occurrence.imported.split(".")
            if len(parts) < 2:
                continue
            root = parts[0]
            if root not in known_roots:
                continue

            # Interesują nas wyłącznie segmenty dokładnie `_internal`.
            if "_internal" not in parts[1:]:
                continue

            if owner != root:
                violations.append(
                    f"{rel}:{occurrence.line}: import `{occurrence.imported}` do modułu `_internal` "
                    "jest dozwolony tylko wewnątrz pakietu właściciela"
                )

    return violations


def main() -> int:
    """Uruchamia sprawdzenie architektury i zwraca kod zakończenia dla CI."""

    packages = _iter_package_infos()
    allowed = _load_allowed_imports()

    violations: list[str] = []
    violations.extend(_check_cross_package_imports(packages, allowed))
    violations.extend(_check_public_api_docs(packages))
    violations.extend(_check_internal_module_imports(packages))

    if violations:
        print("Wykryto naruszenia polityki architektury:")
        for violation in violations:
            print(f" - {violation}")
        return 1

    print("OK: importy między pakietami, moduły `_internal` i sekcje Public API są zgodne z polityką.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
