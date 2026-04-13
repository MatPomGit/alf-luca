from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import numpy as np

from luca_types import Detection, DetectorConfig


@dataclass(slots=True)
class DetectorOutput:
    """Kanoniczny wynik pojedynczego wywołania detektora.

    Uwaga: `debug_mask` jest opcjonalna, bo detektory obiektowe mogą zwracać
    detekcje bez etapu progowania pikseli.
    """

    detections: list[Detection]
    debug_mask: np.ndarray | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class DetectorBackendError(RuntimeError):
    """Typowany wyjątek adaptera detektora, opakowujący błędy bibliotek backendowych."""

    def __init__(self, backend_name: str, message: str) -> None:
        super().__init__(message)
        self.backend_name = backend_name


@runtime_checkable
class DetectorProtocol(Protocol):
    """Kontrakt adaptera detektora zwracającego spójny wynik detekcji."""

    @classmethod
    def default_params(cls) -> dict:
        """Zwraca domyślne parametry specyficzne dla danej metody detekcji."""

    def detect(self, roi_frame: np.ndarray) -> DetectorOutput:
        """Uruchamia detekcję dla obrazu ROI i zwraca `DetectorOutput`."""


class BaseDetector:
    """Abstrakcyjna klasa bazowa dla adapterów detektorów."""

    def __init__(self, config: DetectorConfig) -> None:
        # Przechowujemy już kanoniczny model konfiguracji detekcji.
        self.config = config

    @classmethod
    def default_params(cls) -> dict:
        """Zwraca domyślne parametry metody; implementacje mogą je nadpisywać."""
        return {}

    def detect(self, roi_frame: np.ndarray) -> DetectorOutput:
        """Interfejs detekcji dla ROI."""
        raise NotImplementedError
