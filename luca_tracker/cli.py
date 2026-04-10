from __future__ import annotations
import argparse
import glob
import os
import sys
import time
from typing import List, Optional

from . import __version__
from .io_paths import (
    build_measurement_stem,
    ensure_output_dir,
    parse_camera_source,
    resolve_analysis_input,
    resolve_output_path,
    with_default,
)

DEFAULT_GUI_VIDEO_GLOB_PATTERNS = (
    "video/*.mp4",
    "video/*.mkv",
    "video/*.avi",
    "video/*.mov",
    "video/*.m4v",
    "video/*.webm",
    "*.mp4",
    "*.mkv",
    "*.avi",
    "*.mov",
    "*.m4v",
    "*.webm",
)
DEFAULT_GUI_COLOR_NAMES = ["red", "green", "blue", "white", "yellow"]
DEFAULT_GUI_SELECTION_MODES = ["largest", "stablest", "longest"]
DEFAULT_MP4_QUALITY_TOOL_PATH = "tools/video_tool.py"
DEFAULT_CONSOLE_CLOSE_TIMEOUT_SEC = 4


def _load_gui_metadata() -> tuple[List[str], List[str], str]:
    """Zwraca metadane GUI bez wymuszania zależności od OpenCV/Kivy.

    Funkcja próbuje pobrać wartości z modułu `gui`, ale jeśli środowisko nie ma
    bibliotek GUI (np. tylko analiza CLI), używa bezpiecznych wartości domyślnych.
    """
    try:
        from .gui import GUI_COLOR_NAMES, GUI_SELECTION_MODES, MP4_QUALITY_TOOL_PATH

        return list(GUI_COLOR_NAMES), list(GUI_SELECTION_MODES), MP4_QUALITY_TOOL_PATH
    except Exception:
        # Celowo łagodny fallback, żeby `--help` działało bez ciężkich zależności.
        return list(DEFAULT_GUI_COLOR_NAMES), list(DEFAULT_GUI_SELECTION_MODES), DEFAULT_MP4_QUALITY_TOOL_PATH


