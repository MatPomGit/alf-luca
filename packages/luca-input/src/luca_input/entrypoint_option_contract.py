from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any


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
    ParameterMatrixRow("input", "--display", "display", "input.display", "display"),
    ParameterMatrixRow("input", "--interactive", "interactive", "input.interactive", "interactive"),
    ParameterMatrixRow("detection", "--track_mode", "track_mode", "detector.track_mode", "track_mode"),
    ParameterMatrixRow("detection", "--detector_profile", "detector_profile", "detector.detector_profile", "detector_profile"),
    ParameterMatrixRow("detection", "--enable_experimental_profiles", "enable_experimental_profiles", "detector.enable_experimental_profiles", "enable_experimental_profiles"),
    ParameterMatrixRow("detection", "--threshold", "threshold", "detector.threshold", "threshold"),
    ParameterMatrixRow("detection", "--threshold_mode", "threshold_mode", "detector.threshold_mode", "threshold_mode"),
    ParameterMatrixRow("detection", "--adaptive_block_size", "adaptive_block_size", "detector.adaptive_block_size", "adaptive_block_size"),
    ParameterMatrixRow("detection", "--adaptive_c", "adaptive_c", "detector.adaptive_c", "adaptive_c"),
    ParameterMatrixRow("detection", "--use_clahe", "use_clahe", "detector.use_clahe", "use_clahe"),
    ParameterMatrixRow("detection", "--blur", "blur", "detector.blur", "blur"),
    ParameterMatrixRow("detection", "--min_area", "min_area", "detector.min_area", "min_area"),
    ParameterMatrixRow("detection", "--max_area", "max_area", "detector.max_area", "max_area"),
    ParameterMatrixRow("detection", "--min_circularity", "min_circularity", "detector.min_circularity", "min_circularity"),
    ParameterMatrixRow("detection", "--max_aspect_ratio", "max_aspect_ratio", "detector.max_aspect_ratio", "max_aspect_ratio"),
    ParameterMatrixRow("detection", "--min_peak_intensity", "min_peak_intensity", "detector.min_peak_intensity", "min_peak_intensity"),
    ParameterMatrixRow("detection", "--min_solidity", "min_solidity", "detector.min_solidity", "min_solidity"),
    ParameterMatrixRow("detection", "--erode_iter", "erode_iter", "detector.erode_iter", "erode_iter"),
    ParameterMatrixRow("detection", "--dilate_iter", "dilate_iter", "detector.dilate_iter", "dilate_iter"),
    ParameterMatrixRow("detection", "--opening_kernel", "opening_kernel", "detector.opening_kernel", "opening_kernel"),
    ParameterMatrixRow("detection", "--closing_kernel", "closing_kernel", "detector.closing_kernel", "closing_kernel"),
    ParameterMatrixRow("detection", "--color_name", "color_name", "detector.color_name", "color_name"),
    ParameterMatrixRow("detection", "--hsv_lower", "hsv_lower", "detector.hsv_lower", "hsv_lower"),
    ParameterMatrixRow("detection", "--hsv_upper", "hsv_upper", "detector.hsv_upper", "hsv_upper"),
    ParameterMatrixRow("detection", "--roi", "roi", "detector.roi", "roi"),
    ParameterMatrixRow("detection", "--max_spots", "max_spots", "detector.max_spots", "max_spots"),
    ParameterMatrixRow("detection", "--min_detection_confidence", "min_detection_confidence", "detector.min_detection_confidence", "min_detection_confidence"),
    ParameterMatrixRow("detection", "--min_detection_score", "min_detection_score", "detector.min_detection_score", "min_detection_score"),
    ParameterMatrixRow("detection", "--temporal_stabilization", "temporal_stabilization", "detector.temporal_stabilization", "temporal_stabilization"),
    ParameterMatrixRow("detection", "--temporal_window", "temporal_window", "detector.temporal_window", "temporal_window"),
    ParameterMatrixRow("detection", "--temporal_mode", "temporal_mode", "detector.temporal_mode", "temporal_mode"),
    ParameterMatrixRow("detection", "--min_persistence_frames", "min_persistence_frames", "detector.min_persistence_frames", "min_persistence_frames"),
    ParameterMatrixRow("detection", "--persistence_radius_px", "persistence_radius_px", "detector.persistence_radius_px", "persistence_radius_px"),
    ParameterMatrixRow("tracking", "--multi_track", "multi_track", "tracker.multi_track", "multi_track"),
    ParameterMatrixRow("tracking", "--use_single_object_ekf", "use_single_object_ekf", "tracker.use_single_object_ekf", "use_single_object_ekf"),
    ParameterMatrixRow("tracking", "--experimental_mode", "experimental_mode", "tracker.experimental_mode", "experimental_mode"),
    ParameterMatrixRow(
        "tracking",
        "--experimental_adaptive_association",
        "experimental_adaptive_association",
        "tracker.experimental_adaptive_association",
        "experimental_adaptive_association",
    ),
    ParameterMatrixRow("tracking", "--max_distance", "max_distance", "tracker.max_distance", "max_distance"),
    ParameterMatrixRow("tracking", "--max_missed", "max_missed", "tracker.max_missed", "max_missed"),
    ParameterMatrixRow("tracking", "--distance_weight", "distance_weight", "tracker.distance_weight", "distance_weight"),
    ParameterMatrixRow("tracking", "--area_weight", "area_weight", "tracker.area_weight", "area_weight"),
    ParameterMatrixRow("tracking", "--circularity_weight", "circularity_weight", "tracker.circularity_weight", "circularity_weight"),
    ParameterMatrixRow("tracking", "--brightness_weight", "brightness_weight", "tracker.brightness_weight", "brightness_weight"),
    ParameterMatrixRow("tracking", "--min_match_score", "min_match_score", "tracker.min_match_score", "min_match_score"),
    ParameterMatrixRow("tracking", "--speed_gate_gain", "speed_gate_gain", "tracker.speed_gate_gain", "speed_gate_gain"),
    ParameterMatrixRow("tracking", "--error_gate_gain", "error_gate_gain", "tracker.error_gate_gain", "error_gate_gain"),
    ParameterMatrixRow("tracking", "--min_dynamic_distance", "min_dynamic_distance", "tracker.min_dynamic_distance", "min_dynamic_distance"),
    ParameterMatrixRow("tracking", "--max_dynamic_distance", "max_dynamic_distance", "tracker.max_dynamic_distance", "max_dynamic_distance"),
    ParameterMatrixRow("tracking", "--min_track_start_confidence", "min_track_start_confidence", "tracker.min_track_start_confidence", "min_track_start_confidence"),
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
    ParameterMatrixRow("reporting", "--draw_all_tracks", "draw_all_tracks", "postprocess.draw_all_tracks", "draw_all_tracks"),
    ParameterMatrixRow("reporting", "--use_kalman", "use_kalman", "postprocess.use_kalman", "use_kalman"),
    ParameterMatrixRow("reporting", "--kalman_process_noise", "kalman_process_noise", "postprocess.kalman_process_noise", "kalman_process_noise"),
    ParameterMatrixRow("reporting", "--kalman_measurement_noise", "kalman_measurement_noise", "postprocess.kalman_measurement_noise", "kalman_measurement_noise"),
    ParameterMatrixRow("publication", "--topic", "topic", "(ROS2 runtime-only)", None),
    ParameterMatrixRow("publication", "--node_name", "node_name", "(ROS2 runtime-only)", None),
    ParameterMatrixRow("publication", "--spot_id", "spot_id", "(ROS2 runtime-only)", None),
    ParameterMatrixRow("publication", "--fps", "fps", "(ROS2 runtime-only)", None),
    ParameterMatrixRow("publication", "--frame_width", "frame_width", "(ROS2 runtime-only)", None),
    ParameterMatrixRow("publication", "--frame_height", "frame_height", "(ROS2 runtime-only)", None),
)


