"""Publiczne API pakietu `luca_processing`."""

from luca_processing.detector_interfaces import BaseDetector, DetectorConfig
from luca_processing.detector_registry import available_detector_names, get_default_params, get_detector_class
from luca_processing.detectors import (
    BrightnessDetector,
    COLOR_PRESETS,
    ColorDetector,
    DetectionPersistenceFilter,
    TemporalMaskFilter,
    build_mask,
    contour_to_detection,
    detect_spots,
    detect_spots_with_config,
    ensure_odd,
    get_default_params_for_mode,
    parse_hsv_pair,
    parse_roi,
)
from luca_processing.postprocess import KalmanConfig, apply_kalman_to_points, smooth_xy_with_config

# Lista symboli wspieranych jako stabilny kontrakt dla pozostałych pakietów.
__all__ = [
    "BaseDetector",
    "DetectorConfig",
    "available_detector_names",
    "get_default_params",
    "get_detector_class",
    "BrightnessDetector",
    "COLOR_PRESETS",
    "ColorDetector",
    "DetectionPersistenceFilter",
    "TemporalMaskFilter",
    "build_mask",
    "contour_to_detection",
    "detect_spots",
    "detect_spots_with_config",
    "ensure_odd",
    "get_default_params_for_mode",
    "parse_hsv_pair",
    "parse_roi",
    "KalmanConfig",
    "apply_kalman_to_points",
    "smooth_xy_with_config",
]
