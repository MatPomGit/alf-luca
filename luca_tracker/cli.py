from __future__ import annotations

import argparse
import glob
import sys
from typing import List, Optional, Sequence

DEFAULT_GUI_VIDEO_GLOB_PATTERNS = (
    "/output/*.mp4",
    "/output/*.mkv",
    "/output/*.avi",
    "/output/*.mov",
    "/output/*.m4v",
    "/output/*.webm",
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
    p_track.add_argument("--video", required=True, help="Plik wejściowy wideo (domyślnie szukany także w /output)")
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
    p_track.add_argument("--output_csv", default=None, help="CSV głównej trajektorii (domyślnie auto-nazwa w /output)")
    p_track.add_argument("--trajectory_png", help="PNG z wykresem trajektorii")
    p_track.add_argument("--report_csv", help="CSV z raportem jakości")
    p_track.add_argument("--report_pdf", help="PDF z raportem jakości")
    p_track.add_argument("--color_name", choices=[*gui_colors, "custom"], default="red", help="Preset koloru lub custom")
    p_track.add_argument("--hsv_lower", help="Dolna granica HSV np. 0,80,80")
    p_track.add_argument("--hsv_upper", help="Górna granica HSV np. 10,255,255")
    p_track.add_argument("--multi_track", action="store_true", help="Śledzenie wielu plamek jednocześnie")
    p_track.add_argument("--max_spots", type=int, default=10, help="Maksymalna liczba plamek na klatkę")
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
    p_cmp.add_argument("--reference", required=True, help="Referencyjny CSV (domyślnie z /output dla ścieżki relatywnej)")
    p_cmp.add_argument("--candidate", required=True, help="Porównywany CSV (domyślnie z /output dla ścieżki relatywnej)")
    p_cmp.add_argument("--output_csv", required=True, help="Wyjściowy CSV różnic (zapisywany do /output dla ścieżki relatywnej)")
    p_cmp.add_argument("--report_pdf", help="Opcjonalny raport PDF (zapisywany do /output dla ścieżki relatywnej)")

    p_gui = subparsers.add_parser("gui", help="GUI do strojenia parametrów i podglądu w czasie rzeczywistym")
    p_gui.add_argument("--video", help="Opcjonalny plik wejściowy wideo (domyślnie ładowane są pliki z katalogu /output)")
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
    p_gui.add_argument("--max_spots", type=int, default=10)
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
            parser.error("Dla trybu GUI wymagany jest plik wideo. Podaj --video lub umieść plik *.mp4/*.mkv/*.avi/*.mov/*.m4v/*.webm w katalogu /output.")

    if args.command == "calibrate":
        # Import lokalny ogranicza wymagania środowiskowe do użytego trybu.
        from .tracking import calibrate_camera

        calibrate_camera(args.calib_dir, args.rows, args.cols, args.square_size, args.output_file)
    elif args.command == "track":
        from .tracking import track_video

        track_video(args)
    elif args.command == "compare":
        from .reports import compare_csv

        compare_csv(args.reference, args.candidate, args.output_csv, args.report_pdf)
    elif args.command == "gui":
        from .gui import GUIEnvironmentError, run_gui

        try:
            run_gui(args)
        except GUIEnvironmentError as exc:
            # Komunikat celowo krótki i praktyczny, aby użytkownik mógł szybko naprawić środowisko.
            raise SystemExit(f"Błąd uruchamiania GUI: {exc}") from exc
    else:
        parser.print_help()
