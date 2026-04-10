from __future__ import annotations

import sys

from luca_input.io_paths import RuntimePathResolver
from luca_tracker.cli import build_parser, pick_default_gui_video
from luca_tracker.gui import GUIEnvironmentError, run_gui


def main() -> None:
    """Uruchamia GUI po związaniu argumentów i normalizacji ścieżek wejściowych."""
    parser = build_parser()
    args = parser.parse_args(["gui", *sys.argv[1:]])
    resolver = RuntimePathResolver.for_current_process()

    # Domyślny plik GUI traktujemy jako source asset (repo/FS), a nie artifact pipeline'u.
    if not getattr(args, "video", None):
        args.video = pick_default_gui_video()
    if args.video:
        args.video = resolver.resolve_source_asset(args.video)
    if not args.video:
        raise SystemExit("Dla trybu GUI wymagany jest plik wideo (np. w katalogu ./video).")

    if getattr(args, "calib_file", None):
        args.calib_file = resolver.resolve_input_artifact(args.calib_file)

    try:
        run_gui(args)
    except ImportError as exc:
        raise SystemExit(f"Błąd zależności GUI: {exc}") from exc
    except GUIEnvironmentError as exc:
        raise SystemExit(f"Błąd uruchamiania GUI: {exc}") from exc