def build_parser():
    # Metadane GUI ładujemy leniwie, aby parser CLI działał nawet bez OpenCV/Kivy.
    gui_colors, gui_selection_modes, mp4_tool_path = _load_gui_metadata()
    parser = argparse.ArgumentParser(
        description="Śledzenie jasnej lub kolorowej plamki światła w materiale wideo albo na kamerze na żywo. Obsługuje także opcjonalne wygładzanie filtrem Kalmana."
    )
    # Globalny przełącznik wersji pozwala szybko sprawdzić numer buildu z CLI.
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_cal = subparsers.add_parser("calibrate", help="Kalibracja kamery")
    p_cal.add_argument("--calib_dir", required=True, help="Katalog ze zdjęciami szachownicy")
    p_cal.add_argument("--rows", type=int, default=6, help="Liczba wewnętrznych narożników w wierszu")
    p_cal.add_argument("--cols", type=int, default=9, help="Liczba wewnętrznych narożników w kolumnie")
    p_cal.add_argument("--square_size", type=float, default=1.0, help="Rozmiar pola szachownicy")
    p_cal.add_argument("--output_file", default="camera_calib.npz", help="Plik wynikowy .npz")

    p_track = subparsers.add_parser("track", help="Śledzenie plamki")
    p_track.add_argument("--config", help="Pełna konfiguracja uruchomienia z pliku JSON/YAML (.json/.yaml/.yml)")
    track_source = p_track.add_mutually_exclusive_group()
    track_source.add_argument("--video", help="Plik wejściowy wideo (np. MP4/MKV/AVI/MOV/WEBM)")
    track_source.add_argument("--camera", help="Kamera na żywo: indeks OpenCV (np. 0) albo ścieżka urządzenia")
    p_track.add_argument("--calib_file", help="Plik kalibracji .npz")
    p_track.add_argument("--track_mode", choices=["brightness", "color"], default="brightness")
    p_track.add_argument("--threshold", type=int, default=200, help="Próg jasności")
    p_track.add_argument(
        "--threshold_mode",
        choices=["fixed", "otsu", "adaptive"],
        default="fixed",
        help="Tryb progowania jasności (stały, Otsu lub adaptacyjny).",
    )
    p_track.add_argument(
        "--adaptive_block_size",
        type=int,
        default=31,
        help="Rozmiar okna dla progowania adaptacyjnego (nieparzysty, >=3).",
    )
    p_track.add_argument("--adaptive_c", type=float, default=5.0, help="Stała C odejmowana w progu adaptacyjnym.")
    p_track.add_argument("--use_clahe", action="store_true", help="Włącz CLAHE przed progowaniem (normalizacja lokalnego kontrastu).")
    p_track.add_argument("--blur", type=int, default=11, help="Rozmiar filtra Gaussa")
    p_track.add_argument("--min_area", type=float, default=10.0, help="Minimalne pole plamki")
    p_track.add_argument("--max_area", type=float, default=0.0, help="Maksymalne pole plamki, 0 = brak")
    p_track.add_argument(
        "--min_circularity",
        type=float,
        default=0.0,
        help="Minimalna kolistość (0..1); wyższa wartość redukuje fałszywe trafienia o nieregularnym kształcie.",
    )
    p_track.add_argument(
        "--max_aspect_ratio",
        type=float,
        default=6.0,
        help="Maksymalny stosunek boków bbox; niższa wartość odrzuca podłużne artefakty i smugi.",
    )
    p_track.add_argument(
        "--min_peak_intensity",
        type=float,
        default=0.0,
        help="Minimalna jasność lokalnego maksimum (0..255); zwiększenie odcina słabe odblaski i szum.",
    )
    p_track.add_argument(
        "--min_solidity",
        type=float,
        default=None,
        help="Opcjonalna minimalna zwartość konturu (0..1); pomaga usuwać mocno postrzępione/wnękowe kształty.",
    )
    p_track.add_argument("--erode_iter", type=int, default=2, help="Liczba iteracji erozji")
    p_track.add_argument("--dilate_iter", type=int, default=4, help="Liczba iteracji dylatacji")
    p_track.add_argument("--roi", help="Obszar ROI w formacie x,y,w,h")
    p_track.add_argument("--interactive", action="store_true", help="Interaktywny dobór parametrów")
    p_track.add_argument("--display", action="store_true", help="Podgląd śledzenia")
    p_track.add_argument("--output_csv", default="tracking_results.csv", help="CSV głównej trajektorii")
    p_track.add_argument("--trajectory_png", help="PNG z wykresem trajektorii")
    p_track.add_argument("--report_csv", help="CSV z raportem jakości")
    p_track.add_argument("--report_pdf", help="PDF z raportem jakości")
    p_track.add_argument("--color_name", choices=[*gui_colors, "custom"], default="red", help="Preset koloru lub custom")
    p_track.add_argument("--hsv_lower", help="Dolna granica HSV np. 0,80,80")
    p_track.add_argument("--hsv_upper", help="Górna granica HSV np. 10,255,255")
    p_track.add_argument("--multi_track", action="store_true", help="Śledzenie wielu plamek jednocześnie")
    p_track.add_argument(
        "--use_single_object_ekf",
        action="store_true",
        default=True,
        help="W trybie single-object użyj SingleObjectEKFTracker dla większej odporności na artefakty.",
    )
    p_track.add_argument(
        "--no_single_object_ekf",
        action="store_false",
        dest="use_single_object_ekf",
        help="Wyłącz EKF w trybie single-object (tryb diagnostyczny/raw detekcje).",
    )
    p_track.add_argument("--max_spots", type=int, default=1, help="Maksymalna liczba plamek na klatkę")
    p_track.add_argument("--max_distance", type=float, default=40.0, help="Maksymalny dystans przypisania między klatkami")
    p_track.add_argument("--max_missed", type=int, default=10, help="Maksymalna liczba zgubionych klatek dla toru")
    p_track.add_argument("--distance_weight", type=float, default=1.0, help="Waga składnika dystansu w score parowania")
    p_track.add_argument("--area_weight", type=float, default=0.35, help="Waga różnicy pola w score parowania")
    p_track.add_argument("--circularity_weight", type=float, default=0.2, help="Waga różnicy circularity w score parowania")
    p_track.add_argument("--brightness_weight", type=float, default=0.0, help="Waga różnicy średniej jasności w score parowania")
    p_track.add_argument("--min_match_score", type=float, default=0.5, help="Minimalny akceptowalny score pary track-detection (0..1)")
    p_track.add_argument("--speed_gate_gain", type=float, default=1.5, help="Wpływ prędkości toru na dynamiczną bramkę dystansu")
    p_track.add_argument("--error_gate_gain", type=float, default=1.0, help="Wpływ historii błędów dopasowania na dynamiczną bramkę")
    p_track.add_argument("--min_dynamic_distance", type=float, default=12.0, help="Dolny limit dynamicznej bramki dystansu")
    p_track.add_argument("--max_dynamic_distance", type=float, default=150.0, help="Górny limit dynamicznej bramki dystansu")
    p_track.add_argument("--selection_mode", choices=["largest", "stablest", "longest"], default="stablest")
    p_track.add_argument("--all_tracks_csv", help="CSV ze wszystkimi trajektoriami")
    p_track.add_argument("--annotated_video", help="Wyjściowy plik wideo z narysowanymi trajektoriami (zalecane .mp4)")
    p_track.add_argument("--draw_all_tracks", action="store_true", help="Na filmie wynikowym rysuj wszystkie trajektorie")
    p_track.add_argument("--use_kalman", action="store_true", help="Wygładzanie trajektorii filtrem Kalmana")
    p_track.add_argument("--kalman_process_noise", type=float, default=3e-2, help="Szum procesu dla filtru Kalmana")
    p_track.add_argument("--kalman_measurement_noise", type=float, default=5e-2, help="Szum pomiaru dla filtru Kalmana")
    p_track.add_argument("--pnp_object_points", help="Punkty 3D świata dla PnP w formacie X,Y,Z;X,Y,Z;... (min. 4)")
    p_track.add_argument("--pnp_image_points", help="Punkty 2D obrazu dla PnP w formacie x,y;x,y;... (min. 4)")
    p_track.add_argument("--pnp_world_plane_z", type=float, default=0.0, help="Wysokość płaszczyzny świata Z dla rekonstrukcji XYZ")

    p_cmp = subparsers.add_parser("compare", help="Porównanie dwóch CSV")
    p_cmp.add_argument("--reference", required=True, help="Referencyjny CSV")
    p_cmp.add_argument("--candidate", required=True, help="Porównywany CSV")
    p_cmp.add_argument("--output_csv", required=True, help="Wyjściowy CSV różnic")
    p_cmp.add_argument("--report_pdf", help="Opcjonalny raport PDF")

    p_gui = subparsers.add_parser("gui", help="GUI do strojenia parametrów i podglądu w czasie rzeczywistym")
    p_gui.add_argument("--video", help="Opcjonalny plik wejściowy wideo (np. MP4/MKV/AVI/MOV/WEBM; domyślnie ładowane są pliki z folderu video/)")
    p_gui.add_argument("--calib_file", help="Plik kalibracji .npz (opcjonalnie)")
    p_gui.add_argument("--track_mode", choices=["brightness", "color"], default="brightness")
    p_gui.add_argument("--threshold", type=int, default=200)
    p_gui.add_argument("--threshold_mode", choices=["fixed", "otsu", "adaptive"], default="fixed")
    p_gui.add_argument("--adaptive_block_size", type=int, default=31)
    p_gui.add_argument("--adaptive_c", type=float, default=5.0)
    p_gui.add_argument("--use_clahe", action="store_true")
    p_gui.add_argument("--blur", type=int, default=11)
    p_gui.add_argument("--min_area", type=float, default=10.0)
    p_gui.add_argument("--max_area", type=float, default=0.0)
    p_gui.add_argument(
        "--min_circularity",
        type=float,
        default=0.0,
        help="Minimalna kolistość (0..1); większa wartość zmniejsza liczbę nieregularnych fałszywych trafień.",
    )
    p_gui.add_argument(
        "--max_aspect_ratio",
        type=float,
        default=6.0,
        help="Maksymalny stosunek boków bbox; niższa wartość odrzuca smugi i wydłużone artefakty.",
    )
    p_gui.add_argument(
        "--min_peak_intensity",
        type=float,
        default=0.0,
        help="Minimalna jasność lokalnego maksimum (0..255); podniesienie progu filtruje słabe refleksy.",
    )
    p_gui.add_argument(
        "--min_solidity",
        type=float,
        default=None,
        help="Opcjonalna minimalna zwartość (0..1); pomaga usunąć postrzępione lub wklęsłe kontury.",
    )
    p_gui.add_argument("--erode_iter", type=int, default=2)
    p_gui.add_argument("--dilate_iter", type=int, default=4)
    p_gui.add_argument("--roi", help="Obszar ROI x,y,w,h")
    p_gui.add_argument("--color_name", choices=gui_colors, default="red")
    p_gui.add_argument("--multi_track", action="store_true")
    p_gui.add_argument("--max_spots", type=int, default=1)
    p_gui.add_argument("--max_distance", type=float, default=40.0)
    p_gui.add_argument("--max_missed", type=int, default=10)
    p_gui.add_argument("--selection_mode", choices=gui_selection_modes, default="stablest")
    p_gui.add_argument("--gui_config", default="config/gui_display.yaml", help="Plik YAML z domyślnymi wartościami suwaków GUI.")
    p_gui.add_argument("--mp4_tool_path", default=mp4_tool_path, help="Odnośnik do narzędzia QA MP4 pokazywany w GUI (domyślnie: tools/video_tool.py).")

    p_ros2 = subparsers.add_parser("ros2", help="ROS2 node: śledzenie z kamery fizycznej i publikacja danych")
    p_ros2.add_argument("--video_device", default="/dev/video0", help="Źródło kamery (np. /dev/video0 albo numer kamery)")
    p_ros2.add_argument("--camera_index", type=int, help="Indeks kamery OpenCV, np. 0 (ma priorytet nad --video_device)")
    p_ros2.add_argument("--node_name", default="luca_tracker_node", help="Nazwa ROS2 node")
    p_ros2.add_argument("--topic", default="/luca_tracker/tracking", help="Topic ROS2 dla danych trackingu (std_msgs/String JSON)")
    p_ros2.add_argument("--fps", type=float, default=30.0, help="Docelowa częstotliwość odczytu/publikacji")
    p_ros2.add_argument("--frame_width", type=int, default=0, help="Szerokość klatki (0 = domyślna kamery)")
    p_ros2.add_argument("--frame_height", type=int, default=0, help="Wysokość klatki (0 = domyślna kamery)")
    p_ros2.add_argument("--display", action="store_true", help="Podgląd śledzenia (q = zakończ)")
    p_ros2.add_argument("--turtle_follow", action="store_true", help="Steruj turtlesim (/turtle1/cmd_vel), aby podążał za plamką")
    p_ros2.add_argument("--turtle_cmd_topic", default="/turtle1/cmd_vel", help="Topic komend prędkości turtlesim (Twist)")
    p_ros2.add_argument("--turtle_linear_speed", type=float, default=1.0, help="Maksymalna prędkość liniowa turtle")
    p_ros2.add_argument("--turtle_min_linear_speed", type=float, default=0.05, help="Minimalna prędkość liniowa przy dojazdach")
    p_ros2.add_argument("--turtle_angular_gain", type=float, default=1.2, help="Wzmocnienie P dla skrętu")
    p_ros2.add_argument("--turtle_angular_d_gain", type=float, default=0.35, help="Wzmocnienie D dla skrętu (kompensacja ruchu)")
    p_ros2.add_argument("--turtle_max_angular_speed", type=float, default=1.6, help="Maksymalna prędkość kątowa")
    p_ros2.add_argument("--turtle_center_deadband", type=float, default=0.04, help="Martwa strefa błędu kierunku (znormalizowana)")
    p_ros2.add_argument("--turtle_turn_in_place_threshold", type=float, default=0.65, help="Próg błędu, powyżej którego turtle obraca się w miejscu")
    p_ros2.add_argument("--turtle_target_radius_px", type=float, default=110.0, help="Docelowy promień plamki (proxy dystansu)")
    p_ros2.add_argument("--turtle_radius_arrived_px", type=float, default=130.0, help="Promień plamki oznaczający osiągnięcie celu (stop)")
    p_ros2.add_argument("--turtle_tracking_alpha", type=float, default=0.25, help="Współczynnik EMA pozycji plamki (x,y,r)")
    p_ros2.add_argument("--turtle_cmd_alpha", type=float, default=0.35, help="Współczynnik EMA komend ruchu")
    p_ros2.add_argument("--turtle_linear_accel_limit", type=float, default=1.2, help="Limit przyspieszenia liniowego")
    p_ros2.add_argument("--turtle_angular_accel_limit", type=float, default=2.2, help="Limit przyspieszenia kątowego")
    p_ros2.add_argument("--turtle_log_every_n_frames", type=int, default=10, help="Log diagnostyczny sterowania co N klatek")
    p_ros2.add_argument("--turtle_search_angular_speed", type=float, default=0.0, help="(Legacy) nieużywane: przy braku detekcji turtle zatrzymuje się")
    p_ros2.add_argument("--track_mode", choices=["brightness", "color"], default="brightness")
    p_ros2.add_argument("--threshold", type=int, default=200, help="Próg jasności")
    p_ros2.add_argument(
        "--threshold_mode",
        choices=["fixed", "otsu", "adaptive"],
        default="fixed",
        help="Tryb progowania jasności (stały, Otsu lub adaptacyjny).",
    )
    p_ros2.add_argument(
        "--adaptive_block_size",
        type=int,
        default=31,
        help="Rozmiar okna dla progowania adaptacyjnego (nieparzysty, >=3).",
    )
    p_ros2.add_argument("--adaptive_c", type=float, default=5.0, help="Stała C odejmowana w progu adaptacyjnym.")
    p_ros2.add_argument("--use_clahe", action="store_true", help="Włącz CLAHE przed progowaniem (normalizacja lokalnego kontrastu).")
    p_ros2.add_argument("--blur", type=int, default=11, help="Rozmiar filtra Gaussa")
    p_ros2.add_argument("--min_area", type=float, default=10.0, help="Minimalne pole plamki")
    p_ros2.add_argument("--max_area", type=float, default=0.0, help="Maksymalne pole plamki, 0 = brak")
    p_ros2.add_argument("--erode_iter", type=int, default=2, help="Liczba iteracji erozji")
    p_ros2.add_argument("--dilate_iter", type=int, default=4, help="Liczba iteracji dylatacji")
    p_ros2.add_argument("--max_spots", type=int, default=1, help="Maksymalna liczba detekcji publikowana na klatkę (używana top-1)")
    p_ros2.add_argument("--roi", help="Obszar ROI w formacie x,y,w,h")
    p_ros2.add_argument("--color_name", choices=[*gui_colors, "custom"], default="red", help="Preset koloru lub custom")
    p_ros2.add_argument("--hsv_lower", help="Dolna granica HSV np. 0,80,80")
    p_ros2.add_argument("--hsv_upper", help="Górna granica HSV np. 10,255,255")
    return parser


