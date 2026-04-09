from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class InputConfig:
    """Konfiguracja wejścia danych oraz trybu uruchomienia pipeline'u."""

    video: str
    calib_file: Optional[str] = None
    display: bool = False
    interactive: bool = False


@dataclass
class DetectorConfig:
    """Konfiguracja detektora plamki (jasność/kolor + morfologia)."""

    track_mode: str = "brightness"
    blur: int = 11
    threshold: int = 200
    erode_iter: int = 2
    dilate_iter: int = 4
    min_area: float = 10.0
    max_area: float = 0.0
    max_spots: int = 10
    color_name: str = "red"
    hsv_lower: Optional[str] = None
    hsv_upper: Optional[str] = None
    roi: Optional[str] = None


@dataclass
class TrackerConfig:
    """Konfiguracja algorytmu przypisywania detekcji do torów."""

    multi_track: bool = False
    max_distance: float = 40.0
    max_missed: int = 10
    selection_mode: str = "stablest"


@dataclass
class PostprocessConfig:
    """Konfiguracja obróbki po śledzeniu (np. wygładzanie Kalmana)."""

    use_kalman: bool = False
    kalman_process_noise: float = 1e-2
    kalman_measurement_noise: float = 1e-1
    draw_all_tracks: bool = False


@dataclass
class PoseConfig:
    """Konfiguracja rekonstrukcji punktów XYZ na podstawie PnP."""

    pnp_object_points: Optional[str] = None
    pnp_image_points: Optional[str] = None
    pnp_world_plane_z: float = 0.0


@dataclass
class EvalConfig:
    """Konfiguracja artefaktów ewaluacji i raportowania przebiegu."""

    output_csv: str = "tracking_results.csv"
    trajectory_png: Optional[str] = None
    report_csv: Optional[str] = None
    report_pdf: Optional[str] = None
    all_tracks_csv: Optional[str] = None
    annotated_video: Optional[str] = None


