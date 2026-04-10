from __future__ import annotations

import sys

from luca_tracker.cli import build_parser
from luca_tracking.application_services import run_ros2


def main() -> None:
    """Uruchamia adapter ROS2: parsowanie argumentów i delegacja do usługi aplikacyjnej."""
    parser = build_parser()
    args = parser.parse_args(["ros2", *sys.argv[1:]])
    run_ros2(args)
