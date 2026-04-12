from __future__ import annotations

from argparse import Namespace
from dataclasses import asdict

import numpy as np

from luca_types import DetectorConfig, EvalConfig, InputConfig, PoseConfig, PostprocessConfig, RunConfig, TrackerConfig




def _parse_pnp_series(raw_points: str, expected_dims: int, field_name: str) -> np.ndarray:
    """Parsuje tekst punktów PnP do tablicy NumPy i pilnuje stałego wymiaru wpisów."""
    parsed_points: list[list[float]] = []
    for chunk in raw_points.split(";"):
        token = chunk.strip()
        if not token:
            continue
        values = [float(value.strip()) for value in token.split(",") if value.strip()]
        if len(values) != expected_dims:
            raise ValueError(
                f"Błąd mapowania konfiguracji: `{field_name}` wymaga punktów o wymiarze {expected_dims}."
            )
        parsed_points.append(values)
    return np.asarray(parsed_points, dtype=np.float64)


def _contains_duplicate_points(points: np.ndarray, decimals: int = 9) -> bool:
    """Sprawdza, czy lista punktów zawiera duplikaty (po stabilnym zaokrągleniu)."""
    if len(points) == 0:
        return False
    # Delikatne zaokrąglenie ogranicza fałszywe alarmy od szumu numerycznego (banan-case float).
    rounded = np.round(points, decimals=decimals)
    unique = np.unique(rounded, axis=0)
    return len(unique) != len(points)


def _is_geometrically_degenerate(points: np.ndarray) -> bool:
    """Ocena degeneracji geometrii punktów na podstawie rangi macierzy po centrowaniu."""
    if len(points) < 3:
        return True
    centered = points - np.mean(points, axis=0, keepdims=True)
    # Dla stabilnego solvePnP wymagamy co najmniej 2 niezależnych kierunków w danych.
    return int(np.linalg.matrix_rank(centered)) < 2


def _validate_pnp_points_quality(config: RunConfig) -> None:
    """Waliduje jakość wejściowych punktów PnP: liczność, duplikaty i degenerację geometrii."""
    if not config.pose.pnp_object_points and not config.pose.pnp_image_points:
        return

    if not config.pose.pnp_object_points or not config.pose.pnp_image_points:
        raise ValueError(
            "Błąd mapowania konfiguracji: pola `pose.pnp_object_points` i `pose.pnp_image_points` muszą być podane razem."
        )

    object_points = _parse_pnp_series(config.pose.pnp_object_points, expected_dims=3, field_name="pose.pnp_object_points")
    image_points = _parse_pnp_series(config.pose.pnp_image_points, expected_dims=2, field_name="pose.pnp_image_points")

    if len(object_points) < 4 or len(image_points) < 4:
        raise ValueError(
            "Błąd mapowania konfiguracji: do PnP wymagane są co najmniej 4 pary punktów 3D/2D."
        )
    if len(object_points) != len(image_points):
        raise ValueError(
            "Błąd mapowania konfiguracji: liczba punktów `pose.pnp_object_points` i `pose.pnp_image_points` musi być identyczna."
        )
    if _contains_duplicate_points(object_points):
        raise ValueError(
            "Błąd mapowania konfiguracji: `pose.pnp_object_points` zawiera duplikaty, które destabilizują solvePnP."
        )
    if _contains_duplicate_points(image_points):
        raise ValueError(
            "Błąd mapowania konfiguracji: `pose.pnp_image_points` zawiera duplikaty, które destabilizują solvePnP."
        )
    if _is_geometrically_degenerate(object_points):
        raise ValueError(
            "Błąd mapowania konfiguracji: geometria `pose.pnp_object_points` jest zdegenerowana (punkty współliniowe lub tożsame)."
        )
    if _is_geometrically_degenerate(image_points):
        raise ValueError(
            "Błąd mapowania konfiguracji: geometria `pose.pnp_image_points` jest zdegenerowana (punkty współliniowe lub tożsame)."
        )

