from __future__ import annotations

import argparse
from dataclasses import dataclass


@dataclass(frozen=True)
class ParameterMatrixRow:
    """Opisuje pojedynczy parametr i jego mapowanie między warstwami konfiguracji."""

    domain: str
    cli_option: str
    entrypoint_field: str
    run_config_path: str
    pipeline_field: str | None


# Matryca kontraktu pełni rolę checklisty mapowania między adapterami i pipeline.
PARAMETER_MATRIX: tuple[ParameterMatrixRow, ...] = (
    ParameterMatrixRow("input", "--video", "video", "input.video", "video"),
    ParameterMatrixRow("input", "--camera", "camera", "input.camera", "video"),
    ParameterMatrixRow("input", "--camera_index", "camera_index", "input.camera", "video"),
    ParameterMatrixRow("detection", "--track_mode", "track_mode", "detector.track_mode", "track_mode"),
    ParameterMatrixRow("detection", "--threshold", "threshold", "detector.threshold", "threshold"),
    ParameterMatrixRow("detection", "--threshold_mode", "threshold_mode", "detector.threshold_mode", "threshold_mode"),
    ParameterMatrixRow("detection", "--adaptive_block_size", "adaptive_block_size", "detector.adaptive_block_size", "adaptive_block_size"),
    ParameterMatrixRow("detection", "--adaptive_c", "adaptive_c", "detector.adaptive_c", "adaptive_c"),
    ParameterMatrixRow("detection", "--blur", "blur", "detector.blur", "blur"),
    ParameterMatrixRow("detection", "--min_area", "min_area", "detector.min_area", "min_area"),
    ParameterMatrixRow("detection", "--max_area", "max_area", "detector.max_area", "max_area"),
    ParameterMatrixRow("detection", "--erode_iter", "erode_iter", "detector.erode_iter", "erode_iter"),
    ParameterMatrixRow("detection", "--dilate_iter", "dilate_iter", "detector.dilate_iter", "dilate_iter"),
    ParameterMatrixRow("detection", "--opening_kernel", "opening_kernel", "detector.opening_kernel", "opening_kernel"),
    ParameterMatrixRow("detection", "--closing_kernel", "closing_kernel", "detector.closing_kernel", "closing_kernel"),
    ParameterMatrixRow("detection", "--min_detection_confidence", "min_detection_confidence", "detector.min_detection_confidence", "min_detection_confidence"),
    ParameterMatrixRow("detection", "--min_detection_score", "min_detection_score", "detector.min_detection_score", "min_detection_score"),
    ParameterMatrixRow("detection", "--temporal_stabilization", "temporal_stabilization", "detector.temporal_stabilization", "temporal_stabilization"),
    ParameterMatrixRow("detection", "--temporal_window", "temporal_window", "detector.temporal_window", "temporal_window"),
    ParameterMatrixRow("detection", "--min_persistence_frames", "min_persistence_frames", "detector.min_persistence_frames", "min_persistence_frames"),
    ParameterMatrixRow("detection", "--persistence_radius_px", "persistence_radius_px", "detector.persistence_radius_px", "persistence_radius_px"),
    ParameterMatrixRow("tracking", "--multi_track", "multi_track", "tracker.multi_track", "multi_track"),
    ParameterMatrixRow("tracking", "--max_distance", "max_distance", "tracker.max_distance", "max_distance"),
    ParameterMatrixRow("tracking", "--max_missed", "max_missed", "tracker.max_missed", "max_missed"),
    ParameterMatrixRow("tracking", "--selection_mode", "selection_mode", "tracker.selection_mode", "selection_mode"),
    ParameterMatrixRow("calibration", "--calib_file", "calib_file", "input.calib_file", "calib_file"),
    ParameterMatrixRow("calibration", "--pnp_object_points", "pnp_object_points", "pose.pnp_object_points", "pnp_object_points"),
    ParameterMatrixRow("calibration", "--pnp_image_points", "pnp_image_points", "pose.pnp_image_points", "pnp_image_points"),
    ParameterMatrixRow("calibration", "--pnp_world_plane_z", "pnp_world_plane_z", "pose.pnp_world_plane_z", "pnp_world_plane_z"),
    ParameterMatrixRow("reporting", "--output_csv", "output_csv", "eval.output_csv", "output_csv"),
    ParameterMatrixRow("reporting", "--trajectory_png", "trajectory_png", "eval.trajectory_png", "trajectory_png"),
    ParameterMatrixRow("reporting", "--report_csv", "report_csv", "eval.report_csv", "report_csv"),
    ParameterMatrixRow("reporting", "--report_pdf", "report_pdf", "eval.report_pdf", "report_pdf"),
    ParameterMatrixRow("reporting", "--all_tracks_csv", "all_tracks_csv", "eval.all_tracks_csv", "all_tracks_csv"),
    ParameterMatrixRow("reporting", "--annotated_video", "annotated_video", "eval.annotated_video", "annotated_video"),
    ParameterMatrixRow("publication", "--topic", "topic", "(ROS2 runtime-only)", None),
    ParameterMatrixRow("publication", "--node_name", "node_name", "(ROS2 runtime-only)", None),
)


