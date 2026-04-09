from __future__ import annotations

from typing import Sequence

from .types import TrackPoint

try:
    from kalman_tracker import smooth_xy_sequence
except Exception:
    smooth_xy_sequence = None


def apply_kalman_to_points(points: Sequence[TrackPoint], process_noise: float, measurement_noise: float):
    """Wygładza sekwencję punktów filtrem Kalmana, zachowując brakujące pomiary."""
    if smooth_xy_sequence is None or not points:
        return

    sequence = []
    for point in points:
        if point.x is None or point.y is None:
            sequence.append(None)
        else:
            sequence.append((float(point.x), float(point.y)))

    smoothed = smooth_xy_sequence(
        sequence,
        process_noise=process_noise,
        measurement_noise=measurement_noise,
    )

    for point, result in zip(points, smoothed):
        sx, sy, predicted = result
        if sx is not None and sy is not None:
            point.x = float(sx)
            point.y = float(sy)
        point.kalman_predicted = int(bool(predicted))
