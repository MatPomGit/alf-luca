from __future__ import annotations

from typing import Dict, Type

from .detector_interfaces import BaseDetector
from .detectors import BrightnessDetector, ColorDetector


# Centralna mapa metod detekcji na klasy adapterów.
DETECTOR_REGISTRY: Dict[str, Type[BaseDetector]] = {
    "brightness": BrightnessDetector,
    "color": ColorDetector,
}


def get_detector_class(name: str) -> Type[BaseDetector]:
    """Zwraca klasę detektora dla podanej nazwy metody."""
    detector_cls = DETECTOR_REGISTRY.get(name)
    if detector_cls is None:
        available = ", ".join(sorted(DETECTOR_REGISTRY))
        raise ValueError(f"Nieznana metoda detekcji: {name}. Dostępne: {available}")
    return detector_cls


def get_default_params(name: str) -> dict:
    """Zwraca domyślne parametry dla metody detekcji."""
    return get_detector_class(name).default_params()


def available_detector_names() -> list[str]:
    """Zwraca posortowaną listę nazw wszystkich zarejestrowanych detektorów."""
    return sorted(DETECTOR_REGISTRY.keys())
