from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
for src_dir in sorted((REPO_ROOT / "packages").glob("*/src")):
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

# Moduł `luca_processing` importuje `cv2`, więc gdy OpenCV nie jest dostępny, pomijamy test.
pytest.importorskip("cv2", exc_type=ImportError)

from luca_processing import WorldCoordinateFilter, WorldCoordinateFilterConfig


def test_world_coordinate_filter_rejects_large_outlier_jump() -> None:
    """Sprawdza, że pojedynczy skok odstający nie destabilizuje serii XYZ."""
    filt = WorldCoordinateFilter(
        WorldCoordinateFilterConfig(
            alpha=1.0,
            max_step=100.0,
            min_dynamic_step=10.0,
            missing_tolerance=0,
        )
    )

    stable_points = [(0.0, 0.0, 0.0), (1.0, 0.8, 0.0), (2.0, 1.6, 0.0)]
    outputs = [filt.update(point) for point in stable_points]
    outlier = filt.update((450.0, -300.0, 0.0))

    assert outputs[-1] is not None
    assert outlier == outputs[-1]


def test_world_coordinate_filter_bridges_short_missing_segment() -> None:
    """Weryfikuje, że krótkie braki detekcji utrzymują ciągłość publikowanego XYZ."""
    filt = WorldCoordinateFilter(WorldCoordinateFilterConfig(alpha=1.0, missing_tolerance=2))

    first = filt.update((10.0, 20.0, 0.0))
    missing_a = filt.update(None)
    missing_b = filt.update(None)
    missing_c = filt.update(None)

    assert first == (10.0, 20.0, 0.0)
    assert missing_a == (10.0, 20.0, 0.0)
    assert missing_b == (10.0, 20.0, 0.0)
    assert missing_c is None
