from __future__ import annotations

import argparse
import json
import math
from collections import deque
from dataclasses import asdict
from pathlib import Path
from typing import Deque, Dict, List, Optional, Tuple, Type

import cv2
import numpy as np

from luca_processing.detector_interfaces import BaseDetector, DetectorConfig
from luca_types.types import Detection


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
    try:
        # Dopuszczamy białe znaki w zapisie ROI, np. "10, 20, 300, 200".
        parts = [int(v.strip()) for v in roi_text.split(",")]
    except ValueError as exc:
        raise ValueError("ROI musi zawierać liczby całkowite w formacie x,y,w,h") from exc
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
    h, s, v = parts
    # Walidacja zapobiega cichemu overflow przy konwersji do np.uint8.
    if not (0 <= h <= 180 and 0 <= s <= 255 and 0 <= v <= 255):
        raise ValueError("Zakres HSV poza dozwolonym przedziałem: h 0..180, s/v 0..255")
    return h, s, v


class BrightnessDetector(BaseDetector):
    """Adapter dla detekcji opartej o progowanie jasności."""

    @classmethod
    def default_params(cls) -> dict:
        """Zwraca domyślne parametry specyficzne dla trybu brightness."""
        return {
            "blur": 11,
            "threshold": 200,
            "threshold_mode": "fixed",
            "adaptive_block_size": 31,
            "adaptive_c": 5.0,
            "use_clahe": False,
            "erode_iter": 2,
            "dilate_iter": 4,
            "opening_kernel": 0,
            "closing_kernel": 0,
        }

    def detect_mask(self, roi_frame: np.ndarray) -> np.ndarray:
        """Buduje maskę binarną dla ROI na podstawie jasności pikseli."""
        blur = ensure_odd(self.config.blur)
        threshold_mode = str(getattr(self.config, "threshold_mode", "fixed")).strip().lower()
        if threshold_mode not in {"fixed", "otsu", "adaptive"}:
            raise ValueError(f"Nieobsługiwany threshold_mode: {threshold_mode}")
        gray = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2GRAY)
        # Opcjonalna normalizacja lokalnego kontrastu (CLAHE) poprawia separację plamki
        # przy nierównomiernym oświetleniu sceny.
        if bool(getattr(self.config, "use_clahe", False)):
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            gray = clahe.apply(gray)
        blurred = cv2.GaussianBlur(gray, (blur, blur), 0) if blur > 1 else gray

        if threshold_mode == "fixed":
            _, mask = cv2.threshold(blurred, self.config.threshold, 255, cv2.THRESH_BINARY)
        elif threshold_mode == "otsu":
            _, mask = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        else:
            adaptive_block_size = ensure_odd(max(3, int(getattr(self.config, "adaptive_block_size", 31))))
            adaptive_c = float(getattr(self.config, "adaptive_c", 5.0))
            mask = cv2.adaptiveThreshold(
                blurred,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                adaptive_block_size,
                adaptive_c,
            )
        return _apply_morphology(
            mask,
            erode_iter=self.config.erode_iter,
            dilate_iter=self.config.dilate_iter,
            opening_kernel=self.config.opening_kernel,
            closing_kernel=self.config.closing_kernel,
        )


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
            "opening_kernel": 0,
            "closing_kernel": 0,
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
        return _apply_morphology(
            mask,
            erode_iter=self.config.erode_iter,
            dilate_iter=self.config.dilate_iter,
            opening_kernel=self.config.opening_kernel,
            closing_kernel=self.config.closing_kernel,
        )


def _build_kernel(kernel_size: int) -> Optional[np.ndarray]:
    """Buduje kwadratowe jądro morfologiczne; `<=1` oznacza brak operacji."""
    if kernel_size <= 1:
        return None
    size = max(1, int(kernel_size))
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))


def _apply_morphology(
    mask: np.ndarray,
    erode_iter: int,
    dilate_iter: int,
    opening_kernel: int = 0,
    closing_kernel: int = 0,
) -> np.ndarray:
    """Nakłada wspólne operacje morfologiczne na maskę niezależnie od metody detekcji."""
    if erode_iter > 0:
        mask = cv2.erode(mask, None, iterations=erode_iter)
    if dilate_iter > 0:
        mask = cv2.dilate(mask, None, iterations=dilate_iter)
    opening = _build_kernel(opening_kernel)
    if opening is not None:
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, opening)
    closing = _build_kernel(closing_kernel)
    if closing is not None:
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, closing)
    return mask


