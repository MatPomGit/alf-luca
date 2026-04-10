from __future__ import annotations

from luca_tracker.cli import main as legacy_cli_main


def main() -> None:
    """Uruchamia cienki entrypoint CLI delegujący do parsera i usług aplikacyjnych."""
    legacy_cli_main()
