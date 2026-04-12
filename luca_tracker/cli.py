from __future__ import annotations
import argparse
import glob
import os
import sys
import time
from typing import List, Optional

from . import __version__

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
LEGACY_EXIT_ENV_VAR = "LUCA_CLI_LEGACY_EXIT_BEHAVIOR"


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
    p_cal.add_argument(
        "--interactive-shell",
        action="store_true",
        help="Legacy: po zakończeniu zadania odtwórz dźwięk i odczekaj przed zamknięciem konsoli.",
    )

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
        "--min_detection_confidence",
        type=float,
        default=0.0,
        help="Minimalne confidence detekcji (0..1); filtr anty-false-positive gdy nie ma prawdziwej plamki.",
    )
    p_track.add_argument(
        "--min_detection_score",
        type=float,
        default=0.0,
        help="Minimalny score rankingu detekcji (0..1); odrzuca słabe bloby mimo wysokiej pozycji względnej.",
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
    p_track.add_argument(
        "--interactive-shell",
        action="store_true",
        help="Legacy: po zakończeniu zadania odtwórz dźwięk i odczekaj przed zamknięciem konsoli.",
    )

    p_cmp = subparsers.add_parser("compare", help="Porównanie dwóch CSV")
    p_cmp.add_argument("--reference", required=True, help="Referencyjny CSV")
    p_cmp.add_argument("--candidate", required=True, help="Porównywany CSV")
    p_cmp.add_argument("--output_csv", required=True, help="Wyjściowy CSV różnic")
    p_cmp.add_argument("--report_pdf", help="Opcjonalny raport PDF")
    p_cmp.add_argument(
        "--interactive-shell",
        action="store_true",
        help="Legacy: po zakończeniu zadania odtwórz dźwięk i odczekaj przed zamknięciem konsoli.",
    )

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
    p_ros2.add_argument("--node_name", default="detector_node", help="Nazwa ROS2 node")
    p_ros2.add_argument("--topic", default="/luca_tracker/tracking", help="Topic ROS2 dla danych trackingu (std_msgs/String JSON)")
    p_ros2.add_argument("--spot_id", type=int, default=0, help="ID (indeks) detekcji do publikacji jako obiekt główny")
    p_ros2.add_argument("--fps", type=float, default=30.0, help="Docelowa częstotliwość odczytu/publikacji")
    p_ros2.add_argument("--frame_width", type=int, default=0, help="Szerokość klatki (0 = domyślna kamery)")
    p_ros2.add_argument("--frame_height", type=int, default=0, help="Wysokość klatki (0 = domyślna kamery)")
    p_ros2.add_argument("--display", action="store_true", help="Podgląd śledzenia (q = zakończ)")
    p_ros2.add_argument(
        "--run_metadata_json",
        help="Ścieżka do wcześniej przygotowanego pliku JSON (np. *.run.json) z metadanymi runu publikowanymi na ROS2.",
    )
    p_ros2.add_argument(
        "--message_schema",
        default="luca_tracker.ros2.tracking.v1",
        help="Nazwa/sygnatura schematu JSON publikowanego na topicu ROS2.",
    )
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
    p_ros2.add_argument("--calib_file", help="Plik kalibracji .npz z camera_matrix i dist_coeffs")
    p_ros2.add_argument("--pnp_object_points", help="Punkty 3D świata: X,Y,Z;X,Y,Z;... (min. 4)")
    p_ros2.add_argument("--pnp_image_points", help="Punkty 2D obrazu: x,y;x,y;... (min. 4)")
    p_ros2.add_argument("--pnp_world_plane_z", type=float, default=0.0, help="Płaszczyzna świata Z dla rekonstrukcji XYZ")
    return parser


def pick_default_gui_video() -> Optional[str]:
    # Szukamy domyślnego pliku wideo według listy najczęściej używanych rozszerzeń.
    for pattern in DEFAULT_GUI_VIDEO_GLOB_PATTERNS:
        matches = sorted(glob.glob(pattern))
        if matches:
            return matches[0]
    return None


def _is_env_truthy(value: Optional[str]) -> bool:
    """Zwraca True, gdy wartość ENV reprezentuje stan włączony."""
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _should_use_legacy_exit_behavior(args: argparse.Namespace) -> bool:
    """Wybiera legacy zachowanie shella wyłącznie po jawnej zgodzie flagą lub ENV."""
    if getattr(args, "interactive_shell", False):
        return True
    return _is_env_truthy(os.getenv(LEGACY_EXIT_ENV_VAR))


def _handle_post_command_exit_behavior(args: argparse.Namespace) -> None:
    """Obsługuje końcowe zachowanie CLI po wykonaniu komend analitycznych."""
    if args.command not in {"calibrate", "track", "compare"}:
        return

    print("\n[OK] Analiza zakończona pomyślnie.")

    # Tryb domyślny (CI i skrypty) kończy proces natychmiast bez efektów ubocznych terminala.
    if not _should_use_legacy_exit_behavior(args):
        return

    # Legacy: zachowujemy sygnał dźwiękowy i opóźnienie tylko dla jawnie włączonego trybu.
    print("\a\a", end="")
    timeout_sec = int(os.getenv("LUCA_CONSOLE_CLOSE_TIMEOUT", DEFAULT_CONSOLE_CLOSE_TIMEOUT_SEC))
    print(f"[INFO] Okno konsoli zostanie zamknięte za {timeout_sec} s.")
    time.sleep(max(0, timeout_sec))


def main():
    # Parser i argumenty CLI są przetwarzane bez importu ciężkich modułów.
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:])

    if args.command == "gui" and not getattr(args, "video", None):
        args.video = pick_default_gui_video()
        if not args.video:
            parser.error("Dla trybu GUI wymagany jest plik wideo. Podaj --video lub umieść plik *.mp4/*.mkv/*.avi/*.mov/*.m4v/*.webm w katalogu ./video.")

    if args.command == "calibrate":
        from luca_tracking.application_services import run_calibrate

        run_calibrate(args.calib_dir, args.rows, args.cols, args.square_size, args.output_file)
    elif args.command == "track":
        from luca_tracking.application_services import run_tracking

        try:
            run_tracking(args)
        except ValueError as exc:
            parser.error(str(exc))
    elif args.command == "compare":
        from luca_tracking.application_services import run_compare

        run_compare(args.reference, args.candidate, args.output_csv, args.report_pdf)
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
        from luca_tracking.application_services import run_ros2

        run_ros2(args)
    else:
        parser.print_help()

    _handle_post_command_exit_behavior(args)
