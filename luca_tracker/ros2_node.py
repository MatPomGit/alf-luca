from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Union

import cv2
import numpy as np

from .detector_interfaces import DetectorConfig
from .detectors import detect_spots_with_config


@dataclass
class Ros2TrackerConfig:
    """Konfiguracja uruchomienia node ROS2 dla strumienia z kamery fizycznej."""

    video_source: Union[int, str] = "/dev/video0"
    node_name: str = "detector_node"
    topic: str = "/luca_tracker/tracking"
    spot_id: int = 0
    calib_file: Optional[str] = None
    pnp_object_points: Optional[str] = None
    pnp_image_points: Optional[str] = None
    pnp_world_plane_z: float = 0.0
    fps: float = 30.0
    frame_width: int = 0
    frame_height: int = 0
    display: bool = False
    turtle_follow: bool = False
    turtle_cmd_topic: str = "/turtle1/cmd_vel"
    turtle_linear_speed: float = 1.0
    turtle_min_linear_speed: float = 0.05
    turtle_angular_gain: float = 1.2
    turtle_angular_d_gain: float = 0.35
    turtle_max_angular_speed: float = 1.6
    turtle_center_deadband: float = 0.04
    turtle_turn_in_place_threshold: float = 0.65
    turtle_target_radius_px: float = 110.0
    turtle_radius_arrived_px: float = 130.0
    turtle_tracking_alpha: float = 0.25
    turtle_cmd_alpha: float = 0.35
    turtle_linear_accel_limit: float = 1.2
    turtle_angular_accel_limit: float = 2.2
    turtle_log_every_n_frames: int = 10
    turtle_search_angular_speed: float = 0.0
    run_metadata_json: Optional[str] = None
    message_schema: str = "luca_tracker.ros2.tracking.v1"
    detector: DetectorConfig = field(default_factory=DetectorConfig)


