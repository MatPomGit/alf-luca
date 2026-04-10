from __future__ import annotations

import argparse
import sys

from luca_input.io_paths import RuntimePathResolver
from luca_tracking.application_services import run_ros2


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
    parser.add_argument("--track_mode", choices=["brightness", "color"], default="brightness")
    parser.add_argument("--threshold", type=int, default=200, help="Próg jasności")
    parser.add_argument("--threshold_mode", choices=["fixed", "otsu", "adaptive"], default="fixed")
    parser.add_argument("--adaptive_block_size", type=int, default=31)
    parser.add_argument("--adaptive_c", type=float, default=5.0)
    parser.add_argument("--use_clahe", action="store_true")
    parser.add_argument("--blur", type=int, default=11)
    parser.add_argument("--min_area", type=float, default=10.0)
    parser.add_argument("--max_area", type=float, default=0.0)
    parser.add_argument("--erode_iter", type=int, default=2)
    parser.add_argument("--dilate_iter", type=int, default=4)
    parser.add_argument("--max_spots", type=int, default=1)
    parser.add_argument("--roi", help="Obszar ROI w formacie x,y,w,h")
    parser.add_argument("--color_name", choices=["red", "green", "blue", "white", "yellow", "custom"], default="red")
    parser.add_argument("--hsv_lower")
    parser.add_argument("--hsv_upper")
    parser.add_argument("--calib_file", help="Plik kalibracji .npz")
    parser.add_argument("--pnp_object_points", help="Punkty 3D świata: X,Y,Z;X,Y,Z;... (min. 4)")
    parser.add_argument("--pnp_image_points", help="Punkty 2D obrazu: x,y;x,y;... (min. 4)")
    parser.add_argument("--pnp_world_plane_z", type=float, default=0.0)
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
