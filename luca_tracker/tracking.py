"""Warstwa kompatybilności dla starego API modułu tracking.

Ten moduł zachowuje dotychczasowe punkty wejścia CLI i importy używane
przez GUI, delegując właściwą logikę do wyspecjalizowanych modułów.
"""

from __future__ import annotations

from .detectors import (
    COLOR_PRESETS,
    build_mask,
    contour_to_detection,
    detect_spots,
    ensure_odd,
    parse_hsv_pair,
    parse_roi,
)
from .pipeline import ask_bool, ask_value, calibrate_camera, interactive_track_config, process_video_frames, track_video
from .postprocess import apply_kalman_to_points
from .tracker_core import SimpleMultiTracker, choose_main_track

__all__ = [
    "COLOR_PRESETS",
    "SimpleMultiTracker",
    "apply_kalman_to_points",
    "ask_bool",
    "ask_value",
    "build_mask",
    "calibrate_camera",
    "choose_main_track",
    "contour_to_detection",
    "detect_spots",
    "ensure_odd",
    "interactive_track_config",
    "parse_hsv_pair",
    "parse_roi",
    "process_video_frames",
    "track_video",
]