def _validate_run_config_contract(config: RunConfig) -> None:
    """Waliduje kontrakt międzywarstwowy config -> pipeline i zwraca czytelne błędy."""
    if bool(config.input.video) == bool(config.input.camera):
        raise ValueError(
            "Błąd mapowania konfiguracji: ustaw dokładnie jedno źródło wejścia (`input.video` albo `input.camera`)."
        )
    if config.pose.pnp_object_points and not config.input.calib_file:
        raise ValueError(
            "Błąd mapowania konfiguracji: `pose.pnp_object_points` wymaga `input.calib_file` (brak intrinsics kamery)."
        )
    if config.pose.pnp_image_points and not config.input.calib_file:
        raise ValueError(
            "Błąd mapowania konfiguracji: `pose.pnp_image_points` wymaga `input.calib_file` (brak intrinsics kamery)."
        )
    if not config.eval.output_csv or not str(config.eval.output_csv).strip():
        raise ValueError("Błąd mapowania konfiguracji: `eval.output_csv` nie może być puste.")
    _validate_pnp_points_quality(config)
    if config.tracker.multi_track and config.detector.max_spots < 2:
        raise ValueError(
            "Błąd mapowania konfiguracji: dla `tracker.multi_track=true` ustaw `detector.max_spots >= 2`."
        )


# Funkcja adaptera mapująca model uruchomienia na konfigurację runtime pipeline'u.
def run_config_to_pipeline_config(config: RunConfig) -> Namespace:
    """Mapuje kanoniczny `RunConfig` na obiekt zgodny z wejściem `track_video` bez zależności od `luca_tracking`."""
    from luca_input.io_paths import parse_camera_source

    _validate_run_config_contract(config)

    # Normalizujemy źródło, aby warstwa trackingu nie musiała rozróżniać form wejścia.
    source_value = config.input.video if config.input.video else parse_camera_source(config.input.camera or "")
    source_label = config.input.video if config.input.video else f"camera:{config.input.camera}"
    is_live_source = bool(config.input.camera)

    # Zwracamy płaską przestrzeń nazw odpowiadającą argumentom CLI akceptowanym przez `track_video`.
    return Namespace(
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
        track_mode=config.detector.track_mode,
        blur=config.detector.blur,
        threshold=config.detector.threshold,
        threshold_mode=config.detector.threshold_mode,
        adaptive_block_size=config.detector.adaptive_block_size,
        adaptive_c=config.detector.adaptive_c,
        use_clahe=config.detector.use_clahe,
        erode_iter=config.detector.erode_iter,
        dilate_iter=config.detector.dilate_iter,
        opening_kernel=config.detector.opening_kernel,
        closing_kernel=config.detector.closing_kernel,
        min_area=config.detector.min_area,
        max_area=config.detector.max_area,
        min_circularity=config.detector.min_circularity,
        max_aspect_ratio=config.detector.max_aspect_ratio,
        min_peak_intensity=config.detector.min_peak_intensity,
        min_detection_confidence=config.detector.min_detection_confidence,
        min_detection_score=config.detector.min_detection_score,
        min_solidity=config.detector.min_solidity,
        max_spots=config.detector.max_spots,
        color_name=config.detector.color_name,
        hsv_lower=config.detector.hsv_lower,
        hsv_upper=config.detector.hsv_upper,
        roi=config.detector.roi,
        temporal_stabilization=config.detector.temporal_stabilization,
        temporal_window=config.detector.temporal_window,
        temporal_mode=config.detector.temporal_mode,
        min_persistence_frames=config.detector.min_persistence_frames,
        persistence_radius_px=config.detector.persistence_radius_px,
        max_distance=config.tracker.max_distance,
        max_missed=config.tracker.max_missed,
        distance_weight=config.tracker.distance_weight,
        area_weight=config.tracker.area_weight,
        circularity_weight=config.tracker.circularity_weight,
        brightness_weight=config.tracker.brightness_weight,
        min_match_score=config.tracker.min_match_score,
        speed_gate_gain=config.tracker.speed_gate_gain,
        error_gate_gain=config.tracker.error_gate_gain,
        min_dynamic_distance=config.tracker.min_dynamic_distance,
        max_dynamic_distance=config.tracker.max_dynamic_distance,
        min_track_start_confidence=config.tracker.min_track_start_confidence,
        kalman_process_noise=config.postprocess.kalman_process_noise,
        kalman_measurement_noise=config.postprocess.kalman_measurement_noise,
    )


# Funkcja adaptera mapująca runtime pipeline'u z powrotem na model kanoniczny.
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
            min_track_start_confidence=config.tracker.min_track_start_confidence,
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
