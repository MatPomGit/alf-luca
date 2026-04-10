"""Warstwa kompatybilności: re-eksport API z `luca_processing.detector_interfaces`."""

# Ten moduł zachowuje stare ścieżki importu dla klientów `luca_tracker`.
from luca_processing.detector_interfaces import *  # noqa: F401,F403
