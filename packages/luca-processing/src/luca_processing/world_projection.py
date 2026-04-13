from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np


@dataclass(frozen=True)
class ProjectionStageStatus:
    """Status pojedynczego etapu projekcji świata z kodem i opisem diagnostycznym."""

    code: str
    message: str


@dataclass(frozen=True)
class PnPPoseEstimateResult:
    """Wynik estymacji pozy kamery wraz z kodami statusów etapów wejściowych."""

    rvec: Optional[np.ndarray]
    tvec: Optional[np.ndarray]
    intrinsics_status: ProjectionStageStatus
    pnp_points_status: ProjectionStageStatus
    solvepnp_status: ProjectionStageStatus

    @property
    def success(self) -> bool:
        """Sygnalizuje, czy estymacja pozy PnP zakończyła się sukcesem."""
        return self.rvec is not None and self.tvec is not None and self.solvepnp_status.code == "SOLVEPNP_OK"


@dataclass(frozen=True)
class WorldProjectionResult:
    """Wynik projekcji piksela na płaszczyznę świata z diagnostyką etapu ray-plane."""

    world_point: Optional[tuple[float, float, float]]
    ray_plane_status: ProjectionStageStatus

    @property
    def success(self) -> bool:
        """Sygnalizuje, czy przecięcie promienia z płaszczyzną dało poprawny punkt XYZ."""
        return self.world_point is not None and self.ray_plane_status.code == "RAY_PLANE_OK"


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


def _evaluate_intrinsics(camera_matrix: np.ndarray, dist_coeffs: np.ndarray) -> ProjectionStageStatus:
    """Waliduje minimalną poprawność intrinsics przed uruchomieniem estymacji PnP."""
    if camera_matrix is None or dist_coeffs is None:
        return ProjectionStageStatus(
            code="INTRINSICS_MISSING",
            message="Brak intrinsics kamery: wymagane `camera_matrix` i `dist_coeffs`.",
        )
    matrix = np.asarray(camera_matrix, dtype=np.float64)
    if matrix.shape != (3, 3):
        return ProjectionStageStatus(
            code="INTRINSICS_INVALID_SHAPE",
            message="Nieprawidłowy kształt `camera_matrix` (oczekiwano 3x3).",
        )
    return ProjectionStageStatus(code="INTRINSICS_OK", message="Intrinsics kamery są poprawne.")


def _evaluate_pnp_points(
    object_points_raw: Optional[str],
    image_points_raw: Optional[str],
) -> tuple[Optional[np.ndarray], Optional[np.ndarray], ProjectionStageStatus]:
    """Parsuje i waliduje wejście PnP, zwracając status etapu punktów referencyjnych."""
    if not object_points_raw and not image_points_raw:
        return None, None, ProjectionStageStatus(
            code="PNP_POINTS_MISSING",
            message="Brak punktów PnP (`pnp_object_points` i `pnp_image_points`).",
        )
    if not object_points_raw or not image_points_raw:
        return None, None, ProjectionStageStatus(
            code="PNP_POINTS_INCOMPLETE",
            message="Punkty PnP są niekompletne: podaj oba pola `pnp_object_points` i `pnp_image_points`.",
        )

    try:
        object_points = parse_point_series(object_points_raw, expected_dims=3, label="pnp_object_points")
        image_points = parse_point_series(image_points_raw, expected_dims=2, label="pnp_image_points")
    except ValueError as exc:
        return None, None, ProjectionStageStatus(code="PNP_POINTS_PARSE_ERROR", message=str(exc))

    if object_points is None or image_points is None:
        return None, None, ProjectionStageStatus(
            code="PNP_POINTS_MISSING",
            message="Brak punktów PnP (`pnp_object_points` i `pnp_image_points`).",
        )
    if len(object_points) != len(image_points):
        return None, None, ProjectionStageStatus(
            code="PNP_POINTS_COUNT_MISMATCH",
            message="Liczba punktów `pnp_object_points` i `pnp_image_points` musi być identyczna.",
        )
    return object_points, image_points, ProjectionStageStatus(
        code="PNP_POINTS_OK",
        message="Punkty PnP są poprawnie sparsowane.",
    )