def add_shared_detection_options(parser: argparse.ArgumentParser) -> None:
    """Dodaje zestandaryzowane opcje detekcji do parsera adaptera."""

    parser.add_argument("--track_mode", choices=["brightness", "color"], default="brightness", help="Tryb detekcji plamki")
    parser.add_argument("--threshold", type=int, default=200, help="Próg jasności")
    parser.add_argument("--threshold_mode", choices=["fixed", "otsu", "adaptive"], default="fixed", help="Tryb progowania")
    parser.add_argument("--adaptive_block_size", type=int, default=31, help="Rozmiar okna dla progowania adaptacyjnego")
    parser.add_argument("--adaptive_c", type=float, default=5.0, help="Korekta C dla progowania adaptacyjnego")
    parser.add_argument("--use_clahe", action="store_true", help="Włącza CLAHE przed progowaniem")
    parser.add_argument("--blur", type=int, default=11, help="Rozmiar filtra Gaussa")
    parser.add_argument("--min_area", type=float, default=10.0, help="Minimalne pole plamki")
    parser.add_argument("--max_area", type=float, default=0.0, help="Maksymalne pole plamki, 0 = brak")
    parser.add_argument("--erode_iter", type=int, default=2, help="Liczba iteracji erozji")
    parser.add_argument("--dilate_iter", type=int, default=4, help="Liczba iteracji dylatacji")
    parser.add_argument("--opening_kernel", type=int, default=0, help="Rozmiar jądra opening (0/1 = wyłączone)")
    parser.add_argument("--closing_kernel", type=int, default=0, help="Rozmiar jądra closing (0/1 = wyłączone)")
    parser.add_argument("--roi", help="Obszar ROI w formacie x,y,w,h")
    parser.add_argument("--color_name", choices=["red", "green", "blue", "white", "yellow", "custom"], default="red", help="Preset koloru dla track_mode=color")
    parser.add_argument("--hsv_lower", help="Dolna granica HSV np. 0,80,80")
    parser.add_argument("--hsv_upper", help="Górna granica HSV np. 10,255,255")
    parser.add_argument("--max_spots", type=int, default=1, help="Maksymalna liczba plamek na klatkę")
    parser.add_argument("--min_detection_confidence", type=float, default=0.0, help="Minimalna pewność detekcji")
    parser.add_argument("--min_detection_score", type=float, default=0.0, help="Minimalny wynik rankingu detekcji")
    parser.add_argument("--temporal_stabilization", action="store_true", help="Włącza filtr temporalny maski")
    parser.add_argument("--temporal_window", type=int, default=3, help="Rozmiar okna filtra temporalnego")
    parser.add_argument("--temporal_mode", choices=["majority", "and"], default="majority", help="Strategia agregacji filtra temporalnego")
    parser.add_argument("--min_persistence_frames", type=int, default=1, help="Liczba kolejnych klatek wymaganych do potwierdzenia detekcji")
    parser.add_argument("--persistence_radius_px", type=float, default=12.0, help="Maksymalny skok centroidu [px] przy filtrze trwałości")


def add_shared_tracking_options(parser: argparse.ArgumentParser) -> None:
    """Dodaje wspólne opcje trackera, które mapują się do `TrackerConfig`."""

    parser.add_argument("--multi_track", action="store_true", help="Śledzenie wielu plamek jednocześnie")
    parser.add_argument("--max_distance", type=float, default=40.0, help="Maksymalny dystans przypisania detekcji")
    parser.add_argument("--max_missed", type=int, default=10, help="Ile klatek tor może zniknąć bez usunięcia")
    parser.add_argument("--selection_mode", choices=["largest", "stablest", "longest"], default="stablest", help="Strategia wyboru toru głównego")


def add_shared_calibration_options(parser: argparse.ArgumentParser) -> None:
    """Dodaje wspólne opcje kalibracji/PnP dla trybów track/gui/ros2."""

    parser.add_argument("--calib_file", help="Plik kalibracji .npz z camera_matrix i dist_coeffs")
    parser.add_argument("--pnp_object_points", help="Punkty 3D świata: X,Y,Z;X,Y,Z;... (min. 4)")
    parser.add_argument("--pnp_image_points", help="Punkty 2D obrazu: x,y;x,y;... (min. 4)")
    parser.add_argument("--pnp_world_plane_z", type=float, default=0.0, help="Współrzędna Z płaszczyzny świata")


def add_shared_reporting_options(parser: argparse.ArgumentParser) -> None:
    """Dodaje wspólne opcje raportowania używane przez track/gui."""

    parser.add_argument("--output_csv", default="tracking_results.csv", help="CSV głównej trajektorii")
    parser.add_argument("--trajectory_png", help="PNG z wykresem trajektorii")
    parser.add_argument("--report_csv", help="CSV z raportem jakości")
    parser.add_argument("--report_pdf", help="PDF z raportem jakości")
    parser.add_argument("--all_tracks_csv", help="CSV ze wszystkimi trajektoriami")
    parser.add_argument("--annotated_video", help="Wyjściowy plik wideo z narysowanymi trajektoriami")


def add_shared_postprocess_options(parser: argparse.ArgumentParser) -> None:
    """Dodaje wspólne opcje postprocessingu torów."""

    parser.add_argument("--draw_all_tracks", action="store_true", help="Rysuje wszystkie tory na podglądzie/wyjściu")
    parser.add_argument("--use_kalman", action="store_true", help="Włącza wygładzanie Kalmana")
    parser.add_argument("--kalman_process_noise", type=float, default=3e-2, help="Szum procesu filtra Kalmana")
    parser.add_argument("--kalman_measurement_noise", type=float, default=5e-2, help="Szum pomiaru filtra Kalmana")
