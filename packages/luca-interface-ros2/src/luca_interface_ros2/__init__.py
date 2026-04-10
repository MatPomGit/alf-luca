"""Publiczne API pakietu entrypointu ROS2."""

from luca_interface_ros2.main import main

# Tylko punkt wejściowy jest częścią kontraktu publicznego.
__all__ = ["main"]
