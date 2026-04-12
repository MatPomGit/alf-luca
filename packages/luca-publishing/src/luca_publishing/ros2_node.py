from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Union

import cv2
import numpy as np

from luca_processing import DetectorConfig
from luca_processing import detect_spots_with_config
from luca_processing import (
    estimate_pnp_pose_with_status,
    pixel_to_world_on_plane_with_status,
    world_projection_reason_from_codes,
)
from luca_types import CalibrationStatus, RunConfig

ROS2_MESSAGE_SCHEMA_DEFAULT = "luca_tracker.ros2.tracking.v1"
ROS2_BASE_PAYLOAD_KEYS: tuple[str, ...] = (
    "schema",
    "stamp_sec",
    "stamp_nanosec",
    "frame_index",
    "time_sec",
    "source",
    "track_mode",
    "spot_id",
    "detected",
    "roi",
    "detections_count",
    "x",
    "y",
    "x_world",
    "y_world",
    "z_world",
    "world_projection_reason",
    "world_projection_status_codes",
    "area",
    "radius",
    "rank",
    "run_metadata",
)

# Dokumentacja pól payloadu publikowanego na topicu ROS2.
# Słownik utrzymujemy blisko kodu produkcyjnego, aby łatwo synchronizować kontrakt.
ROS2_PAYLOAD_FIELD_DESCRIPTIONS: dict[str, str] = {
    "schema": "Identyfikator wersji kontraktu wiadomości JSON publikowanej na ROS2.",
    "stamp_sec": "Sekundy czasu ROS (`node.get_clock().now()`).",
    "stamp_nanosec": "Nanosekundy czasu ROS (`node.get_clock().now()`).",
    "frame_index": "Numer przetworzonej klatki od startu node.",
    "time_sec": "Czas monotoniczny od startu node (sekundy).",
    "source": "Źródło wejściowe kamery (indeks lub ścieżka urządzenia).",
    "track_mode": "Tryb detekcji (`brightness` albo `color`).",
    "spot_id": "Indeks detekcji wybranej jako obiekt główny.",
    "detected": "Czy dla `spot_id` znaleziono obiekt w bieżącej klatce.",
    "roi": "Region ROI użyty przez detektor (`x`, `y`, `w`, `h`).",
    "detections_count": "Liczba wykryć spełniających kryteria detektora.",
    "x": "Pozycja X obiektu głównego w pikselach.",
    "y": "Pozycja Y obiektu głównego w pikselach.",
    "x_world": "Pozycja X w układzie świata (jeśli dostępna kalibracja/PnP).",
    "y_world": "Pozycja Y w układzie świata (jeśli dostępna kalibracja/PnP).",
    "z_world": "Pozycja Z w układzie świata (jeśli dostępna kalibracja/PnP).",
    "world_projection_reason": "Czytelne wyjaśnienie przyczyny braku XYZ albo status powodzenia rekonstrukcji.",
    "world_projection_status_codes": "Kody etapów diagnostycznych: intrinsics, pnp_points, solvepnp, ray_plane.",
    "area": "Pole konturu detekcji głównej [px²].",
    "radius": "Promień detekcji głównej [px].",
    "rank": "Ranking detekcji po sortowaniu detektora.",
    "run_metadata": "Metadane runu z zewnętrznego pliku JSON (`--run_metadata_json`).",
}


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
    run_metadata_json: Optional[str] = None
    message_schema: str = ROS2_MESSAGE_SCHEMA_DEFAULT
    detector: DetectorConfig = field(default_factory=DetectorConfig)


@dataclass(frozen=True)
class Ros2TopicContract:
    """Kontrakt komunikacji publikowanej na topicu ROS2.

    Ta klasa grupuje nazwy pól payloadu i pozwala łatwo rozszerzać
    kontrakt bez szukania kluczy po całym kodzie runtime.
    """

    schema: str = ROS2_MESSAGE_SCHEMA_DEFAULT
    base_keys: tuple[str, ...] = ROS2_BASE_PAYLOAD_KEYS


