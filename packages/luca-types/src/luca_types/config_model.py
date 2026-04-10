"""Warstwa kompatybilności: re-eksport kanonicznego modelu konfiguracji `luca_config`."""

# Ten moduł zachowuje stare ścieżki importu dla klientów `luca_types.config_model`.
from luca_types.luca_config import *  # noqa: F401,F403
