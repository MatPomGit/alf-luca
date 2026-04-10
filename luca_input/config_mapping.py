"""Warstwa kompatybilności: re-eksport mapowań konfiguracji z nowego modułu."""

# Ten moduł zachowuje stare ścieżki importu dla klientów `luca_input.config_mapping`.
from luca_input.pipeline_config_mapping import *  # noqa: F401,F403