class TemporalMaskFilter:
    """Prosty bufor masek binarnych stabilizujący detekcję między klatkami."""

    def __init__(self, window_size: int = 3, mode: str = "majority") -> None:
        if window_size <= 0:
            raise ValueError("Temporal window musi być dodatnie.")
        if mode not in {"majority", "and"}:
            raise ValueError("Temporal mode musi być jednym z: majority/and.")
        self.window_size = int(window_size)
        self.mode = mode
        self._buffer: Deque[np.ndarray] = deque(maxlen=self.window_size)
        self._shape: Optional[Tuple[int, int]] = None

    def reset(self) -> None:
        """Czyści historię masek; używamy np. przy zmianie źródła wideo/ROI."""
        self._buffer.clear()
        self._shape = None

    def apply(self, mask: np.ndarray) -> np.ndarray:
        """Zwraca maskę przefiltrowaną po czasie.

        Kompromis techniczny:
        - mniejszy szum migotania pojedynczych pikseli/artefaktów,
        - ale większe opóźnienie reakcji (do ~N klatek dla okna N).
        """
        if mask.ndim != 2:
            raise ValueError("TemporalMaskFilter oczekuje maski jednowarstwowej (H, W).")
        current_shape = (int(mask.shape[0]), int(mask.shape[1]))
        if self._shape is not None and self._shape != current_shape:
            # Zmiana rozmiaru ROI/kadru oznacza inną geometrię pikseli.
            # Reset zapobiega mieszaniu nieporównywalnych masek historycznych.
            self.reset()
        self._shape = current_shape
        binary_mask = np.where(mask > 0, 255, 0).astype(np.uint8)
        self._buffer.append(binary_mask)
        stack = np.stack(list(self._buffer), axis=0)
        if self.mode == "and":
            fused = np.min(stack, axis=0)
        else:
            min_votes = (len(self._buffer) // 2) + 1
            votes = np.count_nonzero(stack > 0, axis=0)
            fused = np.where(votes >= min_votes, 255, 0).astype(np.uint8)
        return fused.astype(np.uint8)


def _embed_mask_in_frame(mask_roi: np.ndarray, frame_shape: Tuple[int, int, int], roi_box: Tuple[int, int, int, int]) -> np.ndarray:
    """Wkleja maskę ROI do pełnego kadru i zeruje piksele poza ROI."""
    x0, y0, w, h = roi_box
    full_mask = np.zeros(frame_shape[:2], dtype=np.uint8)
    full_mask[y0 : y0 + h, x0 : x0 + w] = mask_roi
    return full_mask


def _resolve_detector_class(track_mode: str) -> Type[BaseDetector]:
    """Pobiera klasę adaptera detektora na podstawie nazwy metody."""
    from luca_processing.detector_registry import get_detector_class

    normalized_mode = "brightness" if track_mode == "brightest" else track_mode
    return get_detector_class(normalized_mode)


def get_default_params_for_mode(track_mode: str) -> Dict[str, object]:
    """Udostępnia domyślne parametry zarejestrowane dla wskazanej metody detekcji."""
    detector_cls = _resolve_detector_class(track_mode)
    return detector_cls.default_params()


def contour_to_detection(
    contour: np.ndarray,
    offset_x: int = 0,
    offset_y: int = 0,
    mean_brightness: Optional[float] = None,
) -> Optional[Detection]:
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
        confidence=0.0,
        ellipse_center=ellipse_center,
        ellipse_axes=ellipse_axes,
        ellipse_angle=ellipse_angle,
        mean_brightness=mean_brightness,
    )


def _clip01(value: float) -> float:
    """Ogranicza wartość do zakresu [0, 1], aby uprościć łączenie cech jakościowych."""
    return float(max(0.0, min(1.0, value)))


