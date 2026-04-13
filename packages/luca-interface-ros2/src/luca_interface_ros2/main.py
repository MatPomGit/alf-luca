from __future__ import annotations

import argparse
import sys

from luca_input import (
    RuntimePathResolver,
    add_shared_calibration_options,
    add_shared_detection_options,
    add_shared_ros2_runtime_options,
    add_shared_tracking_options,
)
from luca_tracking import run_ros2


def _build_ros2_parser() -> argparse.ArgumentParser:
    """Buduje lokalny parser adaptera ROS2 bez zależności od legacy CLI."""
    parser = argparse.ArgumentParser(description="ROS2 node: śledzenie z kamery i publikacja danych")
    add_shared_ros2_runtime_options(parser)
    add_shared_detection_options(parser)
    add_shared_tracking_options(parser)
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