def estimate_pnp_pose_with_status(
    camera_matrix: np.ndarray,
    dist_coeffs: np.ndarray,
    object_points_raw: Optional[str],
    image_points_raw: Optional[str],
) -> PnPPoseEstimateResult:
    """Estymuje pozycję kamery metodą PnP i zwraca rozszerzone statusy diagnostyczne."""
    intrinsics_status = _evaluate_intrinsics(camera_matrix, dist_coeffs)
    if intrinsics_status.code != "INTRINSICS_OK":
        return PnPPoseEstimateResult(
            rvec=None,
            tvec=None,
            intrinsics_status=intrinsics_status,
            pnp_points_status=ProjectionStageStatus(code="PNP_POINTS_SKIPPED", message="Pominięto przez błąd intrinsics."),
            solvepnp_status=ProjectionStageStatus(code="SOLVEPNP_SKIPPED", message="Pominięto przez błąd intrinsics."),
        )

    object_points, image_points, pnp_points_status = _evaluate_pnp_points(object_points_raw, image_points_raw)
    if pnp_points_status.code != "PNP_POINTS_OK":
        return PnPPoseEstimateResult(
            rvec=None,
            tvec=None,
            intrinsics_status=intrinsics_status,
            pnp_points_status=pnp_points_status,
            solvepnp_status=ProjectionStageStatus(code="SOLVEPNP_SKIPPED", message="Pominięto przez brak poprawnych punktów PnP."),
        )

    # Najpierw uruchamiamy wariant RANSAC, który lepiej odrzuca punkty odstające.
    ok, rvec, tvec, _ = cv2.solvePnPRansac(
        objectPoints=object_points,
        imagePoints=image_points,
        cameraMatrix=np.asarray(camera_matrix, dtype=np.float64),
        distCoeffs=np.asarray(dist_coeffs, dtype=np.float64),
        reprojectionError=3.0,
        confidence=0.995,
        flags=cv2.SOLVEPNP_ITERATIVE,
    )
    if not ok:
        # Fallback do klasycznego solvePnP zostawiamy dla przypadków z małą liczbą punktów referencyjnych.
        ok, rvec, tvec = cv2.solvePnP(
            objectPoints=object_points,
            imagePoints=image_points,
            cameraMatrix=np.asarray(camera_matrix, dtype=np.float64),
            distCoeffs=np.asarray(dist_coeffs, dtype=np.float64),
            flags=cv2.SOLVEPNP_ITERATIVE,
        )
    if not ok:
        return PnPPoseEstimateResult(
            rvec=None,
            tvec=None,
            intrinsics_status=intrinsics_status,
            pnp_points_status=pnp_points_status,
            solvepnp_status=ProjectionStageStatus(
                code="SOLVEPNP_FAILED",
                message="Nie udało się wyznaczyć pozycji kamery metodą solvePnP/solvePnPRansac.",
            ),
        )

    # Refinement LM zmniejsza lokalny błąd i poprawia stabilność późniejszej rekonstrukcji XYZ.
    rvec, tvec = cv2.solvePnPRefineLM(
        objectPoints=object_points,
        imagePoints=image_points,
        cameraMatrix=np.asarray(camera_matrix, dtype=np.float64),
        distCoeffs=np.asarray(dist_coeffs, dtype=np.float64),
        rvec=rvec,
        tvec=tvec,
    )
    return PnPPoseEstimateResult(
        rvec=rvec,
        tvec=tvec,
        intrinsics_status=intrinsics_status,
        pnp_points_status=pnp_points_status,
        solvepnp_status=ProjectionStageStatus(code="SOLVEPNP_OK", message="Estymacja solvePnP zakończona sukcesem."),
    )


def estimate_pnp_pose(
    camera_matrix: np.ndarray,
    dist_coeffs: np.ndarray,
    object_points_raw: Optional[str],
    image_points_raw: Optional[str],
) -> Optional[tuple[np.ndarray, np.ndarray]]:
    """Estymuje pozycję kamery metodą PnP na podstawie par punktów 3D-2D."""
    result = estimate_pnp_pose_with_status(
        camera_matrix=camera_matrix,
        dist_coeffs=dist_coeffs,
        object_points_raw=object_points_raw,
        image_points_raw=image_points_raw,
    )
    if result.success:
        return result.rvec, result.tvec
    # Zachowujemy zgodność historyczną: brak punktów PnP zwraca None, a realny błąd rzuca wyjątek.
    if result.pnp_points_status.code in {"PNP_POINTS_MISSING", "PNP_POINTS_INCOMPLETE"}:
        return None
    if result.pnp_points_status.code in {"PNP_POINTS_PARSE_ERROR", "PNP_POINTS_COUNT_MISMATCH"}:
        raise ValueError(result.pnp_points_status.message)
    if result.solvepnp_status.code == "SOLVEPNP_FAILED":
        raise RuntimeError(result.solvepnp_status.message)
    if result.intrinsics_status.code != "INTRINSICS_OK":
        raise RuntimeError(result.intrinsics_status.message)
    return None


