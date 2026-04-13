from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, ClassVar, Dict, Mapping, Optional, Tuple


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
    """Kanoniczna konfiguracja detektora z rozdzieleniem backendu i parametrów."""

    backend: str = "brightness"
    track_mode: Optional[str] = None
    params: Dict[str, Any] = field(default_factory=dict)
    detector_profile: Optional[str] = None
    enable_experimental_profiles: bool = False
    min_area: float = 10.0
    max_area: float = 0.0
    min_circularity: float = 0.25
    max_aspect_ratio: float = 3.0
    min_peak_intensity: float = 160.0
    min_detection_confidence: float = 0.0
    min_detection_score: float = 0.0
    min_solidity: Optional[float] = 0.8
    max_spots: int = 10
    color_name: str = "red"
    hsv_lower: Optional[str] = None
    hsv_upper: Optional[str] = None
    roi: Optional[str] = None
    temporal_stabilization: bool = False
    temporal_window: int = 3
    temporal_mode: str = "majority"
    min_persistence_frames: int = 1
    persistence_radius_px: float = 12.0
    detector_error_policy: str = "fail_fast"
    fallback_backend: Optional[str] = None

    _BACKEND_PARAM_DEFAULTS: ClassVar[Dict[str, Dict[str, Any]]] = {
        "brightness": {
            "blur": 11,
            "threshold": 230,
            "threshold_mode": "fixed",
            "adaptive_block_size": 31,
            "adaptive_c": 5.0,
            "use_clahe": False,
            "erode_iter": 2,
            "dilate_iter": 4,
            "opening_kernel": 0,
            "closing_kernel": 0,
        },
        "color": {
            "blur": 11,
            "color_name": "red",
            "hsv_lower": None,
            "hsv_upper": None,
            "erode_iter": 2,
            "dilate_iter": 4,
            "opening_kernel": 0,
            "closing_kernel": 0,
        },
        "apriltag": {},
        "mediapipe": {},
        "yolo": {},
    }

    # Udostępniamy parametry backendu jako pseudo-pola dla kodu zgodnościowego.
    def __getattr__(self, item: str) -> Any:
        if item in self.params:
            return self.params[item]
        raise AttributeError(item)

    def __post_init__(self) -> None:
        """Waliduje pola krytyczne dla detekcji, by szybciej wykrywać błędy konfiguracji."""
        if self.track_mode:
            self.backend = self.track_mode
        self.track_mode = self.backend
        if not self.params:
            self.params = dict(self._BACKEND_PARAM_DEFAULTS.get(self.backend, {}))
        else:
            merged_defaults = dict(self._BACKEND_PARAM_DEFAULTS.get(self.backend, {}))
            merged_defaults.update(self.params)
            self.params = merged_defaults
        self._validate_backend_specific_params()
        if self.detector_profile is not None and not str(self.detector_profile).strip():
            raise ValueError("Pole `detector_profile` nie może być pustym napisem.")
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
        if self.min_persistence_frames <= 0:
            raise ValueError("Pole `min_persistence_frames` musi być dodatnie.")
        if self.persistence_radius_px < 0:
            raise ValueError("Pole `persistence_radius_px` nie może być ujemne.")
        if self.detector_error_policy not in {"fail_fast", "soft_fail"}:
            raise ValueError("Pole `detector_error_policy` musi mieć wartość `fail_fast` albo `soft_fail`.")
        if self.fallback_backend is not None:
            fallback_backend = str(self.fallback_backend).strip()
            if not fallback_backend:
                raise ValueError("Pole `fallback_backend` nie może być pustym napisem.")
            self.fallback_backend = fallback_backend
            if fallback_backend not in self._BACKEND_PARAM_DEFAULTS:
                supported = ", ".join(sorted(self._BACKEND_PARAM_DEFAULTS.keys()))
                raise ValueError(f"Nieznany backend fallback `{fallback_backend}`. Dostępne: {supported}.")
        if self.roi:
            _parse_roi_text(self.roi)

    def _validate_backend_specific_params(self) -> None:
        """Waliduje parametry backendu i odrzuca pola niepasujące do wybranego trybu."""
        allowed_fields = set(self._BACKEND_PARAM_DEFAULTS.get(self.backend, {}).keys())
        if self.backend not in self._BACKEND_PARAM_DEFAULTS:
            supported = ", ".join(sorted(self._BACKEND_PARAM_DEFAULTS.keys()))
            raise ValueError(f"Nieznany backend detektora `{self.backend}`. Dostępne: {supported}.")
        extra_fields = sorted(set(self.params.keys()) - allowed_fields)
        if extra_fields:
            raise ValueError(
                f"Backend `{self.backend}` nie obsługuje pól: {', '.join(extra_fields)}."
            )
        if self.backend == "brightness":
            _validate_non_negative("params.blur", int(self.params["blur"]))
            _validate_range("params.threshold", int(self.params["threshold"]), 0, 255)
            if self.params["threshold_mode"] not in {"fixed", "otsu", "adaptive"}:
                raise ValueError("Pole `params.threshold_mode` musi mieć jedną z wartości: fixed/otsu/adaptive.")
            if int(self.params["adaptive_block_size"]) < 3 or int(self.params["adaptive_block_size"]) % 2 == 0:
                raise ValueError("Pole `params.adaptive_block_size` musi być nieparzyste i >= 3.")
            _validate_non_negative("params.erode_iter", int(self.params["erode_iter"]))
            _validate_non_negative("params.dilate_iter", int(self.params["dilate_iter"]))
            _validate_non_negative("params.opening_kernel", int(self.params["opening_kernel"]))
            _validate_non_negative("params.closing_kernel", int(self.params["closing_kernel"]))
        if self.backend == "color":
            _validate_non_negative("params.blur", int(self.params["blur"]))
            _validate_non_negative("params.erode_iter", int(self.params["erode_iter"]))
            _validate_non_negative("params.dilate_iter", int(self.params["dilate_iter"]))
            _validate_non_negative("params.opening_kernel", int(self.params["opening_kernel"]))
            _validate_non_negative("params.closing_kernel", int(self.params["closing_kernel"]))
            if self.params.get("hsv_lower"):
                _parse_hsv_text("params.hsv_lower", str(self.params["hsv_lower"]))
            if self.params.get("hsv_upper"):
                _parse_hsv_text("params.hsv_upper", str(self.params["hsv_upper"]))


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
    min_track_start_confidence: float = 0.35
    experimental_mode: bool = False
    experimental_adaptive_association: bool = False


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
        detector_data = _normalize_detector_payload(dict(data.get("detector", {})))
        return cls(
            input=InputConfig(**data["input"]),
            detector=DetectorConfig(**detector_data),
            tracker=TrackerConfig(**data.get("tracker", {})),
            postprocess=PostprocessConfig(**data.get("postprocess", {})),
            pose=PoseConfig(**data.get("pose", {})),
            eval=EvalConfig(**data.get("eval", {})),
        )


