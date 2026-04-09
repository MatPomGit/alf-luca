from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Type

import cv2
import numpy as np

from .detector_interfaces import BaseDetector, DetectorConfig
from .types import Detection


# Presety HSV dla najczęściej używanych kolorów plamki.
COLOR_PRESETS: Dict[str, List[Tuple[Tuple[int, int, int], Tuple[int, int, int]]]] = {
    "red": [((0, 80, 80), (10, 255, 255)), ((170, 80, 80), (180, 255, 255))],
    "green": [((35, 60, 60), (90, 255, 255))],
    "blue": [((90, 60, 60), (130, 255, 255))],
    "yellow": [((18, 80, 80), (40, 255, 255))],
    "white": [((0, 0, 180), (180, 60, 255))],
    "orange": [((8, 100, 80), (22, 255, 255))],
    "purple": [((130, 60, 60), (165, 255, 255))],
}


def parse_roi(roi_text: Optional[str], frame_shape: Tuple[int, int, int]) -> Tuple[int, int, int, int]:
    """Parsuje ROI i pilnuje, aby mieściło się w granicach obrazu."""
    if not roi_text:
        h, w = frame_shape[:2]
        return 0, 0, w, h
    parts = [int(v) for v in roi_text.split(",")]
    if len(parts) != 4:
        raise ValueError("ROI musi mieć format x,y,w,h")
    x, y, w, h = parts
    H, W = frame_shape[:2]
    x = max(0, min(x, W - 1))
    y = max(0, min(y, H - 1))
    w = max(1, min(w, W - x))
    h = max(1, min(h, H - y))
    return x, y, w, h


def ensure_odd(value: int) -> int:
    """Wymusza nieparzysty rozmiar jądra (np. dla Gaussa)."""
    return value if value % 2 == 1 else value + 1


def parse_hsv_pair(text: Optional[str], fallback: Tuple[int, int, int]) -> Tuple[int, int, int]:
    """Parsuje trójkę HSV z tekstu lub zwraca wartość zapasową."""
    if not text:
        return fallback
    parts = [int(v.strip()) for v in text.split(",")]
    if len(parts) != 3:
        raise ValueError("Zakres HSV musi mieć 3 wartości: h,s,v")
    return tuple(parts)  # type: ignore


class BrightnessDetector(BaseDetector):
    """Adapter dla detekcji opartej o progowanie jasności."""

    @classmethod
    def default_params(cls) -> dict:
        """Zwraca domyślne parametry specyficzne dla trybu brightness."""
        return {
            "blur": 11,
            "threshold": 200,
            "erode_iter": 2,
            "dilate_iter": 4,
        }

    def detect_mask(self, roi_frame: np.ndarray) -> np.ndarray:
        """Buduje maskę binarną dla ROI na podstawie jasności pikseli."""
        blur = ensure_odd(self.config.blur)
        gray = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (blur, blur), 0)
        _, mask = cv2.threshold(blurred, self.config.threshold, 255, cv2.THRESH_BINARY)
        return _apply_morphology(mask, erode_iter=self.config.erode_iter, dilate_iter=self.config.dilate_iter)


class ColorDetector(BaseDetector):
    """Adapter dla detekcji opartej o zakresy HSV."""

    @classmethod
    def default_params(cls) -> dict:
        """Zwraca domyślne parametry specyficzne dla trybu color."""
        return {
            "blur": 11,
            "color_name": "red",
            "hsv_lower": None,
            "hsv_upper": None,
            "erode_iter": 2,
            "dilate_iter": 4,
        }

    def detect_mask(self, roi_frame: np.ndarray) -> np.ndarray:
        """Buduje maskę binarną dla ROI na podstawie koloru w przestrzeni HSV."""
        blur = ensure_odd(self.config.blur)
        hsv = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2HSV)
        if self.config.color_name == "custom":
            lower = parse_hsv_pair(self.config.hsv_lower, (0, 80, 80))
            upper = parse_hsv_pair(self.config.hsv_upper, (10, 255, 255))
            ranges = [(lower, upper)]
        else:
            if self.config.color_name not in COLOR_PRESETS:
                raise ValueError(f"Nieznany preset koloru: {self.config.color_name}")
            ranges = COLOR_PRESETS[self.config.color_name]

        mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
        for low, high in ranges:
            local = cv2.inRange(hsv, np.array(low, dtype=np.uint8), np.array(high, dtype=np.uint8))
            mask = cv2.bitwise_or(mask, local)
        if blur > 1:
            mask = cv2.GaussianBlur(mask, (blur, blur), 0)
            _, mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
        return _apply_morphology(mask, erode_iter=self.config.erode_iter, dilate_iter=self.config.dilate_iter)


