"""Warstwa kompatybilności dla legacy importów z `detectors`."""

from __future__ import annotations

import warnings

LEGACY_REMOVAL_TARGET = "2026-09-30"

# Ostrzeżenie emituje się przy imporcie legacy modułu i wskazuje docelową ścieżkę migracji.
warnings.warn(
    (
        "`luca_tracker.detectors` is deprecated and will be removed after "
        f"{LEGACY_REMOVAL_TARGET}. Migration path: use `luca_processing.detectors`. "
        "Run `python tools/codemod_luca_tracker_imports.py --write <paths>` and "
        "see `docs/legacy_import_migration.md` for timeline and mappings."
    ),
    DeprecationWarning,
    stacklevel=2,
)

# Cienka warstwa delegująca: re-eksport symboli z docelowego pakietu.
from luca_processing.detectors import *  # noqa: F401,F403
