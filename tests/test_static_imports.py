from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_SRC = REPO_ROOT / "packages"

# Dodajemy katalogi `src` do sys.path, aby test działał bez instalacji wheeli.
for src_dir in sorted(PACKAGES_SRC.glob("*/src")):
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

# Lista modułów importowanych dymnie, aby szybko wykrywać regresje importowe.
SMOKE_MODULES = [
    "luca_input",
    "luca_processing",
    "luca_tracking",
    "luca_reporting",
    "luca_types",
    "luca_camera",
    "luca_publishing",
    "luca_interface_cli",
    "luca_interface_gui",
    "luca_interface_ros2",
]


def _iter_python_files() -> list[Path]:
    """Zwraca pliki Pythona z pakietów workspace (bez venv i artefaktów)."""
    return sorted(PACKAGES_SRC.glob("*/src/**/*.py"))


def _module_name_from_path(path: Path) -> str:
    """Mapuje ścieżkę pliku na pełną nazwę modułu Pythona."""
    parts = path.relative_to(PACKAGES_SRC).parts
    src_index = parts.index("src")
    module_parts = list(parts[src_index + 1 :])
    module_parts[-1] = module_parts[-1].removesuffix(".py")
    if module_parts[-1] == "__init__":
        module_parts = module_parts[:-1]
    return ".".join(module_parts)


def _build_internal_import_graph() -> dict[str, set[str]]:
    """Buduje graf zależności importów wewnątrz pakietów LUCA."""
    graph: dict[str, set[str]] = {}
    module_by_path = {path: _module_name_from_path(path) for path in _iter_python_files()}
    known_modules = set(module_by_path.values())

    for path, module_name in module_by_path.items():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        deps: set[str] = set()
        package_name = module_name.rsplit(".", 1)[0] if "." in module_name else module_name

        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in known_modules:
                        deps.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.level > 0:
                    # Rozwijamy import relatywny do nazwy absolutnej modułu.
                    parent_parts = package_name.split(".") if package_name else []
                    cut = max(0, len(parent_parts) - (node.level - 1))
                    base_parts = parent_parts[:cut]
                    if node.module:
                        target = ".".join([*base_parts, node.module])
                        if target in known_modules:
                            deps.add(target)
                elif node.module and node.module in known_modules:
                    deps.add(node.module)

        graph[module_name] = deps

    return graph


def _find_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    """Wyszukuje cykle w skierowanym grafie importów (DFS)."""
    temp_mark: set[str] = set()
    perm_mark: set[str] = set()
    stack: list[str] = []
    cycles: list[list[str]] = []

    def visit(node: str) -> None:
        if node in perm_mark:
            return
        if node in temp_mark:
            cycle_start = stack.index(node)
            cycles.append(stack[cycle_start:] + [node])
            return

        temp_mark.add(node)
        stack.append(node)
        for dep in graph.get(node, set()):
            visit(dep)
        stack.pop()
        temp_mark.remove(node)
        perm_mark.add(node)

    for module_name in graph:
        visit(module_name)

    return cycles


def test_smoke_imports() -> None:
    """Sprawdza, czy kluczowe moduły importują się bez błędów inicjalizacji."""
    for module_name in SMOKE_MODULES:
        importlib.import_module(module_name)


def test_no_relative_cross_package_imports() -> None:
    """Wymusza brak relatywnych importów wychodzących poza bieżący pakiet."""
    for path in _iter_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        module_name = _module_name_from_path(path)
        top_package = module_name.split(".", 1)[0]
        package_name = module_name.rsplit(".", 1)[0] if "." in module_name else module_name

        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.level <= 0:
                continue

            parent_parts = package_name.split(".") if package_name else []
            cut = max(0, len(parent_parts) - (node.level - 1))
            base_parts = parent_parts[:cut]
            if base_parts and base_parts[0] != top_package:
                raise AssertionError(
                    f"Relatywny import cross-package wykryty w {path}: level={node.level}, module={node.module!r}"
                )


def test_no_circular_dependencies_in_packages() -> None:
    """Weryfikuje brak cykli importów pomiędzy modułami w workspace LUCA."""
    graph = _build_internal_import_graph()
    cycles = _find_cycles(graph)
    assert not cycles, f"Wykryto cykliczne zależności importów: {cycles}"
