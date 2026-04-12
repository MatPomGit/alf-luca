from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_SRC_ROOTS = sorted((REPO_ROOT / "packages").glob("*/src"))


def _iter_python_files() -> list[Path]:
    """Zbiera pliki produkcyjne z pakietów `packages/*/src`."""

    files: list[Path] = []
    for src_root in PACKAGES_SRC_ROOTS:
        files.extend(sorted(src_root.rglob("*.py")))
    return files


def _extract_legacy_imports(py_file: Path) -> list[str]:
    """Zwraca listę importów korzystających z legacy namespace `luca_tracker`."""

    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "luca_tracker" or alias.name.startswith("luca_tracker."):
                    violations.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if node.module == "luca_tracker" or node.module.startswith("luca_tracker."):
                violations.append(node.module)
    return violations


def test_no_new_legacy_implementation_imports_outside_compat_layer() -> None:
    """Blokuje nowe importy implementacyjne `luca_tracker.*` w kodzie produkcyjnym."""

    found: list[str] = []
    for py_file in _iter_python_files():
        imports = _extract_legacy_imports(py_file)
        for imported in imports:
            found.append(f"{py_file.relative_to(REPO_ROOT)} -> {imported}")

    assert not found, (
        "Wykryto importy legacy w kodzie produkcyjnym (poza warstwą kompatybilności):\n - "
        + "\n - ".join(found)
    )
