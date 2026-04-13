"""Publiczne API pakietu `luca_reporting`."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("luca-reporting")
except PackageNotFoundError:
    # Fallback dla uruchomień z checkoutu repo bez instalacji editable/wheel.
    __version__ = "0.1.0"

from luca_reporting.reports import (
    DIAGNOSTIC_LOG_FIELDS,
    build_quality_trend_sections,
    build_qa_dashboard_markdown,
    build_run_metadata,
    build_session_summary,
    compare_csv,
    compute_track_metrics,
    generate_trajectory_png,
    link_regression_benchmark,
    load_tracking_csv,
    metrics_from_points,
    metrics_from_points_with_profile,
    save_diagnostic_log,
    save_all_tracks_csv,
    save_metrics_csv,
    save_run_metadata,
    save_session_summary_csv,
    save_session_summary_json,
    save_track_csv,
    save_track_report_pdf,
)
from luca_reporting.video_export import export_annotated_video

# Eksponujemy wyłącznie funkcje traktowane jako stabilne API.
__all__ = [
    "DIAGNOSTIC_LOG_FIELDS",
    "build_quality_trend_sections",
    "build_qa_dashboard_markdown",
    "build_run_metadata",
    "build_session_summary",
    "compare_csv",
    "compute_track_metrics",
    "generate_trajectory_png",
    "link_regression_benchmark",
    "load_tracking_csv",
    "metrics_from_points",
    "metrics_from_points_with_profile",
    "save_diagnostic_log",
    "save_all_tracks_csv",
    "save_metrics_csv",
    "save_run_metadata",
    "save_session_summary_csv",
    "save_session_summary_json",
    "save_track_csv",
    "save_track_report_pdf",
    "export_annotated_video",
    "__version__",
]
