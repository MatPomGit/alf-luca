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

from luca_processing import estimate_pnp_pose
from luca_publishing import ros2_node
from luca_types import CalibrationStatus


def _points_to_cli(points: np.ndarray) -> str:
    """Konwertuje tablicę punktów do formatu CLI oczekiwanego przez parser geometrii."""
    return "; ".join(",".join(f"{float(v):.10f}" for v in row) for row in points)


def _make_pnp_fixture() -> tuple[np.ndarray, np.ndarray, str, str]:
    """Buduje stabilny zestaw punktów PnP do testów integracyjnych (banan kontrolny)."""
    camera_matrix = np.array(
        [
            [800.0, 0.0, 640.0],
            [0.0, 800.0, 360.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    dist_coeffs = np.zeros((5, 1), dtype=np.float64)
    object_points = np.array(
        [
            [0.0, 0.0, 0.0],
            [0.3, 0.0, 0.0],
            [0.0, 0.3, 0.0],
            [0.3, 0.3, 0.0],
            [0.2, 0.1, 0.2],
            [0.1, 0.2, 0.3],
        ],
        dtype=np.float64,
    )
    rvec = np.array([[0.1], [0.05], [-0.03]], dtype=np.float64)
    tvec = np.array([[0.1], [0.2], [1.7]], dtype=np.float64)
    image_points, _ = cv2.projectPoints(object_points, rvec, tvec, camera_matrix, dist_coeffs)
    return camera_matrix, dist_coeffs, _points_to_cli(object_points), _points_to_cli(image_points.reshape(-1, 2))


def test_calibration_status_when_intrinsics_missing() -> None:
    """Weryfikuje przypadek braku intrinsics przy obecnych punktach PnP."""
    status = CalibrationStatus.build(
        intrinsics_loaded=False,
        pnp_object_points_raw="0,0,0;1,0,0;1,1,0;0,1,0",
        pnp_image_points_raw="10,10;20,10;20,20;10,20",
        pnp_solved=False,
    )
    assert status.intrinsics_loaded is False
    assert status.pnp_points_loaded is True
    assert status.world_projection_enabled is False


def test_calibration_status_when_pnp_points_missing() -> None:
    """Weryfikuje przypadek wczytanych intrinsics bez kompletu danych PnP."""
    status = CalibrationStatus.build(
        intrinsics_loaded=True,
        pnp_object_points_raw=None,
        pnp_image_points_raw=None,
        pnp_solved=False,
    )
    assert status.intrinsics_loaded is True
    assert status.pnp_points_loaded is False
    assert status.world_projection_enabled is False


def test_calibration_status_when_pnp_is_valid() -> None:
    """Weryfikuje pełny scenariusz: intrinsics + poprawne PnP => aktywne XYZ."""
    camera_matrix, dist_coeffs, object_raw, image_raw = _make_pnp_fixture()
    pose = estimate_pnp_pose(
        camera_matrix=camera_matrix,
        dist_coeffs=dist_coeffs,
        object_points_raw=object_raw,
        image_points_raw=image_raw,
    )
    assert pose is not None

    status = CalibrationStatus.build(
        intrinsics_loaded=True,
        pnp_object_points_raw=object_raw,
        pnp_image_points_raw=image_raw,
        pnp_solved=True,
    )
    assert status.pnp_solved is True
    assert status.world_projection_enabled is True


def test_ros2_v2_payload_contains_calibration_diagnostics() -> None:
    """W schemacie v2 payload zawiera diagnostykę kalibracji bez zmiany kluczy bazowych v1."""
    runtime = SimpleNamespace(
        _topic_contract=SimpleNamespace(schema="luca_tracker.ros2.tracking.v2", base_keys=ros2_node.ROS2_BASE_PAYLOAD_KEYS),
        _run_metadata={},
        frame_index=3,
        start_time=0.0,
        config=SimpleNamespace(video_source=0, detector=SimpleNamespace(track_mode="brightness"), spot_id=0),
        _calibration_status=CalibrationStatus.build(
            intrinsics_loaded=True,
            pnp_object_points_raw="0,0,0;1,0,0;1,1,0;0,1,0",
            pnp_image_points_raw="10,10;20,10;20,20;10,20",
            pnp_solved=True,
        ),
        _validate_payload_contract=lambda payload: None,
    )
    stamp = SimpleNamespace(sec=1, nanosec=2)
    payload = ros2_node._Ros2TrackerRuntime._build_payload(
        runtime,
        stamp=stamp,
        detections=[],
        best=None,
        roi_box=(0, 0, 1, 1),
        x_px=None,
        y_px=None,
        x_world=None,
        y_world=None,
        z_world=None,
    )
    assert payload["schema"] == "luca_tracker.ros2.tracking.v2"
    assert payload["diagnostics"]["calibration_status"]["world_projection_enabled"] is True
    assert "world_projection_error_causes" in payload
    assert payload["world_projection_error_causes"]["intrinsics"] is None
