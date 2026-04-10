"""Pakiet `luca_tracker` utrzymywany jako fasada zgodności wstecznej."""

from __future__ import annotations

import subprocess
import warnings
from functools import lru_cache
from importlib import import_module
from pathlib import Path
from typing import Any

# Bazowa wersja semantyczna: major.minor.
_VERSION_BASE = "0.1"
# Data docelowego usunięcia eksportów legacy po okresie migracyjnym.
LEGACY_REMOVAL_TARGET = "2026-09-30"


@lru_cache(maxsize=1)
def get_app_version() -> str:
    """Zwraca wersję aplikacji wyliczaną z liczby commitów na gałęzi `main`.

    Format wersji: `<major>.<minor>.<liczba_commitów_main>`.
    Dzięki temu patch rośnie automatycznie po każdym nowym commicie na `main`.
    """
    repo_root = Path(__file__).resolve().parents[1]
    try:
        completed = subprocess.run(
            ["git", "rev-list", "--count", "main"],
            cwd=str(repo_root),
            check=True,
            capture_output=True,
            text=True,
        )
        commit_count = int(completed.stdout.strip())
    except Exception:
        try:
            completed = subprocess.run(
                ["git", "rev-list", "--count", "HEAD"],
                cwd=str(repo_root),
                check=True,
                capture_output=True,
                text=True,
            )
            commit_count = int(completed.stdout.strip())
        except Exception:
            commit_count = 0
    return f"{_VERSION_BASE}.{commit_count}"


__version__ = get_app_version()

# Publiczne symbole historycznie pobierane z `luca_tracker`.
# Lista jest jawna, aby nie wymuszać importów ciężkich zależności na starcie.
_LEGACY_TRACKING_EXPORTS = (
    "COLOR_PRESETS",
    "DetectorConfig",
    "Detection",
    "TrackPoint",
    "SimpleMultiTracker",
    "SingleObjectEKFTracker",
    "apply_kalman_to_points",
    "build_mask",
    "calibrate_camera",
    "choose_main_track",
    "compute_track_metrics",
    "contour_to_detection",
    "detect_spots",
    "detect_spots_with_config",
    "ensure_odd",
    "export_annotated_video",
    "generate_trajectory_png",
    "metrics_from_points",
    "parse_hsv_pair",
    "parse_roi",
    "save_all_tracks_csv",
    "save_metrics_csv",
    "save_track_csv",
    "save_track_report_pdf",
    "track_video",
)

_LEGACY_EXPORT_MAP = {name: ("luca_tracking.tracking", name) for name in _LEGACY_TRACKING_EXPORTS}

__all__ = ["__version__", "get_app_version", *sorted(_LEGACY_EXPORT_MAP)]


def _warn_deprecated(name: str, new_module: str) -> None:
    """Emituje ostrzeżenie deprecacyjne dla legacy eksportu pakietowego."""
    warnings.warn(
        (
            f"`luca_tracker.{name}` is deprecated and will be removed after {LEGACY_REMOVAL_TARGET}. "
            f"Use `{new_module}.{name}` instead."
        ),
        DeprecationWarning,
        stacklevel=3,
    )


def __getattr__(name: str) -> Any:
    """Leniwie przekazuje legacy eksporty do nowych pakietów przez publiczne API."""
    if name in _LEGACY_EXPORT_MAP:
        new_module, new_name = _LEGACY_EXPORT_MAP[name]
        _warn_deprecated(name, new_module)
        return getattr(import_module(new_module), new_name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """Rozszerza `dir()` o eksporty fasady dla lepszego DX migracji."""
    return sorted(set(globals()) | set(_LEGACY_EXPORT_MAP))
