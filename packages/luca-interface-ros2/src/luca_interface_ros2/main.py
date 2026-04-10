from __future__ import annotations

import sys

from luca_input.io_paths import RuntimePathResolver
from luca_tracker.cli import build_parser
from luca_tracking.application_services import run_ros2


def main() -> None:
    """Uruchamia adapter ROS2 z jednym resolverem ścieżek runtime."""
    parser = build_parser()
    args = parser.parse_args(["ros2", *sys.argv[1:]])
    resolver = RuntimePathResolver.for_current_process()

    # Kalibracja jest traktowana jako artifact wejściowy (często wygenerowany przez LUCA).
    if getattr(args, "calib_file", None):
        args.calib_file = resolver.resolve_input_artifact(args.calib_file)

    run_ros2(args)
