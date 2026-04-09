from __future__ import annotations
import argparse
import glob
import os
import time
import sys
from typing import List, Optional, Sequence

from .io_paths import (
    build_measurement_stem,
    ensure_output_dir,
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
    print("CLI Buduję parser")
    gui_colors, gui_selection_modes, mp4_tool_path = _load_gui_metadata()
    parser = argparse.ArgumentParser(
        description="Śledzenie jasnej lub kolorowej plamki światła w video (np. MP4/MKV/AVI/MOV/WEBM). Obsługuje także opcjonalne wygładzanie filtrem Kalmana."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_cal = subparsers.add_parser("calibrate", help="Kalibracja kamery")
    p_cal.add_argument("--calib_dir", required=True, help="Katalog ze zdjęciami szachownicy")
    p_cal.add_argument("--rows", type=int, default=6, help="Liczba wewnętrznych narożników w wierszu")
    p_cal.add_argument("--cols", type=int, default=9, help="Liczba wewnętrznych narożników w kolumnie")
    p_cal.add_argument("--square_size", type=float, default=1.0, help="Rozmiar pola szachownicy")
    p_cal.add_argument("--output_file", default="camera_calib.npz", help="Plik wynikowy .npz")

    p_track = subparsers.add_parser("track", help="Śledzenie plamki")
    p_track.add_argument("--config", help="Pełna konfiguracja uruchomienia z pliku JSON/YAML (.json/.yaml/.yml)")
    p_track.add_argument("--video", help="Plik wejściowy wideo (np. MP4/MKV/AVI/MOV/WEBM)")
    p_track.add_argument("--calib_file", help="Plik kalibracji .npz")
    p_track.add_argument("--track_mode", choices=["brightness", "color"], default="brightness")
    p_track.add_argument("--threshold", type=int, default=200, help="Próg jasności")
    p_track.add_argument("--blur", type=int, default=11, help="Rozmiar filtra Gaussa")
    p_track.add_argument("--min_area", type=float, default=10.0, help="Minimalne pole plamki")
    p_track.add_argument("--max_area", type=float, default=0.0, help="Maksymalne pole plamki, 0 = brak")
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
    p_track.add_argument("--max_spots", type=int, default=1, help="Maksymalna liczba plamek na klatkę")
    p_track.add_argument("--max_distance", type=float, default=40.0, help="Maksymalny dystans przypisania między klatkami")
    p_track.add_argument("--max_missed", type=int, default=10, help="Maksymalna liczba zgubionych klatek dla toru")
    p_track.add_argument("--selection_mode", choices=["largest", "stablest", "longest"], default="stablest")
    p_track.add_argument("--all_tracks_csv", help="CSV ze wszystkimi trajektoriami")
    p_track.add_argument("--annotated_video", help="Wyjściowy plik wideo z narysowanymi trajektoriami (zalecane .mp4)")
    p_track.add_argument("--draw_all_tracks", action="store_true", help="Na filmie wynikowym rysuj wszystkie trajektorie")
    p_track.add_argument("--use_kalman", action="store_true", help="Wygładzanie trajektorii filtrem Kalmana")
    p_track.add_argument("--kalman_process_noise", type=float, default=1e-2, help="Szum procesu dla filtru Kalmana")
    p_track.add_argument("--kalman_measurement_noise", type=float, default=1e-1, help="Szum pomiaru dla filtru Kalmana")

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
    p_gui.add_argument("--blur", type=int, default=11)
    p_gui.add_argument("--min_area", type=float, default=10.0)
    p_gui.add_argument("--max_area", type=float, default=0.0)
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
    return parser


def normalize_legacy_argv(argv: Sequence[str]) -> List[str]:
    # Normalizujemy stary interfejs `--mode`, aby zachować zgodność wsteczną.
    args = list(argv)
    commands = {"calibrate", "track", "compare", "gui"}
    if not args:
        return ["gui"]
    if args[0] in commands:
        return args
    if "--mode" in args:
        mode_idx = args.index("--mode")
        if mode_idx + 1 < len(args):
            mode = args[mode_idx + 1]
            if mode in commands:
                return [mode, *args[:mode_idx], *args[mode_idx + 2 :]]
    return args


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
    argv = normalize_legacy_argv(sys.argv[1:])
    args = parser.parse_args(argv)

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
            run_config.input.video = resolve_analysis_input(run_config.input.video)
            base = build_measurement_stem(run_config.input.video)
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
            if not args.video:
                parser.error("Dla trybu track wymagany jest --video lub --config.")
            args.video = resolve_analysis_input(args.video)
            base = build_measurement_stem(args.video)
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
