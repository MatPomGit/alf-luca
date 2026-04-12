from __future__ import annotations

import argparse
import sys

from luca_input import RuntimePathResolver, add_shared_calibration_options, add_shared_detection_options
from luca_tracking import run_ros2


def _build_ros2_parser() -> argparse.ArgumentParser:
    """Buduje lokalny parser adaptera ROS2 bez zależności od legacy CLI."""
    parser = argparse.ArgumentParser(description="ROS2 node: śledzenie z kamery i publikacja danych")
    parser.add_argument("--video_device", default="/dev/video0", help="Źródło kamery")
    parser.add_argument("--camera_index", type=int, help="Indeks kamery OpenCV")
    parser.add_argument("--node_name", default="detector_node", help="Nazwa ROS2 node")
    parser.add_argument("--topic", default="/luca_tracker/tracking", help="Topic ROS2 dla danych")
    parser.add_argument("--spot_id", type=int, default=0, help="ID detekcji głównej")
    parser.add_argument("--fps", type=float, default=30.0, help="Docelowa częstotliwość odczytu/publikacji")
    parser.add_argument("--frame_width", type=int, default=0, help="Szerokość klatki (0 = domyślna)")
    parser.add_argument("--frame_height", type=int, default=0, help="Wysokość klatki (0 = domyślna)")
    parser.add_argument("--display", action="store_true", help="Podgląd śledzenia")
    add_shared_detection_options(parser)
    add_shared_calibration_options(parser)
    return parser


def main() -> None:
    """Uruchamia adapter ROS2 z jednym resolverem ścieżek runtime."""
    parser = _build_ros2_parser()
    args = parser.parse_args(sys.argv[1:])
    resolver = RuntimePathResolver.for_current_process()

    # Kalibracja jest traktowana jako artifact wejściowy (często wygenerowany przez LUCA).
    if getattr(args, "calib_file", None):
        args.calib_file = resolver.resolve_input_artifact(args.calib_file)

    run_ros2(args)
