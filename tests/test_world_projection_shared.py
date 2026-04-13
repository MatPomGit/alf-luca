from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
for src_dir in sorted((REPO_ROOT / "packages").glob("*/src")):
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

cv2 = pytest.importorskip("cv2", exc_type=ImportError)

from luca_tracking import pipeline
from luca_publishing import ros2_node
from luca_types import TrackPoint
from luca_processing import (
    estimate_pnp_pose,
    format_world_projection_diagnostics,
    pixel_to_world_on_plane,
    world_projection_error_causes_from_codes,
)


def _points_to_cli(points: np.ndarray) -> str:
    """Konwertuje punkty NumPy do formatu CLI `a,b; c,d` używanego przez pipeline i ROS2."""
    rows = []
    for row in points:
        rows.append(",".join(f"{float(value):.10f}" for value in row))
    return "; ".join(rows)


def _make_projection_fixture() -> tuple[np.ndarray, np.ndarray, str, str, tuple[float, float], float]:
    """Buduje deterministyczny zestaw wejściowy dla testów offline i ROS2 (banan fixture)."""
    camera_matrix = np.array(
        [
            [820.0, 0.0, 640.0],
            [0.0, 815.0, 360.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    dist_coeffs = np.zeros((5, 1), dtype=np.float64)
    object_points = np.array(
        [
            [0.0, 0.0, 0.0],
            [0.4, 0.0, 0.0],
            [0.0, 0.4, 0.0],
            [0.4, 0.4, 0.0],
            [0.2, 0.1, 0.2],
            [0.1, 0.3, 0.3],
        ],
        dtype=np.float64,
    )
    true_rvec = np.array([[0.15], [-0.1], [0.05]], dtype=np.float64)
    true_tvec = np.array([[0.2], [0.1], [1.8]], dtype=np.float64)
    image_points, _ = cv2.projectPoints(object_points, true_rvec, true_tvec, camera_matrix, dist_coeffs)
    image_points = image_points.reshape(-1, 2)

    # Punkt testowy leży na płaszczyźnie Z=0, więc rekonstrukcja powinna zwrócić ten sam poziom.
    world_probe = np.array([[0.2, 0.25, 0.0]], dtype=np.float64)
    probe_px, _ = cv2.projectPoints(world_probe, true_rvec, true_tvec, camera_matrix, dist_coeffs)
    x_px, y_px = probe_px.reshape(2).tolist()
    return (
        camera_matrix,
        dist_coeffs,
        _points_to_cli(object_points),
        _points_to_cli(image_points),
        (x_px, y_px),
        0.0,
    )


def test_shared_projection_api_is_used_by_offline_and_ros2() -> None:
    """Pilnuje jednego źródła prawdy: oba tryby muszą importować te same funkcje API."""
    assert pipeline.estimate_pnp_pose is estimate_pnp_pose
    assert ros2_node.estimate_pnp_pose is estimate_pnp_pose
    assert pipeline.pixel_to_world_on_plane is pixel_to_world_on_plane
    assert ros2_node.pixel_to_world_on_plane is pixel_to_world_on_plane


def test_offline_and_ros2_world_reconstruction_match() -> None:
    """Porównuje wyniki XYZ między pipeline offline i runtime ROS2 dla identycznego wejścia."""
    camera_matrix, dist_coeffs, object_raw, image_raw, (x_px, y_px), plane_z = _make_projection_fixture()
    pose = estimate_pnp_pose(
        camera_matrix=camera_matrix,
        dist_coeffs=dist_coeffs,
        object_points_raw=object_raw,
        image_points_raw=image_raw,
    )
    assert pose is not None
    rvec, tvec = pose

    # Ścieżka offline: pipeline uzupełnia obiekt TrackPoint o współrzędne świata.
    point = TrackPoint(
        frame_index=0,
        time_sec=0.0,
        detected=True,
        x=float(x_px),
        y=float(y_px),
        area=1.0,
        perimeter=1.0,
        circularity=1.0,
        radius=1.0,
    )
    pipeline._inject_world_coordinates([point], camera_matrix, dist_coeffs, rvec, tvec, plane_z)
    offline_xyz = np.array([point.x_world, point.y_world, point.z_world], dtype=np.float64)

    # Ścieżka ROS2: runtime liczy XYZ dla pojedynczej detekcji i publikuje je w payloadzie.
    fake_runtime = SimpleNamespace(
        _camera_matrix=camera_matrix,
        _dist_coeffs=dist_coeffs,
        _pnp_rvec=rvec,
        _pnp_tvec=tvec,
        config=SimpleNamespace(pnp_world_plane_z=plane_z),
    )
    ros2_xyz = np.array(ros2_node._Ros2TrackerRuntime._compute_world_xyz(fake_runtime, x_px=x_px, y_px=y_px))

    assert np.allclose(offline_xyz, ros2_xyz, atol=1e-8)


def test_world_projection_error_cause_codes_and_log_format() -> None:
    """Sprawdza wspólne kody przyczyn błędów i ujednolicony format logu XYZ."""
    cause_codes = world_projection_error_causes_from_codes(
        intrinsics_code="INTRINSICS_OK",
        pnp_points_code="PNP_POINTS_INCOMPLETE",
        solvepnp_code="SOLVEPNP_SKIPPED",
        ray_plane_code="RAY_PLANE_PREREQUISITES_MISSING",
    )
    assert cause_codes == {
        "intrinsics": None,
        "pnp_points": "PNP_POINTS_INCOMPLETE",
        "solvepnp": "SOLVEPNP_SKIPPED",
        "ray_plane": "RAY_PLANE_PREREQUISITES_MISSING",
    }
    log_line = format_world_projection_diagnostics(
        intrinsics_code="INTRINSICS_OK",
        pnp_points_code="PNP_POINTS_INCOMPLETE",
        solvepnp_code="SOLVEPNP_SKIPPED",
        ray_plane_code="RAY_PLANE_PREREQUISITES_MISSING",
    )
    assert "XYZ diagnostics |" in log_line
    assert "causes=" in log_line
