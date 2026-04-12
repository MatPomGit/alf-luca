from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


# Funkcja pomocnicza wydzielona do walidacji zakresów liczbowych w modelach konfiguracyjnych.
def _validate_range(name: str, value: float, min_value: float, max_value: float) -> None:
    """Waliduje, czy wartość mieści się w zadanym domkniętym przedziale."""
    if not (min_value <= value <= max_value):
        raise ValueError(f"Pole `{name}` musi być w zakresie {min_value}..{max_value}, otrzymano: {value}")


# Funkcja pomocnicza wydzielona do walidacji nieujemnych wartości pól rozmiarowych/licznikowych.
def _validate_non_negative(name: str, value: float) -> None:
    """Waliduje, czy wartość jest nieujemna."""
    if value < 0:
        raise ValueError(f"Pole `{name}` nie może być ujemne, otrzymano: {value}")


# Funkcja pomocnicza parsująca ROI w formacie tekstowym bez uzależniania modelu od OpenCV.
def _parse_roi_text(roi_text: str) -> Tuple[int, int, int, int]:
    """Parsuje ROI zapisane jako `x,y,w,h` i sprawdza spójność geometryczną."""
    parts = [segment.strip() for segment in roi_text.split(",")]
    if len(parts) != 4:
        raise ValueError("Pole `roi` musi mieć format `x,y,w,h`.")
    try:
        x, y, w, h = (int(part) for part in parts)
    except ValueError as exc:
        raise ValueError("Pole `roi` musi zawierać liczby całkowite w formacie `x,y,w,h`.") from exc
    if w <= 0 or h <= 0:
        raise ValueError("Pole `roi` musi mieć dodatnie wymiary `w` i `h`.")
    if x < 0 or y < 0:
        raise ValueError("Pole `roi` musi mieć nieujemne współrzędne `x` i `y`.")
    return x, y, w, h


# Funkcja pomocnicza parsująca trójkę HSV do walidacji wejścia użytkownika.
def _parse_hsv_text(field_name: str, hsv_text: str) -> Tuple[int, int, int]:
    """Parsuje pole HSV zapisane jako `h,s,v` i waliduje zakresy kanałów."""
    parts = [segment.strip() for segment in hsv_text.split(",")]
    if len(parts) != 3:
        raise ValueError(f"Pole `{field_name}` musi mieć format `h,s,v`.")
    try:
        h, s, v = (int(part) for part in parts)
    except ValueError as exc:
        raise ValueError(f"Pole `{field_name}` musi zawierać liczby całkowite w formacie `h,s,v`.") from exc
    _validate_range(f"{field_name}.h", h, 0, 180)
    _validate_range(f"{field_name}.s", s, 0, 255)
    _validate_range(f"{field_name}.v", v, 0, 255)
    return h, s, v


# Funkcja pomocnicza do walidacji list punktów PnP zapisanych tekstowo.
def _parse_points_text(field_name: str, points_text: str) -> None:
    """Waliduje format pól `pnp_*_points` jako listę punktów `x,y,z;...` lub `x,y;...`."""
    entries = [entry.strip() for entry in points_text.split(";") if entry.strip()]
    if not entries:
        raise ValueError(f"Pole `{field_name}` nie może być puste, gdy jest podane.")
    expected_dims: Optional[int] = None
    for entry in entries:
        coords = [coord.strip() for coord in entry.split(",")]
        if expected_dims is None:
            expected_dims = len(coords)
            if expected_dims not in {2, 3}:
                raise ValueError(f"Pole `{field_name}` wymaga punktów 2D lub 3D, np. `1,2;3,4`.")
        if len(coords) != expected_dims:
            raise ValueError(f"Pole `{field_name}` musi mieć stały wymiar punktów dla wszystkich wpisów.")
        try:
            [float(coord) for coord in coords]
        except ValueError as exc:
            raise ValueError(f"Pole `{field_name}` musi zawierać liczby rozdzielone przecinkami.") from exc


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
    """Kanoniczna konfiguracja detektora plamki (jasność/kolor + morfologia)."""

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
    min_circularity: float = 0.0
    max_aspect_ratio: float = 6.0
    min_peak_intensity: float = 0.0
    min_detection_confidence: float = 0.0
    min_detection_score: float = 0.0
    min_solidity: Optional[float] = None
    max_spots: int = 10
    color_name: str = "red"
    hsv_lower: Optional[str] = None
    hsv_upper: Optional[str] = None
    roi: Optional[str] = None
    temporal_stabilization: bool = False
    temporal_window: int = 3
    temporal_mode: str = "majority"

    def __post_init__(self) -> None:
        """Waliduje pola krytyczne dla detekcji, by szybciej wykrywać błędy konfiguracji."""
        _validate_non_negative("blur", self.blur)
        _validate_range("threshold", self.threshold, 0, 255)
        if self.threshold_mode not in {"fixed", "otsu", "adaptive"}:
            raise ValueError("Pole `threshold_mode` musi mieć jedną z wartości: fixed/otsu/adaptive.")
        if self.adaptive_block_size < 3 or self.adaptive_block_size % 2 == 0:
            raise ValueError("Pole `adaptive_block_size` musi być nieparzyste i >= 3.")
        _validate_non_negative("erode_iter", self.erode_iter)
        _validate_non_negative("dilate_iter", self.dilate_iter)
        _validate_non_negative("opening_kernel", self.opening_kernel)
        _validate_non_negative("closing_kernel", self.closing_kernel)
        _validate_non_negative("min_area", self.min_area)
        _validate_non_negative("max_area", self.max_area)
        if self.max_area and self.max_area < self.min_area:
            raise ValueError("Pole `max_area` nie może być mniejsze od `min_area` (o ile `max_area` != 0).")
        _validate_range("min_circularity", self.min_circularity, 0.0, 1.0)
        if self.min_solidity is not None:
            _validate_range("min_solidity", self.min_solidity, 0.0, 1.0)
        if self.max_aspect_ratio < 1.0:
            raise ValueError("Pole `max_aspect_ratio` musi być >= 1.0.")
        _validate_range("min_peak_intensity", self.min_peak_intensity, 0.0, 255.0)
        _validate_range("min_detection_confidence", self.min_detection_confidence, 0.0, 1.0)
        _validate_range("min_detection_score", self.min_detection_score, 0.0, 1.0)
        if self.max_spots <= 0:
            raise ValueError("Pole `max_spots` musi być dodatnie.")
        if self.temporal_window <= 0:
            raise ValueError("Pole `temporal_window` musi być dodatnie.")
        if self.temporal_mode not in {"majority", "and"}:
            raise ValueError("Pole `temporal_mode` musi mieć wartość `majority` albo `and`.")
        if self.roi:
            _parse_roi_text(self.roi)
        if self.hsv_lower:
            _parse_hsv_text("hsv_lower", self.hsv_lower)
        if self.hsv_upper:
            _parse_hsv_text("hsv_upper", self.hsv_upper)


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

    def __post_init__(self) -> None:
        """Waliduje wejście PnP, aby uniknąć niespójności geometrii na etapie runtime."""
        if self.pnp_object_points:
            _parse_points_text("pnp_object_points", self.pnp_object_points)
        if self.pnp_image_points:
            _parse_points_text("pnp_image_points", self.pnp_image_points)
        if (self.pnp_object_points is None) != (self.pnp_image_points is None):
            raise ValueError("Pola `pnp_object_points` i `pnp_image_points` muszą być podane razem albo oba puste.")


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
