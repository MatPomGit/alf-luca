from __future__ import annotations

from argparse import Namespace
from typing import Optional

from luca_input import (
    RuntimePathResolver,
    build_measurement_stem,
    with_default,
)
from luca_reporting import compare_csv
from luca_camera import calibrate_camera
from luca_tracking.pipeline import track_video
from luca_tracking.tracking_presets import (
    apply_tracking_preset,
    derive_tracking_preset_from_video,
    list_tracking_presets,
    load_tracking_preset,
    save_tracking_preset,
)
from luca_publishing import run_ros2_tracker_node
from luca_types import RunConfig, load_run_config, run_config_from_entrypoint
from luca_input import run_config_to_pipeline_config


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




def _handle_tracking_presets(run_config: RunConfig | None, args: Namespace) -> tuple[str | None, bool]:
    """Obsługuje auto-tuning i wybór presetów live; zwraca nazwę auto-presetu i flagę listowania."""
    presets_path = getattr(args, "tracking_presets_file", "config/live_tracking_presets.json")

    if getattr(args, "list_live_tracking_presets", False):
        preset_names = list_tracking_presets(presets_path=presets_path)
        if preset_names:
            print("Dostępne presety live:")
            for preset_name in preset_names:
                print(f"- {preset_name}")
        else:
            print("Brak zapisanych presetów live.")
        return None, True

    auto_preset_name: str | None = None
    auto_tune_video = getattr(args, "auto_tune_from_video", None)
    if auto_tune_video:
        auto_tune_video = _PATH_RESOLVER.resolve_source_asset(str(auto_tune_video))
        preset_name = str(getattr(args, "auto_tune_preset_name", "auto_live")).strip() or "auto_live"
        derived = derive_tracking_preset_from_video(auto_tune_video, preset_name=preset_name)
        saved_path = save_tracking_preset(derived, presets_path=presets_path)
        print(f"Zapisano preset live `{preset_name}` do: {saved_path}")
        auto_preset_name = preset_name

    selected_preset = getattr(args, "live_tracking_preset", None) or auto_preset_name
    if selected_preset and run_config is not None and run_config.input.camera:
        loaded_preset = load_tracking_preset(str(selected_preset), presets_path=presets_path)
        apply_tracking_preset(run_config, loaded_preset)
        print(f"Zastosowano preset live `{loaded_preset.name}`.")

    return auto_preset_name, False

def run_tracking(args: Namespace) -> None:
    """Uruchamia przypadek użycia śledzenia dla wejścia CLI (`--config` lub parametry bezpośrednie)."""
    _PATH_RESOLVER.ensure_output_dir()
    _, should_exit = _handle_tracking_presets(None, args)
    if should_exit:
        return

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

        _handle_tracking_presets(run_config, args)
        track_video(run_config_to_pipeline_config(run_config))
        return

    entrypoint_name = "gui" if getattr(args, "display", False) and not getattr(args, "command", None) else "track"
    run_config = run_config_from_entrypoint(args, entrypoint=entrypoint_name)
    if not run_config.input.video and not run_config.input.camera:
        raise ValueError("Dla trybu track wymagane jest jedno źródło: --video albo --camera.")

    if run_config.input.video:
        run_config.input.video = _PATH_RESOLVER.resolve_source_asset(run_config.input.video)
        source_label = run_config.input.video
    else:
        source_label = f"camera:{run_config.input.camera}"

    run_config.eval.output_csv, run_config.eval.trajectory_png, run_config.eval.report_csv, run_config.eval.report_pdf = (
        _resolve_track_output_paths(
            source_label=source_label,
            output_csv=run_config.eval.output_csv,
            trajectory_png=run_config.eval.trajectory_png,
            report_csv=run_config.eval.report_csv,
            report_pdf=run_config.eval.report_pdf,
        )
    )
    if run_config.eval.all_tracks_csv:
        run_config.eval.all_tracks_csv = _PATH_RESOLVER.resolve_output_path(run_config.eval.all_tracks_csv)
    if run_config.eval.annotated_video:
        run_config.eval.annotated_video = _PATH_RESOLVER.resolve_output_path(run_config.eval.annotated_video)
    if run_config.input.calib_file:
        run_config.input.calib_file = _PATH_RESOLVER.resolve_input_artifact(run_config.input.calib_file)
    _handle_tracking_presets(run_config, args)
    track_video(run_config_to_pipeline_config(run_config))


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
    run_config = run_config_from_entrypoint(args, entrypoint="ros2")
    if run_config.input.calib_file:
        run_config.input.calib_file = _PATH_RESOLVER.resolve_input_artifact(run_config.input.calib_file)
    # Przekazujemy do warstwy publikacji jeden model wejściowy jako kontrakt mapowania.
    args.run_config = run_config
    run_ros2_tracker_node(args)