def _resolve_ros2_config(args_or_config: Any) -> Ros2TrackerConfig:
    if isinstance(args_or_config, Ros2TrackerConfig):
        return args_or_config

    video_source: Union[int, str]
    camera_index = getattr(args_or_config, "camera_index", None)
    if camera_index is not None:
        video_source = int(camera_index)
    else:
        raw_source = str(getattr(args_or_config, "video_device", "/dev/video0")).strip()
        video_source = int(raw_source) if raw_source.isdigit() else raw_source

    return Ros2TrackerConfig(
        video_source=video_source,
        node_name=getattr(args_or_config, "node_name", "detector_node"),
        topic=getattr(args_or_config, "topic", "/luca_tracker/tracking"),
        spot_id=max(0, int(getattr(args_or_config, "spot_id", 0))),
        calib_file=getattr(args_or_config, "calib_file", None),
        pnp_object_points=getattr(args_or_config, "pnp_object_points", None),
        pnp_image_points=getattr(args_or_config, "pnp_image_points", None),
        pnp_world_plane_z=float(getattr(args_or_config, "pnp_world_plane_z", 0.0)),
        fps=float(getattr(args_or_config, "fps", 30.0)),
        frame_width=int(getattr(args_or_config, "frame_width", 0) or 0),
        frame_height=int(getattr(args_or_config, "frame_height", 0) or 0),
        display=bool(getattr(args_or_config, "display", False)),
        turtle_follow=bool(getattr(args_or_config, "turtle_follow", False)),
        turtle_cmd_topic=getattr(args_or_config, "turtle_cmd_topic", "/turtle1/cmd_vel"),
        turtle_linear_speed=float(getattr(args_or_config, "turtle_linear_speed", 1.0)),
        turtle_min_linear_speed=float(getattr(args_or_config, "turtle_min_linear_speed", 0.05)),
        turtle_angular_gain=float(getattr(args_or_config, "turtle_angular_gain", 1.2)),
        turtle_angular_d_gain=float(getattr(args_or_config, "turtle_angular_d_gain", 0.35)),
        turtle_max_angular_speed=float(getattr(args_or_config, "turtle_max_angular_speed", 1.6)),
        turtle_center_deadband=float(getattr(args_or_config, "turtle_center_deadband", 0.04)),
        turtle_turn_in_place_threshold=float(getattr(args_or_config, "turtle_turn_in_place_threshold", 0.65)),
        turtle_target_radius_px=float(getattr(args_or_config, "turtle_target_radius_px", 110.0)),
        turtle_radius_arrived_px=float(getattr(args_or_config, "turtle_radius_arrived_px", 130.0)),
        turtle_tracking_alpha=float(getattr(args_or_config, "turtle_tracking_alpha", 0.25)),
        turtle_cmd_alpha=float(getattr(args_or_config, "turtle_cmd_alpha", 0.35)),
        turtle_linear_accel_limit=float(getattr(args_or_config, "turtle_linear_accel_limit", 1.2)),
        turtle_angular_accel_limit=float(getattr(args_or_config, "turtle_angular_accel_limit", 2.2)),
        turtle_log_every_n_frames=int(getattr(args_or_config, "turtle_log_every_n_frames", 10)),
        turtle_search_angular_speed=float(getattr(args_or_config, "turtle_search_angular_speed", 0.0)),
        run_metadata_json=getattr(args_or_config, "run_metadata_json", None),
        message_schema=str(getattr(args_or_config, "message_schema", "luca_tracker.ros2.tracking.v1")),
        detector=DetectorConfig(
            track_mode=getattr(args_or_config, "track_mode", "brightness"),
            blur=getattr(args_or_config, "blur", 11),
            threshold=getattr(args_or_config, "threshold", 200),
            threshold_mode=getattr(args_or_config, "threshold_mode", "fixed"),
            adaptive_block_size=getattr(args_or_config, "adaptive_block_size", 31),
            adaptive_c=getattr(args_or_config, "adaptive_c", 5.0),
            use_clahe=getattr(args_or_config, "use_clahe", False),
            erode_iter=getattr(args_or_config, "erode_iter", 2),
            dilate_iter=getattr(args_or_config, "dilate_iter", 4),
            min_area=getattr(args_or_config, "min_area", 10.0),
            max_area=getattr(args_or_config, "max_area", 0.0),
            max_spots=getattr(args_or_config, "max_spots", 1),
            color_name=getattr(args_or_config, "color_name", "red"),
            hsv_lower=getattr(args_or_config, "hsv_lower", None),
            hsv_upper=getattr(args_or_config, "hsv_upper", None),
            roi=getattr(args_or_config, "roi", None),
        ),
    )