def _apply_morphology(mask: np.ndarray, erode_iter: int, dilate_iter: int) -> np.ndarray:
    """Nakłada wspólne operacje morfologiczne na maskę niezależnie od metody detekcji."""
    if erode_iter > 0:
        mask = cv2.erode(mask, None, iterations=erode_iter)
    if dilate_iter > 0:
        mask = cv2.dilate(mask, None, iterations=dilate_iter)
    return mask


def _resolve_detector_class(track_mode: str) -> Type[BaseDetector]:
    """Pobiera klasę adaptera detektora na podstawie nazwy metody."""
    from .detector_registry import get_detector_class

    normalized_mode = "brightness" if track_mode == "brightest" else track_mode
    return get_detector_class(normalized_mode)


def get_default_params_for_mode(track_mode: str) -> Dict[str, object]:
    """Udostępnia domyślne parametry zarejestrowane dla wskazanej metody detekcji."""
    detector_cls = _resolve_detector_class(track_mode)
    return detector_cls.default_params()


def contour_to_detection(contour, offset_x: int = 0, offset_y: int = 0) -> Optional[Detection]:
    """Przekształca pojedynczy kontur OpenCV do struktury Detection."""
    area = float(cv2.contourArea(contour))
    if area <= 0:
        return None
    perimeter = float(cv2.arcLength(contour, True))
    moments = cv2.moments(contour)
    if moments["m00"] == 0:
        return None

    x = float(moments["m10"] / moments["m00"]) + offset_x
    y = float(moments["m01"] / moments["m00"]) + offset_y
    circ = float(4.0 * math.pi * area / (perimeter * perimeter)) if perimeter > 0 else 0.0
    (_, _), radius = cv2.minEnclosingCircle(contour)
    bx, by, bw, bh = cv2.boundingRect(contour)
    ellipse_center: Optional[Tuple[float, float]] = None
    ellipse_axes: Optional[Tuple[float, float]] = None
    ellipse_angle: Optional[float] = None
    if len(contour) >= 5:
        (ecx, ecy), (axis_a, axis_b), angle = cv2.fitEllipse(contour)
        ellipse_center = (float(ecx + offset_x), float(ecy + offset_y))
        ellipse_axes = (float(axis_a), float(axis_b))
        ellipse_angle = float(angle)
    return Detection(
        x=x,
        y=y,
        area=area,
        perimeter=perimeter,
        circularity=circ,
        radius=float(radius),
        bbox_x=bx + offset_x,
        bbox_y=by + offset_y,
        bbox_w=bw,
        bbox_h=bh,
        ellipse_center=ellipse_center,
        ellipse_axes=ellipse_axes,
        ellipse_angle=ellipse_angle,
    )


def build_mask(
    frame: np.ndarray,
    track_mode: str = "brightness",
    blur: int = 11,
    threshold: int = 200,
    erode_iter: int = 2,
    dilate_iter: int = 4,
    color_name: str = "red",
    hsv_lower: Optional[str] = None,
    hsv_upper: Optional[str] = None,
) -> np.ndarray:
    """Buduje maskę binarną dla pełnej klatki.

    Funkcja zachowuje zgodność wsteczną ze starszym API modułu `tracking`,
    które oczekiwało eksportu `build_mask` z `luca_tracker.detectors`.
    """
    detector_cls = _resolve_detector_class(track_mode)
    detector_config = DetectorConfig(
        track_mode=track_mode,
        blur=blur,
        threshold=threshold,
        erode_iter=erode_iter,
        dilate_iter=dilate_iter,
        color_name=color_name,
        hsv_lower=hsv_lower,
        hsv_upper=hsv_upper,
    )
    return detector_cls(detector_config).detect_mask(frame)