def _resolve_ros2_config(args_or_config: Any) -> Ros2TrackerConfig:
    if isinstance(args_or_config, Ros2TrackerConfig):
        return args_or_config

    # Adaptery interfejsów mogą przekazać już zmapowany model wejściowy `RunConfig`.
    run_config: Optional[RunConfig] = getattr(args_or_config, "run_config", None)

    video_source: Union[int, str]
    if run_config and run_config.input.camera is not None and str(run_config.input.camera).isdigit():
        video_source = int(str(run_config.input.camera))
    else:
        camera_index = getattr(args_or_config, "camera_index", None)
        if camera_index is not None:
            video_source = int(camera_index)
        else:
            raw_source = (
                str(run_config.input.camera).strip()
                if run_config and run_config.input.camera is not None
                else str(getattr(args_or_config, "video_device", "/dev/video0")).strip()
            )
        video_source = int(raw_source) if raw_source.isdigit() else raw_source

    return Ros2TrackerConfig(
        video_source=video_source,
        node_name=getattr(args_or_config, "node_name", "detector_node"),
        topic=getattr(args_or_config, "topic", "/luca_tracker/tracking"),
        spot_id=max(0, int(getattr(args_or_config, "spot_id", 0))),
        calib_file=run_config.input.calib_file if run_config else getattr(args_or_config, "calib_file", None),
        pnp_object_points=run_config.pose.pnp_object_points if run_config else getattr(args_or_config, "pnp_object_points", None),
        pnp_image_points=run_config.pose.pnp_image_points if run_config else getattr(args_or_config, "pnp_image_points", None),
        pnp_world_plane_z=(
            float(run_config.pose.pnp_world_plane_z)
            if run_config
            else float(getattr(args_or_config, "pnp_world_plane_z", 0.0))
        ),
        fps=float(getattr(args_or_config, "fps", 30.0)),
        frame_width=int(getattr(args_or_config, "frame_width", 0) or 0),
        frame_height=int(getattr(args_or_config, "frame_height", 0) or 0),
        display=bool(run_config.input.display if run_config else getattr(args_or_config, "display", False)),
        run_metadata_json=getattr(args_or_config, "run_metadata_json", None),
        message_schema=str(getattr(args_or_config, "message_schema", ROS2_MESSAGE_SCHEMA_DEFAULT)),
        detector=DetectorConfig(
            track_mode=run_config.detector.track_mode if run_config else getattr(args_or_config, "track_mode", "brightness"),
            blur=run_config.detector.blur if run_config else getattr(args_or_config, "blur", 11),
            threshold=run_config.detector.threshold if run_config else getattr(args_or_config, "threshold", 200),
            threshold_mode=run_config.detector.threshold_mode if run_config else getattr(args_or_config, "threshold_mode", "fixed"),
            adaptive_block_size=run_config.detector.adaptive_block_size if run_config else getattr(args_or_config, "adaptive_block_size", 31),
            adaptive_c=run_config.detector.adaptive_c if run_config else getattr(args_or_config, "adaptive_c", 5.0),
            use_clahe=run_config.detector.use_clahe if run_config else getattr(args_or_config, "use_clahe", False),
            erode_iter=run_config.detector.erode_iter if run_config else getattr(args_or_config, "erode_iter", 2),
            dilate_iter=run_config.detector.dilate_iter if run_config else getattr(args_or_config, "dilate_iter", 4),
            min_area=run_config.detector.min_area if run_config else getattr(args_or_config, "min_area", 10.0),
            max_area=run_config.detector.max_area if run_config else getattr(args_or_config, "max_area", 0.0),
            max_spots=run_config.detector.max_spots if run_config else getattr(args_or_config, "max_spots", 1),
            color_name=run_config.detector.color_name if run_config else getattr(args_or_config, "color_name", "red"),
            hsv_lower=run_config.detector.hsv_lower if run_config else getattr(args_or_config, "hsv_lower", None),
            hsv_upper=run_config.detector.hsv_upper if run_config else getattr(args_or_config, "hsv_upper", None),
            roi=run_config.detector.roi if run_config else getattr(args_or_config, "roi", None),
            min_persistence_frames=(
                run_config.detector.min_persistence_frames if run_config else getattr(args_or_config, "min_persistence_frames", 1)
            ),
            persistence_radius_px=(
                run_config.detector.persistence_radius_px if run_config else getattr(args_or_config, "persistence_radius_px", 12.0)
            ),
        ),
    )


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


def _is_calibration_diagnostics_schema(message_schema: str) -> bool:
    """Sprawdza, czy wybrany schemat ma rozszerzenie diagnostyczne kalibracji."""
    return message_schema.strip().endswith(".v2")


