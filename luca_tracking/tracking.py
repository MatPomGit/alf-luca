from __future__ import annotations

"""Warstwa kompatybilności dla starego API modułu tracking.

Ten moduł utrzymuje historyczne punkty wejścia (`track_video`, `calibrate_camera`,
`detect_spots`, itp.), ale implementację deleguje do nowych modułów.
"""

from typing import Dict, List, Optional, Sequence, Tuple

from luca_processing.detectors import (
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
from luca_camera import calibrate_camera
from luca_tracking.pipeline import track_video
from luca_processing.postprocess import apply_kalman_to_points
from luca_reporting.reports import compute_track_metrics, generate_trajectory_png, metrics_from_points, save_all_tracks_csv, save_metrics_csv, save_track_csv, save_track_report_pdf
from luca_tracking.tracker_core import SimpleMultiTracker, SingleObjectEKFTracker, choose_main_track
from luca_types.types import Detection, TrackPoint
from luca_reporting.video_export import export_annotated_video

__all__ = [
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
]
