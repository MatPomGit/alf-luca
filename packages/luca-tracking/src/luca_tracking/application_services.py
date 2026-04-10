from __future__ import annotations

from argparse import Namespace
from typing import Optional

from luca_input.io_paths import (
    RuntimePathResolver,
    build_measurement_stem,
    parse_camera_source,
    with_default,
)
from luca_reporting.reports import compare_csv
from luca_camera import calibrate_camera
from luca_tracking.pipeline import track_video
from luca_publishing.ros2_node import run_ros2_tracker_node
from luca_types.config_model import load_run_config
from luca_input.pipeline_config_mapping import run_config_to_pipeline_config


_PATH_RESOLVER = RuntimePathResolver.for_current_process()


def run_calibrate(calib_dir: str, rows: int, cols: int, square_size: float, output_file: str) -> None:
    """Uruchamia przypadek użycia kalibracji i zapisuje wynik do katalogu wyjściowego."""
    _PATH_RESOLVER.ensure_output_dir()
    resolved_output = _PATH_RESOLVER.resolve_output_path(output_file)
    calibrate_camera(calib_dir, rows, cols, square_size, resolved_output)


def _resolve_track_output_paths(source_label: str, output_csv: str, trajectory_png: Optional[str], report_csv: Optional[str], report_pdf: Optional[str]) -> tuple[str, str, str, str]:
    """Wylicza i normalizuje ścieżki artefaktów trackingu dla pojedynczego uruchomienia."""
    base = build_measurement_stem(source_label)
    output_csv_value = output_csv
    if output_csv_value == "tracking_results.csv":
        output_csv_value = f"{base}_tracking_results.csv"
    resolved_output_csv = _PATH_RESOLVER.resolve_output_path(output_csv_value)
    resolved_trajectory_png = _PATH_RESOLVER.resolve_output_path(trajectory_png or f"{base}_trajectory.png")
    resolved_report_csv = _PATH_RESOLVER.resolve_output_path(report_csv or f"{base}_report.csv")
    resolved_report_pdf = _PATH_RESOLVER.resolve_output_path(report_pdf or f"{base}_report.pdf")
    return resolved_output_csv, resolved_trajectory_png, resolved_report_csv, resolved_report_pdf


def run_tracking(args: Namespace) -> None:
    """Uruchamia przypadek użycia śledzenia dla wejścia CLI (`--config` lub parametry bezpośrednie)."""
    _PATH_RESOLVER.ensure_output_dir()
    if getattr(args, "config", None):
        run_config = load_run_config(args.config)
        if bool(run_config.input.video) == bool(run_config.input.camera):
            raise ValueError("Plik konfiguracyjny musi wskazywać dokładnie jedno źródło: `input.video` albo `input.camera`.")

        source_label = run_config.input.video or f"camera:{run_config.input.camera}"
        if run_config.input.video:
            run_config.input.video = _PATH_RESOLVER.resolve_input_artifact(run_config.input.video)

        base = build_measurement_stem(source_label)
        output_csv_cfg = with_default(run_config.eval.output_csv, f"{base}_track.csv")
        if output_csv_cfg == "tracking_results.csv":
            output_csv_cfg = f"{base}_tracking_results.csv"
        run_config.eval.output_csv = _PATH_RESOLVER.resolve_output_path(output_csv_cfg)
        run_config.eval.trajectory_png = _PATH_RESOLVER.resolve_output_path(with_default(run_config.eval.trajectory_png, f"{base}_trajectory.png"))
        run_config.eval.report_csv = _PATH_RESOLVER.resolve_output_path(with_default(run_config.eval.report_csv, f"{base}_report.csv"))
        run_config.eval.report_pdf = _PATH_RESOLVER.resolve_output_path(with_default(run_config.eval.report_pdf, f"{base}_report.pdf"))
        if run_config.eval.all_tracks_csv:
            run_config.eval.all_tracks_csv = _PATH_RESOLVER.resolve_output_path(run_config.eval.all_tracks_csv)
        if run_config.eval.annotated_video:
            run_config.eval.annotated_video = _PATH_RESOLVER.resolve_output_path(run_config.eval.annotated_video)

        track_video(run_config_to_pipeline_config(run_config))
        return

    if not getattr(args, "video", None) and not getattr(args, "camera", None):
        raise ValueError("Dla trybu track wymagane jest jedno źródło: --video albo --camera.")

    if getattr(args, "video", None):
        video = _PATH_RESOLVER.resolve_source_asset(args.video)
        source_label = video
        is_live_source = False
    else:
        video = parse_camera_source(args.camera)
        source_label = f"camera:{args.camera}"
        is_live_source = True

    resolved_output_csv, resolved_trajectory_png, resolved_report_csv, resolved_report_pdf = _resolve_track_output_paths(
        source_label=source_label,
        output_csv=getattr(args, "output_csv", "tracking_results.csv"),
        trajectory_png=getattr(args, "trajectory_png", None),
        report_csv=getattr(args, "report_csv", None),
        report_pdf=getattr(args, "report_pdf", None),
    )

    args.video = video
    args.source_label = source_label
    args.is_live_source = is_live_source
    args.output_csv = resolved_output_csv
    args.trajectory_png = resolved_trajectory_png
    args.report_csv = resolved_report_csv
    args.report_pdf = resolved_report_pdf
    if getattr(args, "all_tracks_csv", None):
        args.all_tracks_csv = _PATH_RESOLVER.resolve_output_path(args.all_tracks_csv)
    if getattr(args, "annotated_video", None):
        args.annotated_video = _PATH_RESOLVER.resolve_output_path(args.annotated_video)
    if getattr(args, "calib_file", None):
        args.calib_file = _PATH_RESOLVER.resolve_input_artifact(args.calib_file)
    track_video(args)


def run_compare(reference: str, candidate: str, output_csv: str, report_pdf: str | None = None) -> None:
    """Uruchamia przypadek użycia porównania dwóch ścieżek CSV."""
    _PATH_RESOLVER.ensure_output_dir()
    compare_csv(
        _PATH_RESOLVER.resolve_input_artifact(reference),
        _PATH_RESOLVER.resolve_input_artifact(candidate),
        _PATH_RESOLVER.resolve_output_path(output_csv),
        _PATH_RESOLVER.resolve_output_path(report_pdf) if report_pdf else None,
    )


def run_ros2(args: Namespace) -> None:
    """Uruchamia przypadek użycia ROS2 po normalizacji ścieżek wejściowych."""
    if getattr(args, "calib_file", None):
        args.calib_file = _PATH_RESOLVER.resolve_input_artifact(args.calib_file)
    run_ros2_tracker_node(args)