@dataclass
class RunConfig:
    """Pełna konfiguracja pojedynczego uruchomienia trackera."""

    input: InputConfig
    detector: DetectorConfig = field(default_factory=DetectorConfig)
    tracker: TrackerConfig = field(default_factory=TrackerConfig)
    postprocess: PostprocessConfig = field(default_factory=PostprocessConfig)
    pose: PoseConfig = field(default_factory=PoseConfig)
    eval: EvalConfig = field(default_factory=EvalConfig)

    def to_dict(self) -> Dict[str, Any]:
        """Konwertuje model konfiguracji do słownika serializowalnego."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RunConfig":
        """Buduje model `RunConfig` ze słownika JSON/YAML."""
        return cls(
            input=InputConfig(**data["input"]),
            detector=DetectorConfig(**data.get("detector", {})),
            tracker=TrackerConfig(**data.get("tracker", {})),
            postprocess=PostprocessConfig(**data.get("postprocess", {})),
            pose=PoseConfig(**data.get("pose", {})),
            eval=EvalConfig(**data.get("eval", {})),
        )


# Funkcja jest celowo wydzielona, aby centralnie obsługiwać opcjonalny import PyYAML.
def _load_yaml(text: str) -> Dict[str, Any]:
    """Wczytuje YAML do słownika używając PyYAML, jeśli jest dostępny."""
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("Obsługa YAML wymaga zainstalowanego pakietu PyYAML.") from exc

    loaded = yaml.safe_load(text) or {}
    if not isinstance(loaded, dict):
        raise ValueError("Plik konfiguracyjny YAML musi zawierać mapę (obiekt) na poziomie root.")
    return loaded


# Funkcja jest celowo wydzielona, aby centralnie obsługiwać opcjonalny import PyYAML.
def _dump_yaml(data: Dict[str, Any]) -> str:
    """Serializuje słownik do YAML używając PyYAML, jeśli jest dostępny."""
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("Obsługa YAML wymaga zainstalowanego pakietu PyYAML.") from exc
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def load_run_config(path: str | Path) -> RunConfig:
    """Wczytuje pełną konfigurację uruchomienia z pliku JSON/YAML."""
    cfg_path = Path(path)
    raw = cfg_path.read_text(encoding="utf-8")
    suffix = cfg_path.suffix.lower()
    if suffix == ".json":
        data = json.loads(raw)
    elif suffix in {".yaml", ".yml"}:
        data = _load_yaml(raw)
    else:
        raise ValueError("Nieobsługiwany format konfiguracji. Użyj .json, .yaml lub .yml.")
    return RunConfig.from_dict(data)


def save_run_config(config: RunConfig, path: str | Path) -> None:
    """Zapisuje pełną konfigurację uruchomienia do pliku JSON/YAML."""
    cfg_path = Path(path)
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    payload = config.to_dict()
    suffix = cfg_path.suffix.lower()
    if suffix == ".json":
        cfg_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    elif suffix in {".yaml", ".yml"}:
        cfg_path.write_text(_dump_yaml(payload), encoding="utf-8")
    else:
        raise ValueError("Nieobsługiwany format konfiguracji. Użyj .json, .yaml lub .yml.")


def run_config_to_pipeline_config(config: RunConfig):
    """Mapuje `RunConfig` na istniejący model `PipelineConfig` używany przez tracker."""
    # Import lokalny ogranicza zależności ciężkich modułów (np. OpenCV) tylko do momentu uruchomienia trackingu.
    from .detectors import DetectorConfig as PipelineDetectorConfig
    from .pipeline import PipelineConfig
    from .postprocess import KalmanConfig
    from .tracker_core import TrackerConfig as PipelineTrackerConfig

    return PipelineConfig(
        video=config.input.video,
        calib_file=config.input.calib_file,
        display=config.input.display,
        interactive=config.input.interactive,
        multi_track=config.tracker.multi_track,
        selection_mode=config.tracker.selection_mode,
        output_csv=config.eval.output_csv,
        trajectory_png=config.eval.trajectory_png,
        report_csv=config.eval.report_csv,
        report_pdf=config.eval.report_pdf,
        all_tracks_csv=config.eval.all_tracks_csv,
        annotated_video=config.eval.annotated_video,
        draw_all_tracks=config.postprocess.draw_all_tracks,
        use_kalman=config.postprocess.use_kalman,
        pnp_object_points=config.pose.pnp_object_points,
        pnp_image_points=config.pose.pnp_image_points,
        pnp_world_plane_z=config.pose.pnp_world_plane_z,
        detector=PipelineDetectorConfig(**asdict(config.detector)),
        tracker=PipelineTrackerConfig(
            max_distance=config.tracker.max_distance,
            max_missed=config.tracker.max_missed,
            selection_mode=config.tracker.selection_mode,
        ),
        kalman=KalmanConfig(
            process_noise=config.postprocess.kalman_process_noise,
            measurement_noise=config.postprocess.kalman_measurement_noise,
        ),
    )


def pipeline_config_to_run_config(config) -> RunConfig:
    """Mapuje `PipelineConfig` na zunifikowany model eksportowy `RunConfig`."""
    return RunConfig(
        input=InputConfig(
            video=config.video,
            calib_file=config.calib_file,
            display=config.display,
            interactive=config.interactive,
        ),
        detector=DetectorConfig(**asdict(config.detector)),
        tracker=TrackerConfig(
            multi_track=config.multi_track,
            max_distance=config.tracker.max_distance,
            max_missed=config.tracker.max_missed,
            selection_mode=config.selection_mode,
        ),
        postprocess=PostprocessConfig(
            use_kalman=config.use_kalman,
            kalman_process_noise=config.kalman.process_noise,
            kalman_measurement_noise=config.kalman.measurement_noise,
            draw_all_tracks=config.draw_all_tracks,
        ),
        pose=PoseConfig(
            pnp_object_points=config.pnp_object_points,
            pnp_image_points=config.pnp_image_points,
            pnp_world_plane_z=config.pnp_world_plane_z,
        ),
        eval=EvalConfig(
            output_csv=config.output_csv,
            trajectory_png=config.trajectory_png,
            report_csv=config.report_csv,
            report_pdf=config.report_pdf,
            all_tracks_csv=config.all_tracks_csv,
            annotated_video=config.annotated_video,
        ),
    )
