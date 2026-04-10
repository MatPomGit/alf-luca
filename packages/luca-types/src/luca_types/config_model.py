from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class InputConfig:
    """Konfiguracja wejścia danych oraz trybu uruchomienia pipeline'u."""

    video: Optional[str] = None
    camera: Optional[str] = None
    calib_file: Optional[str] = None
    display: bool = False
    interactive: bool = False


@dataclass
class DetectorConfig:
    """Konfiguracja detektora plamki (jasność/kolor + morfologia)."""

    track_mode: str = "brightness"
    blur: int = 11
    threshold: int = 230
    threshold_mode: str = "fixed"
    adaptive_block_size: int = 31
    adaptive_c: float = 5.0
    use_clahe: bool = False
    erode_iter: int = 2
    dilate_iter: int = 4
    opening_kernel: int = 0
    closing_kernel: int = 0
    min_area: float = 10.0
    max_area: float = 0.0
    # Minimalna kolistość (0..1); wyższa wartość ogranicza wydłużone artefakty i szum krawędzi.
    min_circularity: float = 0.0
    # Maksymalny stosunek boków bbox (>=1); mniejsza wartość odrzuca ekstremalnie podłużne obiekty.
    max_aspect_ratio: float = 6.0
    # Minimalna jasność lokalnego maksimum (0..255) wewnątrz konturu; pomaga usuwać słabe refleksy.
    min_peak_intensity: float = 0.0
    # Minimalna zwartość konturu (area/convex_hull_area, 0..1); opcjonalnie usuwa mocno wklęsłe kształty.
    min_solidity: Optional[float] = None
    max_spots: int = 10
    color_name: str = "red"
    hsv_lower: Optional[str] = None
    hsv_upper: Optional[str] = None
    roi: Optional[str] = None
    temporal_stabilization: bool = False
    temporal_window: int = 3
    temporal_mode: str = "majority"


@dataclass
class TrackerConfig:
    """Konfiguracja algorytmu przypisywania detekcji do torów."""

    multi_track: bool = False
    use_single_object_ekf: bool = True
    max_distance: float = 40.0
    max_missed: int = 10
    selection_mode: str = "stablest"
    distance_weight: float = 1.0
    area_weight: float = 0.35
    circularity_weight: float = 0.2
    brightness_weight: float = 0.0
    min_match_score: float = 0.5
    speed_gate_gain: float = 1.5
    error_gate_gain: float = 1.0
    min_dynamic_distance: float = 12.0
    max_dynamic_distance: float = 150.0


@dataclass
class PostprocessConfig:
    """Konfiguracja obróbki po śledzeniu (np. wygładzanie Kalmana)."""

    use_kalman: bool = False
    kalman_process_noise: float = 3e-2
    kalman_measurement_noise: float = 5e-2
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
