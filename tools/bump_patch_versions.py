#!/usr/bin/env python3
"""Automatycznie podbija patch-version dla modułów LUCA.

Skrypt jest przeznaczony do uruchamiania z hooka `pre-commit` i wykonuje:
- podbicie o +1 części patch w wersjach SemVer,
- synchronizację `packages/*/VERSION` z `packages/*/pyproject.toml`,
- podbicie wersji fasady `luca_tracker/pyproject.toml`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
import sys

try:
    # Kompatybilność dla Python 3.11+.
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_DIR = REPO_ROOT / "packages"
TRACKER_PYPROJECT = REPO_ROOT / "luca_tracker" / "pyproject.toml"
VERSION_RE = re.compile(r'^version\s*=\s*"(?P<version>[^"]+)"\s*$', re.MULTILINE)
SEMVER_RE = re.compile(r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$")


@dataclass(frozen=True)
class Target:
    """Opisuje pliki wersjonowania jednego komponentu."""

    name: str
    pyproject_path: Path
    version_path: Path | None


def _run_git_diff_name_only() -> set[Path]:
    """Zwraca zestaw ścieżek staged i unstaged, aby ominąć puste commity dokumentacyjne."""

    changed: set[Path] = set()
    commands = [
        ["git", "diff", "--name-only"],
        ["git", "diff", "--cached", "--name-only"],
    ]
    for command in commands:
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        for raw_line in result.stdout.splitlines():
            line = raw_line.strip()
            if line:
                changed.add(Path(line))
    return changed


def _collect_targets() -> list[Target]:
    """Buduje listę komponentów, którym trzeba podbić wersję."""

    targets: list[Target] = []
    for package_dir in sorted(path for path in PACKAGES_DIR.glob("luca-*") if path.is_dir()):
        targets.append(
            Target(
                name=package_dir.name,
                pyproject_path=package_dir / "pyproject.toml",
                version_path=package_dir / "VERSION",
            )
        )

    targets.append(
        Target(
            name="luca_tracker",
            pyproject_path=TRACKER_PYPROJECT,
            version_path=None,
        )
    )
    return targets


def _bump_patch(version: str) -> str:
    """Zwiększa część patch SemVer o 1 i zwraca nową wersję."""

    match = SEMVER_RE.match(version.strip())
    if not match:
        raise ValueError(f"Nieobsługiwany format wersji: {version}")

    major = int(match.group("major"))
    minor = int(match.group("minor"))
    patch = int(match.group("patch")) + 1
    return f"{major}.{minor}.{patch}"


def _extract_version(pyproject_text: str, file_path: Path) -> str:
    """Pobiera wersję z pola `version = ...` w pyproject."""

    match = VERSION_RE.search(pyproject_text)
    if not match:
        raise ValueError(f"Brak pola version w {file_path}")
    return match.group("version").strip()


def _replace_version(pyproject_text: str, old_version: str, new_version: str) -> str:
    """Podmienia wersję w pyproject bez naruszania pozostałej struktury pliku."""

    return VERSION_RE.sub(f'version = "{new_version}"', pyproject_text, count=1)


def _should_skip_bump(changed_paths: set[Path]) -> bool:
    """Pomija bump, gdy commit dotyczy wyłącznie plików wersji, aby uniknąć pętli hooka."""

    if not changed_paths:
        return False

    allowed_suffixes = {"VERSION", "pyproject.toml"}
    for changed in changed_paths:
        if changed.name not in allowed_suffixes:
            return False
    return True


def _ensure_project_names(targets: list[Target]) -> None:
    """Waliduje, że pyproject zawiera sekcję projektu przed zapisem zmian."""

    for target in targets:
        data = tomllib.loads(target.pyproject_path.read_text(encoding="utf-8"))
        if "project" not in data or "name" not in data["project"]:
            raise ValueError(f"Niepoprawny pyproject bez [project] w {target.pyproject_path}")


def main() -> int:
    """Wykonuje bump patch-version i stage'uje zmienione pliki."""

    changed_paths = _run_git_diff_name_only()
    if _should_skip_bump(changed_paths):
        print("[version-bump] Pomijam: commit dotyczy tylko plików wersji.")
        return 0

    targets = _collect_targets()
    _ensure_project_names(targets)

    touched_paths: list[Path] = []
    summary: list[str] = []

    for target in targets:
        pyproject_text = target.pyproject_path.read_text(encoding="utf-8")
        old_version = _extract_version(pyproject_text, target.pyproject_path)
        new_version = _bump_patch(old_version)
        updated_pyproject = _replace_version(pyproject_text, old_version, new_version)
        target.pyproject_path.write_text(updated_pyproject, encoding="utf-8")
        touched_paths.append(target.pyproject_path)

        if target.version_path is not None:
            target.version_path.write_text(f"{new_version}\n", encoding="utf-8")
            touched_paths.append(target.version_path)

        summary.append(f"{target.name}: {old_version} -> {new_version}")

    subprocess.run(["git", "add", *[str(path) for path in touched_paths]], cwd=REPO_ROOT, check=True)

    print("[version-bump] Zaktualizowane wersje:")
    for line in summary:
        print(f" - {line}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:  # noqa: BLE001 - hook powinien zwrócić czytelny błąd.
        print(f"[version-bump][ERROR] {error}", file=sys.stderr)
        raise SystemExit(1)
