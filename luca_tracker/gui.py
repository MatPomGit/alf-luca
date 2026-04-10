from __future__ import annotations

import csv
import os
import re
import threading
import traceback
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from .config_model import RunConfig, load_run_config, save_run_config
from .reports import RUN_METADATA_FIELDS, build_run_metadata, save_run_metadata
from .tracking import COLOR_PRESETS, SimpleMultiTracker, SingleObjectEKFTracker, detect_spots, ensure_odd, parse_roi
from .types import Detection, TrackPoint
from .video_export import color_for_id, draw_polyline_history
from .gui_components import build_expandable_section, build_path_selector, build_validated_numeric_input
from .gui_models import (
    RunConfigFormMapper,
    build_calibration_dto,
    build_compare_dto,
    parse_ros2_values,
)
from .gui_services import GUIServiceLayer
from .gui_status import UIStatusEmitter, UIStatusEvent
from .io_paths import ensure_output_dir

GUI_MODES = ["calibration", "processing", "compare"]
GUI_SELECTION_MODES = ["largest", "stablest", "longest"]
GUI_COLOR_NAMES = list(COLOR_PRESETS.keys())
GUI_SPEED_FACTORS = [1.0, 1.25, 1.5, 2.0, 3.0, 5.0, 10.0, 20.0]
MP4_QUALITY_TOOL_PATH = "tools/video_tool.py"
WORKFLOW_CARDS = {
    "calibration": {
        "title": "Kalibracja kamery",
        "mode": "calibration",
        "goal": "Wyznaczenie parametrów kamery i szybka walidacja obrazu surowego vs. skorygowanego.",
        "required_inputs": "Wideo kalibracyjne + opcjonalny plik calib.",
        "profile": {
            "detector.track_mode": "brightness",
            "detector.threshold_mode": "fixed",
            "tracker.multi_track": "false",
            "detector.max_spots": "1",
        },
    },
    "processing": {
        "title": "Śledzenie produkcyjne",
        "mode": "processing",
        "goal": "Stabilne śledzenie obiektu i zapis pełnych artefaktów analizy.",
        "required_inputs": "Wideo wejściowe + ROI + parametry detektora/tracker.",
        "profile": {
            "detector.track_mode": "brightness",
            "detector.threshold_mode": "adaptive",
            "tracker.multi_track": "true",
            "postprocess.use_kalman": "true",
            "detector.max_spots": "3",
        },
    },
    "compare": {
        "title": "Porównanie scenariuszy",
        "mode": "compare",
        "goal": "Porównanie detekcji brightness vs color na tych samych klatkach.",
        "required_inputs": "Wideo wejściowe + wspólne progi segmentacji.",
        "profile": {
            "detector.track_mode": "color",
            "detector.threshold_mode": "otsu",
            "tracker.multi_track": "false",
            "detector.max_spots": "2",
        },
    },
}
GUI_INPUT_SOURCES = ["video file", "camera"]
GUI_EVAL_PATH_FIELDS = [
    "eval.output_csv",
    "eval.report_csv",
    "eval.report_pdf",
    "eval.trajectory_png",
    "eval.all_tracks_csv",
    "eval.annotated_video",
]
GUI_SLIDER_STEP = {
    "Threshold": 1,
    "Blur": 2,
    "Adaptive block": 2,
    "Adaptive C": 0.5,
    "Min area": 10,
    "Max area": 50,
    "Min circularity": 0.01,
    "Max aspect ratio": 0.1,
    "Min peak intensity": 1,
    "Min solidity": 0.01,
    "Erode": 1,
    "Dilate": 1,
    "Max spots": 1,
}


class GUIEnvironmentError(RuntimeError):
    """Błąd środowiska uniemożliwiający uruchomienie interfejsu Kivy."""


def _validate_gui_runtime_environment() -> None:
    """Weryfikuje podstawowe wymagania środowiska graficznego przed startem Kivy.

    Na Linuksie Kivy zwykle wymaga aktywnej sesji X11 (`DISPLAY`) albo Wayland
    (`WAYLAND_DISPLAY`). W środowiskach headless komunikat Kivy bywa mało czytelny,
    dlatego zwracamy konkretną podpowiedź wcześniej.
    """
    # Sprawdzenie dotyczy głównie Linuksa, bo tam najczęściej pojawia się błąd
    # "Unable to find any valuable Window provider" przy braku aktywnego displaya.
    if os.name != "posix":
        return
    display = os.environ.get("DISPLAY", "").strip()
    wayland_display = os.environ.get("WAYLAND_DISPLAY", "").strip()
    if _is_display_endpoint_reachable(display, wayland_display):
        return
    raise GUIEnvironmentError(
        "Brak aktywnego serwera graficznego (DISPLAY/WAYLAND_DISPLAY). "
        "Uruchom aplikację w sesji desktopowej lub skonfiguruj X11/Wayland, "
        "a następnie powtórz uruchomienie z logowaniem debug (np. `python -m luca_tracker gui -d`)."
    )


def _is_display_endpoint_reachable(display: str, wayland_display: str) -> bool:
    """Sprawdza, czy wskazany endpoint X11/Wayland wygląda na realnie dostępny.

    Samo ustawienie zmiennych DISPLAY/WAYLAND_DISPLAY bywa mylące (np. w kontenerach),
    dlatego weryfikujemy także obecność odpowiedniego gniazda Unix.
    """
    # Wayland: najpierw sprawdzamy wskazanie bezwzględne, a potem domyślne katalogi runtime.
    if wayland_display:
        wayland_path = Path(wayland_display)
        if wayland_path.is_absolute() and wayland_path.exists():
            return True
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR", "").strip()
        candidates = []
        if runtime_dir:
            candidates.append(Path(runtime_dir) / wayland_display)
        candidates.append(Path(f"/run/user/{os.getuid()}") / wayland_display)
        if any(path.exists() for path in candidates):
            return True

    # X11: sprawdzamy socket /tmp/.X11-unix/X<N> na bazie numeru ekranu z DISPLAY.
    if display:
        match = re.match(r"^(?:[^:]*:)?(?P<num>\d+)(?:\.\d+)?$", display)
        if match:
            socket_path = Path("/tmp/.X11-unix") / f"X{match.group('num')}"
            if socket_path.exists():
                return True
        # Fallback: gdy format DISPLAY jest niestandardowy, akceptujemy tylko localhost/TCP.
        if display.startswith("localhost:") or display.startswith("127.0.0.1:"):
            return True
    return False