def _compute_detection_confidence(
    contour: np.ndarray,
    detection: Detection,
    roi_frame: np.ndarray,
    area_reference: float,
) -> float:
    """Liczy confidence detekcji z cech geometrii, jasności i stabilności rozmiaru.

    Składowe:
    - shape_score: preferuje kształty o wysokiej kolistości i umiarkowanej ekscentryczności,
    - brightness_score: porównuje średnią jasność obiektu do tła z lokalnego bounding boxa,
    - size_stability_score: nagradza pole bliskie medianie pól kandydatów w bieżącej klatce.
    """
    # Cechy kształtu: kolistość i proporcja osi elipsy (gdy dostępna).
    circularity_score = _clip01(detection.circularity)
    axis_ratio_score = 1.0
    if detection.ellipse_axes and min(detection.ellipse_axes) > 0:
        major_axis = max(detection.ellipse_axes)
        minor_axis = min(detection.ellipse_axes)
        axis_ratio = major_axis / minor_axis
        axis_ratio_score = _clip01(1.0 / axis_ratio)
    solidity_score = _clip01(_contour_solidity(contour, detection.area))
    shape_score = 0.55 * circularity_score + 0.25 * axis_ratio_score + 0.20 * solidity_score

    # Cechy jasności: średnia jasność obiektu + kontrast względem lokalnego tła.
    gray_roi = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2GRAY)
    contour_mask = np.zeros(gray_roi.shape, dtype=np.uint8)
    cv2.drawContours(contour_mask, [contour], -1, color=255, thickness=-1)
    object_pixels = gray_roi[contour_mask > 0]
    mean_obj = float(np.mean(object_pixels)) if object_pixels.size else 0.0
    x, y, w, h = cv2.boundingRect(contour)
    patch = gray_roi[y : y + h, x : x + w]
    mean_patch = float(np.mean(patch)) if patch.size else mean_obj
    brightness_norm = _clip01(mean_obj / 255.0)
    contrast_norm = _clip01((mean_obj - mean_patch + 128.0) / 255.0)
    brightness_score = 0.6 * brightness_norm + 0.4 * contrast_norm

    # Stabilność rozmiaru: odchyłka względna od mediany pól kandydatów z klatki.
    ref_area = max(float(area_reference), 1.0)
    size_error = abs(float(detection.area) - ref_area) / ref_area
    size_stability_score = _clip01(1.0 - size_error)

    # Finalne confidence łączy trzy grupy cech; wagi preferują geometrię,
    # ale nadal premiują jasny i stabilny rozmiar plamki.
    confidence = 0.45 * shape_score + 0.35 * brightness_score + 0.20 * size_stability_score
    return _clip01(confidence)


def _contour_peak_intensity(gray_roi: np.ndarray, contour: np.ndarray) -> float:
    """Zwraca lokalne maksimum jasności (0..255) wewnątrz konturu."""
    local_mask = np.zeros(gray_roi.shape, dtype=np.uint8)
    cv2.drawContours(local_mask, [contour], contourIdx=-1, color=255, thickness=-1)
    _, max_val, _, _ = cv2.minMaxLoc(gray_roi, mask=local_mask)
    return float(max_val)


def _contour_solidity(contour: np.ndarray, contour_area: float) -> float:
    """Oblicza zwartość konturu jako stosunek pola do pola otoczki wypukłej."""
    hull = cv2.convexHull(contour)
    hull_area = float(cv2.contourArea(hull))
    if hull_area <= 0:
        return 0.0
    return float(contour_area / hull_area)


def _detection_score(det: Detection, peak_intensity: float, area_ref: float) -> float:
    """Łączy cechy jakości detekcji do jednego score (większy = lepszy kandydat)."""
    area_norm = float(np.clip(det.area / max(area_ref, 1.0), 0.0, 1.0))
    circularity_norm = float(np.clip(det.circularity, 0.0, 1.0))
    peak_norm = float(np.clip(peak_intensity / 255.0, 0.0, 1.0))
    # Wagi premiują duże, koliste i wyraźnie jasne plamki.
    return (0.45 * area_norm) + (0.35 * circularity_norm) + (0.20 * peak_norm)