def pick_default_gui_video() -> Optional[str]:
    # Szukamy domyślnego pliku wideo według listy najczęściej używanych rozszerzeń.
    for pattern in DEFAULT_GUI_VIDEO_GLOB_PATTERNS:
        matches = sorted(glob.glob(pattern))
        if matches:
            return matches[0]
    return None


def main():
    # Parser i argumenty CLI są przetwarzane bez importu ciężkich modułów.
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:])

    if args.command == "gui" and not getattr(args, "video", None):
        args.video = pick_default_gui_video()
        if not args.video:
            parser.error("Dla trybu GUI wymagany jest plik wideo. Podaj --video lub umieść plik *.mp4/*.mkv/*.avi/*.mov/*.m4v/*.webm w katalogu ./video.")

    if args.command == "calibrate":
        ensure_output_dir()
        args.output_file = resolve_output_path(args.output_file)
        # Import lokalny ogranicza wymagania środowiskowe do użytego trybu.
        from .tracking import calibrate_camera

        calibrate_camera(args.calib_dir, args.rows, args.cols, args.square_size, args.output_file)
    elif args.command == "track":
        from .config_model import load_run_config, run_config_to_pipeline_config
        from .tracking import track_video

        ensure_output_dir()
        if args.config:
            run_config = load_run_config(args.config)
            if bool(run_config.input.video) == bool(run_config.input.camera):
                parser.error("Plik konfiguracyjny musi wskazywać dokładnie jedno źródło: `input.video` albo `input.camera`.")
            source_label = run_config.input.video or f"camera:{run_config.input.camera}"
            if run_config.input.video:
                run_config.input.video = resolve_analysis_input(run_config.input.video)
            base = build_measurement_stem(source_label)
            output_csv_cfg = with_default(run_config.eval.output_csv, f"{base}_track.csv")
            if output_csv_cfg == "tracking_results.csv":
                output_csv_cfg = f"{base}_tracking_results.csv"
            run_config.eval.output_csv = resolve_output_path(output_csv_cfg)
            run_config.eval.trajectory_png = resolve_output_path(
                with_default(run_config.eval.trajectory_png, f"{base}_trajectory.png")
            )
            run_config.eval.report_csv = resolve_output_path(with_default(run_config.eval.report_csv, f"{base}_report.csv"))
            run_config.eval.report_pdf = resolve_output_path(with_default(run_config.eval.report_pdf, f"{base}_report.pdf"))
            if run_config.eval.all_tracks_csv:
                run_config.eval.all_tracks_csv = resolve_output_path(run_config.eval.all_tracks_csv)
            if run_config.eval.annotated_video:
                run_config.eval.annotated_video = resolve_output_path(run_config.eval.annotated_video)
            track_video(run_config_to_pipeline_config(run_config))
        else:
            if not args.video and not args.camera:
                parser.error("Dla trybu track wymagane jest jedno źródło: --video albo --camera.")
            if args.video:
                args.video = resolve_analysis_input(args.video)
                args.source_label = args.video
                args.is_live_source = False
            else:
                args.video = parse_camera_source(args.camera)
                args.source_label = f"camera:{args.camera}"
                args.is_live_source = True
            base = build_measurement_stem(args.source_label)
            output_csv_value = args.output_csv
            if output_csv_value == "tracking_results.csv":
                output_csv_value = f"{base}_tracking_results.csv"
            args.output_csv = resolve_output_path(output_csv_value)
            args.trajectory_png = resolve_output_path(args.trajectory_png or f"{base}_trajectory.png")
            args.report_csv = resolve_output_path(args.report_csv or f"{base}_report.csv")
            args.report_pdf = resolve_output_path(args.report_pdf or f"{base}_report.pdf")
            if args.all_tracks_csv:
                args.all_tracks_csv = resolve_output_path(args.all_tracks_csv)
            if args.annotated_video:
                args.annotated_video = resolve_output_path(args.annotated_video)
            if args.calib_file:
                args.calib_file = resolve_analysis_input(args.calib_file)
            track_video(args)
    elif args.command == "compare":
        from .reports import compare_csv

        ensure_output_dir()
        args.reference = resolve_analysis_input(args.reference)
        args.candidate = resolve_analysis_input(args.candidate)
        args.output_csv = resolve_output_path(args.output_csv)
        if args.report_pdf:
            args.report_pdf = resolve_output_path(args.report_pdf)
        compare_csv(args.reference, args.candidate, args.output_csv, args.report_pdf)
    elif args.command == "gui":
        try:
            from .gui import GUIEnvironmentError, run_gui
        except ImportError as exc:
            # Import modułu GUI może się nie udać już na etapie ładowania (np. brak cv2).
            raise SystemExit(f"Błąd zależności GUI: {exc}") from exc

        try:
            run_gui(args)
        except ImportError as exc:
            # Wspólny komunikat dla brakujących zależności GUI (Kivy/OpenCV/backend okna).
            raise SystemExit(f"Błąd zależności GUI: {exc}") from exc
        except GUIEnvironmentError as exc:
            # Komunikat celowo krótki i praktyczny, aby użytkownik mógł szybko naprawić środowisko.
            raise SystemExit(f"Błąd uruchamiania GUI: {exc}") from exc
    elif args.command == "ros2":
        from .ros2_node import run_ros2_tracker_node

        run_ros2_tracker_node(args)
    else:
        parser.print_help()

    if args.command in {"calibrate", "track", "compare"}:
        print("\n[OK] Analiza zakończona pomyślnie.")
        print("\a\a", end="")
        timeout_sec = int(os.getenv("LUCA_CONSOLE_CLOSE_TIMEOUT", DEFAULT_CONSOLE_CLOSE_TIMEOUT_SEC))
        print(f"[INFO] Okno konsoli zostanie zamknięte za {timeout_sec} s.")
        time.sleep(max(0, timeout_sec))
        if os.name == "nt":
            os.system("exit")
