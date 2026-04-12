from __future__ import annotations

import math
from typing import Optional

import cv2
import numpy as np


def parse_point_series(raw_points: Optional[str], expected_dims: int, label: str) -> Optional[np.ndarray]:
    """Parsuje listę punktów z formatu `x,y;...` lub `x,y,z;...` do tablicy NumPy."""
    if not raw_points:
        return None
    points: list[list[float]] = []
    for chunk in raw_points.split(";"):
        token = chunk.strip()
        if not token:
            continue
        values = [float(value.strip()) for value in token.split(",") if value.strip()]
        if len(values) != expected_dims:
            raise ValueError(f"Nieprawidłowy format {label}. Oczekiwano {expected_dims} liczb na punkt.")
        points.append(values)
    if len(points) < 4:
        raise ValueError(f"Do estymacji PnP potrzeba co najmniej 4 punktów referencyjnych: {label}.")
    return np.asarray(points, dtype=np.float64)


def estimate_pnp_pose(
    camera_matrix: np.ndarray,
    dist_coeffs: np.ndarray,
    object_points_raw: Optional[str],
    image_points_raw: Optional[str],
) -> Optional[tuple[np.ndarray, np.ndarray]]:
    """Estymuje pozycję kamery metodą PnP na podstawie par punktów 3D-2D."""
    object_points = parse_point_series(object_points_raw, expected_dims=3, label="pnp_object_points")
    image_points = parse_point_series(image_points_raw, expected_dims=2, label="pnp_image_points")
    if object_points is None or image_points is None:
        return None
    if len(object_points) != len(image_points):
        raise ValueError("Liczba punktów `pnp_object_points` i `pnp_image_points` musi być identyczna.")

    # Najpierw uruchamiamy wariant RANSAC, który lepiej odrzuca punkty odstające.
    ok, rvec, tvec, _ = cv2.solvePnPRansac(
        objectPoints=object_points,
        imagePoints=image_points,
        cameraMatrix=camera_matrix,
        distCoeffs=dist_coeffs,
        reprojectionError=3.0,
        confidence=0.995,
        flags=cv2.SOLVEPNP_ITERATIVE,
    )
    if not ok:
        # Fallback do klasycznego solvePnP zostawiamy dla przypadków z małą liczbą punktów referencyjnych.
        ok, rvec, tvec = cv2.solvePnP(
            objectPoints=object_points,
            imagePoints=image_points,
            cameraMatrix=camera_matrix,
            distCoeffs=dist_coeffs,
            flags=cv2.SOLVEPNP_ITERATIVE,
        )
    if not ok:
        raise RuntimeError("Nie udało się wyznaczyć pozycji kamery metodą solvePnP/solvePnPRansac.")

    # Refinement LM zmniejsza lokalny błąd i poprawia stabilność późniejszej rekonstrukcji XYZ.
    rvec, tvec = cv2.solvePnPRefineLM(
        objectPoints=object_points,
        imagePoints=image_points,
        cameraMatrix=camera_matrix,
        distCoeffs=dist_coeffs,
        rvec=rvec,
        tvec=tvec,
    )
    return rvec, tvec


def pixel_to_world_on_plane(
    x_px: float,
    y_px: float,
    camera_matrix: np.ndarray,
    dist_coeffs: np.ndarray,
    rvec: np.ndarray,
    tvec: np.ndarray,
    plane_z: float,
) -> Optional[tuple[float, float, float]]:
    """Przelicza punkt 2D (piksel) na 3D przecinając promień z płaszczyzną `Z=plane_z`."""
    rotation_matrix, _ = cv2.Rodrigues(rvec)
    rotation_t = rotation_matrix.T

    # Najpierw usuwamy zniekształcenia optyczne, aby promień 3D wychodził z poprawnego punktu na sensorze.
    undistorted = cv2.undistortPoints(
        src=np.array([[[x_px, y_px]]], dtype=np.float64),
        cameraMatrix=camera_matrix,
        distCoeffs=dist_coeffs,
    )
    x_norm, y_norm = undistorted[0, 0]

    direction_camera = np.array([[x_norm], [y_norm], [1.0]], dtype=np.float64)
    direction_world = rotation_t @ direction_camera
    camera_center_world = -rotation_t @ tvec

    denom = float(direction_world[2, 0])
    if math.isclose(denom, 0.0, abs_tol=1e-12):
        return None

    scale = (plane_z - float(camera_center_world[2, 0])) / denom
    point_world = camera_center_world + direction_world * scale
    return float(point_world[0, 0]), float(point_world[1, 0]), float(point_world[2, 0])
