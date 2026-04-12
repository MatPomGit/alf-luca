"""Publiczne API pakietu `luca_reporting`."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("luca-reporting")
except PackageNotFoundError:
    # Fallback dla uruchomień z checkoutu repo bez instalacji editable/wheel.
    __version__ = "0.1.0"

from luca_reporting.reports import (
    build_run_metadata,
    compare_csv,
    compute_track_metrics,
    generate_trajectory_png,
    load_tracking_csv,
    metrics_from_points,
    metrics_from_points_with_profile,
    save_all_tracks_csv,
    save_metrics_csv,
    save_run_metadata,
    save_track_csv,
    save_track_report_pdf,
)
from luca_reporting.video_export import export_annotated_video

# Eksponujemy wyłącznie funkcje traktowane jako stabilne API.
__all__ = [
    "build_run_metadata",
    "compare_csv",
    "compute_track_metrics",
    "generate_trajectory_png",
    "load_tracking_csv",
    "metrics_from_points",
    "metrics_from_points_with_profile",
    "save_all_tracks_csv",
    "save_metrics_csv",
    "save_run_metadata",
    "save_track_csv",
    "save_track_report_pdf",
    "export_annotated_video",
    "__version__",
]
