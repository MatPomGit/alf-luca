from __future__ import annotations

import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for src_dir in sorted((REPO_ROOT / "packages").glob("*/src")):
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

# Środowisko CI bez bibliotek systemowych OpenCV wymaga lekkiego stubu modułu `cv2`.
if "cv2" not in sys.modules:
    sys.modules["cv2"] = types.SimpleNamespace()

from luca_reporting import metrics_from_points_with_profile
from luca_types import TrackPoint


def _point(frame_index: int, x: float | None, y: float | None, confidence: float | None, predicted: int = 0) -> TrackPoint:
    """Buduje punkt testowy z domyślnymi polami niewpływającymi na metryki jakości."""
    return TrackPoint(
        frame_index=frame_index,
        time_sec=frame_index / 30.0,
        detected=x is not None and y is not None,
        x=x,
        y=y,
        area=100.0 if x is not None else None,
        perimeter=30.0 if x is not None else None,
        circularity=0.9 if x is not None else None,
        radius=8.0 if x is not None else None,
        confidence=confidence,
        kalman_predicted=predicted,
    )


def test_extended_profile_contains_new_quality_metrics() -> None:
    """Weryfikuje, że profil rozszerzony eksportuje nowe metryki stabilności i jakości."""
    points = [
        _point(0, 10.0, 10.0, 0.95),
        _point(1, 11.0, 10.8, 0.94),
        _point(2, 12.0, 11.4, 0.93),
        _point(3, None, None, None, predicted=1),
        _point(4, 14.1, 12.5, 0.91),
    ]
    metrics = metrics_from_points_with_profile(points, metric_profile="extended")

    for key in ("p95_step", "step_cv", "prediction_ratio", "stability_index", "quality_score"):
        assert key in metrics
    assert 0.0 <= float(metrics["stability_index"]) <= 1.0
    assert 0.0 <= float(metrics["quality_score"]) <= 100.0


def test_quality_score_rewards_stable_track() -> None:
    """Sprawdza, że stabilniejszy tor dostaje wyższy wynik jakości niż tor z jitterem i lukami."""
    stable = [
        _point(0, 100.0, 100.0, 0.97),
        _point(1, 101.0, 100.7, 0.96),
        _point(2, 102.0, 101.4, 0.95),
        _point(3, 103.0, 102.0, 0.96),
        _point(4, 104.0, 102.8, 0.95),
    ]
    noisy = [
        _point(0, 100.0, 100.0, 0.7),
        _point(1, 112.0, 91.0, 0.45),
        _point(2, None, None, None, predicted=1),
        _point(3, 86.0, 117.0, 0.4),
        _point(4, 120.0, 85.0, 0.42),
    ]

    stable_metrics = metrics_from_points_with_profile(stable, metric_profile="extended")
    noisy_metrics = metrics_from_points_with_profile(noisy, metric_profile="extended")

    assert float(stable_metrics["quality_score"]) > float(noisy_metrics["quality_score"])
    assert float(stable_metrics["stability_index"]) > float(noisy_metrics["stability_index"])
