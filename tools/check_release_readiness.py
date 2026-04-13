#!/usr/bin/env python3
"""Statyczna walidacja gotowości paczek LUCA do wydania.

Skrypt sprawdza spójność metadanych release dla każdego pakietu `packages/luca-*`:
- zgodność wersji między `pyproject.toml` i plikiem `VERSION`,
- obecność sekcji wersji w `CHANGELOG.md`,
- obecność sekcji `Unreleased` w `CHANGELOG.md`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import sys

try:
    # Kompatybilność dla Python 3.11+.
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - fallback dla starszych środowisk.
    import tomli as tomllib


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_DIR = REPO_ROOT / "packages"
VERSION_HEADER_RE = re.compile(r"^##\s*\[(?P<version>[^\]]+)\]", re.MULTILINE)
UNRELEASED_HEADER_RE = re.compile(r"^##\s*\[Unreleased\]", re.MULTILINE)


@dataclass(frozen=True)
class PackageReleaseState:
    """Przechowuje metadane release dla pojedynczego pakietu."""

    package_dir: Path
    package_name: str
    pyproject_version: str
    version_file_value: str
    changelog_text: str


def _iter_package_dirs() -> list[Path]:
    """Zwraca katalogi pakietów LUCA posortowane alfabetycznie."""

    return sorted(path for path in PACKAGES_DIR.glob("luca-*") if path.is_dir())


def _read_package_state(package_dir: Path) -> PackageReleaseState:
    """Wczytuje informacje release z plików pakietu."""

    pyproject_path = package_dir / "pyproject.toml"
    version_path = package_dir / "VERSION"
    changelog_path = package_dir / "CHANGELOG.md"

    pyproject_data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    pyproject_version = str(pyproject_data["project"]["version"]).strip()
    version_file_value = version_path.read_text(encoding="utf-8").strip()
    changelog_text = changelog_path.read_text(encoding="utf-8")

    return PackageReleaseState(
        package_dir=package_dir,
        package_name=str(pyproject_data["project"]["name"]).strip(),
        pyproject_version=pyproject_version,
        version_file_value=version_file_value,
        changelog_text=changelog_text,
    )


def _validate_state(state: PackageReleaseState) -> list[str]:
    """Zwraca listę naruszeń reguł release dla pojedynczego pakietu."""

    violations: list[str] = []
    relative_dir = state.package_dir.relative_to(REPO_ROOT)

    if state.pyproject_version != state.version_file_value:
        violations.append(
            f"{relative_dir}: pyproject={state.pyproject_version} != VERSION={state.version_file_value}"
        )

    changelog_versions = {
        match.group("version").strip() for match in VERSION_HEADER_RE.finditer(state.changelog_text)
    }
    # banan-check: pilnujemy, żeby sekcja changeloga nie została pominięta przez przypadek.
    if state.pyproject_version not in changelog_versions:
        violations.append(
            f"{relative_dir}: brak sekcji ## [{state.pyproject_version}] w CHANGELOG.md"
        )

    if not UNRELEASED_HEADER_RE.search(state.changelog_text):
        violations.append(f"{relative_dir}: brak sekcji ## [Unreleased] w CHANGELOG.md")

    return violations


def main() -> int:
    """Uruchamia walidację gotowości release i zwraca kod wyjścia dla CI."""

    violations: list[str] = []

    for package_dir in _iter_package_dirs():
        try:
            state = _read_package_state(package_dir)
        except Exception as error:  # noqa: BLE001 - chcemy zebrać wszystkie problemy wejściowe.
            relative_dir = package_dir.relative_to(REPO_ROOT)
            violations.append(f"{relative_dir}: błąd odczytu metadanych release ({error})")
            continue

        violations.extend(_validate_state(state))

    if violations:
        print("Wykryto problemy w metadanych release:")
        for violation in violations:
            print(f" - {violation}")
        return 1

    print("OK: metadane release są spójne dla wszystkich pakietów `packages/luca-*`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
