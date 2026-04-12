from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.codemod_luca_tracker_imports import rewrite_text


def test_rewrite_text_reports_migrated_imports() -> None:
    """Sprawdza, że licznik migracji rośnie dla automatycznie przepisywanych importów."""

    before = (
        "from luca_tracker import track_video, calibrate_camera\n"
        "from luca_tracker.detectors import DetectorConfig\n"
    )

    outcome = rewrite_text(before)

    assert "from luca_tracking.tracking import track_video, calibrate_camera" in outcome.text
    assert "from luca_processing.detectors import DetectorConfig" in outcome.text
    assert outcome.migrated_imports == 3
    assert outcome.requires_manual_intervention is False


def test_rewrite_text_marks_manual_intervention_when_legacy_import_remains() -> None:
    """Sprawdza raportowanie plików wymagających ręcznego dokończenia migracji."""

    before = "from luca_tracker import not_mapped_symbol\n"

    outcome = rewrite_text(before)

    assert outcome.text == before
    assert outcome.migrated_imports == 0
    assert outcome.requires_manual_intervention is True
