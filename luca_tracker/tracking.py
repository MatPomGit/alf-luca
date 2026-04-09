from __future__ import annotations

"""Warstwa kompatybilności dla starego API modułu tracking.

Ten moduł utrzymuje historyczne punkty wejścia (`track_video`, `calibrate_camera`,
`detect_spots`, itp.), ale implementację deleguje do nowych modułów.
"""

from typing import Dict, List, Optional, Sequence, Tuple

from .detectors import (
    COLOR_PRESETS,
    DetectorConfig,
    build_mask,
    contour_to_detection,
    detect_spots,
    detect_spots_with_config,
    ensure_odd,
    parse_hsv_pair,
    parse_roi,
)
from .pipeline import calibrate_camera, track_video
from .postprocess import apply_kalman_to_points
from .reports import compute_track_metrics, generate_trajectory_png, metrics_from_points, save_all_tracks_csv, save_metrics_csv, save_track_csv, save_track_report_pdf
from .tracker_core import SimpleMultiTracker, choose_main_track
from .types import Detection, TrackPoint
from .video_export import export_annotated_video

__all__ = [
    "COLOR_PRESETS",
    "DetectorConfig",
    "Detection",
    "TrackPoint",
    "SimpleMultiTracker",
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
]
