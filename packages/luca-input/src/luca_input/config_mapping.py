"""Warstwa kompatybilności: re-eksport mapowań konfiguracji z nowego modułu."""

# Ten moduł zachowuje stare ścieżki importu dla klientów `luca_input.config_mapping`.
# Walidacje jakości punktów PnP (liczność, duplikaty, degeneracja) są utrzymywane
# w `pipeline_config_mapping`, aby tryby `track` i `ros2` miały identyczną semantykę błędów.
from luca_input.pipeline_config_mapping import *  # noqa: F401,F403