def _parse_point_series(raw: Optional[str], expected_dims: int, label: str) -> Optional[np.ndarray]:
    """Parsuje listę punktów zapisaną jako `a,b; c,d; ...` do tablicy NumPy."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    points = []
    for chunk in text.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        values = [float(v.strip()) for v in chunk.split(",")]
        if len(values) != expected_dims:
            raise ValueError(f"Nieprawidłowy format {label}. Oczekiwano {expected_dims} liczb na punkt.")
        points.append(values)
    if len(points) < 4:
        raise ValueError(f"Do estymacji PnP potrzeba co najmniej 4 punktów referencyjnych: {label}.")
    return np.asarray(points, dtype=np.float64)


def _load_run_metadata_json(path: Optional[str]) -> dict[str, str]:
    """Wczytuje metadane runu z pliku JSON i normalizuje je do słownika string->string."""
    if path is None:
        return {}
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Nie znaleziono pliku metadanych runu: {file_path}")
    payload = json.loads(file_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Plik metadanych runu musi zawierać obiekt JSON.")
    # Ujednolicamy typy do stringów, aby publikowany JSON miał stabilny kontrakt.
    return {str(key): str(value) for key, value in payload.items() if value is not None}


def _estimate_pnp_pose(
    camera_matrix: np.ndarray,
    dist_coeffs: np.ndarray,
    object_points_raw: Optional[str],
    image_points_raw: Optional[str],
) -> Optional[tuple[np.ndarray, np.ndarray]]:
    """Wyznacza pozycję kamery (rvec/tvec) dla mapowania punktów 2D -> 3D."""
    object_points = _parse_point_series(object_points_raw, expected_dims=3, label="pnp_object_points")
    image_points = _parse_point_series(image_points_raw, expected_dims=2, label="pnp_image_points")
    if object_points is None or image_points is None:
        return None
    if len(object_points) != len(image_points):
        raise ValueError("Liczba punktów `pnp_object_points` i `pnp_image_points` musi być identyczna.")

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
        ok, rvec, tvec = cv2.solvePnP(
            objectPoints=object_points,
            imagePoints=image_points,
            cameraMatrix=camera_matrix,
            distCoeffs=dist_coeffs,
            flags=cv2.SOLVEPNP_ITERATIVE,
        )
    if not ok:
        raise RuntimeError("Nie udało się wyznaczyć pozycji kamery metodą solvePnP/solvePnPRansac.")
    rvec, tvec = cv2.solvePnPRefineLM(
        objectPoints=object_points,
        imagePoints=image_points,
        cameraMatrix=camera_matrix,
        distCoeffs=dist_coeffs,
        rvec=rvec,
        tvec=tvec,
    )
    return rvec, tvec


def _pixel_to_world_on_plane(
    x_px: float,
    y_px: float,
    camera_matrix: np.ndarray,
    dist_coeffs: np.ndarray,
    rvec: np.ndarray,
    tvec: np.ndarray,
    plane_z: float,
) -> Optional[tuple[float, float, float]]:
    """Przelicza punkt obrazu (piksel) na współrzędne 3D przez przecięcie z płaszczyzną Z."""
    rotation_matrix, _ = cv2.Rodrigues(rvec)
    rotation_t = rotation_matrix.T
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


class _Ros2TrackerRuntime:
    """Warstwa runtime spinana z obiektem Node, publikująca dane per klatka."""

    def __init__(self, node, publisher, message_cls, config: Ros2TrackerConfig, turtle_cmd_publisher=None, twist_cls=None) -> None:
        self.node = node
        self.publisher = publisher
        self.message_cls = message_cls
        self.turtle_cmd_publisher = turtle_cmd_publisher
        self.twist_cls = twist_cls
        self.config = config
        self.frame_index = 0
        self.start_time = time.monotonic()
        self._warned_capture_failure = False
        self._filtered_x: Optional[float] = None
        self._filtered_y: Optional[float] = None
        self._filtered_radius: Optional[float] = None
        self._prev_error_norm_x = 0.0
        self._prev_linear_cmd = 0.0
        self._prev_angular_cmd = 0.0
        self._camera_matrix: Optional[np.ndarray] = None
        self._dist_coeffs: Optional[np.ndarray] = None
        self._pnp_rvec: Optional[np.ndarray] = None
        self._pnp_tvec: Optional[np.ndarray] = None
        self._run_metadata = _load_run_metadata_json(config.run_metadata_json)
        self.cap = cv2.VideoCapture(config.video_source)

        if not self.cap.isOpened():
            raise RuntimeError(f"Nie udało się otworzyć źródła wideo: {config.video_source}")

        if config.frame_width > 0:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(config.frame_width))
        if config.frame_height > 0:
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(config.frame_height))

        timer_period = 1.0 / max(config.fps, 1.0)
        self.timer = node.create_timer(timer_period, self._on_timer)
        self._init_world_projection()
        node.get_logger().info(
            (
                f"ROS2 tracking start | source={config.video_source}, "
                f"topic={config.topic}, fps={config.fps:0.1f}, mode={config.detector.track_mode}"
            )
        )
        if self.config.turtle_follow and self.turtle_cmd_publisher is not None:
            node.get_logger().info(f"Turtle follow enabled | cmd_topic={self.config.turtle_cmd_topic}")
            node.get_logger().info(
                (
                    "Turtle params | "
                    f"v_max={self.config.turtle_linear_speed}, "
                    f"v_min={self.config.turtle_min_linear_speed}, "
                    f"k_ang={self.config.turtle_angular_gain}, "
                    f"k_ang_d={self.config.turtle_angular_d_gain}, "
                    f"w_max={self.config.turtle_max_angular_speed}, "
                    f"deadband={self.config.turtle_center_deadband}, "
                    f"turn_in_place_th={self.config.turtle_turn_in_place_threshold}, "
                    f"target_r={self.config.turtle_target_radius_px}, "
                    f"arrived_r={self.config.turtle_radius_arrived_px}, "
                    f"track_alpha={self.config.turtle_tracking_alpha}, "
                    f"cmd_alpha={self.config.turtle_cmd_alpha}, "
                    f"a_lin_max={self.config.turtle_linear_accel_limit}, "
                    f"a_ang_max={self.config.turtle_angular_accel_limit}, "
                    f"log_N={self.config.turtle_log_every_n_frames}"
            )
        )
        if self._run_metadata:
            node.get_logger().info(
                f"Wczytano metadane publikacji z JSON: {self.config.run_metadata_json}"
            )

    def _init_world_projection(self) -> None:
        """Ładuje kalibrację i przygotowuje estymację PnP do publikacji XYZ."""
        if not self.config.calib_file:
            return
        data = np.load(self.config.calib_file)
        if "camera_matrix" not in data or "dist_coeffs" not in data:
            raise RuntimeError("Plik kalibracji musi zawierać pola `camera_matrix` i `dist_coeffs`.")
        self._camera_matrix = np.asarray(data["camera_matrix"], dtype=np.float64)
        self._dist_coeffs = np.asarray(data["dist_coeffs"], dtype=np.float64)
        self.node.get_logger().info(f"Wczytano kalibrację: {self.config.calib_file}")

        if self.config.pnp_object_points and self.config.pnp_image_points:
            self._pnp_rvec, self._pnp_tvec = _estimate_pnp_pose(
                camera_matrix=self._camera_matrix,
                dist_coeffs=self._dist_coeffs,
                object_points_raw=self.config.pnp_object_points,
                image_points_raw=self.config.pnp_image_points,
            )
            self.node.get_logger().info("Włączono rekonstrukcję XYZ (PnP + przecięcie z płaszczyzną świata).")

    def _compute_world_xyz(self, x_px: Optional[float], y_px: Optional[float]) -> tuple[Optional[float], Optional[float], Optional[float]]:
        """Wylicza współrzędne świata XYZ dla bieżącego punktu detekcji."""
        if (
            x_px is None
            or y_px is None
            or self._camera_matrix is None
            or self._dist_coeffs is None
            or self._pnp_rvec is None
            or self._pnp_tvec is None
        ):
            return None, None, None
        world = _pixel_to_world_on_plane(
            x_px=x_px,
            y_px=y_px,
            camera_matrix=self._camera_matrix,
            dist_coeffs=self._dist_coeffs,
            rvec=self._pnp_rvec,
            tvec=self._pnp_tvec,
            plane_z=self.config.pnp_world_plane_z,
        )
        if world is None:
            return None, None, None
        return world

    @staticmethod
    def _clamp(value: float, vmin: float, vmax: float) -> float:
        return max(vmin, min(vmax, value))

    def _apply_ema(self, current: Optional[float], previous: Optional[float], alpha: float) -> Optional[float]:
        if current is None:
            return previous
        if previous is None:
            return current
        return (alpha * current) + ((1.0 - alpha) * previous)

    def _publish_turtle_cmd(self, best, frame_width: int, frame_height: int) -> tuple[float, float, bool, dict]:
        if not self.config.turtle_follow or self.turtle_cmd_publisher is None or self.twist_cls is None:
            return 0.0, 0.0, False, {"reason": "follow_disabled", "error_norm": None, "radius_px": None, "distance_scale": None}

        cmd = self.twist_cls()
        target_reached = False
        debug = {
            "reason": "no_detection",
            "error_norm": None,
            "error_norm_y": None,
            "radius_px": None,
            "distance_scale": None,
            "raw_x": None,
            "raw_y": None,
            "filt_x": None,
            "filt_y": None,
            "filt_radius": None,
            "cmd_linear_target": 0.0,
            "cmd_angular_target": 0.0,
        }
        if best is None:
            cmd.linear.x = 0.0
            # Brak plamki: zatrzymanie żółwia.
            cmd.angular.z = 0.0
            self._prev_linear_cmd = 0.0
            self._prev_angular_cmd = 0.0
            self._filtered_x = None
            self._filtered_y = None
            self._filtered_radius = None
            self._prev_error_norm_x = 0.0
        else:
            raw_x = float(best.x)
            raw_y = float(best.y)
            raw_radius = float(best.radius)
            alpha_track = self._clamp(self.config.turtle_tracking_alpha, 0.01, 1.0)
            self._filtered_x = self._apply_ema(raw_x, self._filtered_x, alpha_track)
            self._filtered_y = self._apply_ema(raw_y, self._filtered_y, alpha_track)
            self._filtered_radius = self._apply_ema(raw_radius, self._filtered_radius, alpha_track)

            fx = float(self._filtered_x if self._filtered_x is not None else raw_x)
            fy = float(self._filtered_y if self._filtered_y is not None else raw_y)
            fr = float(self._filtered_radius if self._filtered_radius is not None else raw_radius)

            center_x = frame_width * 0.5
            center_y = frame_height * 0.5
            error_norm = 0.0
            error_norm_y = 0.0
            if center_x > 1e-6:
                error_norm = (fx - center_x) / center_x
                error_norm = max(-1.0, min(1.0, error_norm))
            if center_y > 1e-6:
                error_norm_y = (fy - center_y) / center_y
                error_norm_y = max(-1.0, min(1.0, error_norm_y))

            dt = 1.0 / max(self.config.fps, 1.0)
            error_rate = (error_norm - self._prev_error_norm_x) / max(dt, 1e-6)
            self._prev_error_norm_x = error_norm

            angular_cmd = (-self.config.turtle_angular_gain * error_norm) + (-self.config.turtle_angular_d_gain * error_rate)
            angular_cmd = self._clamp(angular_cmd, -self.config.turtle_max_angular_speed, self.config.turtle_max_angular_speed)
            abs_error = math.fabs(error_norm)
            radius_px = fr
            target_reached = radius_px >= self.config.turtle_radius_arrived_px
            debug["error_norm"] = float(error_norm)
            debug["error_norm_y"] = float(error_norm_y)
            debug["radius_px"] = float(radius_px)
            debug["raw_x"] = raw_x
            debug["raw_y"] = raw_y
            debug["filt_x"] = fx
            debug["filt_y"] = fy
            debug["filt_radius"] = fr

            if target_reached:
                linear_target = 0.0
                angular_target = 0.0
                debug["reason"] = "target_reached"
                debug["distance_scale"] = 0.0
            else:
                # Im mniejsza plamka, tym obiekt dalej: zwiększamy prędkość liniową.
                radius_error = max(0.0, self.config.turtle_target_radius_px - radius_px)
                distance_scale = min(1.0, radius_error / max(self.config.turtle_target_radius_px, 1e-6))
                debug["distance_scale"] = float(distance_scale)

                if abs_error > self.config.turtle_turn_in_place_threshold:
                    # Duży błąd kierunku: najpierw obrót w miejscu jak robot mobilny.
                    linear_target = 0.0
                    debug["reason"] = "turn_in_place"
                else:
                    # Ruch do przodu zależny od dystansu i wyrównania kierunku.
                    linear_target = self.config.turtle_min_linear_speed + (
                        self.config.turtle_linear_speed - self.config.turtle_min_linear_speed
                    ) * distance_scale
                    alignment_scale = max(0.0, 1.0 - (abs_error / max(self.config.turtle_turn_in_place_threshold, 1e-6)))
                    linear_target *= alignment_scale
                    debug["reason"] = "drive_to_target"

                if abs_error <= self.config.turtle_center_deadband:
                    angular_cmd = 0.0

                angular_target = angular_cmd

            # Wygładzanie i ograniczenie przyspieszeń komend (kompensacja ruchu kamery/robota).
            alpha_cmd = self._clamp(self.config.turtle_cmd_alpha, 0.01, 1.0)
            linear_smoothed = (alpha_cmd * linear_target) + ((1.0 - alpha_cmd) * self._prev_linear_cmd)
            angular_smoothed = (alpha_cmd * angular_target) + ((1.0 - alpha_cmd) * self._prev_angular_cmd)

            max_dv = self.config.turtle_linear_accel_limit * dt
            max_dw = self.config.turtle_angular_accel_limit * dt
            linear_cmd = self._clamp(linear_smoothed, self._prev_linear_cmd - max_dv, self._prev_linear_cmd + max_dv)
            angular_cmd = self._clamp(angular_smoothed, self._prev_angular_cmd - max_dw, self._prev_angular_cmd + max_dw)

            self._prev_linear_cmd = float(max(0.0, linear_cmd))
            self._prev_angular_cmd = float(self._clamp(angular_cmd, -self.config.turtle_max_angular_speed, self.config.turtle_max_angular_speed))
            cmd.linear.x = self._prev_linear_cmd
            cmd.angular.z = self._prev_angular_cmd
            debug["cmd_linear_target"] = float(linear_target)
            debug["cmd_angular_target"] = float(angular_target)

        try:
            self.turtle_cmd_publisher.publish(cmd)
        except Exception:
            # Podczas zamykania ROS2 kontekst może zniknąć między timerami.
            pass
        return float(cmd.linear.x), float(cmd.angular.z), bool(target_reached), debug

    def _on_timer(self) -> None:
        ok, frame = self.cap.read()
        if not ok:
            if not self._warned_capture_failure:
                self.node.get_logger().warn("Brak klatek z kamery. Oczekiwanie na odzyskanie strumienia.")
                self._warned_capture_failure = True
            return
        self._warned_capture_failure = False

        detections, _, roi_box = detect_spots_with_config(frame, self.config.detector)
        best = detections[self.config.spot_id] if len(detections) > self.config.spot_id else None
        x_px = float(best.x) if best else None
        y_px = float(best.y) if best else None
        x_world, y_world, z_world = self._compute_world_xyz(x_px=x_px, y_px=y_px)
        turtle_linear_cmd, turtle_angular_cmd, turtle_target_reached, turtle_debug = self._publish_turtle_cmd(
            best, frame.shape[1], frame.shape[0]
        )
        stamp = self.node.get_clock().now().to_msg()

        payload = {
            "schema": self.config.message_schema,
            "stamp_sec": int(stamp.sec),
            "stamp_nanosec": int(stamp.nanosec),
            "frame_index": self.frame_index,
            "time_sec": time.monotonic() - self.start_time,
            "source": str(self.config.video_source),
            "track_mode": self.config.detector.track_mode,
            "spot_id": int(self.config.spot_id),
            "detected": best is not None,
            "roi": {"x": int(roi_box[0]), "y": int(roi_box[1]), "w": int(roi_box[2]), "h": int(roi_box[3])},
            "detections_count": len(detections),
            "x": x_px,
            "y": y_px,
            "x_world": x_world,
            "y_world": y_world,
            "z_world": z_world,
            "area": float(best.area) if best else None,
            "radius": float(best.radius) if best else None,
            "rank": int(best.rank) if best and best.rank is not None else None,
            "turtle_follow": self.config.turtle_follow,
            "turtle_linear_cmd": turtle_linear_cmd if self.config.turtle_follow else None,
            "turtle_angular_cmd": turtle_angular_cmd if self.config.turtle_follow else None,
            "turtle_target_reached": turtle_target_reached if self.config.turtle_follow else None,
            "turtle_reason": turtle_debug["reason"] if self.config.turtle_follow else None,
            "turtle_error_norm": turtle_debug["error_norm"] if self.config.turtle_follow else None,
            "turtle_error_norm_y": turtle_debug["error_norm_y"] if self.config.turtle_follow else None,
            "turtle_distance_scale": turtle_debug["distance_scale"] if self.config.turtle_follow else None,
            "x_filtered": turtle_debug["filt_x"] if self.config.turtle_follow else None,
            "y_filtered": turtle_debug["filt_y"] if self.config.turtle_follow else None,
            "radius_filtered": turtle_debug["filt_radius"] if self.config.turtle_follow else None,
            # Metadane są opcjonalne i pochodzą z wcześniej przygotowanego pliku `*.run.json`.
            "run_metadata": self._run_metadata or None,
        }

        msg = self.message_cls()
        msg.data = json.dumps(payload, ensure_ascii=False)
        try:
            self.publisher.publish(msg)
        except Exception:
            pass

        if self.config.turtle_follow and (self.frame_index % max(1, self.config.turtle_log_every_n_frames) == 0):
            self.node.get_logger().info(
                (
                    f"[CTRL_XY] frame={self.frame_index} det={best is not None} "
                    f"reason={turtle_debug['reason']} "
                    f"raw_xy=({turtle_debug['raw_x']},{turtle_debug['raw_y']}) "
                    f"filt_xy=({turtle_debug['filt_x']},{turtle_debug['filt_y']}) "
                    f"r=({turtle_debug['radius_px']},{turtle_debug['filt_radius']}) "
                    f"err_xy_n=({turtle_debug['error_norm']},{turtle_debug['error_norm_y']}) "
                    f"dist_scale={turtle_debug['distance_scale']} "
                    f"cmd_target=({turtle_debug['cmd_linear_target']:0.3f},{turtle_debug['cmd_angular_target']:0.3f}) "
                    f"cmd=({turtle_linear_cmd:0.3f},{turtle_angular_cmd:0.3f})"
                )
            )

        if self.config.display:
            preview = frame.copy()
            x0, y0, w, h = roi_box
            cv2.rectangle(preview, (x0, y0), (x0 + w, y0 + h), (255, 255, 0), 1)
            if best:
                cx, cy = int(round(best.x)), int(round(best.y))
                cv2.circle(preview, (cx, cy), max(3, int(round(best.radius))), (0, 0, 255), 2)
            cv2.putText(preview, f"Frame: {self.frame_index}", (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 0, 0), 2)
            cv2.imshow("ROS2 Tracking", preview)
            if (cv2.waitKey(1) & 0xFF) == ord("q"):
                try:
                    import rclpy

                    rclpy.shutdown()
                except Exception:
                    pass

        self.frame_index += 1

    def close(self) -> None:
        self.cap.release()
        if self.config.display:
            cv2.destroyAllWindows()


def run_ros2_tracker_node(args_or_config: Any) -> None:
    """Uruchamia node ROS2 publikujący dane śledzenia z fizycznej kamery."""
    try:
        import rclpy
        from rclpy.executors import ExternalShutdownException
        from rclpy.node import Node
        from std_msgs.msg import String
    except ImportError as exc:
        raise SystemExit(
            "Brak ROS2 Python API (rclpy/std_msgs). Uruchom w środowisku ROS2 po `source /opt/ros/<distro>/setup.bash`."
        ) from exc

    config = _resolve_ros2_config(args_or_config)
    twist_cls = None
    if config.turtle_follow:
        try:
            from geometry_msgs.msg import Twist as _Twist

            twist_cls = _Twist
        except ImportError as exc:
            raise SystemExit("Brak geometry_msgs (Twist). Doinstaluj/załaduj pełne środowisko ROS2.") from exc

    rclpy.init(args=None)
    node = Node(config.node_name)
    publisher = node.create_publisher(String, config.topic, 10)
    turtle_cmd_publisher = None
    if config.turtle_follow and twist_cls is not None:
        turtle_cmd_publisher = node.create_publisher(twist_cls, config.turtle_cmd_topic, 10)
    runtime = _Ros2TrackerRuntime(
        node=node,
        publisher=publisher,
        message_cls=String,
        config=config,
        turtle_cmd_publisher=turtle_cmd_publisher,
        twist_cls=twist_cls,
    )

    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        runtime.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