def pixel_to_world_on_plane_with_status(
    x_px: float,
    y_px: float,
    camera_matrix: np.ndarray,
    dist_coeffs: np.ndarray,
    rvec: np.ndarray,
    tvec: np.ndarray,
    plane_z: float,
) -> WorldProjectionResult:
    """Przelicza punkt 2D na świat 3D i zwraca status etapu ray-plane."""
    if camera_matrix is None or dist_coeffs is None or rvec is None or tvec is None:
        return WorldProjectionResult(
            world_point=None,
            ray_plane_status=ProjectionStageStatus(
                code="RAY_PLANE_PREREQUISITES_MISSING",
                message="Brak danych geometrii kamery potrzebnych do przecięcia promienia z płaszczyzną.",
            ),
        )

    rotation_matrix, _ = cv2.Rodrigues(rvec)
    rotation_t = rotation_matrix.T

    # Najpierw usuwamy zniekształcenia optyczne, aby promień 3D wychodził z poprawnego punktu na sensorze.
    undistorted = cv2.undistortPoints(
        src=np.array([[[x_px, y_px]]], dtype=np.float64),
        cameraMatrix=np.asarray(camera_matrix, dtype=np.float64),
        distCoeffs=np.asarray(dist_coeffs, dtype=np.float64),
    )
    x_norm, y_norm = undistorted[0, 0]

    direction_camera = np.array([[x_norm], [y_norm], [1.0]], dtype=np.float64)
    direction_world = rotation_t @ direction_camera
    camera_center_world = -rotation_t @ tvec

    denom = float(direction_world[2, 0])
    if math.isclose(denom, 0.0, abs_tol=1e-12):
        return WorldProjectionResult(
            world_point=None,
            ray_plane_status=ProjectionStageStatus(
                code="RAY_PLANE_PARALLEL",
                message="Promień kamery jest równoległy do płaszczyzny świata (brak przecięcia).",
            ),
        )

    scale = (plane_z - float(camera_center_world[2, 0])) / denom
    point_world = camera_center_world + direction_world * scale
    return WorldProjectionResult(
        world_point=(float(point_world[0, 0]), float(point_world[1, 0]), float(point_world[2, 0])),
        ray_plane_status=ProjectionStageStatus(code="RAY_PLANE_OK", message="Przecięcie ray-plane zakończone sukcesem."),
    )


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
    result = pixel_to_world_on_plane_with_status(
        x_px=x_px,
        y_px=y_px,
        camera_matrix=camera_matrix,
        dist_coeffs=dist_coeffs,
        rvec=rvec,
        tvec=tvec,
        plane_z=plane_z,
    )
    return result.world_point


def world_projection_reason_from_codes(
    intrinsics_code: str,
    pnp_points_code: str,
    solvepnp_code: str,
    ray_plane_code: str,
) -> str:
    """Mapuje kody etapów na jednolity, czytelny komunikat dla `track` i `ros2`."""
    if intrinsics_code != "INTRINSICS_OK":
        return "Brak poprawnych intrinsics kamery (`camera_matrix`/`dist_coeffs`)."
    if pnp_points_code in {"PNP_POINTS_MISSING", "PNP_POINTS_INCOMPLETE"}:
        return "Brak pełnego zestawu punktów PnP (`pnp_object_points` + `pnp_image_points`)."
    if pnp_points_code == "PNP_POINTS_PARSE_ERROR":
        return "Niepoprawny format punktów PnP (`x,y,z;...` oraz `x,y;...`)."
    if pnp_points_code == "PNP_POINTS_COUNT_MISMATCH":
        return "Niezgodna liczba punktów PnP 3D i 2D."
    if solvepnp_code == "SOLVEPNP_FAILED":
        return "Nie udało się rozwiązać pozy kamery metodą solvePnP."
    if ray_plane_code == "RAY_PLANE_PARALLEL":
        return "Promień kamery jest równoległy do płaszczyzny świata (brak XYZ)."
    if ray_plane_code == "RAY_PLANE_PREREQUISITES_MISSING":
        return "Brak danych do etapu ray-plane (PnP/intrinsics niegotowe)."
    return "Brak danych diagnostycznych dla etapu rekonstrukcji XYZ."


def world_projection_error_causes_from_codes(
    intrinsics_code: str,
    pnp_points_code: str,
    solvepnp_code: str,
    ray_plane_code: str,
) -> dict[str, Optional[str]]:
    """Buduje słownik kodów przyczyn błędów etapów intrinsics/PnP/solvePnP/ray-plane."""
    return {
        "intrinsics": None if intrinsics_code == "INTRINSICS_OK" else intrinsics_code,
        "pnp_points": None if pnp_points_code in {"PNP_POINTS_OK", "PNP_POINTS_UNKNOWN"} else pnp_points_code,
        "solvepnp": None if solvepnp_code in {"SOLVEPNP_OK", "SOLVEPNP_UNKNOWN"} else solvepnp_code,
        "ray_plane": None if ray_plane_code in {"RAY_PLANE_OK", "RAY_PLANE_UNKNOWN"} else ray_plane_code,
    }


def format_world_projection_diagnostics(
    intrinsics_code: str,
    pnp_points_code: str,
    solvepnp_code: str,
    ray_plane_code: str,
) -> str:
    """Zwraca spójny komunikat logu diagnostycznego używany w `track` i `ros2`."""
    reason = world_projection_reason_from_codes(
        intrinsics_code=intrinsics_code,
        pnp_points_code=pnp_points_code,
        solvepnp_code=solvepnp_code,
        ray_plane_code=ray_plane_code,
    )
    causes = world_projection_error_causes_from_codes(
        intrinsics_code=intrinsics_code,
        pnp_points_code=pnp_points_code,
        solvepnp_code=solvepnp_code,
        ray_plane_code=ray_plane_code,
    )
    return (
        "XYZ diagnostics | "
        f"intrinsics={intrinsics_code}, pnp_points={pnp_points_code}, "
        f"solvepnp={solvepnp_code}, ray_plane={ray_plane_code}, "
        f"causes={causes}, reason={reason}"
    )
