from __future__ import annotations

import argparse

from luca_input import (
    add_shared_calibration_options,
    add_shared_detection_options,
    add_shared_postprocess_options,
    add_shared_reporting_options,
    add_shared_ros2_runtime_options,
    add_shared_runtime_source_options,
    add_shared_tracking_options,
)


def build_parser() -> argparse.ArgumentParser:
    """Buduje parser dla interfejsu CLI opartego wyłącznie o usługi aplikacyjne."""
    parser = argparse.ArgumentParser(
        description="Interfejs CLI LUCA dla przypadków użycia: kalibracja, tracking, porównanie i ROS2."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_calibrate = subparsers.add_parser("calibrate", help="Kalibracja kamery")
    p_calibrate.add_argument("--calib_dir", required=True, help="Katalog ze zdjęciami szachownicy")
    p_calibrate.add_argument("--rows", type=int, default=6, help="Liczba wewnętrznych narożników w wierszu")
    p_calibrate.add_argument("--cols", type=int, default=9, help="Liczba wewnętrznych narożników w kolumnie")
    p_calibrate.add_argument("--square_size", type=float, default=1.0, help="Rozmiar pola szachownicy")
    p_calibrate.add_argument("--output_file", default="camera_calib.npz", help="Plik wynikowy .npz")

    p_track = subparsers.add_parser("track", help="Śledzenie plamki")
    p_track.add_argument("--config", help="Pełna konfiguracja uruchomienia z pliku JSON/YAML (.json/.yaml/.yml)")
    # Najpierw dodajemy zunifikowane opcje źródła, aby opisy `--help` były spójne między adapterami.
    track_source = p_track.add_mutually_exclusive_group()
    add_shared_runtime_source_options(track_source)
    p_track.add_argument("--display", action="store_true", help="Podgląd śledzenia")
    p_track.add_argument(
        "--auto_tune_from_video",
        help="Nagranie referencyjne do automatycznego doboru parametrów i zapisania presetu live.",
    )
    p_track.add_argument(
        "--auto_tune_preset_name",
        default="auto_live",
        help="Nazwa zapisywanego presetu wyznaczonego automatycznie z nagrania.",
    )
    p_track.add_argument(
        "--live_tracking_preset",
        help="Nazwa gotowego presetu parametrów do użycia podczas śledzenia kamerą na żywo.",
    )
    p_track.add_argument(
        "--tracking_presets_file",
        default="config/live_tracking_presets.json",
        help="Plik JSON z presetami trackingu live.",
    )
    p_track.add_argument(
        "--list_live_tracking_presets",
        action="store_true",
        help="Wypisuje dostępne presety live z pliku i kończy działanie.",
    )

    # Wspólne opcje są centralizowane, aby `--help` miał identyczne nazwy i opisy między adapterami.
    add_shared_detection_options(p_track)
    add_shared_tracking_options(p_track)
    add_shared_calibration_options(p_track)
    add_shared_reporting_options(p_track)
    add_shared_postprocess_options(p_track)

    p_compare = subparsers.add_parser("compare", help="Porównanie dwóch CSV")
    p_compare.add_argument("--reference", required=True, help="Referencyjny CSV")
    p_compare.add_argument("--candidate", required=True, help="Porównywany CSV")
    p_compare.add_argument("--output_csv", required=True, help="Wyjściowy CSV różnic")
    p_compare.add_argument("--report_pdf", help="Opcjonalny raport PDF")

    p_ros2 = subparsers.add_parser("ros2", help="ROS2 node: śledzenie z kamery fizycznej i publikacja danych")
    add_shared_ros2_runtime_options(p_ros2)
    add_shared_detection_options(p_ros2)
    add_shared_tracking_options(p_ros2)
    add_shared_calibration_options(p_ros2)
    return parser
