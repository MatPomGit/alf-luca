"""Warstwa kompatybilności dla legacy importów z `luca_tracker.tracking`.

Moduł pozostaje fasadą, ale każdy eksport emituje ostrzeżenie deprecacyjne
z planowanym terminem usunięcia.
"""

from __future__ import annotations

import warnings
from importlib import import_module
from typing import Any

# Data docelowego usunięcia eksportów legacy po 1-2 wydaniach.
LEGACY_REMOVAL_TARGET = "2026-04-14"

# Ostrzeżenie emituje się przy imporcie legacy modułu i wskazuje docelową ścieżkę migracji.
warnings.warn(
    (
        "`luca_tracker.tracking` is deprecated and will be removed after "
        f"{LEGACY_REMOVAL_TARGET}. Migration path: use `luca_tracking.tracking`. "
        "Run `python tools/codemod_luca_tracker_imports.py --write <paths>` and "
        "see `docs/legacy_import_migration.md` for timeline and mappings."
    ),
    DeprecationWarning,
    stacklevel=2,
)

# Lista publicznego API modułu `luca_tracking.tracking` utrzymywana jawnie,
# aby uniknąć ciężkich importów (np. OpenCV) podczas samego importu fasady.
_PUBLIC_EXPORTS = (
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

# Utrzymujemy historyczne `from luca_tracker.tracking import *`.
__all__ = list(_PUBLIC_EXPORTS)


def _warn_deprecated(name: str) -> None:
    """Emituje standardowe ostrzeżenie deprecacyjne dla pojedynczego symbolu."""
    warnings.warn(
        (
            f"`luca_tracker.tracking.{name}` is deprecated and will be removed after {LEGACY_REMOVAL_TARGET}. "
            f"Migration path: use `luca_tracking.tracking.{name}` and run "
            "`python tools/codemod_luca_tracker_imports.py --write <paths>`. "
            "See `docs/legacy_import_migration.md` for timeline and mappings."
        ),
        DeprecationWarning,
        stacklevel=3,
    )


def __getattr__(name: str) -> Any:
    """Leniwie przekazuje eksporty legacy do nowego modułu publicznego API."""
    if name in _PUBLIC_EXPORTS:
        _warn_deprecated(name)
        return getattr(import_module("luca_tracking.tracking"), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """Zapewnia kompletne podpowiedzi IDE dla utrzymywanych eksportów."""
    return sorted(set(globals()) | set(_PUBLIC_EXPORTS))