def detect_spots(
    frame: np.ndarray,
    track_mode: str,
    blur: int,
    threshold: int,
    erode_iter: int,
    dilate_iter: int,
    min_area: float,
    max_area: float,
    max_spots: int,
    color_name: str,
    hsv_lower: Optional[str],
    hsv_upper: Optional[str],
    roi: Optional[str],
) -> Tuple[List[Detection], np.ndarray, Tuple[int, int, int, int]]:
    """Wykrywa plamki na klatce i zwraca detekcje, maskę oraz użyte ROI."""
    x0, y0, w, h = parse_roi(roi, frame.shape)
    roi_frame = frame[y0 : y0 + h, x0 : x0 + w]
    detector_cls = _resolve_detector_class(track_mode)
    detector_config = DetectorConfig(
        track_mode=track_mode,
        blur=blur,
        threshold=threshold,
        erode_iter=erode_iter,
        dilate_iter=dilate_iter,
        color_name=color_name,
        hsv_lower=hsv_lower,
        hsv_upper=hsv_upper,
    )
    mask = detector_cls(detector_config).detect_mask(roi_frame)

    contours, _ = cv2.findContours(mask.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    detections: List[Detection] = []
    for contour in contours:
        det = contour_to_detection(contour, offset_x=x0, offset_y=y0)
        if det is None:
            continue
        if det.area < min_area:
            continue
        if max_area > 0 and det.area > max_area:
            continue
        detections.append(det)

    detections.sort(key=lambda d: d.area, reverse=True)
    detections = detections[:max_spots]
    for idx, det in enumerate(detections, start=1):
        det.rank = idx

    return detections, mask, (x0, y0, w, h)


def detect_spots_with_config(frame: np.ndarray, config: DetectorConfig):
    """Uruchamia detekcję na podstawie obiektu konfiguracyjnego."""
    return detect_spots(
        frame=frame,
        track_mode=config.track_mode,
        blur=config.blur,
        threshold=config.threshold,
        erode_iter=config.erode_iter,
        dilate_iter=config.dilate_iter,
        min_area=config.min_area,
        max_area=config.max_area,
        max_spots=config.max_spots,
        color_name=config.color_name,
        hsv_lower=config.hsv_lower,
        hsv_upper=config.hsv_upper,
        roi=config.roi,
    )


def _build_parser() -> argparse.ArgumentParser:
    """Tworzy parser CLI do samodzielnego uruchamiania modułu detekcji."""
    from .detector_registry import available_detector_names

    parser = argparse.ArgumentParser(description="Standalone detector for single image.")
    parser.add_argument("--image", required=True, help="Path to input image.")
    parser.add_argument("--track_mode", choices=available_detector_names(), default="brightness")
    parser.add_argument("--threshold", type=int, default=200)
    parser.add_argument("--blur", type=int, default=11)
    parser.add_argument("--min_area", type=float, default=10.0)
    parser.add_argument("--max_area", type=float, default=0.0)
    parser.add_argument("--erode_iter", type=int, default=2)
    parser.add_argument("--dilate_iter", type=int, default=4)
    parser.add_argument("--max_spots", type=int, default=10)
    parser.add_argument("--color_name", default="red")
    parser.add_argument("--hsv_lower")
    parser.add_argument("--hsv_upper")
    parser.add_argument("--roi")
    parser.add_argument("--mask_out", help="Optional path to save generated mask image.")
    parser.add_argument("--json_out", help="Optional path to save detections as JSON.")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Punkt wejścia standalone: wykrywa plamki na pojedynczym obrazie."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    image = cv2.imread(args.image)
    if image is None:
        raise FileNotFoundError(f"Unable to read image: {args.image}")

    config = DetectorConfig(**{k: v for k, v in vars(args).items() if k in set(asdict(DetectorConfig()).keys())})
    detections, mask, roi_box = detect_spots_with_config(image, config)

    if args.mask_out:
        cv2.imwrite(args.mask_out, mask)

    payload = {
        "roi": list(roi_box),
        "count": len(detections),
        "detections": [asdict(det) for det in detections],
    }
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
