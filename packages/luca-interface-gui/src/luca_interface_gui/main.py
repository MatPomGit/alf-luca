from __future__ import annotations

import glob
import sys

from luca_input.io_paths import RuntimePathResolver

from .gui_parser import build_gui_parser
from .gui_runner import GUIEnvironmentError, run_gui

_DEFAULT_GUI_VIDEO_GLOB_PATTERNS = (
    "video/*.mp4",
    "video/*.mkv",
    "video/*.avi",
    "video/*.mov",
    "video/*.m4v",
    "video/*.webm",
    "*.mp4",
    "*.mkv",
    "*.avi",
    "*.mov",
    "*.m4v",
    "*.webm",
)


def _pick_default_gui_video() -> str | None:
    """Wybiera pierwszy dostępny plik wideo dla uruchomienia GUI bez jawnego --video."""
    for pattern in _DEFAULT_GUI_VIDEO_GLOB_PATTERNS:
        matches = sorted(glob.glob(pattern))
        if matches:
            return matches[0]
    return None


def main() -> None:
    """Uruchamia GUI po związaniu argumentów i normalizacji ścieżek wejściowych."""
    parser = build_gui_parser()
    args = parser.parse_args(sys.argv[1:])
    resolver = RuntimePathResolver.for_current_process()

    # Domyślny plik GUI traktujemy jako source asset (repo/FS), a nie artifact pipeline'u.
    if not getattr(args, "video", None):
        args.video = _pick_default_gui_video()
    if args.video:
        args.video = resolver.resolve_source_asset(args.video)
    if not args.video and not getattr(args, "camera", None):
        raise SystemExit("Dla trybu GUI wymagany jest plik wideo lub kamera wejściowa.")

    if getattr(args, "calib_file", None):
        args.calib_file = resolver.resolve_input_artifact(args.calib_file)

    try:
        run_gui(args)
    except ImportError as exc:
        raise SystemExit(f"Błąd zależności GUI: {exc}") from exc
    except GUIEnvironmentError as exc:
        raise SystemExit(f"Błąd uruchamiania GUI: {exc}") from exc