def add_shared_runtime_source_options(argument_sink: Any) -> None:
    """Dodaje wspólne opcje źródła trackingu dla adapterów track/gui.

    `argument_sink` może być parserem lub grupą muteksu, co pozwala zachować
    regułę wzajemnego wykluczania źródeł bez duplikacji opisów.
    """

    argument_sink.add_argument("--video", help="Plik wejściowy wideo (np. MP4/MKV/AVI/MOV/WEBM)")
    argument_sink.add_argument("--camera", help="Kamera na żywo: indeks OpenCV (np. 0) albo ścieżka urządzenia")


def add_shared_ros2_runtime_options(parser: argparse.ArgumentParser) -> None:
    """Dodaje opcje runtime-only ROS2, które nie trafiają do `RunConfig`."""

    parser.add_argument("--video_device", default="/dev/video0", help="Źródło kamery")
    parser.add_argument("--camera_index", type=int, help="Indeks kamery OpenCV")
    parser.add_argument("--node_name", default="detector_node", help="Nazwa ROS2 node")
    parser.add_argument("--topic", default="/luca_tracker/tracking", help="Topic ROS2 dla danych")
    parser.add_argument("--spot_id", type=int, default=0, help="ID detekcji głównej")
    parser.add_argument("--fps", type=float, default=30.0, help="Docelowa częstotliwość odczytu/publikacji")
    parser.add_argument("--frame_width", type=int, default=0, help="Szerokość klatki (0 = domyślna)")
    parser.add_argument("--frame_height", type=int, default=0, help="Wysokość klatki (0 = domyślna)")
    parser.add_argument("--display", action="store_true", help="Podgląd śledzenia")


