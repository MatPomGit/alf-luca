from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class Detection:
    x: float
    y: float
    area: float
    perimeter: float
    circularity: float
    radius: float
    bbox_x: int
    bbox_y: int
    bbox_w: int
    bbox_h: int
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
    track_id: Optional[int]
    rank: Optional[int] = None
    kalman_predicted: int = 0
    x_world: Optional[float] = None
    y_world: Optional[float] = None
    z_world: Optional[float] = None