def _parse_yaml_scalar(raw: str):
    value = raw.strip()
    lower = value.lower()
    if lower in {"true", "yes", "on"}:
        return True
    if lower in {"false", "no", "off"}:
        return False
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def load_gui_yaml_config(path: str) -> Dict[str, object]:
    cfg: Dict[str, object] = {}
    if not path:
        return cfg
    cfg_path = Path(path)
    if not cfg_path.exists():
        return cfg
    with cfg_path.open("r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or ":" not in stripped:
                continue
            key, value = stripped.split(":", 1)
            key = key.strip()
            if key:
                cfg[key] = _parse_yaml_scalar(value)
    return cfg


def _cfg_value(cfg: Dict[str, object], key: str, default):
    return cfg.get(key, default)


def discover_video_files(video_dir: str = "video", preferred_video: Optional[str] = None) -> List[Path]:
    exts = {".mp4", ".avi", ".mov", ".mkv", ".m4v"}
    files: List[Path] = []
    # Szukamy plików najpierw w globalnym katalogu analizy `/output`, a potem w lokalnym `video/`.
    for base in [ensure_output_dir(), Path(video_dir)]:
        if base.exists() and base.is_dir():
            for p in sorted(base.iterdir()):
                if p.is_file() and p.suffix.lower() in exts and p not in files:
                    files.append(p)
    if preferred_video:
        pref = Path(preferred_video)
        if pref.exists() and pref.is_file() and pref not in files:
            files.insert(0, pref)
    return files


def choose_auto_color_name(frame: np.ndarray, roi: Optional[str] = None) -> str:
    x, y, w, h = parse_roi(roi, frame.shape)
    cut = frame[y : y + h, x : x + w]
    hsv = cv2.cvtColor(cut, cv2.COLOR_BGR2HSV)

    best_name = GUI_COLOR_NAMES[0]
    best_score = -1
    for name in GUI_COLOR_NAMES:
        score = 0
        for lo, hi in COLOR_PRESETS[name]:
            mask = cv2.inRange(hsv, np.array(lo, dtype=np.uint8), np.array(hi, dtype=np.uint8))
            score += int(np.count_nonzero(mask))
        if score > best_score:
            best_score = score
            best_name = name
    return best_name


def _draw_detection_layer(
    frame: np.ndarray,
    detections: Sequence[Detection],
    label_prefix: str = "",
    color: Tuple[int, int, int] = (0, 255, 0),
) -> np.ndarray:
    canvas = frame.copy()
    for d in detections:
        cx, cy = int(round(d.x)), int(round(d.y))
        cv2.circle(canvas, (cx, cy), max(4, int(round(d.radius))), color, 2, cv2.LINE_AA)
        if d.ellipse_center is not None and d.ellipse_axes is not None and d.ellipse_angle is not None:
            ecx, ecy = d.ellipse_center
            axis_a, axis_b = d.ellipse_axes
            cv2.ellipse(
                canvas,
                (int(round(ecx)), int(round(ecy))),
                (max(1, int(round(axis_a / 2.0))), max(1, int(round(axis_b / 2.0)))),
                d.ellipse_angle,
                0,
                360,
                (0, 200, 255),
                2,
                cv2.LINE_AA,
            )
        txt = f"{label_prefix}A={d.area:.0f} R={d.rank} XY=({d.x:.1f},{d.y:.1f})"
        cv2.putText(canvas, txt, (cx + 6, cy - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
    return canvas


def _draw_single_track_marker(
    image: np.ndarray,
    xy: Optional[Tuple[float, float]],
    predicted_only: bool,
    label: str = "EKF",
) -> None:
    """Rysuje punkt śledzenia pojedynczego obiektu na wskazanym obrazie."""
    if xy is None:
        return
    cx, cy = int(round(xy[0])), int(round(xy[1]))
    color = (0, 180, 255) if predicted_only else (0, 255, 0)
    cv2.circle(image, (cx, cy), 7, color, 2, cv2.LINE_AA)
    cv2.drawMarker(image, (cx, cy), color, cv2.MARKER_CROSS, markerSize=14, thickness=2)
    cv2.putText(
        image,
        f"{label}{' PRED' if predicted_only else ''}",
        (cx + 8, cy - 10),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        color,
        1,
        cv2.LINE_AA,
    )


def _stack_h(images: Sequence[np.ndarray]) -> np.ndarray:
    h = min(img.shape[0] for img in images)
    resized = []
    for img in images:
        scale = h / img.shape[0]
        w = max(1, int(round(img.shape[1] * scale)))
        resized.append(cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA))
    return np.hstack(resized)


def _draw_hud_panel(
    image: np.ndarray,
    lines: Sequence[str],
    origin: Tuple[int, int],
    text_color: Tuple[int, int, int] = (245, 245, 245),
    bg_color: Tuple[int, int, int] = (25, 25, 25),
    alpha: float = 0.55,
    line_h: int = 22,
) -> None:
    if not lines:
        return
    x, y = origin
    pad = 10
    max_w = 0
    for line in lines:
        (w, _), _ = cv2.getTextSize(line, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
        max_w = max(max_w, w)
    panel_w = max_w + 2 * pad
    panel_h = len(lines) * line_h + 2 * pad
    x2 = min(image.shape[1] - 1, x + panel_w)
    y2 = min(image.shape[0] - 1, y + panel_h)
    x = max(0, min(x, image.shape[1] - 2))
    y = max(0, min(y, image.shape[0] - 2))

    overlay = image.copy()
    cv2.rectangle(overlay, (x, y), (x2, y2), bg_color, -1)
    cv2.addWeighted(overlay, alpha, image, 1 - alpha, 0, image)
    cv2.rectangle(image, (x, y), (x2, y2), (85, 85, 85), 1, cv2.LINE_AA)

    ty = y + pad + 14
    for line in lines:
        cv2.putText(image, line, (x + pad, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.55, text_color, 1, cv2.LINE_AA)
        ty += line_h


def _clip_slider(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def run_gui(args):
    # Ustawienia providerów Kivy ograniczają ostrzeżenia o deprecjacji pygame oraz mtdev.
    os.environ.setdefault("KIVY_TEXT", "sdl2,pil")
    os.environ.setdefault("KIVY_IMAGE", "sdl2,pil")
    os.environ.setdefault("KIVY_WINDOW", "sdl2")
    os.environ.setdefault("KIVY_NO_MTDEV", "1")
    _validate_gui_runtime_environment()
    try:
        from kivy.app import App
        from kivy.clock import Clock
        from kivy.core.window import Window
        from kivy.graphics.texture import Texture
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.button import Button
        from kivy.uix.checkbox import CheckBox
        from kivy.uix.image import Image
        from kivy.uix.label import Label
        from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
        from kivy.uix.textinput import TextInput
        from kivy.uix.scrollview import ScrollView
        from kivy.uix.slider import Slider
        from kivy.uix.spinner import Spinner
        from kivy.uix.togglebutton import ToggleButton
    except ImportError as exc:
        raise ImportError(
            "Tryb GUI wymaga bibliotek Kivy/OpenCV oraz backendu okna. "
            "Zainstaluj: pip install kivy opencv-python, a na Linuksie doinstaluj zależności SDL2/X11."
        ) from exc
    # Kivy może się zaimportować, ale bez providera okna `Window` bywa `None`.
    # Wtedy zamiast późniejszego `AttributeError` zwracamy jasny komunikat o przyczynie.
    if Window is None:
        raise GUIEnvironmentError(
            "Kivy nie znalazł działającego providera okna (Window=None). "
            "Doinstaluj backend GUI (np. SDL2/X11) i jego zależności systemowe "
            "albo uruchom aplikację w środowisku z aktywnym serwerem graficznym."
        )

    video_files = discover_video_files("video", args.video)
    if not video_files:
        raise FileNotFoundError("Nie znaleziono plików wideo. Dodaj plik do folderu 'video/' lub podaj --video.")

    output_dir = ensure_output_dir()
    camera_matrix = None
    dist_coeffs = None
    if args.calib_file:
        data = np.load(args.calib_file)
        camera_matrix = data.get("camera_matrix")
        dist_coeffs = data.get("dist_coeffs")

    gui_cfg = load_gui_yaml_config(args.gui_config)

    class TrackerGUIApp(App):
        def __init__(self):
            super().__init__()
            self.video_files = video_files
            self.output_dir = output_dir
            self.camera_matrix = camera_matrix
            self.dist_coeffs = dist_coeffs
            self.current_video_idx = max(0, min(len(self.video_files) - 1, int(_cfg_value(gui_cfg, "video_index", 0))))
            self.cap = self._open_video(self.current_video_idx)
            self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 25.0
            self.frame_index = 0
            self.last_frame: Optional[np.ndarray] = None
            self.speed_accumulator = 0.0
            self.analysis_rows: List[Dict[str, object]] = []
            self.tracker = SimpleMultiTracker(max_distance=args.max_distance, max_missed=args.max_missed)
            self.single_tracker = SingleObjectEKFTracker(
                dt=1.0 / max(self.fps, 1e-6),
                process_noise=1e-2,
                measurement_noise=5.0,
                gating_distance=max(20.0, float(args.max_distance) * 1.5),
                max_prediction_frames=max(15, int(args.max_missed) * 3),
            )
            self.single_track_history: List[TrackPoint] = []
            self.texture: Optional[Texture] = None

            self.mode = GUI_MODES[1]
            self.track_mode = args.track_mode
            self.color_name = args.color_name
            self.threshold = int(np.clip(args.threshold, 0, 255))
            self.threshold_mode = str(args.threshold_mode)
            self.adaptive_block_size = ensure_odd(max(3, int(args.adaptive_block_size)))
            self.adaptive_c = float(args.adaptive_c)
            self.use_clahe = bool(args.use_clahe)
            self.blur = int(np.clip(args.blur, 1, 31))
            self.min_area = float(args.min_area)
            self.max_area = float(args.max_area)
            # Wyższy próg kolistości redukuje fałszywe trafienia o nieregularnym obrysie.
            self.min_circularity = float(np.clip(args.min_circularity, 0.0, 1.0))
            # Niższy limit ratio bbox tłumi bardzo wydłużone kontury (np. smugi i odbicia liniowe).
            self.max_aspect_ratio = float(max(1.0, args.max_aspect_ratio))
            # Minimalny peak jasności odcina słabe refleksy, które często są niestabilne między klatkami.
            self.min_peak_intensity = float(np.clip(args.min_peak_intensity, 0.0, 255.0))
            raw_min_solidity = 0.0 if args.min_solidity is None else float(args.min_solidity)
            # Zwartość (solidity) pomaga wyciąć postrzępione/wklęsłe artefakty segmentacji.
            self.min_solidity = float(np.clip(raw_min_solidity, 0.0, 1.0))
            self.erode_iter = int(np.clip(args.erode_iter, 0, 10))
            self.dilate_iter = int(np.clip(args.dilate_iter, 0, 10))
            self.multi_track = bool(args.multi_track)
            self.max_spots = int(np.clip(args.max_spots, 1, 20))
            self.selection_mode = args.selection_mode
            self.use_calib = self.camera_matrix is not None and self.dist_coeffs is not None
            self.analyze_enabled = False
            self.paused = False
            self.auto_params = bool(_cfg_value(gui_cfg, "auto_params", False))
            cfg_speed = float(_cfg_value(gui_cfg, "speed_factor", 1.0))
            self.speed_factor = cfg_speed if cfg_speed in GUI_SPEED_FACTORS else 1.0
            # Konfigurowalny rozmiar czcionki GUI pozwala łatwo zwiększyć czytelność interfejsu.
            cfg_font_size = float(_cfg_value(gui_cfg, "font_size", 28))
            self.gui_font_size = float(np.clip(cfg_font_size, 12, 72))
            self.row_height = max(44, int(self.gui_font_size * 2.1))
            self.capture_state = "idle"
            self.nav_targets: List[Tuple[str, object]] = []
            self.nav_index = 0
            self.recording_enabled = False
            self.recording_annotated_writer = None
            self.recording_binary_writer = None
            self.recording_base_path: Optional[Path] = None
            # Mapa kontrolek formularza RunConfig używana do pełnego importu/eksportu ustawień.
            self.run_config_fields: Dict[str, TextInput] = {}
            self.selected_workflow_key = "processing"
            self.workflow_card_buttons: Dict[str, Button] = {}
            self.section_defaults: Dict[str, Dict[str, str]] = {}
            self.artifact_labels: Dict[str, Label] = {}
            self.checklist_checks: Dict[str, CheckBox] = {}
            # Emiter statusów agreguje logikę przekazywania komunikatów do paska statusu i logu zdarzeń.
            self.status_emitter = UIStatusEmitter(self._on_status_event)
            # Mapper izoluje translację kontrolek GUI <-> model RunConfig.
            self.run_config_mapper = RunConfigFormMapper(
                parse_required=self._parse_required,
                parse_int=self._parse_int,
                parse_float=self._parse_float,
                parse_bool=self._parse_bool_field,
                parse_optional=self._parse_optional_text,
            )
            # Warstwa serwisowa centralizuje uruchamianie operacji track/calibrate/compare/ros2.
            self.services = GUIServiceLayer.create_default()

        def _open_video(self, idx: int):
            cap = cv2.VideoCapture(str(self.video_files[idx]))
            if not cap.isOpened():
                raise FileNotFoundError(f"Nie udało się otworzyć pliku video: {self.video_files[idx]}")
            return cap

        def _save_analysis_rows(self, video_idx: int):
            if not self.analysis_rows:
                return
            video_name = self.video_files[video_idx].stem
            out_file = self.output_dir / f"{video_name}_gui_analysis.csv"
            # Zestaw metadanych jest zgodny z trybem `track`, aby uprościć analizę porównawczą.
            run_metadata = build_run_metadata(
                input_source=str(self.video_files[video_idx]),
                detector_name=self.track_mode,
                smoother_name="none",
                config_payload={
                    "mode": self.mode,
                    "track_mode": self.track_mode,
                    "threshold": self.threshold,
                    "threshold_mode": self.threshold_mode,
                    "adaptive_block_size": self.adaptive_block_size,
                    "adaptive_c": self.adaptive_c,
                    "use_clahe": self.use_clahe,
                    "blur": self.blur,
                    "min_area": self.min_area,
                    "max_area": self.max_area,
                    "min_circularity": self.min_circularity,
                    "max_aspect_ratio": self.max_aspect_ratio,
                    "min_peak_intensity": self.min_peak_intensity,
                    "min_solidity": self.min_solidity,
                    "erode_iter": self.erode_iter,
                    "dilate_iter": self.dilate_iter,
                    "multi_track": self.multi_track,
                    "max_spots": self.max_spots,
                    "selection_mode": self.selection_mode,
                    "color_name": self.color_name,
                    "roi": args.roi,
                },
            )
            with out_file.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=[
                        "frame_index",
                        "time_sec",
                        "input_source",
                        "mode",
                        "track_mode",
                        "detections",
                        "main_x",
                        "main_y",
                        "threshold",
                        "threshold_mode",
                        "adaptive_block_size",
                        "adaptive_c",
                        "use_clahe",
                        "blur",
                        "min_area",
                        "max_area",
                        "min_circularity",
                        "max_aspect_ratio",
                        "min_peak_intensity",
                        "min_solidity",
                        "color_name",
                    ]
                    + list(RUN_METADATA_FIELDS),
                )
                writer.writeheader()
                for row in self.analysis_rows:
                    writer.writerow(
                        {
                            **row,
                            **{field: run_metadata.get(field, "") for field in RUN_METADATA_FIELDS},
                        }
                    )
            save_run_metadata(run_metadata, str(out_file))
            print(f"[GUI] Zapisano analizę: {out_file}")

        def _switch_video(self, idx: int):
            if idx == self.current_video_idx:
                return
            self._save_analysis_rows(self.current_video_idx)
            self.analysis_rows = []
            if self.recording_enabled:
                self.recording_enabled = False
                self.btn_record.text = "Record video: OFF"
                self._release_recording_writers()
            self.cap.release()
            self.cap = self._open_video(idx)
            self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 25.0
            self.current_video_idx = idx
            self.frame_index = 0
            self.speed_accumulator = 0.0
            self.last_frame = None
            self.tracker = SimpleMultiTracker(max_distance=args.max_distance, max_missed=args.max_missed)
            self.single_tracker = SingleObjectEKFTracker(
                dt=1.0 / max(self.fps, 1e-6),
                process_noise=1e-2,
                measurement_noise=5.0,
                gating_distance=max(20.0, float(args.max_distance) * 1.5),
                max_prediction_frames=max(15, int(args.max_missed) * 3),
            )
            self.single_track_history = []
            if self.run_config_fields:
                current_video = str(self.video_files[self.current_video_idx])
                stem = self.video_files[self.current_video_idx].stem
                if self.input_source_mode_spinner.text == "video file":
                    self.input_source_value_input.text = current_video
                self._sync_input_source_fields()
                self.run_config_fields["eval.output_csv"].text = str(self.output_dir / f"{stem}_tracking.csv")
                self.run_config_fields["eval.trajectory_png"].text = str(self.output_dir / f"{stem}_trajectory.png")
                self.run_config_fields["eval.report_csv"].text = str(self.output_dir / f"{stem}_report.csv")
                self.run_config_fields["eval.report_pdf"].text = str(self.output_dir / f"{stem}_report.pdf")
                self.run_config_fields["eval.all_tracks_csv"].text = str(self.output_dir / f"{stem}_all_tracks.csv")
                self.run_config_fields["eval.annotated_video"].text = str(self.output_dir / f"{stem}_annotated.mp4")
                self._update_artifact_panel()
                self._update_checklist_status()

        def _make_slider(self, label: str, min_v: float, max_v: float, value: float, step: float, on_change):
            # Buduje jeden wiersz suwaka i zwraca referencję do kontrolki, aby obsłużyć nawigację klawiaturą/myszką.
            row = BoxLayout(orientation="horizontal", size_hint_y=None, height=self.row_height, spacing=8)
            lbl = Label(text=label, size_hint_x=0.36, halign="left", valign="middle", font_size=self.gui_font_size)
            lbl.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
            value_lbl = Label(text=str(value), size_hint_x=0.16, font_size=self.gui_font_size)
            slider = Slider(min=min_v, max=max_v, value=value, step=step, size_hint_x=0.48)

            def _update(_, val):
                if step >= 1:
                    casted = int(round(val))
                else:
                    casted = round(float(val), 2)
                value_lbl.text = str(casted)
                on_change(casted)

            slider.bind(value=_update)
            row.add_widget(lbl)
            row.add_widget(slider)
            row.add_widget(value_lbl)
            return row, slider

        def _set_capture_state(self, state: str):
            # Centralny stan pracy nagrywania/analityki, wykorzystywany przez przyciski START/PAUSE/RESUME/STOP.
            self.capture_state = state
            self.analyze_enabled = state == "running"
            self.paused = state == "paused"
            self.btn_analyze.state = "down" if self.analyze_enabled else "normal"
            self.btn_analyze.text = f"Analyze: {'ON' if self.analyze_enabled else 'OFF'}"
            self.btn_start.disabled = state == "running"
            self.btn_pause.disabled = state != "running"
            self.btn_resume.disabled = state != "paused"
            self.btn_stop.disabled = state in {"idle", "stopped"}
            self.status_label.text = f"Stan nagrania: {state.upper()}"

        def _step_selected_control(self, direction: int):
            # Zmienia wartość aktualnie wybranego pola: spinnera, suwaka lub przełącznika.
            if not self.nav_targets:
                return
            _, widget = self.nav_targets[self.nav_index]
            if isinstance(widget, Spinner):
                values = list(widget.values)
                if not values:
                    return
                idx = values.index(widget.text) if widget.text in values else 0
                widget.text = values[(idx + direction) % len(values)]
                return
            if isinstance(widget, Slider):
                step = GUI_SLIDER_STEP.get(self.nav_targets[self.nav_index][0], widget.step or 1)
                widget.value = _clip_slider(widget.value + direction * step, widget.min, widget.max)
                return
            if isinstance(widget, ToggleButton):
                widget.state = "normal" if widget.state == "down" else "down"

        def _move_focus(self, direction: int):
            # Przesuwa fokus między polami GUI, aby dało się sterować samą klawiaturą.
            if not self.nav_targets:
                return
            self.nav_index = (self.nav_index + direction) % len(self.nav_targets)
            self._refresh_focus_styles()

        def _refresh_focus_styles(self):
            # Proste podświetlenie aktualnie wybranego pola nawigacji.
            for idx, (_, widget) in enumerate(self.nav_targets):
                if hasattr(widget, "background_color"):
                    widget.background_color = (0.2, 0.55, 0.85, 1.0) if idx == self.nav_index else (1, 1, 1, 1)

        def _start_capture(self, *_):
            if self.capture_state in {"idle", "stopped"}:
                self._restart_video()
            self._set_capture_state("running")

        def _pause_capture(self, *_):
            if self.capture_state == "running":
                self._set_capture_state("paused")

        def _resume_capture(self, *_):
            if self.capture_state == "paused":
                self._set_capture_state("running")

        def _stop_capture(self, *_):
            if self.capture_state in {"running", "paused"}:
                self._set_capture_state("stopped")

        def _ensure_recording_writers(self, annotated: np.ndarray, mask_bgr: np.ndarray) -> None:
            """Inicjalizuje pliki wideo dla widoku anotowanego i binarnego."""
            if self.recording_annotated_writer is not None and self.recording_binary_writer is not None:
                return
            stem = self.video_files[self.current_video_idx].stem
            self.recording_base_path = self.output_dir / f"{stem}_gui_record_f{self.frame_index:06d}"
            fps = max(float(self.fps), 1.0)
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            annotated_path = str(self.recording_base_path) + "_annotated.mp4"
            binary_path = str(self.recording_base_path) + "_binary.mp4"
            self.recording_annotated_writer = cv2.VideoWriter(
                annotated_path,
                fourcc,
                fps,
                (annotated.shape[1], annotated.shape[0]),
            )
            self.recording_binary_writer = cv2.VideoWriter(
                binary_path,
                fourcc,
                fps,
                (mask_bgr.shape[1], mask_bgr.shape[0]),
            )
            if not self.recording_annotated_writer.isOpened() or not self.recording_binary_writer.isOpened():
                self._release_recording_writers()
                self.recording_enabled = False
                self.status_label.text = "Błąd zapisu wideo: nie udało się otworzyć plików MP4."
                return
            self.status_label.text = f"Nagrywanie ON: {self.recording_base_path.name}_*.mp4"

        def _release_recording_writers(self) -> None:
            """Zwalnia uchwyty zapisu wideo i czyści stan nagrywania."""
            if self.recording_annotated_writer is not None:
                self.recording_annotated_writer.release()
            if self.recording_binary_writer is not None:
                self.recording_binary_writer.release()
            self.recording_annotated_writer = None
            self.recording_binary_writer = None

        def _toggle_recording(self, *_):
            """Przełącza tryb nagrywania podglądu GUI do plików MP4."""
            self.recording_enabled = not self.recording_enabled
            if not self.recording_enabled:
                self._release_recording_writers()
                self.btn_record.text = "Record video: OFF"
                self.status_label.text = "Nagrywanie OFF"
                return
            self.btn_record.text = "Record video: ON"
            self.status_label.text = "Nagrywanie ON (oczekiwanie na klatkę)..."

        def _quit_app(self, *_):
            # Kończy działanie aplikacji po kliknięciu przycisku QUIT.
            self.stop()

        def _switch_video_by_delta(self, delta: int):
            target = (self.current_video_idx + delta) % len(self.video_files)
            self.video_spinner.text = self.video_files[target].name

        def _on_window_resize(self, _, width: float, height: float):
            # Dopasowuje panel kontrolek i obraz do nowego rozmiaru okna.
            control_height = max(240, int(height * 0.36))
            self.scroll_controls.height = control_height
            self.image_widget.size_hint_y = 1

        def _on_mouse_scroll(self, _, _x: float, _y: float, _sx: float, sy: float):
            # Rolka myszy: bez SHIFT przełącza fokus, z SHIFT zmienia wartość aktywnej kontrolki.
            if sy == 0:
                return False
            direction = 1 if sy > 0 else -1
            if "shift" in Window.modifiers:
                self._step_selected_control(direction)
            else:
                self._move_focus(-direction)
            return True

        def _apply_large_font_to_widget_tree(self, widget) -> None:
            # Rekurencyjnie ustawia większą czcionkę dla całego drzewa kontrolek, aby zachować spójny wygląd GUI.
            if hasattr(widget, "font_size"):
                widget.font_size = self.gui_font_size
            if hasattr(widget, "children"):
                for child in widget.children:
                    self._apply_large_font_to_widget_tree(child)

        def _on_status_event(self, event: UIStatusEvent) -> None:
            """Obsługuje jednolite zdarzenia statusu i rozsyła je do paska oraz logu UI."""
            prefix = {
                "success": "✅",
                "warning": "⚠️",
                "error": "❌",
                "info": "ℹ️",
            }.get(event.level, "ℹ️")
            entry = f"[{event.level.upper()}] {event.message}"
            print(f"[GUI] {entry}")
            if hasattr(self, "status_label"):
                self.status_label.text = f"{prefix} {event.message}"
            if hasattr(self, "event_log"):
                self.event_log.text = f"{entry}\n{self.event_log.text}".strip()
                if event.details:
                    self.event_log.text = f"{event.details}\n{self.event_log.text}".strip()

        def _set_status(self, level: str, message: str) -> None:
            """Warstwa zgodności wywołująca nowy emiter statusów."""
            self.status_emitter.emit(level, message)

        def _build_labeled_input(self, container: BoxLayout, label: str, value: str) -> TextInput:
            """Buduje standardowy wiersz formularza z etykietą i polem tekstowym."""
            row = BoxLayout(orientation="horizontal", size_hint_y=None, height=self.row_height, spacing=8)
            lbl = Label(text=label, size_hint_x=0.4, halign="left", valign="middle", font_size=self.gui_font_size)
            lbl.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
            inp = TextInput(text=value, multiline=False, size_hint_x=0.6, font_size=self.gui_font_size)
            row.add_widget(lbl)
            row.add_widget(inp)
            container.add_widget(row)
            return inp

        def _open_path_dialog(self, mode: str) -> Optional[str]:
            """Otwiera natywny dialog wyboru ścieżki (plik/folder) i zwraca wynik lub `None`."""
            try:
                from tkinter import Tk, filedialog
            except Exception as exc:  # noqa: BLE001
                self._set_status("warning", f"Dialog systemowy niedostępny: {exc}")
                return None

            root = Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            # Wybór typu dialogu zależy od celu pola: plik wejściowy/wyjściowy lub katalog.
            if mode == "file_open":
                selected = filedialog.askopenfilename()
            elif mode == "file_save":
                selected = filedialog.asksaveasfilename()
            elif mode == "directory":
                selected = filedialog.askdirectory()
            else:
                selected = ""
            root.destroy()
            cleaned = str(selected).strip()
            return cleaned or None

        def _set_path_from_dialog(self, target: TextInput, mode: str) -> None:
            """Podstawia wynik z dialogu do wskazanego pola formularza."""
            selected = self._open_path_dialog(mode)
            if selected:
                target.text = selected

        def _build_path_input(
            self,
            container: BoxLayout,
            label: str,
            value: str,
            file_mode: Optional[str] = "file_save",
            directory_selector: bool = True,
            on_value_change: Optional[Callable[[], None]] = None,
        ) -> TextInput:
            """Buduje wiersz formularza dla ścieżek z przyciskami dialogów (plik/katalog)."""
            row = BoxLayout(orientation="horizontal", size_hint_y=None, height=self.row_height, spacing=8)
            lbl = Label(text=label, size_hint_x=0.28, halign="left", valign="middle", font_size=self.gui_font_size)
            lbl.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
            inp = TextInput(text=value, multiline=False, size_hint_x=0.52, font_size=self.gui_font_size)
            if on_value_change is not None:
                inp.bind(text=lambda *_: on_value_change())
            row.add_widget(lbl)
            row.add_widget(inp)
            if file_mode:
                btn_file = Button(text="Plik", size_hint_x=0.1, font_size=max(14, int(self.gui_font_size * 0.75)))
                btn_file.bind(on_press=lambda *_: self._set_path_from_dialog(inp, file_mode))
                row.add_widget(btn_file)
            if directory_selector:
                btn_dir = Button(text="Katalog", size_hint_x=0.1, font_size=max(14, int(self.gui_font_size * 0.75)))
                btn_dir.bind(on_press=lambda *_: self._set_path_from_dialog(inp, "directory"))
                row.add_widget(btn_dir)
            container.add_widget(row)
            return inp

        def _build_expandable_section(self, container: BoxLayout, title: str):
            """Buduje prostą sekcję rozwijaną, aby grupować pola zaawansowane."""
            section = BoxLayout(orientation="vertical", size_hint_y=None, spacing=4)
            header = ToggleButton(
                text=f"▾ {title}",
                size_hint_y=None,
                height=self.row_height,
                state="down",
                font_size=self.gui_font_size,
            )
            body = BoxLayout(orientation="vertical", size_hint_y=None, spacing=6)
            body.bind(minimum_height=body.setter("height"))

            def _toggle(_instance, state: str) -> None:
                expanded = state == "down"
                body.height = body.minimum_height if expanded else 0
                body.opacity = 1.0 if expanded else 0.0
                body.disabled = not expanded
                header.text = f"{'▾' if expanded else '▸'} {title}"

            header.bind(state=_toggle)
            section.add_widget(header)
            section.add_widget(body)
            section.bind(minimum_height=section.setter("height"))
            _toggle(header, "down")
            return section, body

        def _build_section_header(self, container: BoxLayout, title: str) -> None:
            """Dodaje nagłówek sekcji formularza zgodnej z RunConfig."""
            header = Label(
                text=f"[b]{title}[/b]",
                markup=True,
                size_hint_y=None,
                height=max(28, int(self.gui_font_size * 1.4)),
                halign="left",
                valign="middle",
                font_size=max(16, int(self.gui_font_size * 0.8)),
            )
            header.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
            container.add_widget(header)

        def _register_section_defaults(self) -> None:
            """Zapamiętuje wartości startowe pól per sekcja, aby reset działał tylko lokalnie."""
            sections = ["input", "detector", "tracker", "postprocess", "pose", "eval"]
            self.section_defaults = {section: {} for section in sections}
            for key, widget in self.run_config_fields.items():
                section = key.split(".", 1)[0]
                if section in self.section_defaults:
                    self.section_defaults[section][key] = widget.text

        def _select_workflow_card(self, workflow_key: str) -> None:
            """Aktywuje kartę workflow i aktualizuje tryb podglądu zgodnie ze scenariuszem."""
            if workflow_key not in WORKFLOW_CARDS:
                return
            self.selected_workflow_key = workflow_key
            self.mode = WORKFLOW_CARDS[workflow_key]["mode"]
            for key, button in self.workflow_card_buttons.items():
                button.background_color = (0.2, 0.5, 0.9, 1) if key == workflow_key else (0.2, 0.2, 0.2, 1)
            if hasattr(self, "workflow_goal_label"):
                card = WORKFLOW_CARDS[workflow_key]
                self.workflow_goal_label.text = (
                    f"[b]Cel:[/b] {card['goal']}\n[b]Wymagane wejścia:[/b] {card['required_inputs']}"
                )
            self._update_checklist_status()

        def _apply_workflow_profile(self, *_args) -> None:
            """Wczytuje predefiniowany profil parametrów dla bieżącej karty workflow."""
            card = WORKFLOW_CARDS.get(self.selected_workflow_key, {})
            profile = card.get("profile", {})
            for field_name, value in profile.items():
                if field_name in self.run_config_fields:
                    self.run_config_fields[field_name].text = str(value)
            if "detector.track_mode" in self.run_config_fields:
                self.track_mode = self.run_config_fields["detector.track_mode"].text.strip() or self.track_mode
                self.track_spinner.text = self.track_mode
            if "detector.threshold_mode" in self.run_config_fields:
                self.threshold_mode = self.run_config_fields["detector.threshold_mode"].text.strip() or self.threshold_mode
                self.threshold_mode_spinner.text = self.threshold_mode
            if "detector.max_spots" in self.run_config_fields:
                try:
                    self.max_spots = int(self.run_config_fields["detector.max_spots"].text.strip())
                    self.slider_refs["Max spots"].value = _clip_slider(self.max_spots, 1, 20)
                except ValueError:
                    pass
            if "tracker.multi_track" in self.run_config_fields:
                self.multi_track = self.run_config_fields["tracker.multi_track"].text.strip().lower() in {"1", "true", "yes", "on"}
                self.btn_multi.state = "down" if self.multi_track else "normal"
                self.btn_multi.text = "Multi track: ON" if self.multi_track else "Multi track: OFF"
            self._set_status("info", f"Załadowano profil: {card.get('title', self.selected_workflow_key)}")
            self._update_checklist_status()

        def _reset_current_section(self, *_args) -> None:
            """Resetuje wyłącznie aktywną sekcję formularza, bez ingerencji w pozostałe pola."""
            section = self.section_spinner.text.strip().lower()
            defaults = self.section_defaults.get(section, {})
            for key, value in defaults.items():
                if key in self.run_config_fields:
                    self.run_config_fields[key].text = value
            self._set_status("info", f"Zresetowano sekcję: {section}")
            self._update_artifact_panel()
            self._update_checklist_status()

        def _update_artifact_panel(self) -> None:
            """Odświeża panel wyników i pokazuje ścieżki do artefaktów generowanych przez pipeline."""
            mapping = {
                "CSV (tracking)": "eval.output_csv",
                "CSV (report)": "eval.report_csv",
                "CSV (all tracks)": "eval.all_tracks_csv",
                "PDF": "eval.report_pdf",
                "PNG": "eval.trajectory_png",
                "MP4": "eval.annotated_video",
            }
            for label, field_key in mapping.items():
                widget = self.run_config_fields.get(field_key)
                target = widget.text.strip() if widget else ""
                marker = "✅" if target and Path(target).exists() else "⏳"
                if label in self.artifact_labels:
                    self.artifact_labels[label].text = f"{marker} {label}: {target or '-'}"

        def _update_checklist_status(self) -> None:
            """Aktualizuje checklistę etapów workflow na bazie stanu formularza i wyników."""
            input_video_widget = self.run_config_fields.get("input.video")
            input_camera_widget = self.run_config_fields.get("input.camera")
            has_input = bool(input_video_widget and input_video_widget.text.strip()) or bool(
                input_camera_widget and input_camera_widget.text.strip()
            )
            has_parameters = all(
                self.run_config_fields.get(key) and self.run_config_fields[key].text.strip()
                for key in ("detector.track_mode", "detector.threshold_mode", "tracker.max_distance")
            )
            has_run = bool(self.analysis_rows)
            has_artifacts = any(
                label.text.startswith("✅") for label in self.artifact_labels.values()
            )
            states = {
                "input": has_input,
                "params": has_parameters,
                "run": has_run,
                "artifacts": has_artifacts,
            }
            for key, value in states.items():
                if key in self.checklist_checks:
                    self.checklist_checks[key].active = value

        def _parse_required(self, raw: str, name: str) -> str:
            """Waliduje pole wymagane i zwraca oczyszczoną wartość."""
            val = raw.strip()
            if not val:
                raise ValueError(f"Pole '{name}' jest wymagane.")
            return val

        def _parse_int(self, raw: str, name: str, min_value: Optional[int] = None) -> int:
            """Parsuje liczbę całkowitą z walidacją zakresu minimalnego."""
            try:
                value = int(raw.strip())
            except ValueError as exc:
                raise ValueError(f"Pole '{name}' musi być liczbą całkowitą.") from exc
            if min_value is not None and value < min_value:
                raise ValueError(f"Pole '{name}' musi być >= {min_value}.")
            return value

        def _parse_float(self, raw: str, name: str, min_value: Optional[float] = None) -> float:
            """Parsuje liczbę zmiennoprzecinkową z walidacją zakresu minimalnego."""
            try:
                value = float(raw.strip())
            except ValueError as exc:
                raise ValueError(f"Pole '{name}' musi być liczbą.")
            if min_value is not None and value < min_value:
                raise ValueError(f"Pole '{name}' musi być >= {min_value}.")
            return value

        def _run_background_task(self, name: str, target, success_message: str):
            """Uruchamia zadanie modułowe w tle i publikuje statusy przez wspólny emiter."""
            def _job():
                try:
                    target()
                except Exception as exc:  # noqa: BLE001
                    self.status_emitter.error(f"{name}: {exc}", details=traceback.format_exc())
                    return
                self.status_emitter.success(success_message)

            threading.Thread(target=_job, daemon=True).start()

        def _collect_ros2_parser_fields(self) -> List[Tuple[str, str, str]]:
            """Pobiera listę parametrów ROS2 bez duplikowania definicji parsera w GUI."""
            from .cli import build_parser

            parser = build_parser()
            ros2_actions = []
            for action in parser._actions:
                if getattr(action, "dest", None) == "command" and hasattr(action, "choices"):
                    ros2_parser = action.choices.get("ros2")
                    if ros2_parser:
                        ros2_actions = ros2_parser._actions
                        break

            fields: List[Tuple[str, str, str]] = []
            for action in ros2_actions:
                if not action.option_strings:
                    continue
                if action.dest in {"help"}:
                    continue
                default = "" if action.default is None else str(action.default)
                fields.append((action.dest, action.option_strings[0], default))
            return fields

        def _parse_optional_text(self, raw: str) -> Optional[str]:
            """Zwraca `None` dla pustego pola tekstowego, aby poprawnie mapować wartości opcjonalne."""
            cleaned = raw.strip()
            return cleaned or None

        def _parse_bool_field(self, raw: str, name: str) -> bool:
            """Parsuje wartość logiczną z pola tekstowego."""
            lowered = raw.strip().lower()
            if lowered in {"1", "true", "yes", "on"}:
                return True
            if lowered in {"0", "false", "no", "off"}:
                return False
            raise ValueError(f"Pole '{name}' musi mieć wartość bool (true/false).")

        def _sync_input_source_fields(self) -> None:
            """Synchronizuje pola `input.video` i `input.camera` na bazie sekcji Input source."""
            mode = getattr(self, "input_source_mode_spinner", None)
            source_input = getattr(self, "input_source_value_input", None)
            if mode is None or source_input is None:
                return
            selected_mode = mode.text.strip().lower()
            source_value = source_input.text.strip()
            if selected_mode == "camera":
                self.run_config_fields["input.camera"].text = source_value
                self.run_config_fields["input.video"].text = ""
            else:
                self.run_config_fields["input.video"].text = source_value
                self.run_config_fields["input.camera"].text = ""

        def _on_input_source_mode_change(self, _, selected_mode: str) -> None:
            """Obsługuje zmianę trybu źródła wejściowego i dba o spójność pól formularza."""
            # Dla kamery zostawiamy tekstową wartość (np. indeks lub URI), a dla pliku uruchamiamy tryb ścieżki.
            if selected_mode == "camera" and not self.input_source_value_input.text.strip():
                self.input_source_value_input.text = "0"
            self._sync_input_source_fields()

        def _normalize_path(self, raw: str) -> Optional[Path]:
            """Normalizuje tekstową ścieżkę do postaci absolutnej bez wymuszania istnienia pliku."""
            cleaned = raw.strip()
            if not cleaned:
                return None
            return Path(cleaned).expanduser().resolve(strict=False)

        def _collect_path_warnings(self, cfg: RunConfig) -> List[str]:
            """Zwraca listę ostrzeżeń o potencjalnym nadpisaniu istniejących artefaktów."""
            warnings: List[str] = []
            for field_name in GUI_EVAL_PATH_FIELDS:
                value = getattr(cfg.eval, field_name.split(".", 1)[1])
                normalized = self._normalize_path(value or "")
                if normalized and normalized.exists():
                    warnings.append(f"Plik docelowy już istnieje i może zostać nadpisany: {normalized}")
            return warnings

        def _validate_run_config(self, cfg: RunConfig) -> None:
            """Weryfikuje zakresy i zależności pomiędzy kontrolkami formularza RunConfig."""
            if bool(cfg.input.video) == bool(cfg.input.camera):
                raise ValueError("Sekcja input wymaga dokładnie jednego źródła: `video` albo `camera`.")
            if cfg.detector.blur < 1 or cfg.detector.blur % 2 == 0:
                raise ValueError("`detector.blur` musi być nieparzyste i >= 1.")
            if cfg.detector.adaptive_block_size < 3 or cfg.detector.adaptive_block_size % 2 == 0:
                raise ValueError("`detector.adaptive_block_size` musi być nieparzyste i >= 3.")
            if cfg.detector.max_area > 0 and cfg.detector.max_area < cfg.detector.min_area:
                raise ValueError("`detector.max_area` musi być 0 (bez limitu) albo >= `detector.min_area`.")
            if cfg.detector.temporal_window < 1:
                raise ValueError("`detector.temporal_window` musi być >= 1.")
            if cfg.detector.hsv_lower and not cfg.detector.hsv_upper:
                raise ValueError("Dla HSV custom wymagane są jednocześnie `hsv_lower` i `hsv_upper`.")
            if cfg.detector.hsv_upper and not cfg.detector.hsv_lower:
                raise ValueError("Dla HSV custom wymagane są jednocześnie `hsv_lower` i `hsv_upper`.")
            if cfg.tracker.max_dynamic_distance < cfg.tracker.min_dynamic_distance:
                raise ValueError("`tracker.max_dynamic_distance` musi być >= `tracker.min_dynamic_distance`.")
            if cfg.pose.pnp_object_points and not cfg.pose.pnp_image_points:
                raise ValueError("Dla rekonstrukcji PnP wymagane są oba pola: `pnp_object_points` i `pnp_image_points`.")
            if cfg.pose.pnp_image_points and not cfg.pose.pnp_object_points:
                raise ValueError("Dla rekonstrukcji PnP wymagane są oba pola: `pnp_object_points` i `pnp_image_points`.")
            normalized_outputs: Dict[Path, List[str]] = {}
            for field_name in GUI_EVAL_PATH_FIELDS:
                value = getattr(cfg.eval, field_name.split(".", 1)[1])
                normalized = self._normalize_path(value or "")
                if normalized is not None:
                    normalized_outputs.setdefault(normalized, []).append(field_name)
            duplicate_outputs = {path: keys for path, keys in normalized_outputs.items() if len(keys) > 1}
            if duplicate_outputs:
                parts = [f"{path} <= {', '.join(keys)}" for path, keys in duplicate_outputs.items()]
                raise ValueError("Konflikt ścieżek output: wiele artefaktów wskazuje ten sam plik.\n" + "\n".join(parts))
            input_video = self._normalize_path(cfg.input.video or "")
            calib_file = self._normalize_path(cfg.input.calib_file or "")
            for output_path in normalized_outputs:
                if input_video is not None and output_path == input_video:
                    raise ValueError("Konflikt ścieżek: `eval.*` nie może nadpisywać `input.video`.")
                if calib_file is not None and output_path == calib_file:
                    raise ValueError("Konflikt ścieżek: `eval.*` nie może nadpisywać `input.calib_file`.")

        def _populate_run_config_form(self, cfg: RunConfig) -> None:
            """Wypełnia formularz GUI na podstawie kompletnego modelu RunConfig."""
            RunConfigFormMapper.populate_fields(self.run_config_fields, cfg)
            if cfg.input.camera:
                self.input_source_mode_spinner.text = "camera"
                self.input_source_value_input.text = cfg.input.camera
            else:
                self.input_source_mode_spinner.text = "video file"
                self.input_source_value_input.text = cfg.input.video or ""

        def build(self):
            # Dodatkowe zabezpieczenie: jeśli provider okna zniknie w trakcie startu,
            # pokażemy czytelny błąd zamiast trudnego do diagnozy wyjątku atrybutu.
            if Window is None:
                raise GUIEnvironmentError(
                    "Nie można zbudować GUI, ponieważ provider okna Kivy nie jest dostępny."
                )
            Window.minimum_width = 1100
            Window.minimum_height = 720
            if hasattr(Window, "maximize"):
                Window.maximize()

            root = BoxLayout(orientation="vertical", spacing=8, padding=8)
            tabs = TabbedPanel(do_default_tab=False, tab_pos="top_mid")
            root.add_widget(tabs)

            tracking_tab = TabbedPanelItem(text="Tracking")
            tracking_layout = BoxLayout(orientation="vertical", spacing=8)
            # `fit_mode=\"contain\"` zastępuje usunięte właściwości `allow_stretch` i `keep_ratio`.
            self.image_widget = Image(fit_mode="contain")
            tracking_layout.add_widget(self.image_widget)

            controls = BoxLayout(orientation="vertical", spacing=6, size_hint_y=None)
            controls.bind(minimum_height=controls.setter("height"))

            workflow_header = Label(
                text="[b]Workflow cards[/b]",
                markup=True,
                size_hint_y=None,
                height=self.row_height,
                halign="left",
                valign="middle",
                font_size=self.gui_font_size,
            )
            workflow_header.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
            controls.add_widget(workflow_header)
            workflow_cards_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=int(self.row_height * 1.2), spacing=8)
            for key, card in WORKFLOW_CARDS.items():
                btn = Button(text=card["title"])
                btn.bind(on_press=lambda _, workflow_key=key: self._select_workflow_card(workflow_key))
                self.workflow_card_buttons[key] = btn
                workflow_cards_row.add_widget(btn)
                self.nav_targets.append((f"Workflow {card['title']}", btn))
            controls.add_widget(workflow_cards_row)
            self.workflow_goal_label = Label(
                text="",
                markup=True,
                size_hint_y=None,
                height=int(self.row_height * 1.4),
                halign="left",
                valign="middle",
                font_size=max(14, int(self.gui_font_size * 0.65)),
            )
            self.workflow_goal_label.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
            controls.add_widget(self.workflow_goal_label)

            row_top = BoxLayout(orientation="horizontal", size_hint_y=None, height=self.row_height, spacing=8)
            self.video_spinner = Spinner(
                text=self.video_files[self.current_video_idx].name,
                values=[p.name for p in self.video_files],
                size_hint_x=0.35,
            )
            self.video_spinner.bind(text=self._on_video_change)
            row_top.add_widget(self.video_spinner)

            self.track_spinner = Spinner(text=self.track_mode, values=["brightness", "color"], size_hint_x=0.2)
            self.track_spinner.bind(text=lambda _, val: setattr(self, "track_mode", val))
            row_top.add_widget(self.track_spinner)

            self.threshold_mode_spinner = Spinner(
                text=self.threshold_mode,
                values=["fixed", "otsu", "adaptive"],
                size_hint_x=0.17,
            )
            self.threshold_mode_spinner.bind(text=lambda _, val: setattr(self, "threshold_mode", val))
            row_top.add_widget(self.threshold_mode_spinner)

            self.color_spinner = Spinner(text=self.color_name, values=GUI_COLOR_NAMES, size_hint_x=0.13)
            self.color_spinner.bind(text=lambda _, val: setattr(self, "color_name", val))
            row_top.add_widget(self.color_spinner)

            self.speed_spinner = Spinner(text=f"x{self.speed_factor:g}", values=[f"x{x:g}" for x in GUI_SPEED_FACTORS], size_hint_x=0.15)
            self.speed_spinner.bind(text=self._on_speed_change)
            row_top.add_widget(self.speed_spinner)

            controls.add_widget(row_top)
            self.nav_targets.extend(
                [
                    ("Video", self.video_spinner),
                    ("Track", self.track_spinner),
                    ("Threshold mode", self.threshold_mode_spinner),
                    ("Color", self.color_spinner),
                    ("Speed", self.speed_spinner),
                ]
            )

            checklist_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=self.row_height, spacing=12)
            checklist_items = [
                ("input", "1. Wejście"),
                ("params", "2. Parametry"),
                ("run", "3. Uruchomienie"),
                ("artifacts", "4. Eksport artefaktów"),
            ]
            for key, text in checklist_items:
                item = BoxLayout(orientation="horizontal", spacing=4)
                checkbox = CheckBox(disabled=True)
                self.checklist_checks[key] = checkbox
                item.add_widget(checkbox)
                item.add_widget(Label(text=text, halign="left", valign="middle", font_size=max(14, int(self.gui_font_size * 0.62))))
                checklist_row.add_widget(item)
            controls.add_widget(checklist_row)

            self._build_section_header(controls, "RunConfig / input")
            self._build_section_header(controls, "Input source")
            input_source_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=self.row_height, spacing=8)
            input_source_label = Label(
                text="source mode",
                size_hint_x=0.28,
                halign="left",
                valign="middle",
                font_size=self.gui_font_size,
            )
            input_source_label.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
            self.input_source_mode_spinner = Spinner(text="video file", values=GUI_INPUT_SOURCES, size_hint_x=0.2)
            self.input_source_mode_spinner.bind(text=self._on_input_source_mode_change)
            self.input_source_value_input = TextInput(
                text=str(self.video_files[self.current_video_idx]),
                multiline=False,
                size_hint_x=0.42,
                font_size=self.gui_font_size,
            )
            self.input_source_value_input.bind(text=lambda *_: self._sync_input_source_fields())
            input_source_row.add_widget(input_source_label)
            input_source_row.add_widget(self.input_source_mode_spinner)
            input_source_row.add_widget(self.input_source_value_input)
            btn_source_file = Button(text="Plik", size_hint_x=0.1, font_size=max(14, int(self.gui_font_size * 0.75)))
            btn_source_file.bind(on_press=lambda *_: self._set_path_from_dialog(self.input_source_value_input, "file_open"))
            input_source_row.add_widget(btn_source_file)
            controls.add_widget(input_source_row)
            self.run_config_fields["input.video"] = TextInput(text=str(self.video_files[self.current_video_idx]), multiline=False)
            self.run_config_fields["input.camera"] = TextInput(text="", multiline=False)
            self.run_config_fields["input.calib_file"] = self._build_path_input(
                controls,
                "input.calib_file",
                args.calib_file or "",
                file_mode="file_open",
                directory_selector=True,
            )
            self.run_config_fields["input.display"] = self._build_labeled_input(controls, "input.display", "false")
            self.run_config_fields["input.interactive"] = self._build_labeled_input(controls, "input.interactive", "false")
            self._sync_input_source_fields()

            self._build_section_header(controls, "RunConfig / detector")
            detector_defaults = {
                "detector.track_mode": self.track_mode,
                "detector.blur": str(self.blur),
                "detector.threshold": str(self.threshold),
                "detector.threshold_mode": self.threshold_mode,
                "detector.adaptive_block_size": str(self.adaptive_block_size),
                "detector.adaptive_c": str(self.adaptive_c),
                "detector.use_clahe": str(self.use_clahe).lower(),
                "detector.erode_iter": str(self.erode_iter),
                "detector.dilate_iter": str(self.dilate_iter),
                "detector.opening_kernel": "0",
                "detector.closing_kernel": "0",
                "detector.min_area": str(self.min_area),
                "detector.max_area": str(self.max_area),
                "detector.min_circularity": str(self.min_circularity),
                "detector.max_aspect_ratio": str(self.max_aspect_ratio),
                "detector.min_peak_intensity": str(self.min_peak_intensity),
                "detector.min_solidity": str(self.min_solidity),
                "detector.max_spots": str(self.max_spots),
                "detector.color_name": self.color_name,
                "detector.hsv_lower": "",
                "detector.hsv_upper": "",
                "detector.roi": args.roi or "",
                "detector.temporal_stabilization": "false",
                "detector.temporal_window": "3",
                "detector.temporal_mode": "majority",
            }
            for key, value in detector_defaults.items():
                self.run_config_fields[key] = self._build_labeled_input(controls, key, value)

            self._build_section_header(controls, "RunConfig / tracker")
            tracker_defaults = {
                "tracker.multi_track": str(self.multi_track).lower(),
                "tracker.use_single_object_ekf": "true",
                "tracker.max_distance": str(args.max_distance),
                "tracker.max_missed": str(args.max_missed),
                "tracker.selection_mode": self.selection_mode,
                "tracker.distance_weight": "1.0",
                "tracker.area_weight": "0.35",
                "tracker.circularity_weight": "0.2",
                "tracker.brightness_weight": "0.0",
                "tracker.min_match_score": "0.5",
                "tracker.speed_gate_gain": "1.5",
                "tracker.error_gate_gain": "1.0",
                "tracker.min_dynamic_distance": "12.0",
                "tracker.max_dynamic_distance": "150.0",
            }
            for key, value in tracker_defaults.items():
                self.run_config_fields[key] = self._build_labeled_input(controls, key, value)

            self._build_section_header(controls, "RunConfig / postprocess")
            for key, value in {
                "postprocess.use_kalman": "false",
                "postprocess.kalman_process_noise": "0.03",
                "postprocess.kalman_measurement_noise": "0.05",
                "postprocess.draw_all_tracks": "false",
            }.items():
                self.run_config_fields[key] = self._build_labeled_input(controls, key, value)

            self._build_section_header(controls, "RunConfig / pose")
            for key, value in {
                "pose.pnp_object_points": "",
                "pose.pnp_image_points": "",
                "pose.pnp_world_plane_z": "0.0",
            }.items():
                self.run_config_fields[key] = self._build_labeled_input(controls, key, value)

            self._build_section_header(controls, "Outputs")
            video_stem = self.video_files[self.current_video_idx].stem
            eval_defaults = {
                "eval.output_csv": str(self.output_dir / f"{video_stem}_tracking.csv"),
                "eval.trajectory_png": str(self.output_dir / f"{video_stem}_trajectory.png"),
                "eval.report_csv": str(self.output_dir / f"{video_stem}_report.csv"),
                "eval.report_pdf": str(self.output_dir / f"{video_stem}_report.pdf"),
                "eval.all_tracks_csv": str(self.output_dir / f"{video_stem}_all_tracks.csv"),
                "eval.annotated_video": str(self.output_dir / f"{video_stem}_annotated.mp4"),
            }
            for key, value in eval_defaults.items():
                self.run_config_fields[key] = self._build_labeled_input(controls, key, value)
                self.run_config_fields[key].bind(text=lambda *_: self._update_artifact_panel())

            scenario_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=self.row_height, spacing=8)
            self.section_spinner = Spinner(
                text="detector",
                values=["input", "detector", "tracker", "postprocess", "pose", "eval"],
                size_hint_x=0.25,
            )
            scenario_row.add_widget(self.section_spinner)
            btn_apply_profile = Button(text="Zastosuj profil scenariusza", size_hint_x=0.45)
            btn_apply_profile.bind(on_press=self._apply_workflow_profile)
            scenario_row.add_widget(btn_apply_profile)
            btn_reset_section = Button(text="Reset bieżącej sekcji", size_hint_x=0.30)
            btn_reset_section.bind(on_press=self._reset_current_section)
            scenario_row.add_widget(btn_reset_section)
            controls.add_widget(scenario_row)
            self.nav_targets.extend(
                [
                    ("Sekcja resetu", self.section_spinner),
                    ("Zastosuj profil", btn_apply_profile),
                    ("Reset sekcji", btn_reset_section),
                ]
            )

            self._build_section_header(controls, "Wyniki i artefakty")
            artifacts_panel = BoxLayout(orientation="vertical", size_hint_y=None, spacing=4)
            artifacts_panel.bind(minimum_height=artifacts_panel.setter("height"))
            for label in ["CSV (tracking)", "CSV (report)", "CSV (all tracks)", "PDF", "PNG", "MP4"]:
                path_label = Label(
                    text=f"⏳ {label}: -",
                    size_hint_y=None,
                    height=max(22, int(self.gui_font_size * 0.8)),
                    halign="left",
                    valign="middle",
                    font_size=max(14, int(self.gui_font_size * 0.62)),
                )
                path_label.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
                self.artifact_labels[label] = path_label
                artifacts_panel.add_widget(path_label)
            controls.add_widget(artifacts_panel)

            slider_rows = [
                ("Threshold", 0, 255, self.threshold, 1, lambda v: setattr(self, "threshold", int(v))),
                ("Blur", 1, 31, self.blur, 2, lambda v: setattr(self, "blur", ensure_odd(int(v)))),
                (
                    "Adaptive block",
                    3,
                    99,
                    self.adaptive_block_size,
                    2,
                    lambda v: setattr(self, "adaptive_block_size", ensure_odd(max(3, int(v)))),
                ),
                ("Adaptive C", -20, 20, self.adaptive_c, 0.5, lambda v: setattr(self, "adaptive_c", float(v))),
                ("Min area", 0, 5000, self.min_area, 1, lambda v: setattr(self, "min_area", float(v))),
                ("Max area", 0, 20000, self.max_area, 1, lambda v: setattr(self, "max_area", float(v))),
                ("Min circularity", 0, 1, self.min_circularity, 0.01, lambda v: setattr(self, "min_circularity", float(v))),
                ("Max aspect ratio", 1, 20, self.max_aspect_ratio, 0.1, lambda v: setattr(self, "max_aspect_ratio", float(v))),
                ("Min peak intensity", 0, 255, self.min_peak_intensity, 1, lambda v: setattr(self, "min_peak_intensity", float(v))),
                ("Min solidity", 0, 1, self.min_solidity, 0.01, lambda v: setattr(self, "min_solidity", float(v))),
                ("Erode", 0, 10, self.erode_iter, 1, lambda v: setattr(self, "erode_iter", int(v))),
                ("Dilate", 0, 10, self.dilate_iter, 1, lambda v: setattr(self, "dilate_iter", int(v))),
                ("Max spots", 1, 20, self.max_spots, 1, lambda v: setattr(self, "max_spots", int(v))),
            ]
            self.slider_refs = {}
            for key, mn, mx, val, step, fn in slider_rows:
                row, slider = self._make_slider(key, mn, mx, val, step, fn)
                controls.add_widget(row)
                self.slider_refs[key] = slider
                self.nav_targets.append((key, slider))

            toggles = BoxLayout(orientation="horizontal", size_hint_y=None, height=self.row_height, spacing=8)
            self.btn_analyze = ToggleButton(text="Analyze: OFF", state="normal")
            self.btn_analyze.bind(state=self._toggle_analyze)
            toggles.add_widget(self.btn_analyze)

            self.btn_auto = ToggleButton(text="Auto params: ON" if self.auto_params else "Auto params: OFF", state="down" if self.auto_params else "normal")
            self.btn_auto.bind(state=self._toggle_auto)
            toggles.add_widget(self.btn_auto)

            self.btn_multi = ToggleButton(text="Multi track: ON" if self.multi_track else "Multi track: OFF", state="down" if self.multi_track else "normal")
            self.btn_multi.bind(state=self._toggle_multi)
            toggles.add_widget(self.btn_multi)

            self.btn_calib = ToggleButton(text="Use calib: ON" if self.use_calib else "Use calib: OFF", state="down" if self.use_calib else "normal")
            self.btn_calib.bind(state=self._toggle_calib)
            toggles.add_widget(self.btn_calib)

            self.btn_clahe = ToggleButton(
                text="CLAHE: ON" if self.use_clahe else "CLAHE: OFF",
                state="down" if self.use_clahe else "normal",
            )
            self.btn_clahe.bind(state=self._toggle_clahe)
            toggles.add_widget(self.btn_clahe)
            controls.add_widget(toggles)
            self.nav_targets.extend(
                [
                    ("Analyze", self.btn_analyze),
                    ("Auto", self.btn_auto),
                    ("Multi", self.btn_multi),
                    ("Calib", self.btn_calib),
                    ("CLAHE", self.btn_clahe),
                ]
            )

            row_action = BoxLayout(orientation="horizontal", size_hint_y=None, height=self.row_height, spacing=8)
            btn_prev_video = Button(text="Prev video")
            btn_prev_video.bind(on_press=lambda *_: self._switch_video_by_delta(-1))
            row_action.add_widget(btn_prev_video)

            btn_next_video = Button(text="Next video")
            btn_next_video.bind(on_press=lambda *_: self._switch_video_by_delta(1))
            row_action.add_widget(btn_next_video)

            btn_restart = Button(text="Restart video")
            btn_restart.bind(on_press=lambda *_: self._restart_video())
            row_action.add_widget(btn_restart)

            btn_export_cfg = Button(text="Eksport run config")
            btn_export_cfg.bind(on_press=lambda *_: self._export_run_config())
            row_action.add_widget(btn_export_cfg)

            btn_load_cfg = Button(text="Wczytaj run config")
            btn_load_cfg.bind(on_press=lambda *_: self._load_run_config_from_path())
            row_action.add_widget(btn_load_cfg)

            btn_run_tracking = Button(text="Uruchom tracking")
            btn_run_tracking.bind(on_press=lambda *_: self._run_tracking_pipeline())
            row_action.add_widget(btn_run_tracking)

            btn_mp4 = Button(text="Pokaż komendę QA wideo")
            btn_mp4.bind(
                on_press=lambda *_: print(
                    "[GUI] Narzędzie do weryfikacji wideo:",
                    f"python {args.mp4_tool_path} --input twoj_plik.mkv --analyze-only",
                )
            )
            row_action.add_widget(btn_mp4)
            controls.add_widget(row_action)
            self.nav_targets.extend(
                [
                    ("Prev video", btn_prev_video),
                    ("Next video", btn_next_video),
                    ("Restart video", btn_restart),
                    ("Wczytaj run config", btn_load_cfg),
                    ("Uruchom tracking", btn_run_tracking),
                    ("QA video", btn_mp4),
                ]
            )

            #row_capture = BoxLayout(orientation="horizontal", size_hint_y=None, height=42, spacing=8)
            row_capture = BoxLayout(orientation="horizontal", size_hint_y=None, height=self.row_height, spacing=8)
            self.btn_record = Button(text="Record video: OFF")
            self.btn_record.bind(on_press=self._toggle_recording)
            row_capture.add_widget(self.btn_record)

            self.btn_start = Button(text="START")
            self.btn_start.bind(on_press=self._start_capture)
            row_capture.add_widget(self.btn_start)

            self.btn_pause = Button(text="PAUSE")
            self.btn_pause.bind(on_press=self._pause_capture)
            row_capture.add_widget(self.btn_pause)

            self.btn_resume = Button(text="RESUME")
            self.btn_resume.bind(on_press=self._resume_capture)
            row_capture.add_widget(self.btn_resume)

            self.btn_stop = Button(text="STOP")
            self.btn_stop.bind(on_press=self._stop_capture)
            row_capture.add_widget(self.btn_stop)

            self.btn_quit = Button(text="QUIT")
            self.btn_quit.bind(on_press=self._quit_app)
            row_capture.add_widget(self.btn_quit)
            controls.add_widget(row_capture)
            self.nav_targets.extend(
                [
                    ("Record", self.btn_record),
                    ("START", self.btn_start),
                    ("PAUSE", self.btn_pause),
                    ("RESUME", self.btn_resume),
                    ("STOP", self.btn_stop),
                    ("QUIT", self.btn_quit),
                ]
            )

            self.scroll_controls = ScrollView(size_hint=(1, None), size=(Window.width, 300), do_scroll_x=False)
            self.scroll_controls.add_widget(controls)
            tracking_layout.add_widget(self.scroll_controls)
            tracking_tab.add_widget(tracking_layout)
            tabs.add_widget(tracking_tab)

            calibration_tab = TabbedPanelItem(text="Calibration")
            calibration_layout = BoxLayout(orientation="vertical", spacing=8, padding=8)
            self.calib_dir_input = build_path_selector(self, calibration_layout, "calib_dir", "images_calib", file_mode="directory")
            self.calib_output_input = build_path_selector(self, calibration_layout, "output_file", "camera_calib.npz", file_mode="file_save")

            def _build_calibration_numeric_section(section_body):
                # Wspólny komponent pola liczbowego dba o szybką walidację i kolor błędu.
                self.calib_rows_input = build_validated_numeric_input(
                    self, section_body, "rows", "6", parse_value=lambda raw: float(int(raw)), min_value=2
                )
                self.calib_cols_input = build_validated_numeric_input(
                    self, section_body, "cols", "9", parse_value=lambda raw: float(int(raw)), min_value=2
                )
                self.calib_square_input = build_validated_numeric_input(
                    self, section_body, "square_size", "1.0", parse_value=float, min_value=0.0001
                )

            build_expandable_section(self, calibration_layout, "Parametry planszy", _build_calibration_numeric_section)
            calib_run = Button(text="Uruchom", size_hint_y=None, height=self.row_height)
            calib_run.bind(on_press=lambda *_: self._run_calibration())
            calibration_layout.add_widget(calib_run)
            calibration_tab.add_widget(calibration_layout)
            tabs.add_widget(calibration_tab)

            compare_tab = TabbedPanelItem(text="Compare")
            compare_layout = BoxLayout(orientation="vertical", spacing=8, padding=8)
            self.compare_ref_input = build_path_selector(self, compare_layout, "reference", "", file_mode="file_open")
            self.compare_candidate_input = build_path_selector(self, compare_layout, "candidate", "", file_mode="file_open")
            self.compare_output_input = build_path_selector(self, compare_layout, "output_csv", "compare_output.csv", file_mode="file_save")
            self.compare_report_input = build_path_selector(self, compare_layout, "report_pdf (opcjonalnie)", "", file_mode="file_save")
            compare_run = Button(text="Uruchom", size_hint_y=None, height=self.row_height)
            compare_run.bind(on_press=lambda *_: self._run_compare())
            compare_layout.add_widget(compare_run)
            compare_tab.add_widget(compare_layout)
            tabs.add_widget(compare_tab)

            ros2_tab = TabbedPanelItem(text="ROS2")
            ros2_scroll = ScrollView(do_scroll_x=False)
            ros2_layout = BoxLayout(orientation="vertical", spacing=8, padding=8, size_hint_y=None)
            ros2_layout.bind(minimum_height=ros2_layout.setter("height"))
            self.ros2_inputs: Dict[str, TextInput] = {}
            for dest, option_name, default in self._collect_ros2_parser_fields():
                self.ros2_inputs[dest] = self._build_labeled_input(ros2_layout, option_name, default)
            ros2_run = Button(text="Uruchom", size_hint_y=None, height=self.row_height)
            ros2_run.bind(on_press=lambda *_: self._run_ros2())
            ros2_layout.add_widget(ros2_run)
            ros2_scroll.add_widget(ros2_layout)
            ros2_tab.add_widget(ros2_scroll)
            tabs.add_widget(ros2_tab)

            status_panel = BoxLayout(orientation="vertical", size_hint_y=None, height=max(200, int(self.gui_font_size * 8)))
            self.status_label = Label(
                text="Ready",
                size_hint_y=None,
                height=max(30, int(self.gui_font_size * 1.6)),
                halign="left",
                valign="middle",
                font_size=self.gui_font_size,
            )
            self.status_label.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
            status_panel.add_widget(self.status_label)
            self.event_log = TextInput(readonly=True, multiline=True, font_size=max(14, self.gui_font_size * 0.6))
            status_panel.add_widget(self.event_log)
            root.add_widget(status_panel)

            Window.bind(on_key_down=self._on_key_down)
            Window.bind(on_resize=self._on_window_resize)
            Window.bind(on_mouse_scroll=self._on_mouse_scroll)
            self._apply_large_font_to_widget_tree(controls)
            self._register_section_defaults()
            self._select_workflow_card(self.selected_workflow_key)
            self._update_artifact_panel()
            self._update_checklist_status()
            self._refresh_focus_styles()
            self._set_capture_state("idle")
            self._set_status("info", "GUI gotowe. Wybierz zakładkę i uruchom zadanie.")
            Clock.schedule_interval(self._update_frame, float(np.clip(_cfg_value(gui_cfg, "wait_ms_running", 16), 1, 200)) / 1000.0)
            return root

        def _on_video_change(self, _, selected_name: str):
            idx = [p.name for p in self.video_files].index(selected_name)
            self._switch_video(idx)

        def _run_tracking_pipeline(self):
            """Uruchamia pipeline śledzenia przez warstwę serwisową."""
            if not self.video_files:
                self.status_emitter.error("Brak dostępnych plików wideo do uruchomienia trackingu.")
                return
            try:
                cfg = self._build_current_run_config()
            except ValueError as exc:
                self.status_emitter.error(str(exc))
                return
            for warning in self._collect_path_warnings(cfg):
                self.status_emitter.warning(warning)
            self.status_emitter.info("Uruchamianie track_video w tle...")

            def _run_tracking_job() -> None:
                # Po zakończeniu pipeline odświeżamy checklistę i panel artefaktów w tym samym przebiegu.
                self.services.run_tracking(cfg)
                self._update_artifact_panel()
                self._update_checklist_status()

            self._run_background_task(
                "Tracking",
                _run_tracking_job,
                f"Tracking zakończony. Wynik: {cfg.eval.output_csv}",
            )

        def _run_calibration(self):
            """Waliduje DTO Calibration i uruchamia usługę kalibracji."""
            try:
                config = build_calibration_dto(
                    calib_dir=self.calib_dir_input.text,
                    rows=self.calib_rows_input.text,
                    cols=self.calib_cols_input.text,
                    square_size=self.calib_square_input.text,
                    output_file=self.calib_output_input.text,
                    parse_required=self._parse_required,
                    parse_int=self._parse_int,
                    parse_float=self._parse_float,
                )
            except ValueError as exc:
                self.status_emitter.error(str(exc))
                return

            self.status_emitter.info("Uruchamianie kalibracji...")
            self._run_background_task(
                "Calibration",
                lambda: self.services.run_calibration(config),
                f"Kalibracja zakończona. Plik: {config.output_file}",
            )

        def _run_compare(self):
            """Waliduje DTO Compare i uruchamia usługę porównania CSV."""
            try:
                config = build_compare_dto(
                    reference=self.compare_ref_input.text,
                    candidate=self.compare_candidate_input.text,
                    output_csv=self.compare_output_input.text,
                    report_pdf=self.compare_report_input.text,
                    parse_required=self._parse_required,
                )
            except ValueError as exc:
                self.status_emitter.error(str(exc))
                return

            self.status_emitter.info("Uruchamianie compare_csv...")
            self._run_background_task(
                "Compare",
                lambda: self.services.run_compare(config),
                f"Porównanie zakończone. Wynik: {config.output_csv}",
            )

        def _run_ros2(self):
            """Waliduje DTO ROS2 i uruchamia node trackera przez warstwę serwisową."""
            try:
                config = parse_ros2_values({key: widget.text for key, widget in self.ros2_inputs.items()})
            except ValueError as exc:
                self.status_emitter.error(str(exc))
                return

            self.status_emitter.warning("Uruchamianie ROS2 node (zadanie długotrwałe)...")
            self._run_background_task(
                "ROS2",
                lambda: self.services.run_ros2(config),
                "ROS2 node zakończył działanie.",
            )

        def _on_speed_change(self, _, selected: str):
            self.speed_factor = float(selected.replace("x", ""))

        def _toggle_analyze(self, _, state: str):
            desired = state == "down"
            self.btn_analyze.text = f"Analyze: {'ON' if desired else 'OFF'}"
            if desired and self.capture_state in {"idle", "stopped"}:
                self._start_capture()
            elif not desired and self.capture_state in {"running", "paused"}:
                self._stop_capture()

        def _toggle_auto(self, _, state: str):
            self.auto_params = state == "down"
            self.btn_auto.text = f"Auto params: {'ON' if self.auto_params else 'OFF'}"

        def _toggle_multi(self, _, state: str):
            self.multi_track = state == "down"
            self.btn_multi.text = f"Multi track: {'ON' if self.multi_track else 'OFF'}"

        def _toggle_calib(self, _, state: str):
            enabled = state == "down" and self.camera_matrix is not None and self.dist_coeffs is not None
            self.use_calib = enabled
            self.btn_calib.text = f"Use calib: {'ON' if self.use_calib else 'OFF'}"
            if not enabled:
                self.btn_calib.state = "normal"

        def _toggle_clahe(self, _, state: str):
            # Przełącznik CLAHE pozwala szybko sprawdzić wpływ lokalnego kontrastu na detekcję.
            self.use_clahe = state == "down"
            self.btn_clahe.text = f"CLAHE: {'ON' if self.use_clahe else 'OFF'}"

        def _restart_video(self):
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            self.frame_index = 0
            self.speed_accumulator = 0.0
            self.last_frame = None
            self.tracker = SimpleMultiTracker(max_distance=args.max_distance, max_missed=args.max_missed)
            self.single_tracker = SingleObjectEKFTracker(
                dt=1.0 / max(self.fps, 1e-6),
                process_noise=1e-2,
                measurement_noise=5.0,
                gating_distance=max(20.0, float(args.max_distance) * 1.5),
                max_prediction_frames=max(15, int(args.max_missed) * 3),
            )
            self.single_track_history = []

        def _build_current_run_config(self) -> RunConfig:
            """Buduje pełny model konfiguracji korzystając z mappera kontrolek RunConfig."""
            self._sync_input_source_fields()
            cfg = self.run_config_mapper.build_from_fields(self.run_config_fields)
            self._validate_run_config(cfg)
            return cfg

        def _load_run_config_from_path(self) -> None:
            """Wczytuje plik run config i mapuje jego stan do wszystkich kontrolek formularza."""
            default_path = self.output_dir / f"{self.video_files[self.current_video_idx].stem}_run_config.yaml"
            candidate_path = Path(default_path)
            if not candidate_path.exists():
                json_path = self.output_dir / f"{self.video_files[self.current_video_idx].stem}_run_config.json"
                candidate_path = json_path if json_path.exists() else candidate_path
            try:
                cfg = load_run_config(candidate_path)
                self._validate_run_config(cfg)
                self._populate_run_config_form(cfg)
                self._set_status("success", f"Wczytano run config: {candidate_path}")
            except Exception as exc:  # noqa: BLE001
                self._set_status("error", f"Nie udało się wczytać run config: {exc}")

        def _export_run_config(self):
            """Eksportuje bieżące ustawienia GUI do pliku run config (preferowany YAML, fallback JSON)."""
            try:
                cfg = self._build_current_run_config()
            except ValueError as exc:
                self._set_status("error", str(exc))
                return
            for warning in self._collect_path_warnings(cfg):
                self._set_status("warning", warning)
            export_path = self.output_dir / f"{self.video_files[self.current_video_idx].stem}_run_config.yaml"
            try:
                save_run_config(cfg, export_path)
            except RuntimeError:
                export_path = self.output_dir / f"{self.video_files[self.current_video_idx].stem}_run_config.json"
                save_run_config(cfg, export_path)
            self.status_label.text = f"Wyeksportowano run config: {export_path}"
            print(f"[GUI] Wyeksportowano run config: {export_path}")

        def _on_key_down(self, _, key, __, ___, ____):
            if key == 113:
                self.stop()
                return True
            if key == 32:
                if self.capture_state == "running":
                    self._pause_capture()
                elif self.capture_state == "paused":
                    self._resume_capture()
                else:
                    self._start_capture()
                return True
            if key in (273, 274):
                self._move_focus(-1 if key == 273 else 1)
                return True
            if key in (275, 276):
                self._step_selected_control(1 if key == 275 else -1)
                return True
            if key == 115:
                self._stop_capture()
                return True
            if key == 109:
                print(
                    "[GUI] Narzędzie do weryfikacji wideo:",
                    f"python {args.mp4_tool_path} --input twoj_plik.mkv --analyze-only",
                )
                return True
            return False

        def _apply_auto_params(self, frame: np.ndarray):
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            self.threshold = int(np.clip(np.percentile(gray, 99.5), 60, 250))
            self.threshold_mode = "fixed"
            self.adaptive_block_size = 31
            self.adaptive_c = 5.0
            self.use_clahe = False
            self.blur = 9
            self.min_area = max(5.0, frame.shape[0] * frame.shape[1] * 0.00002)
            self.max_area = frame.shape[0] * frame.shape[1] * 0.25
            self.min_circularity = 0.1
            self.max_aspect_ratio = 4.0
            self.min_peak_intensity = float(np.clip(np.percentile(gray, 97.0), 40, 255))
            self.min_solidity = 0.5
            self.erode_iter = 1
            self.dilate_iter = 2
            self.color_name = choose_auto_color_name(frame, args.roi)
            self.track_mode = "brightness"
            self.max_spots = 1
            self.mode = "processing"
            self._select_workflow_card("processing")

            self.track_spinner.text = self.track_mode
            self.threshold_mode_spinner.text = self.threshold_mode
            self.color_spinner.text = self.color_name
            self.slider_refs["Threshold"].value = self.threshold
            self.slider_refs["Blur"].value = self.blur
            self.slider_refs["Adaptive block"].value = self.adaptive_block_size
            self.slider_refs["Adaptive C"].value = self.adaptive_c
            self.slider_refs["Min area"].value = _clip_slider(self.min_area, 0, 5000)
            self.slider_refs["Max area"].value = _clip_slider(self.max_area, 0, 20000)
            self.slider_refs["Min circularity"].value = _clip_slider(self.min_circularity, 0, 1)
            self.slider_refs["Max aspect ratio"].value = _clip_slider(self.max_aspect_ratio, 1, 20)
            self.slider_refs["Min peak intensity"].value = _clip_slider(self.min_peak_intensity, 0, 255)
            self.slider_refs["Min solidity"].value = _clip_slider(self.min_solidity, 0, 1)
            self.slider_refs["Erode"].value = self.erode_iter
            self.slider_refs["Dilate"].value = self.dilate_iter
            self.slider_refs["Max spots"].value = self.max_spots

        def _update_frame(self, _dt):
            should_advance = self.capture_state == "running"
            if should_advance:
                self.speed_accumulator += self.speed_factor
                frames_to_advance = max(1, int(self.speed_accumulator))
                self.speed_accumulator -= int(self.speed_accumulator)
            else:
                frames_to_advance = 1

            if should_advance or self.last_frame is None:
                ok, frame = False, None
                for _ in range(frames_to_advance):
                    ok, frame = self.cap.read()
                    if not ok:
                        break
                if not ok or frame is None:
                    self._restart_video()
                    return
                self.last_frame = frame
                if self.analyze_enabled:
                    self.frame_index += frames_to_advance

            frame = self.last_frame.copy()
            if self.auto_params:
                self._apply_auto_params(frame)

            processed = cv2.undistort(frame, self.camera_matrix, self.dist_coeffs) if self.use_calib else frame
            detections, mask, roi_box = detect_spots(
                frame=processed,
                track_mode=self.track_mode,
                blur=ensure_odd(max(1, self.blur)),
                threshold=self.threshold,
                threshold_mode=self.threshold_mode,
                adaptive_block_size=int(self.adaptive_block_size),
                adaptive_c=float(self.adaptive_c),
                use_clahe=bool(self.use_clahe),
                erode_iter=self.erode_iter,
                dilate_iter=self.dilate_iter,
                min_area=float(self.min_area),
                max_area=float(self.max_area),
                min_circularity=float(self.min_circularity),
                max_aspect_ratio=float(self.max_aspect_ratio),
                min_peak_intensity=float(self.min_peak_intensity),
                min_solidity=float(self.min_solidity),
                max_spots=max(1, self.max_spots),
                color_name=self.color_name,
                hsv_lower=None,
                hsv_upper=None,
                roi=args.roi,
            )

            mask_bgr = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
            x0, y0, w, h = roi_box
            annotated = _draw_detection_layer(processed, detections, color=(0, 255, 0))
            cv2.rectangle(annotated, (x0, y0), (x0 + w, y0 + h), (255, 255, 0), 1)
            cv2.rectangle(mask_bgr, (x0, y0), (x0 + w, y0 + h), (255, 255, 0), 1)

            single_state = self.single_tracker.update(detections)
            tracked_xy: Optional[Tuple[float, float]]
            if single_state["x"] is None or single_state["y"] is None:
                tracked_xy = None
            else:
                tracked_xy = (float(single_state["x"]), float(single_state["y"]))
            predicted_only = bool(single_state.get("predicted_only", True))

            if tracked_xy is not None and self.analyze_enabled:
                self.single_track_history.append(
                    TrackPoint(
                        frame_index=self.frame_index,
                        time_sec=self.frame_index / self.fps,
                        detected=not predicted_only,
                        x=tracked_xy[0],
                        y=tracked_xy[1],
                        area=None,
                        perimeter=None,
                        circularity=None,
                        radius=None,
                        track_id=1,
                        rank=0,
                        kalman_predicted=int(predicted_only),
                    )
                )
                draw_polyline_history(annotated, self.single_track_history, (80, 230, 255), max_tail=120)
                draw_polyline_history(mask_bgr, self.single_track_history, (80, 230, 255), max_tail=120)
            _draw_single_track_marker(annotated, tracked_xy, predicted_only, label="EKF")
            _draw_single_track_marker(mask_bgr, tracked_xy, predicted_only, label="EKF")

            if self.mode == "calibration":
                preview = _stack_h([frame, processed])
            elif self.mode == "processing":
                if self.multi_track and self.analyze_enabled:
                    self.tracker.update(detections, self.frame_index, self.frame_index / self.fps)
                    for tid, data in self.tracker.tracks.items():
                        draw_polyline_history(annotated, data["points"], color_for_id(tid), max_tail=80)
                preview = _stack_h([annotated, mask_bgr])
            else:
                det_bright, _, _ = detect_spots(
                    frame=processed,
                    track_mode="brightness",
                    blur=ensure_odd(max(1, self.blur)),
                    threshold=self.threshold,
                    threshold_mode=self.threshold_mode,
                    adaptive_block_size=int(self.adaptive_block_size),
                    adaptive_c=float(self.adaptive_c),
                    use_clahe=bool(self.use_clahe),
                    erode_iter=self.erode_iter,
                    dilate_iter=self.dilate_iter,
                    min_area=float(self.min_area),
                    max_area=float(self.max_area),
                    min_circularity=float(self.min_circularity),
                    max_aspect_ratio=float(self.max_aspect_ratio),
                    min_peak_intensity=float(self.min_peak_intensity),
                    min_solidity=float(self.min_solidity),
                    max_spots=max(1, self.max_spots),
                    color_name=self.color_name,
                    hsv_lower=None,
                    hsv_upper=None,
                    roi=args.roi,
                )
                det_color, _, _ = detect_spots(
                    frame=processed,
                    track_mode="color",
                    blur=ensure_odd(max(1, self.blur)),
                    threshold=self.threshold,
                    threshold_mode=self.threshold_mode,
                    adaptive_block_size=int(self.adaptive_block_size),
                    adaptive_c=float(self.adaptive_c),
                    use_clahe=bool(self.use_clahe),
                    erode_iter=self.erode_iter,
                    dilate_iter=self.dilate_iter,
                    min_area=float(self.min_area),
                    max_area=float(self.max_area),
                    min_circularity=float(self.min_circularity),
                    max_aspect_ratio=float(self.max_aspect_ratio),
                    min_peak_intensity=float(self.min_peak_intensity),
                    min_solidity=float(self.min_solidity),
                    max_spots=max(1, self.max_spots),
                    color_name=self.color_name,
                    hsv_lower=None,
                    hsv_upper=None,
                    roi=args.roi,
                )
                bright_view = _draw_detection_layer(processed, det_bright, label_prefix="B ", color=(255, 80, 80))
                color_view = _draw_detection_layer(processed, det_color, label_prefix="C ", color=(80, 255, 80))
                preview = _stack_h([bright_view, color_view, mask_bgr])

            _draw_hud_panel(
                preview,
                [
                    f"Video: {self.video_files[self.current_video_idx].name}",
                    f"Mode: {self.mode} | Track: {self.track_mode} | Thresh: {self.threshold_mode}",
                    f"Detections: {len(detections)} | Frame: {self.frame_index}",
                    f"Single EKF: {'PRED' if predicted_only else 'MEAS'} | Max spots: {self.max_spots}",
                    f"CLAHE: {'ON' if self.use_clahe else 'OFF'} | Auto: {'ON' if self.auto_params else 'OFF'} | Speed: x{self.speed_factor:g}",
                ],
                origin=(10, 10),
                bg_color=(18, 26, 36),
                alpha=0.62,
            )

            if tracked_xy is not None and self.analyze_enabled:
                self.analysis_rows.append(
                    {
                        "frame_index": self.frame_index,
                        "time_sec": self.frame_index / self.fps,
                        "input_source": self.video_files[self.current_video_idx].name,
                        "mode": self.mode,
                        "track_mode": self.track_mode,
                        "detections": len(detections),
                        "main_x": round(float(tracked_xy[0]), 3),
                        "main_y": round(float(tracked_xy[1]), 3),
                        "threshold": self.threshold,
                        "threshold_mode": self.threshold_mode,
                        "adaptive_block_size": self.adaptive_block_size,
                        "adaptive_c": self.adaptive_c,
                        "use_clahe": self.use_clahe,
                        "blur": self.blur,
                        "min_area": self.min_area,
                        "max_area": self.max_area,
                        "min_circularity": self.min_circularity,
                        "max_aspect_ratio": self.max_aspect_ratio,
                        "min_peak_intensity": self.min_peak_intensity,
                        "min_solidity": self.min_solidity,
                        "color_name": self.color_name,
                    }
                )
            if self.recording_enabled:
                self._ensure_recording_writers(annotated, mask_bgr)
                if self.recording_annotated_writer is not None and self.recording_binary_writer is not None:
                    self.recording_annotated_writer.write(annotated)
                    self.recording_binary_writer.write(mask_bgr)

            rgb = cv2.cvtColor(preview, cv2.COLOR_BGR2RGB)
            buf = rgb.tobytes()
            if self.texture is None or self.texture.size != (rgb.shape[1], rgb.shape[0]):
                self.texture = Texture.create(size=(rgb.shape[1], rgb.shape[0]), colorfmt="rgb")
                self.texture.flip_vertical()
            self.texture.blit_buffer(buf, colorfmt="rgb", bufferfmt="ubyte")
            self.image_widget.texture = self.texture
            self.status_label.text = (
                f"{self.video_files[self.current_video_idx].name} | detections={len(detections)} | "
                f"frame={self.frame_index} | analyze={'ON' if self.analyze_enabled else 'OFF'}"
            )

        def on_stop(self):
            if self.cap:
                self.cap.release()
            self._release_recording_writers()
            self._save_analysis_rows(self.current_video_idx)

    TrackerGUIApp().run()