def add_shared_detection_options(parser: argparse.ArgumentParser) -> None:
    """Dodaje zestandaryzowane opcje detekcji do parsera adaptera."""

    parser.add_argument("--track_mode", choices=["brightness", "color"], default="brightness", help="Tryb detekcji plamki")
    parser.add_argument("--detector_profile", help="Opcjonalny profil detekcji (np. bright_default, bright_low_light_exp)")
    parser.add_argument(
        "--enable_experimental_profiles",
        action="store_true",
        help="Pozwala uruchamiać profile eksperymentalne detektora.",
    )
    parser.add_argument("--threshold", type=int, default=200, help="Próg jasności")
    parser.add_argument("--threshold_mode", choices=["fixed", "otsu", "adaptive"], default="fixed", help="Tryb progowania")
    parser.add_argument("--adaptive_block_size", type=int, default=31, help="Rozmiar okna dla progowania adaptacyjnego")
    parser.add_argument("--adaptive_c", type=float, default=5.0, help="Korekta C dla progowania adaptacyjnego")
    parser.add_argument("--use_clahe", action="store_true", help="Włącza CLAHE przed progowaniem")
    parser.add_argument("--blur", type=int, default=11, help="Rozmiar filtra Gaussa")
    parser.add_argument("--min_area", type=float, default=10.0, help="Minimalne pole plamki")
    parser.add_argument("--max_area", type=float, default=0.0, help="Maksymalne pole plamki, 0 = brak")
    parser.add_argument("--min_circularity", type=float, default=0.25, help="Minimalna kolistość konturu (0..1)")
    parser.add_argument("--max_aspect_ratio", type=float, default=3.0, help="Maksymalny stosunek boków bbox")
    parser.add_argument("--min_peak_intensity", type=float, default=160.0, help="Minimalna jasność lokalnego maksimum (0..255)")
    parser.add_argument("--min_solidity", type=float, default=0.8, help="Minimalna zwartość konturu (0..1)")
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
    parser.add_argument(
        "--use_single_object_ekf",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="W trybie single-object używa trackera EKF",
    )
    parser.add_argument("--experimental_mode", action="store_true", help="Włącza eksperymentalne heurystyki use-case trackingu")
    parser.add_argument(
        "--experimental_adaptive_association",
        action="store_true",
        help="Włącza eksperymentalne strojenie bramek i score parowania detekcji do torów.",
    )
    parser.add_argument("--max_distance", type=float, default=40.0, help="Maksymalny dystans przypisania detekcji")
    parser.add_argument("--max_missed", type=int, default=10, help="Ile klatek tor może zniknąć bez usunięcia")
    parser.add_argument("--distance_weight", type=float, default=1.0, help="Waga składnika dystansu w score parowania")
    parser.add_argument("--area_weight", type=float, default=0.35, help="Waga różnicy pola w score parowania")
    parser.add_argument("--circularity_weight", type=float, default=0.2, help="Waga różnicy circularity w score parowania")
    parser.add_argument("--brightness_weight", type=float, default=0.0, help="Waga różnicy jasności w score parowania")
    parser.add_argument("--min_match_score", type=float, default=0.5, help="Minimalny akceptowalny score parowania (0..1)")
    parser.add_argument("--speed_gate_gain", type=float, default=1.5, help="Wpływ prędkości toru na dynamiczną bramkę")
    parser.add_argument("--error_gate_gain", type=float, default=1.0, help="Wpływ historii błędów na dynamiczną bramkę")
    parser.add_argument("--min_dynamic_distance", type=float, default=12.0, help="Dolny limit dynamicznej bramki dystansu")
    parser.add_argument("--max_dynamic_distance", type=float, default=150.0, help="Górny limit dynamicznej bramki dystansu")
    parser.add_argument("--min_track_start_confidence", type=float, default=0.35, help="Minimalna pewność detekcji do startu nowego toru")
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