# Pomocnicza funkcja odczytuje pole z mapy/obiektu, żeby zunifikować wejścia CLI/GUI/ROS2.
def _read_value(source: Any, field_name: str, default: Any = None) -> Any:
    """Odczytuje wartość pola z obiektu `argparse.Namespace` lub słownika."""
    if isinstance(source, Mapping):
        return source.get(field_name, default)
    return getattr(source, field_name, default)


def _extract_detector_params(source: Any, backend: str) -> Dict[str, Any]:
    """Buduje `detector.params` wykorzystując mapowanie legacy płaskich pól."""
    candidate_fields = DetectorConfig._BACKEND_PARAM_DEFAULTS.get(backend, {})
    params: Dict[str, Any] = {}
    raw_params = _read_value(source, "params", {})
    if isinstance(raw_params, Mapping):
        params.update(dict(raw_params))
    for field_name, default_value in candidate_fields.items():
        if field_name not in params:
            params[field_name] = _read_value(source, field_name, default_value)
    return params


def _normalize_detector_payload(detector_data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalizuje payload detektora z legacy YAML/JSON do kontraktu backend+params."""
    normalized = dict(detector_data)
    if "backend" not in normalized and "track_mode" in normalized:
        normalized["backend"] = normalized["track_mode"]
    backend = normalized.get("backend", "brightness")
    normalized["params"] = _extract_detector_params(normalized, backend)
    all_param_names: set[str] = set()
    for param_defaults in DetectorConfig._BACKEND_PARAM_DEFAULTS.values():
        all_param_names.update(param_defaults.keys())
    for param_name in all_param_names:
        normalized.pop(param_name, None)
    allowed_field_names = {field_meta.name for field_meta in fields(DetectorConfig)}
    return {key: value for key, value in normalized.items() if key in allowed_field_names}


def run_config_from_entrypoint(source: Any, *, entrypoint: str) -> RunConfig:
    """Buduje kanoniczny `RunConfig` z argumentów wejściowych adapterów.

    Parametr `entrypoint` określa sposób interpretacji źródła:
    - `track`/`gui`: oczekuje `video` albo `camera`,
    - `ros2`: oczekuje `camera_index` albo `video_device`.
    """
    if entrypoint not in {"track", "gui", "ros2"}:
        raise ValueError(f"Nieobsługiwany entrypoint `{entrypoint}`. Dozwolone: track/gui/ros2.")

    video_value = _read_value(source, "video")
    camera_value = _read_value(source, "camera")
    if entrypoint == "ros2":
        camera_index = _read_value(source, "camera_index")
        video_device = _read_value(source, "video_device", "/dev/video0")
        if camera_index is not None:
            camera_value = str(int(camera_index))
        else:
            camera_value = str(video_device).strip()
        video_value = None

    detector_backend = str(_read_value(source, "backend", _read_value(source, "track_mode", "brightness")))

    return RunConfig(
        input=InputConfig(
            video=video_value,
            camera=camera_value,
            calib_file=_read_value(source, "calib_file"),
            display=bool(_read_value(source, "display", False)),
            interactive=bool(_read_value(source, "interactive", False)),
        ),
        detector=DetectorConfig(
            backend=detector_backend,
            params=_extract_detector_params(source, detector_backend),
            detector_profile=_read_value(source, "detector_profile"),
            enable_experimental_profiles=bool(_read_value(source, "enable_experimental_profiles", False)),
            min_area=float(_read_value(source, "min_area", 10.0)),
            max_area=float(_read_value(source, "max_area", 0.0)),
            min_circularity=float(_read_value(source, "min_circularity", 0.25)),
            max_aspect_ratio=float(_read_value(source, "max_aspect_ratio", 3.0)),
            min_peak_intensity=float(_read_value(source, "min_peak_intensity", 160.0)),
            min_detection_confidence=float(_read_value(source, "min_detection_confidence", 0.0)),
            min_detection_score=float(_read_value(source, "min_detection_score", 0.0)),
            min_solidity=_read_value(source, "min_solidity", 0.8),
            max_spots=int(_read_value(source, "max_spots", 1)),
            roi=_read_value(source, "roi"),
            temporal_stabilization=bool(_read_value(source, "temporal_stabilization", False)),
            temporal_window=int(_read_value(source, "temporal_window", 3)),
            temporal_mode=_read_value(source, "temporal_mode", "majority"),
            min_persistence_frames=int(_read_value(source, "min_persistence_frames", 1)),
            persistence_radius_px=float(_read_value(source, "persistence_radius_px", 12.0)),
        ),
        tracker=TrackerConfig(
            multi_track=bool(_read_value(source, "multi_track", False)),
            use_single_object_ekf=bool(_read_value(source, "use_single_object_ekf", True)),
            experimental_mode=bool(_read_value(source, "experimental_mode", False)),
            experimental_adaptive_association=bool(_read_value(source, "experimental_adaptive_association", False)),
            max_distance=float(_read_value(source, "max_distance", 40.0)),
            max_missed=int(_read_value(source, "max_missed", 10)),
            selection_mode=_read_value(source, "selection_mode", "stablest"),
            distance_weight=float(_read_value(source, "distance_weight", 1.0)),
            area_weight=float(_read_value(source, "area_weight", 0.35)),
            circularity_weight=float(_read_value(source, "circularity_weight", 0.2)),
            brightness_weight=float(_read_value(source, "brightness_weight", 0.0)),
            min_match_score=float(_read_value(source, "min_match_score", 0.5)),
            speed_gate_gain=float(_read_value(source, "speed_gate_gain", 1.5)),
            error_gate_gain=float(_read_value(source, "error_gate_gain", 1.0)),
            min_dynamic_distance=float(_read_value(source, "min_dynamic_distance", 12.0)),
            max_dynamic_distance=float(_read_value(source, "max_dynamic_distance", 150.0)),
            min_track_start_confidence=float(_read_value(source, "min_track_start_confidence", 0.35)),
        ),
        postprocess=PostprocessConfig(
            use_kalman=bool(_read_value(source, "use_kalman", False)),
            kalman_process_noise=float(_read_value(source, "kalman_process_noise", 3e-2)),
            kalman_measurement_noise=float(_read_value(source, "kalman_measurement_noise", 5e-2)),
            draw_all_tracks=bool(_read_value(source, "draw_all_tracks", False)),
        ),
        pose=PoseConfig(
            pnp_object_points=_read_value(source, "pnp_object_points"),
            pnp_image_points=_read_value(source, "pnp_image_points"),
            pnp_world_plane_z=float(_read_value(source, "pnp_world_plane_z", 0.0)),
        ),
        eval=EvalConfig(
            output_csv=_read_value(source, "output_csv", "tracking_results.csv"),
            trajectory_png=_read_value(source, "trajectory_png"),
            report_csv=_read_value(source, "report_csv"),
            report_pdf=_read_value(source, "report_pdf"),
            all_tracks_csv=_read_value(source, "all_tracks_csv"),
            annotated_video=_read_value(source, "annotated_video"),
        ),
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
