from __future__ import annotations

from dataclasses import asdict

from luca_types.config_model import InputConfig, DetectorConfig, TrackerConfig, PostprocessConfig, PoseConfig, EvalConfig, RunConfig


def run_config_to_pipeline_config(config: RunConfig):
    """Mapuje `RunConfig` na model `PipelineConfig` wykorzystywany podczas śledzenia."""
    from luca_processing.detectors import DetectorConfig as PipelineDetectorConfig
    from luca_processing.postprocess import KalmanConfig
    from luca_tracking.pipeline import PipelineConfig
    from luca_tracking.tracker_core import TrackerConfig as PipelineTrackerConfig
    from luca_input.io_paths import parse_camera_source

    if bool(config.input.video) == bool(config.input.camera):
        raise ValueError("Konfiguracja musi zawierać dokładnie jedno źródło wejścia: `input.video` albo `input.camera`.")

    source_value = config.input.video if config.input.video else parse_camera_source(config.input.camera or "")
    source_label = config.input.video if config.input.video else f"camera:{config.input.camera}"
    is_live_source = bool(config.input.camera)

    return PipelineConfig(
        video=source_value,
        source_label=source_label,
        is_live_source=is_live_source,
        calib_file=config.input.calib_file,
        display=config.input.display,
        interactive=config.input.interactive,
        multi_track=config.tracker.multi_track,
        use_single_object_ekf=config.tracker.use_single_object_ekf,
        selection_mode=config.tracker.selection_mode,
        output_csv=config.eval.output_csv,
        trajectory_png=config.eval.trajectory_png,
        report_csv=config.eval.report_csv,
        report_pdf=config.eval.report_pdf,
        all_tracks_csv=config.eval.all_tracks_csv,
        annotated_video=config.eval.annotated_video,
        draw_all_tracks=config.postprocess.draw_all_tracks,
        use_kalman=config.postprocess.use_kalman,
        pnp_object_points=config.pose.pnp_object_points,
        pnp_image_points=config.pose.pnp_image_points,
        pnp_world_plane_z=config.pose.pnp_world_plane_z,
        detector=PipelineDetectorConfig(**asdict(config.detector)),
        tracker=PipelineTrackerConfig(
            max_distance=config.tracker.max_distance,
            max_missed=config.tracker.max_missed,
            selection_mode=config.tracker.selection_mode,
            distance_weight=config.tracker.distance_weight,
            area_weight=config.tracker.area_weight,
            circularity_weight=config.tracker.circularity_weight,
            brightness_weight=config.tracker.brightness_weight,
            min_match_score=config.tracker.min_match_score,
            speed_gate_gain=config.tracker.speed_gate_gain,
            error_gate_gain=config.tracker.error_gate_gain,
            min_dynamic_distance=config.tracker.min_dynamic_distance,
            max_dynamic_distance=config.tracker.max_dynamic_distance,
        ),
        kalman=KalmanConfig(
            process_noise=config.postprocess.kalman_process_noise,
            measurement_noise=config.postprocess.kalman_measurement_noise,
        ),
    )


def pipeline_config_to_run_config(config) -> RunConfig:
    """Mapuje `PipelineConfig` na zunifikowany model eksportowy `RunConfig`."""
    return RunConfig(
        input=InputConfig(
            video=None if getattr(config, "is_live_source", False) else str(config.video),
            camera=str(config.video) if getattr(config, "is_live_source", False) else None,
            calib_file=config.calib_file,
            display=config.display,
            interactive=config.interactive,
        ),
        detector=DetectorConfig(**asdict(config.detector)),
        tracker=TrackerConfig(
            multi_track=config.multi_track,
            use_single_object_ekf=getattr(config, "use_single_object_ekf", True),
            max_distance=config.tracker.max_distance,
            max_missed=config.tracker.max_missed,
            selection_mode=config.selection_mode,
            distance_weight=config.tracker.distance_weight,
            area_weight=config.tracker.area_weight,
            circularity_weight=config.tracker.circularity_weight,
            brightness_weight=config.tracker.brightness_weight,
            min_match_score=config.tracker.min_match_score,
            speed_gate_gain=config.tracker.speed_gate_gain,
            error_gate_gain=config.tracker.error_gate_gain,
            min_dynamic_distance=config.tracker.min_dynamic_distance,
            max_dynamic_distance=config.tracker.max_dynamic_distance,
        ),
        postprocess=PostprocessConfig(
            use_kalman=config.use_kalman,
            kalman_process_noise=config.kalman.process_noise,
            kalman_measurement_noise=config.kalman.measurement_noise,
            draw_all_tracks=config.draw_all_tracks,
        ),
        pose=PoseConfig(
            pnp_object_points=config.pnp_object_points,
            pnp_image_points=config.pnp_image_points,
            pnp_world_plane_z=config.pnp_world_plane_z,
        ),
        eval=EvalConfig(
            output_csv=config.output_csv,
            trajectory_png=config.trajectory_png,
            report_csv=config.report_csv,
            report_pdf=config.report_pdf,
            all_tracks_csv=config.all_tracks_csv,
            annotated_video=config.annotated_video,
        ),
    )
