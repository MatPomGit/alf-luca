from __future__ import annotations

import argparse

from luca_input import (
    add_shared_calibration_options,
    add_shared_detection_options,
    add_shared_postprocess_options,
    add_shared_reporting_options,
    add_shared_tracking_options,
)


def build_gui_parser() -> argparse.ArgumentParser:
    """Buduje parser argumentów dla adaptera GUI."""
    parser = argparse.ArgumentParser(description="Interfejs GUI LUCA (adapter bez legacy namespace).")
    parser.add_argument("--video", help="Plik wejściowy wideo (np. MP4/MKV/AVI/MOV/WEBM)")
    parser.add_argument("--camera", help="Kamera na żywo: indeks OpenCV (np. 0) albo ścieżka urządzenia")
    parser.add_argument("--display", action="store_true", help="Podgląd śledzenia")

    # Wspólny zestaw opcji utrzymuje zgodność kontraktu między GUI/CLI/ROS2.
    add_shared_detection_options(parser)
    add_shared_tracking_options(parser)
    add_shared_calibration_options(parser)
    add_shared_reporting_options(parser)
    add_shared_postprocess_options(parser)

    parser.add_argument("--config", help="Pełna konfiguracja uruchomienia z pliku JSON/YAML (.json/.yaml/.yml)")
    return parser
