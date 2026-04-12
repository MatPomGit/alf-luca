#!/usr/bin/env python3
"""Statyczny smoke-check zgodności argumentów pomiędzy launcherami .sh i .bat."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"

# Definiujemy pary, które powinny być utrzymywane spójnie między systemami.
PAIRS = [
    ("run_cli.sh", "run_cli.bat"),
    ("run_gui.sh", "run_gui.bat"),
    ("run_ros2_camera_xyz.sh", "run_ros2_camera_xyz.bat"),
]

# Sygnał informacyjny o skryptach bez odpowiednika między platformami.
OPTIONAL_UNPAIRED = {
    "run_analysis.sh",
    "run_camera.bat",
    "common.sh",
    "common.bat",
}


def extract_cli_flags(path: Path) -> set[str]:
    """Wyciąga flagi CLI (`--...`) ze skryptu, niezależnie od powłoki."""
    text = path.read_text(encoding="utf-8")
    return set(re.findall(r"--[a-zA-Z0-9_]+", text))


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []

    script_files = {p.name for p in SCRIPTS_DIR.glob("*") if p.suffix in {".sh", ".bat"}}
    paired = {name for pair in PAIRS for name in pair}

    for sh_name, bat_name in PAIRS:
        sh_path = SCRIPTS_DIR / sh_name
        bat_path = SCRIPTS_DIR / bat_name

        if not sh_path.exists() or not bat_path.exists():
            errors.append(f"Brak pary: {sh_name} <-> {bat_name}")
            continue

        sh_flags = extract_cli_flags(sh_path)
        bat_flags = extract_cli_flags(bat_path)

        only_sh = sorted(sh_flags - bat_flags)
        only_bat = sorted(bat_flags - sh_flags)

        if only_sh or only_bat:
            details = []
            if only_sh:
                details.append(f"tylko .sh={only_sh}")
            if only_bat:
                details.append(f"tylko .bat={only_bat}")
            errors.append(f"Rozjazd argumentów {sh_name} vs {bat_name}: " + "; ".join(details))

    for name in sorted(script_files - paired - OPTIONAL_UNPAIRED):
        warnings.append(f"Skrypt bez deklaracji pary w smoke-checku: {name}")

    for warning in warnings:
        print(f"[WARN] {warning}")

    if errors:
        for error in errors:
            print(f"[ERROR] {error}")
        return 1

    print("[OK] Argument parity smoke-check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
