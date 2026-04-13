from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Tuple


@dataclass
class Detection:
    # Minimalny kontrakt wymagany przez tracker niezależnie od typu detektora.
    x: float
    y: float
    confidence: float = 0.0

    # Cechy blobowe pozostają opcjonalne, bo nie każdy detektor je dostarcza.
    area: Optional[float] = None
    perimeter: Optional[float] = None
    circularity: Optional[float] = None
    radius: Optional[float] = None

    # Neutralna reprezentacja bbox dla detektorów obiektowych.
    bbox: Optional[Tuple[int, int, int, int]] = None
    bbox_x: Optional[int] = None
    bbox_y: Optional[int] = None
    bbox_w: Optional[int] = None
    bbox_h: Optional[int] = None

    # Metadane neutralne dla detektorów klasyfikujących/segmentujących.
    label: Optional[str] = None
    source_id: Optional[str | int] = None
    extra: dict[str, Any] = field(default_factory=dict)

    ellipse_center: Optional[Tuple[float, float]] = None
    ellipse_axes: Optional[Tuple[float, float]] = None
    ellipse_angle: Optional[float] = None
    mean_brightness: Optional[float] = None
    rank: int = 0


@dataclass
class TrackPoint:
    frame_index: int
    time_sec: float
    detected: bool
    x: Optional[float]
    y: Optional[float]
    area: Optional[float]
    perimeter: Optional[float]
    circularity: Optional[float]
    radius: Optional[float]
    confidence: Optional[float] = None
    track_id: Optional[int] = None
    rank: Optional[int] = None
    kalman_predicted: int = 0
    x_world: Optional[float] = None
    y_world: Optional[float] = None
    z_world: Optional[float] = None
