from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from .tracking import COLOR_PRESETS, SimpleMultiTracker, detect_spots, ensure_odd, parse_roi
from .types import Detection
from .video_export import color_for_id, draw_polyline_history

GUI_MODES = ["calibration", "processing", "compare"]
GUI_SELECTION_MODES = ["largest", "stablest", "longest"]
GUI_COLOR_NAMES = list(COLOR_PRESETS.keys())
GUI_SPEED_FACTORS = [1.0, 1.25, 1.5, 2.0, 3.0, 5.0, 10.0, 20.0]
MP4_QUALITY_TOOL_PATH = "tools/video_tool.py"


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
    video_path = Path(video_dir)
    if video_path.exists() and video_path.is_dir():
        files.extend(sorted(p for p in video_path.iterdir() if p.is_file() and p.suffix.lower() in exts))
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
        raise ImportError("Tryb GUI wymaga biblioteki kivy. Zainstaluj: pip install kivy") from exc

    video_files = discover_video_files("video", args.video)
    if not video_files:
        raise FileNotFoundError("Nie znaleziono plików wideo. Dodaj plik do folderu 'video/' lub podaj --video.")

    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)
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
            self.texture: Optional[Texture] = None

            self.mode = GUI_MODES[1]
            self.track_mode = args.track_mode
            self.color_name = args.color_name
            self.threshold = int(np.clip(args.threshold, 0, 255))
            self.blur = int(np.clip(args.blur, 1, 31))
            self.min_area = float(args.min_area)
            self.max_area = float(args.max_area)
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
                        "blur",
                        "min_area",
                        "max_area",
                        "color_name",
                    ],
                )
                writer.writeheader()
                writer.writerows(self.analysis_rows)
            print(f"[GUI] Zapisano analizę: {out_file}")

        def _switch_video(self, idx: int):
            if idx == self.current_video_idx:
                return
            self._save_analysis_rows(self.current_video_idx)
            self.analysis_rows = []
            self.cap.release()
            self.cap = self._open_video(idx)
            self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 25.0
            self.current_video_idx = idx
            self.frame_index = 0
            self.speed_accumulator = 0.0
            self.last_frame = None
            self.tracker = SimpleMultiTracker(max_distance=args.max_distance, max_missed=args.max_missed)

        def _make_slider(self, label: str, min_v: float, max_v: float, value: float, step: float, on_change):
            row = BoxLayout(orientation="horizontal", size_hint_y=None, height=44, spacing=8)
            lbl = Label(text=label, size_hint_x=0.36, halign="left", valign="middle")
            lbl.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
            value_lbl = Label(text=str(value), size_hint_x=0.16)
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

        def build(self):
            Window.minimum_width = 1100
            Window.minimum_height = 720

            root = BoxLayout(orientation="vertical", spacing=8, padding=8)
            self.image_widget = Image(allow_stretch=True, keep_ratio=True)
            root.add_widget(self.image_widget)

            controls = BoxLayout(orientation="vertical", spacing=6, size_hint_y=None)
            controls.bind(minimum_height=controls.setter("height"))

            row_top = BoxLayout(orientation="horizontal", size_hint_y=None, height=42, spacing=8)
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

            self.color_spinner = Spinner(text=self.color_name, values=GUI_COLOR_NAMES, size_hint_x=0.15)
            self.color_spinner.bind(text=lambda _, val: setattr(self, "color_name", val))
            row_top.add_widget(self.color_spinner)

            self.speed_spinner = Spinner(text=f"x{self.speed_factor:g}", values=[f"x{x:g}" for x in GUI_SPEED_FACTORS], size_hint_x=0.15)
            self.speed_spinner.bind(text=self._on_speed_change)
            row_top.add_widget(self.speed_spinner)

            controls.add_widget(row_top)

            slider_rows = [
                ("Threshold", 0, 255, self.threshold, 1, lambda v: setattr(self, "threshold", int(v))),
                ("Blur", 1, 31, self.blur, 2, lambda v: setattr(self, "blur", ensure_odd(int(v)))),
                ("Min area", 0, 5000, self.min_area, 1, lambda v: setattr(self, "min_area", float(v))),
                ("Max area", 0, 20000, self.max_area, 1, lambda v: setattr(self, "max_area", float(v))),
                ("Erode", 0, 10, self.erode_iter, 1, lambda v: setattr(self, "erode_iter", int(v))),
                ("Dilate", 0, 10, self.dilate_iter, 1, lambda v: setattr(self, "dilate_iter", int(v))),
                ("Max spots", 1, 20, self.max_spots, 1, lambda v: setattr(self, "max_spots", int(v))),
            ]
            self.slider_refs = {}
            for key, mn, mx, val, step, fn in slider_rows:
                row, slider = self._make_slider(key, mn, mx, val, step, fn)
                controls.add_widget(row)
                self.slider_refs[key] = slider

            toggles = BoxLayout(orientation="horizontal", size_hint_y=None, height=44, spacing=8)
            self.btn_analyze = ToggleButton(text="Analyze: OFF", state="normal")
            self.btn_analyze.bind(state=self._toggle_analyze)
            toggles.add_widget(self.btn_analyze)

            self.btn_pause = ToggleButton(text="Pause: OFF", state="normal")
            self.btn_pause.bind(state=self._toggle_pause)
            toggles.add_widget(self.btn_pause)

            self.btn_auto = ToggleButton(text="Auto params: ON" if self.auto_params else "Auto params: OFF", state="down" if self.auto_params else "normal")
            self.btn_auto.bind(state=self._toggle_auto)
            toggles.add_widget(self.btn_auto)

            self.btn_multi = ToggleButton(text="Multi track: ON" if self.multi_track else "Multi track: OFF", state="down" if self.multi_track else "normal")
            self.btn_multi.bind(state=self._toggle_multi)
            toggles.add_widget(self.btn_multi)

            self.btn_calib = ToggleButton(text="Use calib: ON" if self.use_calib else "Use calib: OFF", state="down" if self.use_calib else "normal")
            self.btn_calib.bind(state=self._toggle_calib)
            toggles.add_widget(self.btn_calib)
            controls.add_widget(toggles)

            row_action = BoxLayout(orientation="horizontal", size_hint_y=None, height=42, spacing=8)
            btn_restart = Button(text="Restart video")
            btn_restart.bind(on_press=lambda *_: self._restart_video())
            row_action.add_widget(btn_restart)

            btn_mp4 = Button(text="Pokaż komendę QA wideo")
            btn_mp4.bind(
                on_press=lambda *_: print(
                    "[GUI] Narzędzie do weryfikacji wideo:",
                    f"python {args.mp4_tool_path} --input twoj_plik.mkv --analyze-only",
                )
            )
            row_action.add_widget(btn_mp4)
            controls.add_widget(row_action)

            self.status_label = Label(text="Ready", size_hint_y=None, height=30, halign="left", valign="middle")
            self.status_label.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
            controls.add_widget(self.status_label)

            scroll = ScrollView(size_hint=(1, None), size=(Window.width, 300), do_scroll_x=False)
            scroll.add_widget(controls)
            root.add_widget(scroll)

            Window.bind(on_key_down=self._on_key_down)
            Clock.schedule_interval(self._update_frame, float(np.clip(_cfg_value(gui_cfg, "wait_ms_running", 16), 1, 200)) / 1000.0)
            return root

        def _on_video_change(self, _, selected_name: str):
            idx = [p.name for p in self.video_files].index(selected_name)
            self._switch_video(idx)

        def _on_speed_change(self, _, selected: str):
            self.speed_factor = float(selected.replace("x", ""))

        def _toggle_analyze(self, _, state: str):
            self.analyze_enabled = state == "down"
            self.btn_analyze.text = f"Analyze: {'ON' if self.analyze_enabled else 'OFF'}"

        def _toggle_pause(self, _, state: str):
            self.paused = state == "down"
            self.btn_pause.text = f"Pause: {'ON' if self.paused else 'OFF'}"

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

        def _restart_video(self):
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            self.frame_index = 0
            self.speed_accumulator = 0.0
            self.last_frame = None
            self.tracker = SimpleMultiTracker(max_distance=args.max_distance, max_missed=args.max_missed)

        def _on_key_down(self, _, key, __, ___, ____):
            if key == 113:
                self.stop()
                return True
            if key == 32:
                self.btn_pause.state = "normal" if self.btn_pause.state == "down" else "down"
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
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            self.threshold = int(np.clip(np.percentile(gray, 99.5), 60, 250))
            self.blur = 9
            self.min_area = max(5.0, frame.shape[0] * frame.shape[1] * 0.00002)
            self.max_area = frame.shape[0] * frame.shape[1] * 0.25
            self.erode_iter = 1
            self.dilate_iter = 2
            self.color_name = choose_auto_color_name(frame, args.roi)
            self.track_mode = "color" if float(np.mean(hsv[..., 1])) >= 40.0 else "brightness"
            self.max_spots = max(1, min(20, int((frame.shape[0] * frame.shape[1]) / 50000)))
            self.mode = "processing"

            self.mode_spinner.text = self.mode
            self.track_spinner.text = self.track_mode
            self.color_spinner.text = self.color_name
            self.slider_refs["Threshold"].value = self.threshold
            self.slider_refs["Blur"].value = self.blur
            self.slider_refs["Min area"].value = _clip_slider(self.min_area, 0, 5000)
            self.slider_refs["Max area"].value = _clip_slider(self.max_area, 0, 20000)
            self.slider_refs["Erode"].value = self.erode_iter
            self.slider_refs["Dilate"].value = self.dilate_iter
            self.slider_refs["Max spots"].value = self.max_spots

        def _update_frame(self, _dt):
            should_advance = self.analyze_enabled and not self.paused
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
                erode_iter=self.erode_iter,
                dilate_iter=self.dilate_iter,
                min_area=float(self.min_area),
                max_area=float(self.max_area),
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
                    erode_iter=self.erode_iter,
                    dilate_iter=self.dilate_iter,
                    min_area=float(self.min_area),
                    max_area=float(self.max_area),
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
                    erode_iter=self.erode_iter,
                    dilate_iter=self.dilate_iter,
                    min_area=float(self.min_area),
                    max_area=float(self.max_area),
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
                    f"Mode: {self.mode} | Track: {self.track_mode}",
                    f"Detections: {len(detections)} | Frame: {self.frame_index}",
                    f"Auto params: {'ON' if self.auto_params else 'OFF'} | Speed: x{self.speed_factor:g}",
                ],
                origin=(10, 10),
                bg_color=(18, 26, 36),
                alpha=0.62,
            )

            if detections and self.analyze_enabled:
                main_det = detections[0]
                self.analysis_rows.append(
                    {
                        "frame_index": self.frame_index,
                        "time_sec": self.frame_index / self.fps,
                        "video_file": self.video_files[self.current_video_idx].name,
                        "mode": self.mode,
                        "track_mode": self.track_mode,
                        "detections": len(detections),
                        "main_x": round(float(main_det.x), 3),
                        "main_y": round(float(main_det.y), 3),
                        "threshold": self.threshold,
                        "blur": self.blur,
                        "min_area": self.min_area,
                        "max_area": self.max_area,
                        "color_name": self.color_name,
                    }
                )

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
            self._save_analysis_rows(self.current_video_idx)

    TrackerGUIApp().run()
