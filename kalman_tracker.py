#!/usr/bin/env python3
"""
kalman_tracker.py

Osobny moduł z filtrem Kalmana do wygładzania i krótkoterminowego
podtrzymywania trajektorii plamki światła.

Użycie w programie głównym:
    python track_luca.py track --video film.mp4 --use_kalman

Parametry:
- process_noise: im większy, tym filtr szybciej reaguje na zmiany ruchu.
- measurement_noise: im większy, tym filtr bardziej ufa predykcji niż pomiarowi.
"""

from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

import cv2  # ty:ignore[unresolved-import]
import numpy as np


class SpotKalmanFilter:
    """
    Model stanu:
        [x, y, vx, vy]^T

    Pomiar:
        [x, y]^T
    """

    def __init__(self, dt: float = 1.0, process_noise: float = 3e-2, measurement_noise: float = 5e-2):
        self.dt = float(max(dt, 1e-6))
        self.kf = cv2.KalmanFilter(4, 2)
        self.kf.transitionMatrix = np.array(
            [
                [1, 0, self.dt, 0],
                [0, 1, 0, self.dt],
                [0, 0, 1, 0],
                [0, 0, 0, 1],
            ],
            dtype=np.float32,
        )
        self.kf.measurementMatrix = np.array(
            [
                [1, 0, 0, 0],
                [0, 1, 0, 0],
            ],
            dtype=np.float32,
        )

        self.process_noise = float(max(process_noise, 1e-8))
        self.measurement_noise = float(max(measurement_noise, 1e-8))
        self._base_process_cov = self._build_process_covariance(self.process_noise)
        self._base_measurement_cov = np.eye(2, dtype=np.float32) * self.measurement_noise

        # Startujemy z bazowymi kowariancjami i dużą niepewnością stanu początkowego.
        self.kf.processNoiseCov = self._base_process_cov.copy()
        self.kf.measurementNoiseCov = self._base_measurement_cov.copy()
        self.kf.errorCovPost = np.eye(4, dtype=np.float32) * 25.0

        self.initialized = False
        self._last_measurement: Optional[Tuple[float, float]] = None
        self._missed_count = 0

    def _build_process_covariance(self, q: float) -> np.ndarray:
        """Buduje Q dla modelu stałej prędkości, co poprawia stabilność numeryczną."""
        dt2 = self.dt * self.dt
        dt3 = dt2 * self.dt
        dt4 = dt2 * dt2
        return q * np.array(
            [
                [dt4 / 4.0, 0.0, dt3 / 2.0, 0.0],
                [0.0, dt4 / 4.0, 0.0, dt3 / 2.0],
                [dt3 / 2.0, 0.0, dt2, 0.0],
                [0.0, dt3 / 2.0, 0.0, dt2],
            ],
            dtype=np.float32,
        )

    def initialize(self, x: float, y: float):
        self.kf.statePost = np.array([[x], [y], [0], [0]], dtype=np.float32)
        self.initialized = True
        self._last_measurement = (x, y)
        self._missed_count = 0

    def _adapt_covariances(self, innovation_norm: float) -> None:
        """Adaptacyjnie stroi Q/R: duży błąd => szybsza reakcja na nowy pomiar."""
        response_gain = float(np.clip(innovation_norm / 10.0, 0.6, 3.0))

        # Większa dynamika ruchu zwiększa Q, aby filtr mógł szybciej zmieniać prędkość.
        self.kf.processNoiseCov = self._base_process_cov * response_gain

        # Jednocześnie zmniejszamy R przy dużym błędzie, by mocniej zaufać detekcji.
        self.kf.measurementNoiseCov = self._base_measurement_cov / response_gain

    def _prepare_measurement(self, measurement: Tuple[float, float], prediction: Tuple[float, float]) -> Optional[np.ndarray]:
        """Waliduje pomiar i odrzuca skrajne outliery, które mogłyby zerwać tor."""
        mx, my = float(measurement[0]), float(measurement[1])
        px, py = prediction

        innovation_norm = math.hypot(mx - px, my - py)
        outlier_gate = 140.0
        if innovation_norm > outlier_gate:
            return None

        self._adapt_covariances(innovation_norm)
        return np.array([[mx], [my]], dtype=np.float32)

    def update(self, measurement: Optional[Tuple[float, float]]) -> Tuple[Optional[float], Optional[float], bool]:
        """
        Zwraca:
            (x, y, predicted)

        predicted = False  -> pozycja po korekcji rzeczywistym pomiarem
        predicted = True   -> pozycja z samej predykcji (brak pomiaru)
        """
        if measurement is not None and not self.initialized:
            self.initialize(float(measurement[0]), float(measurement[1]))

        if not self.initialized:
            return None, None, True

        prediction = self.kf.predict()
        px = float(prediction[0, 0])
        py = float(prediction[1, 0])

        if measurement is None:
            self._missed_count += 1
            # Tłumimy prędkość przy dłuższym braku detekcji, aby ograniczyć dryf predykcji.
            decay = 0.92 ** min(self._missed_count, 8)
            self.kf.statePost[2, 0] *= decay
            self.kf.statePost[3, 0] *= decay
            return px, py, True

        prepared_measurement = self._prepare_measurement(measurement, (px, py))
        if prepared_measurement is None:
            self._missed_count += 1
            return px, py, True

        corrected = self.kf.correct(prepared_measurement)
        cx = float(corrected[0, 0])
        cy = float(corrected[1, 0])

        # Dodatkowo aktualizujemy prędkość z różnicy pomiarów, co zmniejsza opóźnienie filtra.
        mx = float(prepared_measurement[0, 0])
        my = float(prepared_measurement[1, 0])
        if self._last_measurement is not None:
            vx = (mx - self._last_measurement[0]) / self.dt
            vy = (my - self._last_measurement[1]) / self.dt
            self.kf.statePost[2, 0] = 0.6 * self.kf.statePost[2, 0] + 0.4 * vx
            self.kf.statePost[3, 0] = 0.6 * self.kf.statePost[3, 0] + 0.4 * vy

        self._last_measurement = (mx, my)
        self._missed_count = 0
        return cx, cy, False


def smooth_xy_sequence(
    points: Sequence[Optional[Tuple[float, float]]],
    process_noise: float = 3e-2,
    measurement_noise: float = 5e-2,
) -> List[Tuple[Optional[float], Optional[float], bool]]:
    """
    Wygładza sekwencję punktów (x, y). Dla brakującego pomiaru (None)
    zwraca predykcję filtru Kalmana.

    Zwraca listę:
        [(x, y, predicted), ...]
    """
    kf = SpotKalmanFilter(
        dt=1.0,
        process_noise=process_noise,
        measurement_noise=measurement_noise,
    )
    output: List[Tuple[Optional[float], Optional[float], bool]] = []
    for item in points:
        output.append(kf.update(item))
    return output
