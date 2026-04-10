from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable

import numpy as np


@dataclass
class DetectorConfig:
    """Konfiguracja bazowa używana przez wszystkie adaptery detekcji."""

    track_mode: str = "brightness"
    blur: int = 11
    threshold: int = 200
    threshold_mode: str = "fixed"
    adaptive_block_size: int = 31
    adaptive_c: float = 5.0
    use_clahe: bool = False
    erode_iter: int = 2
    dilate_iter: int = 4
    opening_kernel: int = 0
    closing_kernel: int = 0
    min_area: float = 10.0
    max_area: float = 0.0
    # Minimalna kolistość (0..1); wyższa wartość ogranicza wydłużone artefakty i szum krawędzi.
    min_circularity: float = 0.0
    # Maksymalny stosunek boków bbox (>=1); mniejsza wartość odrzuca ekstremalnie podłużne obiekty.
    max_aspect_ratio: float = 6.0
    # Minimalna jasność lokalnego maksimum (0..255) wewnątrz konturu; pomaga usuwać słabe refleksy.
    min_peak_intensity: float = 0.0
    # Minimalna zwartość konturu (area/convex_hull_area, 0..1); opcjonalnie usuwa mocno wklęsłe kształty.
    min_solidity: Optional[float] = None
    max_spots: int = 10
    color_name: str = "red"
    hsv_lower: Optional[str] = None
    hsv_upper: Optional[str] = None
    roi: Optional[str] = None
    temporal_stabilization: bool = False
    temporal_window: int = 3
    temporal_mode: str = "majority"


@runtime_checkable
class DetectorProtocol(Protocol):
    """Kontrakt adaptera detektora zwracającego binarną maskę ROI."""

    @classmethod
    def default_params(cls) -> dict:
        """Zwraca domyślne parametry specyficzne dla danej metody detekcji."""

    def detect_mask(self, roi_frame: np.ndarray) -> np.ndarray:
        """Buduje maskę binarną dla obrazu ROI."""


class BaseDetector:
    """Abstrakcyjna klasa bazowa dla adapterów detektorów."""

    def __init__(self, config: DetectorConfig) -> None:
        self.config = config

    @classmethod
    def default_params(cls) -> dict:
        """Zwraca domyślne parametry metody; implementacje mogą je nadpisywać."""
        return {}

    def detect_mask(self, roi_frame: np.ndarray) -> np.ndarray:
        """Interfejs wykrywania maski dla ROI."""
        raise NotImplementedError
