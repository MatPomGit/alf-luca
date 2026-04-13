from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Type

from luca_processing.detector_interfaces import BaseDetector
from luca_processing.detectors import BrightnessDetector, ColorDetector


def _validate_passthrough(_: Dict[str, Any]) -> None:
    """Domyślny validator dla backendów bez ścisłego schematu parametrów."""


@dataclass(frozen=True)
class DetectorRegistration:
    """Opisuje pojedynczy wpis rejestru detektorów wraz z walidacją i capability flags."""

    adapter_cls: Type[BaseDetector]
    params_validator: Callable[[Dict[str, Any]], None] = _validate_passthrough
    capabilities: set[str] = field(default_factory=set)


class UnsupportedDetectorAdapter(BaseDetector):
    """Adapter zastępczy dla backendów zarejestrowanych koncepcyjnie, ale bez implementacji."""

    def detect(self, roi_frame):  # type: ignore[override]
        raise NotImplementedError(f"Backend `{self.config.track_mode}` nie ma jeszcze implementacji adaptera.")


def _validate_brightness_params(params: Dict[str, Any]) -> None:
    """Waliduje parametry backendu brightness."""
    required = {"blur", "threshold", "threshold_mode", "adaptive_block_size", "adaptive_c", "use_clahe"}
    missing = sorted(required - set(params.keys()))
    if missing:
        raise ValueError(f"Backend `brightness` wymaga pól params: {', '.join(missing)}")


def _validate_color_params(params: Dict[str, Any]) -> None:
    """Waliduje parametry backendu color."""
    required = {"blur", "color_name"}
    missing = sorted(required - set(params.keys()))
    if missing:
        raise ValueError(f"Backend `color` wymaga pól params: {', '.join(missing)}")


# Centralna mapa metod detekcji na komplet metadanych adapterów.
DETECTOR_REGISTRY: Dict[str, DetectorRegistration] = {
    "brightness": DetectorRegistration(
        adapter_cls=BrightnessDetector,
        params_validator=_validate_brightness_params,
        capabilities={"provides_mask"},
    ),
    "color": DetectorRegistration(
        adapter_cls=ColorDetector,
        params_validator=_validate_color_params,
        capabilities={"provides_mask"},
    ),
    "apriltag": DetectorRegistration(
        adapter_cls=UnsupportedDetectorAdapter,
        capabilities={"provides_pose"},
    ),
    "mediapipe": DetectorRegistration(
        adapter_cls=UnsupportedDetectorAdapter,
        capabilities={"provides_pose"},
    ),
    "yolo": DetectorRegistration(
        adapter_cls=UnsupportedDetectorAdapter,
        capabilities={"requires_model_file"},
    ),
}


def get_detector_class(name: str) -> Type[BaseDetector]:
    """Zwraca klasę detektora dla podanej nazwy metody."""
    registration = DETECTOR_REGISTRY.get(name)
    if registration is None:
        available = ", ".join(sorted(DETECTOR_REGISTRY))
        raise ValueError(f"Nieznana metoda detekcji: {name}. Dostępne: {available}")
    return registration.adapter_cls


def get_default_params(name: str) -> dict:
    """Zwraca domyślne parametry dla metody detekcji."""
    return get_detector_class(name).default_params()


def validate_params(name: str, params: Dict[str, Any]) -> None:
    """Uruchamia walidator parametrów dla podanego backendu detektora."""
    registration = DETECTOR_REGISTRY.get(name)
    if registration is None:
        available = ", ".join(sorted(DETECTOR_REGISTRY))
        raise ValueError(f"Nieznana metoda detekcji: {name}. Dostępne: {available}")
    registration.params_validator(params)


def get_capabilities(name: str) -> set[str]:
    """Zwraca capability flags backendu detektora."""
    registration = DETECTOR_REGISTRY.get(name)
    if registration is None:
        available = ", ".join(sorted(DETECTOR_REGISTRY))
        raise ValueError(f"Nieznana metoda detekcji: {name}. Dostępne: {available}")
    return set(registration.capabilities)


def available_detector_names() -> list[str]:
    """Zwraca posortowaną listę nazw wszystkich zarejestrowanych detektorów."""
    return sorted(DETECTOR_REGISTRY.keys())
