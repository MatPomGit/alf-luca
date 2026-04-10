from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np

from luca_types.luca_config import DetectorConfig


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
        # Przechowujemy już kanoniczny model konfiguracji detekcji.
        self.config = config

    @classmethod
    def default_params(cls) -> dict:
        """Zwraca domyślne parametry metody; implementacje mogą je nadpisywać."""
        return {}

    def detect_mask(self, roi_frame: np.ndarray) -> np.ndarray:
        """Interfejs wykrywania maski dla ROI."""
        raise NotImplementedError
