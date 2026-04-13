"""Warstwa kompatybilności dla legacy importów z `video_export`."""

from __future__ import annotations

import warnings

LEGACY_REMOVAL_TARGET = "2026-04-14"

# Ostrzeżenie emituje się przy imporcie legacy modułu i wskazuje docelową ścieżkę migracji.
warnings.warn(
    (
        "`luca_tracker.video_export` is deprecated and will be removed after "
        f"{LEGACY_REMOVAL_TARGET}. Migration path: use `luca_reporting.video_export`. "
        "Run `python tools/codemod_luca_tracker_imports.py --write <paths>` and "
        "see `docs/legacy_import_migration.md` for timeline and mappings."
    ),
    DeprecationWarning,
    stacklevel=2,
)

# Cienka warstwa delegująca: re-eksport symboli z docelowego pakietu.
from luca_reporting.video_export import *  # noqa: F401,F403
