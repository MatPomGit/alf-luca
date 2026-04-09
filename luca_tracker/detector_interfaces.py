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
    erode_iter: int = 2
    dilate_iter: int = 4
    min_area: float = 10.0
    max_area: float = 0.0
    max_spots: int = 10
    color_name: str = "red"
    hsv_lower: Optional[str] = None
    hsv_upper: Optional[str] = None
    roi: Optional[str] = None


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
