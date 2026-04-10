from __future__ import annotations

import sys

from luca_tracker.cli import build_parser, pick_default_gui_video
from luca_tracker.gui import GUIEnvironmentError, run_gui


def main() -> None:
    """Uruchamia GUI po związaniu argumentów wejściowych i mapowaniu ich do DTO/serwisów."""
    parser = build_parser()
    args = parser.parse_args(["gui", *sys.argv[1:]])
    if not getattr(args, "video", None):
        args.video = pick_default_gui_video()
    if not args.video:
        raise SystemExit("Dla trybu GUI wymagany jest plik wideo (np. w katalogu ./video).")
    try:
        run_gui(args)
    except ImportError as exc:
        raise SystemExit(f"Błąd zależności GUI: {exc}") from exc
    except GUIEnvironmentError as exc:
        raise SystemExit(f"Błąd uruchamiania GUI: {exc}") from exc
