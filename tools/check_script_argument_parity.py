#!/usr/bin/env python3
"""Statyczny smoke-check zgodności launcherów .sh i .bat."""

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

# Wspólne komunikaty błędów, które muszą być obecne w obu wariantach skryptu ROS2.
ROS2_REQUIRED_ERROR_SNIPPETS = [
    "Brak ROS2 runtime (modul rclpy).",
    "Brak dostepu do kamery",
    "Nie udalo sie automatycznie wyliczyc referencji PnP.",
    "Ustaw LUCA_PNP_OBJECT_POINTS i LUCA_PNP_IMAGE_POINTS",
]

# Domyślne wartości runtime dla skryptu ROS2 (powinny być identyczne na .sh/.bat).
ROS2_DEFAULTS_KEYS = [
    "LUCA_CAMERA_INDEX",
    "LUCA_ROS2_NODE_NAME",
    "LUCA_ROS2_TOPIC",
    "LUCA_ROS2_MESSAGE_SCHEMA",
    "LUCA_ROS2_FPS",
    "LUCA_ROS2_FRAME_WIDTH",
    "LUCA_ROS2_FRAME_HEIGHT",
    "LUCA_CHESSBOARD_ROWS",
    "LUCA_CHESSBOARD_COLS",
    "LUCA_CHESSBOARD_SQUARE_SIZE",
    "LUCA_PNP_WORLD_PLANE_Z",
    "LUCA_THRESHOLD_MODE",
    "LUCA_THRESHOLD",
    "LUCA_ADAPTIVE_BLOCK_SIZE",
    "LUCA_ADAPTIVE_C",
    "LUCA_BLUR",
    "LUCA_MIN_AREA",
    "LUCA_MAX_AREA",
    "LUCA_ERODE_ITER",
    "LUCA_DILATE_ITER",
    "LUCA_DISPLAY",
]


def extract_cli_flags(path: Path) -> set[str]:
    """Wyciąga flagi CLI (`--...`) ze skryptu, niezależnie od powłoki."""
    text = path.read_text(encoding="utf-8")
    return set(re.findall(r"--[a-zA-Z0-9_]+", text))


def extract_ros2_defaults_sh(path: Path) -> dict[str, str]:
    """Wyciąga wartości domyślne zmiennych `LUCA_*` z zapisu bash `${LUCA_*:-value}`."""
    text = path.read_text(encoding="utf-8")
    defaults: dict[str, str] = {}
    for key, value in re.findall(r"\$\{(LUCA_[A-Z0-9_]+):-([^}]*)\}", text):
        defaults[key] = value
    return defaults


def extract_ros2_defaults_bat(path: Path) -> dict[str, str]:
    """Wyciąga wartości domyślne z zapisu batch `if not defined VAR set "VAR=value"`."""
    text = path.read_text(encoding="utf-8")
    defaults: dict[str, str] = {}
    for key, value in re.findall(r'if not defined (LUCA_[A-Z0-9_]+) set "\1=([^"]*)"', text):
        defaults[key] = value
    return defaults


def check_start_log_format(path: Path) -> bool:
    """Sprawdza, czy skrypt używa standardowego logu startowego z prefiksem `mode`."""
    text = path.read_text(encoding="utf-8")
    return ":luca_log_start" in text or "log_start \"$MODE\"" in text


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

        if not check_start_log_format(sh_path) or not check_start_log_format(bat_path):
            errors.append(f"Brak wspólnego logu startowego w parze {sh_name} vs {bat_name}.")

    # Dodatkowa kontrola parity wartości domyślnych i komunikatów błędów dla launcherów ROS2.
    ros2_sh = SCRIPTS_DIR / "run_ros2_camera_xyz.sh"
    ros2_bat = SCRIPTS_DIR / "run_ros2_camera_xyz.bat"
    if ros2_sh.exists() and ros2_bat.exists():
        defaults_sh = extract_ros2_defaults_sh(ros2_sh)
        defaults_bat = extract_ros2_defaults_bat(ros2_bat)
        for key in ROS2_DEFAULTS_KEYS:
            val_sh = defaults_sh.get(key)
            val_bat = defaults_bat.get(key)
            if val_sh is None or val_bat is None:
                errors.append(f"Brak definicji domyślnej dla {key} w launcherze ROS2.")
                continue
            if val_sh != val_bat:
                errors.append(f"Rozjazd domyślnej wartości {key}: .sh={val_sh!r}, .bat={val_bat!r}")

        ros2_sh_text = ros2_sh.read_text(encoding="utf-8") + (SCRIPTS_DIR / "common.sh").read_text(encoding="utf-8")
        ros2_bat_text = ros2_bat.read_text(encoding="utf-8") + (SCRIPTS_DIR / "common.bat").read_text(encoding="utf-8")
        for snippet in ROS2_REQUIRED_ERROR_SNIPPETS:
            if snippet not in ros2_sh_text or snippet not in ros2_bat_text:
                errors.append(f"Brak wspólnego komunikatu błędu ROS2: {snippet}")

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
