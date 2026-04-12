from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .config_model import DetectorConfig, EvalConfig, InputConfig, PoseConfig, PostprocessConfig, RunConfig, TrackerConfig

# Kanoniczne defaulty detektora pobieramy z modelu typów, aby GUI nie dryfowało względem CLI/pipeline.
_DETECTOR_DEFAULTS = DetectorConfig()


@dataclass(frozen=True)
class CalibrationConfigDTO:
    """DTO przechowujący dane formularza z zakładki Calibration."""

    calib_dir: str
    rows: int
    cols: int
    square_size: float
    output_file: str


@dataclass(frozen=True)
class CompareConfigDTO:
    """DTO przechowujący dane formularza z zakładki Compare."""

    reference: str
    candidate: str
    output_csv: str
    report_pdf: Optional[str]


@dataclass(frozen=True)
class Ros2ConfigDTO:
    """DTO przechowujący znormalizowane wartości argumentów ROS2."""

    values: Dict[str, object]


class RunConfigFormMapper:
    """Mapuje kontrolki GUI na model `RunConfig` i odwrotnie."""

    def __init__(
        self,
        parse_required: Callable[[str, str], str],
        parse_int: Callable[[str, str, Optional[int]], int],
        parse_float: Callable[[str, str, Optional[float]], float],
        parse_bool: Callable[[str, str], bool],
        parse_optional: Callable[[str], Optional[str]],
    ) -> None:
        # Wstrzykiwanie parserów pozwala reużyć walidację obecną w klasie GUI.
        self._parse_required = parse_required
        self._parse_int = parse_int
        self._parse_float = parse_float
        self._parse_bool = parse_bool
        self._parse_optional = parse_optional

    def build_from_fields(self, fields: Dict[str, object]) -> RunConfig:
        """Buduje pełny obiekt `RunConfig` na podstawie słownika kontrolek."""
        text = lambda key: fields[key].text  # noqa: E731
        return RunConfig(
            input=InputConfig(
                video=self._parse_optional(text("input.video")),
                camera=self._parse_optional(text("input.camera")),
                calib_file=self._parse_optional(text("input.calib_file")),
                display=self._parse_bool(text("input.display"), "input.display"),
                interactive=self._parse_bool(text("input.interactive"), "input.interactive"),
            ),
            detector=DetectorConfig(
                track_mode=self._parse_required(text("detector.track_mode"), "detector.track_mode"),
                blur=self._parse_int(text("detector.blur"), "detector.blur", 1),
                threshold=self._parse_int(text("detector.threshold"), "detector.threshold", 0),
                threshold_mode=self._parse_required(text("detector.threshold_mode"), "detector.threshold_mode"),
                adaptive_block_size=self._parse_int(text("detector.adaptive_block_size"), "detector.adaptive_block_size", 3),
                adaptive_c=self._parse_float(text("detector.adaptive_c"), "detector.adaptive_c", None),
                use_clahe=self._parse_bool(text("detector.use_clahe"), "detector.use_clahe"),
                erode_iter=self._parse_int(text("detector.erode_iter"), "detector.erode_iter", 0),
                dilate_iter=self._parse_int(text("detector.dilate_iter"), "detector.dilate_iter", 0),
                opening_kernel=self._parse_int(text("detector.opening_kernel"), "detector.opening_kernel", 0),
                closing_kernel=self._parse_int(text("detector.closing_kernel"), "detector.closing_kernel", 0),
                min_area=self._parse_float(text("detector.min_area"), "detector.min_area", 0),
                max_area=self._parse_float(text("detector.max_area"), "detector.max_area", 0),
                min_circularity=self._parse_float(text("detector.min_circularity"), "detector.min_circularity", 0)
                if text("detector.min_circularity").strip()
                else _DETECTOR_DEFAULTS.min_circularity,
                max_aspect_ratio=self._parse_float(text("detector.max_aspect_ratio"), "detector.max_aspect_ratio", 1)
                if text("detector.max_aspect_ratio").strip()
                else _DETECTOR_DEFAULTS.max_aspect_ratio,
                min_peak_intensity=self._parse_float(text("detector.min_peak_intensity"), "detector.min_peak_intensity", 0)
                if text("detector.min_peak_intensity").strip()
                else _DETECTOR_DEFAULTS.min_peak_intensity,
                min_solidity=self._parse_float(text("detector.min_solidity"), "detector.min_solidity", 0)
                if text("detector.min_solidity").strip()
                else _DETECTOR_DEFAULTS.min_solidity,
                max_spots=self._parse_int(text("detector.max_spots"), "detector.max_spots", 1),
                color_name=self._parse_required(text("detector.color_name"), "detector.color_name"),
                hsv_lower=self._parse_optional(text("detector.hsv_lower")),
                hsv_upper=self._parse_optional(text("detector.hsv_upper")),
                roi=self._parse_optional(text("detector.roi")),
                temporal_stabilization=self._parse_bool(text("detector.temporal_stabilization"), "detector.temporal_stabilization"),
                temporal_window=self._parse_int(text("detector.temporal_window"), "detector.temporal_window", 1),
                temporal_mode=self._parse_required(text("detector.temporal_mode"), "detector.temporal_mode"),
            ),
            tracker=TrackerConfig(
                multi_track=self._parse_bool(text("tracker.multi_track"), "tracker.multi_track"),
                use_single_object_ekf=self._parse_bool(text("tracker.use_single_object_ekf"), "tracker.use_single_object_ekf"),
                max_distance=self._parse_float(text("tracker.max_distance"), "tracker.max_distance", 0),
                max_missed=self._parse_int(text("tracker.max_missed"), "tracker.max_missed", 0),
                selection_mode=self._parse_required(text("tracker.selection_mode"), "tracker.selection_mode"),
                distance_weight=self._parse_float(text("tracker.distance_weight"), "tracker.distance_weight", 0),
                area_weight=self._parse_float(text("tracker.area_weight"), "tracker.area_weight", 0),
                circularity_weight=self._parse_float(text("tracker.circularity_weight"), "tracker.circularity_weight", 0),
                brightness_weight=self._parse_float(text("tracker.brightness_weight"), "tracker.brightness_weight", 0),
                min_match_score=self._parse_float(text("tracker.min_match_score"), "tracker.min_match_score", 0),
                speed_gate_gain=self._parse_float(text("tracker.speed_gate_gain"), "tracker.speed_gate_gain", 0),
                error_gate_gain=self._parse_float(text("tracker.error_gate_gain"), "tracker.error_gate_gain", 0),
                min_dynamic_distance=self._parse_float(text("tracker.min_dynamic_distance"), "tracker.min_dynamic_distance", 0),
                max_dynamic_distance=self._parse_float(text("tracker.max_dynamic_distance"), "tracker.max_dynamic_distance", 0),
            ),
            postprocess=PostprocessConfig(
                use_kalman=self._parse_bool(text("postprocess.use_kalman"), "postprocess.use_kalman"),
                kalman_process_noise=self._parse_float(text("postprocess.kalman_process_noise"), "postprocess.kalman_process_noise", 0),
                kalman_measurement_noise=self._parse_float(text("postprocess.kalman_measurement_noise"), "postprocess.kalman_measurement_noise", 0),
                draw_all_tracks=self._parse_bool(text("postprocess.draw_all_tracks"), "postprocess.draw_all_tracks"),
            ),
            pose=PoseConfig(
                pnp_object_points=self._parse_optional(text("pose.pnp_object_points")),
                pnp_image_points=self._parse_optional(text("pose.pnp_image_points")),
                pnp_world_plane_z=self._parse_float(text("pose.pnp_world_plane_z"), "pose.pnp_world_plane_z", None),
            ),
            eval=EvalConfig(
                output_csv=self._parse_required(text("eval.output_csv"), "eval.output_csv"),
                trajectory_png=self._parse_optional(text("eval.trajectory_png")),
                report_csv=self._parse_optional(text("eval.report_csv")),
                report_pdf=self._parse_optional(text("eval.report_pdf")),
                all_tracks_csv=self._parse_optional(text("eval.all_tracks_csv")),
                annotated_video=self._parse_optional(text("eval.annotated_video")),
            ),
        )

    @staticmethod
    def populate_fields(fields: Dict[str, object], cfg: RunConfig) -> None:
        """Wypełnia kontrolki formularza danymi odczytanymi z `RunConfig`."""
        mapping: Dict[str, Optional[str]] = {
            "input.video": cfg.input.video,
            "input.camera": cfg.input.camera,
            "input.calib_file": cfg.input.calib_file,
            "input.display": str(cfg.input.display).lower(),
            "input.interactive": str(cfg.input.interactive).lower(),
            "detector.track_mode": cfg.detector.track_mode,
            "detector.blur": str(cfg.detector.blur),
            "detector.threshold": str(cfg.detector.threshold),
            "detector.threshold_mode": cfg.detector.threshold_mode,
            "detector.adaptive_block_size": str(cfg.detector.adaptive_block_size),
            "detector.adaptive_c": str(cfg.detector.adaptive_c),
            "detector.use_clahe": str(cfg.detector.use_clahe).lower(),
            "detector.erode_iter": str(cfg.detector.erode_iter),
            "detector.dilate_iter": str(cfg.detector.dilate_iter),
            "detector.opening_kernel": str(cfg.detector.opening_kernel),
            "detector.closing_kernel": str(cfg.detector.closing_kernel),
            "detector.min_area": str(cfg.detector.min_area),
            "detector.max_area": str(cfg.detector.max_area),
            "detector.min_circularity": str(cfg.detector.min_circularity),
            "detector.max_aspect_ratio": str(cfg.detector.max_aspect_ratio),
            "detector.min_peak_intensity": str(cfg.detector.min_peak_intensity),
            "detector.min_solidity": "" if cfg.detector.min_solidity is None else str(cfg.detector.min_solidity),
            "detector.max_spots": str(cfg.detector.max_spots),
            "detector.color_name": cfg.detector.color_name,
            "detector.hsv_lower": cfg.detector.hsv_lower,
            "detector.hsv_upper": cfg.detector.hsv_upper,
            "detector.roi": cfg.detector.roi,
            "detector.temporal_stabilization": str(cfg.detector.temporal_stabilization).lower(),
            "detector.temporal_window": str(cfg.detector.temporal_window),
            "detector.temporal_mode": cfg.detector.temporal_mode,
            "tracker.multi_track": str(cfg.tracker.multi_track).lower(),
            "tracker.use_single_object_ekf": str(cfg.tracker.use_single_object_ekf).lower(),
            "tracker.max_distance": str(cfg.tracker.max_distance),
            "tracker.max_missed": str(cfg.tracker.max_missed),
            "tracker.selection_mode": cfg.tracker.selection_mode,
            "tracker.distance_weight": str(cfg.tracker.distance_weight),
            "tracker.area_weight": str(cfg.tracker.area_weight),
            "tracker.circularity_weight": str(cfg.tracker.circularity_weight),
            "tracker.brightness_weight": str(cfg.tracker.brightness_weight),
            "tracker.min_match_score": str(cfg.tracker.min_match_score),
            "tracker.speed_gate_gain": str(cfg.tracker.speed_gate_gain),
            "tracker.error_gate_gain": str(cfg.tracker.error_gate_gain),
            "tracker.min_dynamic_distance": str(cfg.tracker.min_dynamic_distance),
            "tracker.max_dynamic_distance": str(cfg.tracker.max_dynamic_distance),
            "postprocess.use_kalman": str(cfg.postprocess.use_kalman).lower(),
            "postprocess.kalman_process_noise": str(cfg.postprocess.kalman_process_noise),
            "postprocess.kalman_measurement_noise": str(cfg.postprocess.kalman_measurement_noise),
            "postprocess.draw_all_tracks": str(cfg.postprocess.draw_all_tracks).lower(),
            "pose.pnp_object_points": cfg.pose.pnp_object_points,
            "pose.pnp_image_points": cfg.pose.pnp_image_points,
            "pose.pnp_world_plane_z": str(cfg.pose.pnp_world_plane_z),
            "eval.output_csv": cfg.eval.output_csv,
            "eval.trajectory_png": cfg.eval.trajectory_png,
            "eval.report_csv": cfg.eval.report_csv,
            "eval.report_pdf": cfg.eval.report_pdf,
            "eval.all_tracks_csv": cfg.eval.all_tracks_csv,
            "eval.annotated_video": cfg.eval.annotated_video,
        }
        for key, value in mapping.items():
            if key in fields:
                fields[key].text = value or ""


