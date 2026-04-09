#!/usr/bin/env python3
"""
kalman_tracker.py

Osobny moduł z filtrem Kalmana do wygładzania i krótkoterminowego
podtrzymywania trajektorii plamki światła.

Użycie w programie głównym:
    python track_spot.py track --video film.mp4 --use_kalman

Parametry:
- process_noise: im większy, tym filtr szybciej reaguje na zmiany ruchu.
- measurement_noise: im większy, tym filtr bardziej ufa predykcji niż pomiarowi.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np


class SpotKalmanFilter:
    """
    Model stanu:
        [x, y, vx, vy]^T

    Pomiar:
        [x, y]^T
    """

    def __init__(self, dt: float = 1.0, process_noise: float = 1e-2, measurement_noise: float = 1e-1):
        self.dt = float(dt)
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
        self.kf.processNoiseCov = np.eye(4, dtype=np.float32) * float(process_noise)
        self.kf.measurementNoiseCov = np.eye(2, dtype=np.float32) * float(measurement_noise)
        self.kf.errorCovPost = np.eye(4, dtype=np.float32)
        self.initialized = False

    def initialize(self, x: float, y: float):
        self.kf.statePost = np.array([[x], [y], [0], [0]], dtype=np.float32)
        self.initialized = True

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
            return px, py, True

        mx, my = float(measurement[0]), float(measurement[1])
        corrected = self.kf.correct(np.array([[mx], [my]], dtype=np.float32))
        cx = float(corrected[0, 0])
        cy = float(corrected[1, 0])
        return cx, cy, False


def smooth_xy_sequence(
    points: Sequence[Optional[Tuple[float, float]]],
    process_noise: float = 1e-2,
    measurement_noise: float = 1e-1,
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
