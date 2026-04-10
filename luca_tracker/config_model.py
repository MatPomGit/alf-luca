"""Warstwa kompatybilności: re-eksport API konfiguracji z nowych paczek."""

# Ten moduł zachowuje stare ścieżki importu dla klientów `luca_tracker`.
from luca_types.config_model import *  # noqa: F401,F403
from luca_input.config_mapping import *  # noqa: F401,F403