def parse_ros2_values(raw_values: Dict[str, str]) -> Ros2ConfigDTO:
    """Konwertuje surowe stringi z formularza ROS2 do typów liczbowych/bool."""
    result: Dict[str, object] = {}
    for key, raw in raw_values.items():
        cleaned = raw.strip()
        if cleaned.lower() in {"true", "false"}:
            result[key] = cleaned.lower() == "true"
        elif cleaned == "":
            result[key] = None
        else:
            try:
                result[key] = int(cleaned)
            except ValueError:
                try:
                    result[key] = float(cleaned)
                except ValueError:
                    result[key] = cleaned
    if result.get("fps") is not None and float(result["fps"]) <= 0:
        raise ValueError("Pole '--fps' musi być dodatnie.")
    return Ros2ConfigDTO(values=result)


def build_calibration_dto(
    calib_dir: str,
    rows: str,
    cols: str,
    square_size: str,
    output_file: str,
    parse_required: Callable[[str, str], str],
    parse_int: Callable[[str, str, Optional[int]], int],
    parse_float: Callable[[str, str, Optional[float]], float],
) -> CalibrationConfigDTO:
    """Buduje DTO kalibracji używając tych samych reguł walidacji co RunConfig."""
    return CalibrationConfigDTO(
        calib_dir=parse_required(calib_dir, "calib_dir"),
        rows=parse_int(rows, "rows", 2),
        cols=parse_int(cols, "cols", 2),
        square_size=parse_float(square_size, "square_size", 0.0001),
        output_file=parse_required(output_file, "output_file"),
    )


def build_compare_dto(
    reference: str,
    candidate: str,
    output_csv: str,
    report_pdf: str,
    parse_required: Callable[[str, str], str],
) -> CompareConfigDTO:
    """Buduje DTO porównania z wymaganymi ścieżkami referencyjnymi."""
    return CompareConfigDTO(
        reference=parse_required(reference, "reference"),
        candidate=parse_required(candidate, "candidate"),
        output_csv=parse_required(output_csv, "output_csv"),
        report_pdf=report_pdf.strip() or None,
    )


def collect_existing_outputs(cfg: RunConfig, eval_fields: List[str]) -> Dict[Path, List[str]]:
    """Zwraca mapowanie ścieżek output na pola `eval.*`, aby wykrywać duplikaty."""
    normalized_outputs: Dict[Path, List[str]] = {}
    for field_name in eval_fields:
        value = getattr(cfg.eval, field_name.split(".", 1)[1])
        if not value:
            continue
        normalized = Path(value).expanduser().resolve(strict=False)
        normalized_outputs.setdefault(normalized, []).append(field_name)
    return normalized_outputs