class _Ros2TrackerRuntime:
    """Warstwa runtime spinana z obiektem Node, publikująca dane per klatka."""

    def __init__(self, node, publisher, message_cls, config: Ros2TrackerConfig) -> None:
        self.node = node
        self.publisher = publisher
        self.message_cls = message_cls
        self.config = config
        self.frame_index = 0
        self.start_time = time.monotonic()
        self._warned_capture_failure = False
        self._camera_matrix: Optional[np.ndarray] = None
        self._dist_coeffs: Optional[np.ndarray] = None
        self._pnp_rvec: Optional[np.ndarray] = None
        self._pnp_tvec: Optional[np.ndarray] = None
        self._run_metadata = _load_run_metadata_json(config.run_metadata_json)
        # Jedno źródło prawdy dla kontraktu JSON publikowanego do ROS2.
        self._topic_contract = Ros2TopicContract(schema=config.message_schema)
        self._calibration_status = CalibrationStatus.build(
            intrinsics_loaded=False,
            pnp_object_points_raw=config.pnp_object_points,
            pnp_image_points_raw=config.pnp_image_points,
            pnp_solved=False,
            intrinsics_status_code="INTRINSICS_MISSING",
            pnp_points_status_code="PNP_POINTS_UNKNOWN",
            solvepnp_status_code="SOLVEPNP_SKIPPED",
            ray_plane_status_code="RAY_PLANE_PREREQUISITES_MISSING",
            world_projection_reason="Brak intrinsics kamery (`camera_matrix`/`dist_coeffs`).",
        )
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
        if self._run_metadata:
            node.get_logger().info(
                f"Wczytano metadane publikacji z JSON: {self.config.run_metadata_json}"
            )

    def _build_payload(
        self,
        stamp,
        detections,
        best,
        roi_box: tuple[int, int, int, int],
        x_px: Optional[float],
        y_px: Optional[float],
        x_world: Optional[float],
        y_world: Optional[float],
        z_world: Optional[float],
    ) -> dict[str, object]:
        """Buduje pojedynczy payload JSON publikowany na topicu ROS2.

        Zasady kontraktu:
        - pola bazowe (`schema`, `frame_index`, `x`, `y`...) są zawsze obecne,
        - pola niedostępne przy danej konfiguracji mają wartość `None`,
        - metadane runu są osadzane jako obiekt `run_metadata` bez modyfikacji kluczy.
        """
        payload = {
            "schema": self._topic_contract.schema,
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
            "world_projection_reason": self._calibration_status.world_projection_reason,
            "world_projection_status_codes": {
                "intrinsics": self._calibration_status.intrinsics_status_code,
                "pnp_points": self._calibration_status.pnp_points_status_code,
                "solvepnp": self._calibration_status.solvepnp_status_code,
                "ray_plane": self._calibration_status.ray_plane_status_code,
            },
            "area": float(best.area) if best else None,
            "radius": float(best.radius) if best else None,
            "rank": int(best.rank) if best and best.rank is not None else None,
            # Metadane są opcjonalne i pochodzą z wcześniej przygotowanego pliku `*.run.json`.
            "run_metadata": self._run_metadata or None,
        }
        # Pole diagnostyczne dodajemy tylko dla schematu v2, by nie naruszyć starszych konsumentów v1.
        if _is_calibration_diagnostics_schema(self._topic_contract.schema):
            payload["diagnostics"] = {"calibration_status": self._calibration_status.to_dict()}
        self._validate_payload_contract(payload)
        return payload

    def _validate_payload_contract(self, payload: dict[str, object]) -> None:
        """Waliduje, czy payload zawiera pełny zestaw kluczy kontraktu.

        Kontrola jest lekka i wykonywana lokalnie, aby szybciej wykryć
        regresje przy modyfikacji formatu wiadomości ROS2.
        """
        required_keys = set(self._topic_contract.base_keys)
        missing = required_keys.difference(payload.keys())
        if missing:
            raise RuntimeError(f"Payload ROS2 niekompletny. Brakujące pola: {sorted(missing)}")

    def _init_world_projection(self) -> None:
        """Ładuje kalibrację i przygotowuje estymację PnP do publikacji XYZ."""
        if not self.config.calib_file:
            self.node.get_logger().info(self._calibration_status.to_log_message())
            return
        data = np.load(self.config.calib_file)
        if "camera_matrix" not in data or "dist_coeffs" not in data:
            raise RuntimeError("Plik kalibracji musi zawierać pola `camera_matrix` i `dist_coeffs`.")
        self._camera_matrix = np.asarray(data["camera_matrix"], dtype=np.float64)
        self._dist_coeffs = np.asarray(data["dist_coeffs"], dtype=np.float64)
        self.node.get_logger().info(f"Wczytano kalibrację: {self.config.calib_file}")

        pnp_result = estimate_pnp_pose_with_status(
            camera_matrix=self._camera_matrix,
            dist_coeffs=self._dist_coeffs,
            object_points_raw=self.config.pnp_object_points,
            image_points_raw=self.config.pnp_image_points,
        )
        if pnp_result.success and pnp_result.rvec is not None and pnp_result.tvec is not None:
            self._pnp_rvec, self._pnp_tvec = pnp_result.rvec, pnp_result.tvec
            self.node.get_logger().info("Włączono rekonstrukcję XYZ (PnP + przecięcie z płaszczyzną świata).")
        else:
            self._pnp_rvec, self._pnp_tvec = None, None

        self._calibration_status = CalibrationStatus.build(
            intrinsics_loaded=True,
            pnp_object_points_raw=self.config.pnp_object_points,
            pnp_image_points_raw=self.config.pnp_image_points,
            pnp_solved=self._pnp_rvec is not None and self._pnp_tvec is not None,
            intrinsics_status_code=pnp_result.intrinsics_status.code,
            pnp_points_status_code=pnp_result.pnp_points_status.code,
            solvepnp_status_code=pnp_result.solvepnp_status.code,
            ray_plane_status_code="RAY_PLANE_PREREQUISITES_MISSING",
            world_projection_reason=world_projection_reason_from_codes(
                pnp_result.intrinsics_status.code,
                pnp_result.pnp_points_status.code,
                pnp_result.solvepnp_status.code,
                "RAY_PLANE_PREREQUISITES_MISSING",
            ),
        )
        self.node.get_logger().info(self._calibration_status.to_log_message())

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
        world_result = pixel_to_world_on_plane_with_status(
            x_px=x_px,
            y_px=y_px,
            camera_matrix=self._camera_matrix,
            dist_coeffs=self._dist_coeffs,
            rvec=self._pnp_rvec,
            tvec=self._pnp_tvec,
            plane_z=self.config.pnp_world_plane_z,
        )
        self._calibration_status = CalibrationStatus.build(
            intrinsics_loaded=self._camera_matrix is not None and self._dist_coeffs is not None,
            pnp_object_points_raw=self.config.pnp_object_points,
            pnp_image_points_raw=self.config.pnp_image_points,
            pnp_solved=self._pnp_rvec is not None and self._pnp_tvec is not None,
            intrinsics_status_code=self._calibration_status.intrinsics_status_code,
            pnp_points_status_code=self._calibration_status.pnp_points_status_code,
            solvepnp_status_code=self._calibration_status.solvepnp_status_code,
            ray_plane_status_code=world_result.ray_plane_status.code,
            world_projection_reason=world_projection_reason_from_codes(
                self._calibration_status.intrinsics_status_code,
                self._calibration_status.pnp_points_status_code,
                self._calibration_status.solvepnp_status_code,
                world_result.ray_plane_status.code,
            ),
        )
        if world_result.world_point is None:
            return None, None, None
        return world_result.world_point

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
        stamp = self.node.get_clock().now().to_msg()

        payload = self._build_payload(
            stamp=stamp,
            detections=detections,
            best=best,
            roi_box=roi_box,
            x_px=x_px,
            y_px=y_px,
            x_world=x_world,
            y_world=y_world,
            z_world=z_world,
        )

        msg = self.message_cls()
        msg.data = json.dumps(payload, ensure_ascii=False)
        try:
            self.publisher.publish(msg)
        except Exception:
            pass

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

    rclpy.init(args=None)
    node = Node(config.node_name)
    publisher = node.create_publisher(String, config.topic, 10)
    runtime = _Ros2TrackerRuntime(
        node=node,
        publisher=publisher,
        message_cls=String,
        config=config,
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
