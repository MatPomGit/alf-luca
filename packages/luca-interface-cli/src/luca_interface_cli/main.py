from __future__ import annotations

from luca_input.io_paths import RuntimePathResolver
from luca_tracker.cli import main as legacy_cli_main


def main() -> None:
    """Uruchamia entrypoint CLI po inicjalizacji wspólnego resolvera ścieżek."""
    # Resolver jest współdzielony z usługami aplikacyjnymi i utrzymuje wspólny katalog runu.
    RuntimePathResolver.for_current_process().ensure_output_dir()
    legacy_cli_main()
