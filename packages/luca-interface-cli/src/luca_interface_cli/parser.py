from __future__ import annotations

import argparse

from luca_input import (
    add_shared_calibration_options,
    add_shared_detection_options,
    add_shared_postprocess_options,
    add_shared_reporting_options,
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
    track_source = p_track.add_mutually_exclusive_group()
    track_source.add_argument("--video", help="Plik wejściowy wideo (np. MP4/MKV/AVI/MOV/WEBM)")
    track_source.add_argument("--camera", help="Kamera na żywo: indeks OpenCV (np. 0) albo ścieżka urządzenia")
    p_track.add_argument("--display", action="store_true", help="Podgląd śledzenia")

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
    p_ros2.add_argument("--video_device", default="/dev/video0", help="Źródło kamery")
    p_ros2.add_argument("--camera_index", type=int, help="Indeks kamery OpenCV")
    p_ros2.add_argument("--node_name", default="detector_node", help="Nazwa ROS2 node")
    p_ros2.add_argument("--topic", default="/luca_tracker/tracking", help="Topic ROS2 dla danych")
    p_ros2.add_argument("--spot_id", type=int, default=0, help="ID detekcji głównej")
    p_ros2.add_argument("--fps", type=float, default=30.0, help="Docelowa częstotliwość odczytu/publikacji")
    p_ros2.add_argument("--frame_width", type=int, default=0, help="Szerokość klatki (0 = domyślna)")
    p_ros2.add_argument("--frame_height", type=int, default=0, help="Wysokość klatki (0 = domyślna)")
    p_ros2.add_argument("--display", action="store_true", help="Podgląd śledzenia")
    add_shared_detection_options(p_ros2)
    add_shared_calibration_options(p_ros2)
    return parser
