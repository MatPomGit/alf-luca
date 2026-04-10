"""Warstwa kompatybilności: re-eksport API z `luca_processing.detector_registry`."""

# Ten moduł zachowuje stare ścieżki importu dla klientów `luca_tracker`.
from luca_processing.detector_registry import *  # noqa: F401,F403

"""Do wywalenia z czasem"""