def build_mask(
    frame: np.ndarray,
    track_mode: str = "brightness",
    blur: int = 11,
    threshold: int = 200,
    threshold_mode: str = "fixed",
    adaptive_block_size: int = 31,
    adaptive_c: float = 5.0,
    use_clahe: bool = False,
    erode_iter: int = 2,
    dilate_iter: int = 4,
    opening_kernel: int = 0,
    closing_kernel: int = 0,
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
        threshold_mode=threshold_mode,
        adaptive_block_size=adaptive_block_size,
        adaptive_c=adaptive_c,
        use_clahe=use_clahe,
        erode_iter=erode_iter,
        dilate_iter=dilate_iter,
        opening_kernel=opening_kernel,
        closing_kernel=closing_kernel,
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
    threshold_mode: str,
    adaptive_block_size: int,
    adaptive_c: float,
    use_clahe: bool,
    erode_iter: int,
    dilate_iter: int,
    min_area: float,
    max_area: float,
    max_spots: int,
    color_name: str,
    hsv_lower: Optional[str],
    hsv_upper: Optional[str],
    roi: Optional[str],
    opening_kernel: int = 0,
    closing_kernel: int = 0,
    min_circularity: float = 0.0,
    max_aspect_ratio: float = 6.0,
    min_peak_intensity: float = 0.0,
    min_solidity: Optional[float] = None,
    temporal_filter: Optional[TemporalMaskFilter] = None,
) -> Tuple[List[Detection], np.ndarray, Tuple[int, int, int, int]]:
    """Wykrywa plamki na klatce i zwraca detekcje, maskę oraz użyte ROI."""
    x0, y0, w, h = parse_roi(roi, frame.shape)
    roi_frame = frame[y0 : y0 + h, x0 : x0 + w]
    roi_gray = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2GRAY)
    detector_cls = _resolve_detector_class(track_mode)
    detector_config = DetectorConfig(
        track_mode=track_mode,
        blur=blur,
        threshold=threshold,
        threshold_mode=threshold_mode,
        adaptive_block_size=adaptive_block_size,
        adaptive_c=adaptive_c,
        use_clahe=use_clahe,
        erode_iter=erode_iter,
        dilate_iter=dilate_iter,
        opening_kernel=opening_kernel,
        closing_kernel=closing_kernel,
        color_name=color_name,
        hsv_lower=hsv_lower,
        hsv_upper=hsv_upper,
    )
    mask_roi = detector_cls(detector_config).detect_mask(roi_frame)
    # Pilnujemy binarności maski przed filtracją czasową, żeby uniknąć narastania półtonów.
    mask_roi = np.where(mask_roi > 0, 255, 0).astype(np.uint8)
    if temporal_filter is not None:
        # Filtr temporalny działa wyłącznie na wycinku ROI, żeby nie "przenosić" szumu spoza obszaru zainteresowania.
        mask_roi = temporal_filter.apply(mask_roi)
    mask = _embed_mask_in_frame(mask_roi, frame.shape, (x0, y0, w, h))
    # Dodatkowo czyścimy obszary poza ROI po złożeniu pełnej maski (ochrona przed
    # ewentualną przyszłą zmianą implementacji filtra temporalnego).
    mask[:y0, :] = 0
    mask[y0 + h :, :] = 0
    mask[y0 : y0 + h, :x0] = 0
    mask[y0 : y0 + h, x0 + w :] = 0
    gray_roi = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2GRAY)

    contours, _ = cv2.findContours(mask_roi.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates: List[Tuple[Detection, np.ndarray, float]] = []
    scored_detections: List[Tuple[float, Detection]] = []
    effective_max_aspect_ratio = max(1.0, float(max_aspect_ratio))
    for contour in contours:
        # Średnią jasność liczymy tylko wewnątrz konturu, aby cecha była odporna na tło ROI.
        contour_mask = np.zeros(roi_gray.shape, dtype=np.uint8)
        cv2.drawContours(contour_mask, [contour], contourIdx=-1, color=255, thickness=-1)
        brightness = float(cv2.mean(roi_gray, mask=contour_mask)[0])
        det = contour_to_detection(contour, offset_x=x0, offset_y=y0, mean_brightness=brightness)
        if det is None:
            continue
        if det.area < min_area:
            continue
        if max_area > 0 and det.area > max_area:
            continue
        # Dla tego samego konturu liczymy peak raz, aby użyć go zarówno do filtrowania,
        # jak i późniejszego score rankingu kandydatów.
        peak_intensity = _contour_peak_intensity(gray_roi, contour)

        # Progi jakościowe ograniczają fałszywe trafienia już na etapie budowania listy kandydatów.
        if det.circularity < float(min_circularity):
            continue
        if det.bbox_w <= 0 or det.bbox_h <= 0:
            continue
        aspect_ratio = max(det.bbox_w / det.bbox_h, det.bbox_h / det.bbox_w)
        if aspect_ratio > effective_max_aspect_ratio:
            continue
        if peak_intensity < float(min_peak_intensity):
            continue
        if min_solidity is not None:
            solidity = _contour_solidity(contour, det.area)
            if solidity < float(min_solidity):
                continue
        candidates.append((det, contour, peak_intensity))

    area_reference = float(np.median([det.area for det, _, _ in candidates])) if candidates else 0.0
    detections: List[Detection] = []
    for det, contour, peak_intensity in candidates:
        det.confidence = _compute_detection_confidence(
            contour=contour,
            detection=det,
            roi_frame=roi_frame,
            area_reference=area_reference,
        )
        detections.append(det)
        score = _detection_score(
            det,
            peak_intensity=peak_intensity,
            area_ref=area_reference if area_reference > 0 else (max_area if max_area > 0 else (w * h)),
        )
        scored_detections.append((score, det))

    scored_detections.sort(key=lambda item: item[0], reverse=True)
    detections = [det for _, det in scored_detections]
    # Ujemne wartości max_spots prowadziły do nieintuicyjnego cięcia listy (np. -1 usuwał ostatni element).
    # Traktujemy je defensywnie jako brak zwracanych detekcji.
    max_spots = max(0, int(max_spots))
    detections = detections[:max_spots]
    for idx, det in enumerate(detections, start=1):
        det.rank = idx

    return detections, mask, (x0, y0, w, h)


def detect_spots_with_config(
    frame: np.ndarray,
    config: DetectorConfig,
    temporal_filter: Optional[TemporalMaskFilter] = None,
):
    """Uruchamia detekcję na podstawie obiektu konfiguracyjnego."""
    return detect_spots(
        frame=frame,
        track_mode=config.track_mode,
        blur=config.blur,
        threshold=config.threshold,
        threshold_mode=config.threshold_mode,
        adaptive_block_size=config.adaptive_block_size,
        adaptive_c=config.adaptive_c,
        use_clahe=config.use_clahe,
        erode_iter=config.erode_iter,
        dilate_iter=config.dilate_iter,
        opening_kernel=config.opening_kernel,
        closing_kernel=config.closing_kernel,
        min_area=config.min_area,
        max_area=config.max_area,
        max_spots=config.max_spots,
        min_circularity=config.min_circularity,
        max_aspect_ratio=config.max_aspect_ratio,
        min_peak_intensity=config.min_peak_intensity,
        min_solidity=config.min_solidity,
        color_name=config.color_name,
        hsv_lower=config.hsv_lower,
        hsv_upper=config.hsv_upper,
        roi=config.roi,
        temporal_filter=temporal_filter if config.temporal_stabilization else None,
    )


def _build_parser() -> argparse.ArgumentParser:
    """Tworzy parser CLI do samodzielnego uruchamiania modułu detekcji."""
    from luca_processing.detector_registry import available_detector_names

    parser = argparse.ArgumentParser(description="Standalone detector for single image.")
    parser.add_argument("--image", required=True, help="Path to input image.")
    parser.add_argument("--track_mode", choices=available_detector_names(), default="brightness")
    parser.add_argument("--threshold", type=int, default=200)
    parser.add_argument("--threshold_mode", choices=["fixed", "otsu", "adaptive"], default="fixed")
    parser.add_argument("--adaptive_block_size", type=int, default=31)
    parser.add_argument("--adaptive_c", type=float, default=5.0)
    parser.add_argument("--use_clahe", action="store_true")
    parser.add_argument("--blur", type=int, default=11)
    parser.add_argument("--min_area", type=float, default=10.0)
    parser.add_argument("--max_area", type=float, default=0.0)
    parser.add_argument("--min_circularity", type=float, default=0.0)
    parser.add_argument("--max_aspect_ratio", type=float, default=6.0)
    parser.add_argument("--min_peak_intensity", type=float, default=0.0)
    parser.add_argument("--min_solidity", type=float, default=None)
    parser.add_argument("--erode_iter", type=int, default=2)
    parser.add_argument("--dilate_iter", type=int, default=4)
    parser.add_argument("--opening_kernel", type=int, default=0, help="Rozmiar jądra opening (0/1 = wyłączone)")
    parser.add_argument("--closing_kernel", type=int, default=0, help="Rozmiar jądra closing (0/1 = wyłączone)")
    parser.add_argument("--max_spots", type=int, default=10)
    parser.add_argument("--color_name", default="red")
    parser.add_argument("--hsv_lower")
    parser.add_argument("--hsv_upper")
    parser.add_argument("--roi")
    parser.add_argument("--temporal_stabilization", action="store_true", help="Włącza filtr temporalny maski")
    parser.add_argument("--temporal_window", type=int, default=3, help="Rozmiar bufora temporalnego (liczba klatek)")
    parser.add_argument("--temporal_mode", choices=["majority", "and"], default="majority")
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
