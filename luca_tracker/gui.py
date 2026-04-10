from __future__ import annotations

import csv
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from .config_model import (
    DetectorConfig as RunDetectorConfig,
    EvalConfig,
    InputConfig,
    PostprocessConfig,
    RunConfig,
    TrackerConfig as RunTrackerConfig,
    save_run_config,
)
from .reports import RUN_METADATA_FIELDS, build_run_metadata, save_run_metadata
from .tracking import COLOR_PRESETS, SimpleMultiTracker, SingleObjectEKFTracker, detect_spots, ensure_odd, parse_roi
from .types import Detection, TrackPoint
from .video_export import color_for_id, draw_polyline_history
from .io_paths import ensure_output_dir

GUI_MODES = ["calibration", "processing", "compare"]
GUI_SELECTION_MODES = ["largest", "stablest", "longest"]
GUI_COLOR_NAMES = list(COLOR_PRESETS.keys())
GUI_SPEED_FACTORS = [1.0, 1.25, 1.5, 2.0, 3.0, 5.0, 10.0, 20.0]
MP4_QUALITY_TOOL_PATH = "tools/video_tool.py"
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
        "a następnie powtórz uruchomienie z logowaniem debug (np. `python track_luca.py gui -d`)."
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
        from kivy.uix.image import Image
        from kivy.uix.label import Label
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
            self.min_circularity = float(np.clip(args.min_circularity, 0.0, 1.0))
            self.max_aspect_ratio = float(max(1.0, args.max_aspect_ratio))
            self.min_peak_intensity = float(np.clip(args.min_peak_intensity, 0.0, 255.0))
            raw_min_solidity = 0.0 if args.min_solidity is None else float(args.min_solidity)
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
                video_file=str(self.video_files[video_idx]),
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
                        "video_file",
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
            # `fit_mode=\"contain\"` zastępuje usunięte właściwości `allow_stretch` i `keep_ratio`.
            self.image_widget = Image(fit_mode="contain")
            root.add_widget(self.image_widget)

            controls = BoxLayout(orientation="vertical", spacing=6, size_hint_y=None)
            controls.bind(minimum_height=controls.setter("height"))

            row_top = BoxLayout(orientation="horizontal", size_hint_y=None, height=self.row_height, spacing=8)
            self.video_spinner = Spinner(
                text=self.video_files[self.current_video_idx].name,
                values=[p.name for p in self.video_files],
                size_hint_x=0.3,
            )
            self.video_spinner.bind(text=self._on_video_change)
            row_top.add_widget(self.video_spinner)

            self.mode_spinner = Spinner(text=self.mode, values=GUI_MODES, size_hint_x=0.2)
            self.mode_spinner.bind(text=lambda _, val: setattr(self, "mode", val))
            row_top.add_widget(self.mode_spinner)

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
                    ("Mode", self.mode_spinner),
                    ("Track", self.track_spinner),
                    ("Threshold mode", self.threshold_mode_spinner),
                    ("Color", self.color_spinner),
                    ("Speed", self.speed_spinner),
                ]
            )

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

            self.status_label = Label(text="Ready", size_hint_y=None, height=max(30, int(self.gui_font_size * 1.6)), halign="left", valign="middle", font_size=self.gui_font_size)
            self.status_label.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
            controls.add_widget(self.status_label)

            self.scroll_controls = ScrollView(size_hint=(1, None), size=(Window.width, 300), do_scroll_x=False)
            self.scroll_controls.add_widget(controls)
            root.add_widget(self.scroll_controls)

            Window.bind(on_key_down=self._on_key_down)
            Window.bind(on_resize=self._on_window_resize)
            Window.bind(on_mouse_scroll=self._on_mouse_scroll)
            self._apply_large_font_to_widget_tree(controls)
            self._refresh_focus_styles()
            self._set_capture_state("idle")
            Clock.schedule_interval(self._update_frame, float(np.clip(_cfg_value(gui_cfg, "wait_ms_running", 16), 1, 200)) / 1000.0)
            return root

        def _on_video_change(self, _, selected_name: str):
            idx = [p.name for p in self.video_files].index(selected_name)
            self._switch_video(idx)

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
            """Buduje pełny model konfiguracji z aktualnego stanu kontrolek GUI."""
            return RunConfig(
                input=InputConfig(
                    video=str(self.video_files[self.current_video_idx]),
                    calib_file=args.calib_file,
                    display=False,
                    interactive=False,
                ),
                detector=RunDetectorConfig(
                    track_mode=self.track_mode,
                    blur=ensure_odd(max(1, int(self.blur))),
                    threshold=int(self.threshold),
                    threshold_mode=self.threshold_mode,
                    adaptive_block_size=int(self.adaptive_block_size),
                    adaptive_c=float(self.adaptive_c),
                    use_clahe=bool(self.use_clahe),
                    erode_iter=int(self.erode_iter),
                    dilate_iter=int(self.dilate_iter),
                    min_area=float(self.min_area),
                    max_area=float(self.max_area),
                    min_circularity=float(self.min_circularity),
                    max_aspect_ratio=float(self.max_aspect_ratio),
                    min_peak_intensity=float(self.min_peak_intensity),
                    min_solidity=float(self.min_solidity),
                    max_spots=max(1, int(self.max_spots)),
                    color_name=self.color_name,
                    hsv_lower=None,
                    hsv_upper=None,
                    roi=args.roi,
                ),
                tracker=RunTrackerConfig(
                    multi_track=bool(self.multi_track),
                    max_distance=float(args.max_distance),
                    max_missed=int(args.max_missed),
                    selection_mode=self.selection_mode,
                ),
                postprocess=PostprocessConfig(
                    use_kalman=False,
                    kalman_process_noise=1e-2,
                    kalman_measurement_noise=1e-1,
                    draw_all_tracks=False,
                ),
                eval=EvalConfig(
                    output_csv=str(self.output_dir / f"{self.video_files[self.current_video_idx].stem}_tracking.csv"),
                    trajectory_png=str(self.output_dir / f"{self.video_files[self.current_video_idx].stem}_trajectory.png"),
                    report_csv=str(self.output_dir / f"{self.video_files[self.current_video_idx].stem}_report.csv"),
                    report_pdf=str(self.output_dir / f"{self.video_files[self.current_video_idx].stem}_report.pdf"),
                    all_tracks_csv=str(self.output_dir / f"{self.video_files[self.current_video_idx].stem}_all_tracks.csv"),
                    annotated_video=str(self.output_dir / f"{self.video_files[self.current_video_idx].stem}_annotated.mp4"),
                ),
            )

        def _export_run_config(self):
            """Eksportuje bieżące ustawienia GUI do pliku run config (preferowany YAML, fallback JSON)."""
            cfg = self._build_current_run_config()
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

            self.mode_spinner.text = self.mode
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
                        "video_file": self.video_files[self.current_video_idx].name,
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
