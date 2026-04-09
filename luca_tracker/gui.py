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


def run_gui(args):
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
    selected_video_idx = max(0, min(len(video_files) - 1, int(_cfg_value(gui_cfg, "video_index", 0))))
    current_video_idx = selected_video_idx

    cv2.namedWindow("GUI", cv2.WINDOW_NORMAL)

    def noop(_=None):
        return None

    cv2.createTrackbar("Mode 0:K 1:P 2:C", "GUI", 1, 2, noop)
    cv2.createTrackbar("Track 0:Bright 1:Color", "GUI", 0 if args.track_mode == "brightness" else 1, 1, noop)
    cv2.createTrackbar("Color", "GUI", max(0, GUI_COLOR_NAMES.index(args.color_name)), len(GUI_COLOR_NAMES) - 1, noop)
    cv2.createTrackbar("Threshold", "GUI", int(np.clip(args.threshold, 0, 255)), 255, noop)
    cv2.createTrackbar("Blur", "GUI", int(np.clip(args.blur, 1, 31)), 31, noop)
    cv2.createTrackbar("Min area", "GUI", int(np.clip(args.min_area, 0, 5000)), 5000, noop)
    cv2.createTrackbar("Max area (0=off)", "GUI", int(np.clip(args.max_area, 0, 20000)), 20000, noop)
    cv2.createTrackbar("Erode", "GUI", int(np.clip(args.erode_iter, 0, 10)), 10, noop)
    cv2.createTrackbar("Dilate", "GUI", int(np.clip(args.dilate_iter, 0, 10)), 10, noop)
    cv2.createTrackbar("Multi track", "GUI", 1 if args.multi_track else 0, 1, noop)
    cv2.createTrackbar("Max spots", "GUI", int(np.clip(args.max_spots, 1, 20)), 20, noop)
    cv2.createTrackbar("Selection", "GUI", max(0, GUI_SELECTION_MODES.index(args.selection_mode)), 2, noop)
    cv2.createTrackbar("Use calib", "GUI", 1 if camera_matrix is not None else 0, 1, noop)
    cv2.createTrackbar("Analyze (0=setup,1=run)", "GUI", 0, 1, noop)
    cv2.createTrackbar("Pause", "GUI", 0, 1, noop)
    cv2.createTrackbar("Auto params", "GUI", 1 if bool(_cfg_value(gui_cfg, "auto_params", False)) else 0, 1, noop)
    speed_default = float(_cfg_value(gui_cfg, "speed_factor", 1.0))
    speed_default_idx = GUI_SPEED_FACTORS.index(speed_default) if speed_default in GUI_SPEED_FACTORS else 0
    cv2.createTrackbar("Speed", "GUI", speed_default_idx, len(GUI_SPEED_FACTORS) - 1, noop)
    if len(video_files) > 1:
        cv2.createTrackbar("Video index", "GUI", selected_video_idx, len(video_files) - 1, noop)

    def open_video(index: int):
        capture = cv2.VideoCapture(str(video_files[index]))
        if not capture.isOpened():
            raise FileNotFoundError(f"Nie udało się otworzyć pliku video: {video_files[index]}")
        return capture

    cap = open_video(selected_video_idx)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frame_index = 0
    last_frame: Optional[np.ndarray] = None
    tracker = SimpleMultiTracker(max_distance=args.max_distance, max_missed=args.max_missed)
    analysis_rows: List[Dict[str, object]] = []
    speed_accumulator = 0.0

    def save_analysis_rows(video_idx: int, rows: List[Dict[str, object]]):
        if not rows:
            return
        video_name = video_files[video_idx].stem
        out_file = output_dir / f"{video_name}_gui_analysis.csv"
        with out_file.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "frame_index", "time_sec", "video_file", "mode", "track_mode", "detections",
                    "main_x", "main_y", "threshold", "blur", "min_area", "max_area", "color_name",
                ],
            )
            writer.writeheader()
            writer.writerows(rows)
        print(f"[GUI] Zapisano analizę: {out_file}")

    while True:
        selected_video_idx = cv2.getTrackbarPos("Video index", "GUI") if len(video_files) > 1 else current_video_idx
        if selected_video_idx != current_video_idx:
            save_analysis_rows(current_video_idx, analysis_rows)
            analysis_rows = []
            cap.release()
            cap = open_video(selected_video_idx)
            fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
            current_video_idx = selected_video_idx
            tracker = SimpleMultiTracker(max_distance=args.max_distance, max_missed=args.max_missed)
            frame_index = 0
            last_frame = None
            speed_accumulator = 0.0

        analyze_enabled = cv2.getTrackbarPos("Analyze (0=setup,1=run)", "GUI") == 1
        paused = cv2.getTrackbarPos("Pause", "GUI") == 1
        speed_factor = GUI_SPEED_FACTORS[cv2.getTrackbarPos("Speed", "GUI")]
        should_advance = analyze_enabled and not paused
        if should_advance:
            speed_accumulator += speed_factor
            frames_to_advance = max(1, int(speed_accumulator))
            speed_accumulator -= int(speed_accumulator)
        else:
            frames_to_advance = 1

        if should_advance or last_frame is None:
            ok, frame = False, None
            for _ in range(frames_to_advance):
                ok, frame = cap.read()
                if not ok:
                    break
            if not ok or frame is None:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                tracker = SimpleMultiTracker(max_distance=args.max_distance, max_missed=args.max_missed)
                frame_index = 0
                speed_accumulator = 0.0
                continue
            last_frame = frame
            if analyze_enabled:
                frame_index += frames_to_advance
        frame = last_frame.copy()

        mode = GUI_MODES[cv2.getTrackbarPos("Mode 0:K 1:P 2:C", "GUI")]
        track_mode = "color" if cv2.getTrackbarPos("Track 0:Bright 1:Color", "GUI") == 1 else "brightness"
        color_name = GUI_COLOR_NAMES[cv2.getTrackbarPos("Color", "GUI")]
        threshold = cv2.getTrackbarPos("Threshold", "GUI")
        blur = ensure_odd(max(1, cv2.getTrackbarPos("Blur", "GUI")))
        min_area = float(cv2.getTrackbarPos("Min area", "GUI"))
        max_area = float(cv2.getTrackbarPos("Max area (0=off)", "GUI"))
        erode_iter = cv2.getTrackbarPos("Erode", "GUI")
        dilate_iter = cv2.getTrackbarPos("Dilate", "GUI")
        multi_track = cv2.getTrackbarPos("Multi track", "GUI") == 1
        max_spots = max(1, cv2.getTrackbarPos("Max spots", "GUI"))
        use_calib = cv2.getTrackbarPos("Use calib", "GUI") == 1 and camera_matrix is not None and dist_coeffs is not None
        auto_params = cv2.getTrackbarPos("Auto params", "GUI") == 1

        if auto_params:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            threshold = int(np.clip(np.percentile(gray, 99.5), 60, 250))
            blur = 9
            min_area = max(5.0, frame.shape[0] * frame.shape[1] * 0.00002)
            max_area = frame.shape[0] * frame.shape[1] * 0.25
            erode_iter = 1
            dilate_iter = 2
            color_name = choose_auto_color_name(frame, args.roi)
            track_mode = "color" if float(np.mean(hsv[..., 1])) >= 40.0 else "brightness"
            max_spots = max(1, min(20, int((frame.shape[0] * frame.shape[1]) / 50000)))
            mode = "processing"
            cv2.setTrackbarPos("Mode 0:K 1:P 2:C", "GUI", GUI_MODES.index(mode))
            cv2.setTrackbarPos("Track 0:Bright 1:Color", "GUI", 1 if track_mode == "color" else 0)
            cv2.setTrackbarPos("Color", "GUI", GUI_COLOR_NAMES.index(color_name))
            cv2.setTrackbarPos("Threshold", "GUI", int(np.clip(threshold, 0, 255)))
            cv2.setTrackbarPos("Blur", "GUI", int(np.clip(blur, 1, 31)))
            cv2.setTrackbarPos("Min area", "GUI", int(np.clip(min_area, 0, 5000)))
            cv2.setTrackbarPos("Max area (0=off)", "GUI", int(np.clip(max_area, 0, 20000)))
            cv2.setTrackbarPos("Erode", "GUI", erode_iter)
            cv2.setTrackbarPos("Dilate", "GUI", dilate_iter)
            cv2.setTrackbarPos("Multi track", "GUI", 1)
            cv2.setTrackbarPos("Max spots", "GUI", max_spots)
            cv2.setTrackbarPos("Use calib", "GUI", 1 if use_calib else 0)

        processed = cv2.undistort(frame, camera_matrix, dist_coeffs) if use_calib else frame
        detections, mask, roi_box = detect_spots(
            frame=processed,
            track_mode=track_mode,
            blur=blur,
            threshold=threshold,
            erode_iter=erode_iter,
            dilate_iter=dilate_iter,
            min_area=min_area,
            max_area=max_area,
            max_spots=max_spots,
            color_name=color_name,
            hsv_lower=None,
            hsv_upper=None,
            roi=args.roi,
        )

        mask_bgr = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
        x0, y0, w, h = roi_box
        annotated = _draw_detection_layer(processed, detections, color=(0, 255, 0))
        cv2.rectangle(annotated, (x0, y0), (x0 + w, y0 + h), (255, 255, 0), 1)

        if mode == "calibration":
            preview = _stack_h([frame, processed])
        elif mode == "processing":
            if multi_track and analyze_enabled:
                tracker.update(detections, frame_index, frame_index / fps)
                for tid, data in tracker.tracks.items():
                    hist = data["points"]
                    draw_polyline_history(annotated, hist, color_for_id(tid), max_tail=80)
            preview = _stack_h([annotated, mask_bgr])
        else:
            det_bright, _, _ = detect_spots(frame=processed, track_mode="brightness", blur=blur, threshold=threshold, erode_iter=erode_iter, dilate_iter=dilate_iter, min_area=min_area, max_area=max_area, max_spots=max_spots, color_name=color_name, hsv_lower=None, hsv_upper=None, roi=args.roi)
            det_color, _, _ = detect_spots(frame=processed, track_mode="color", blur=blur, threshold=threshold, erode_iter=erode_iter, dilate_iter=dilate_iter, min_area=min_area, max_area=max_area, max_spots=max_spots, color_name=color_name, hsv_lower=None, hsv_upper=None, roi=args.roi)
            bright_view = _draw_detection_layer(processed, det_bright, label_prefix="B ", color=(255, 80, 80))
            color_view = _draw_detection_layer(processed, det_color, label_prefix="C ", color=(80, 255, 80))
            preview = _stack_h([bright_view, color_view, mask_bgr])

        _draw_hud_panel(preview, [f"Video: {video_files[current_video_idx].name}", f"Mode: {mode} | Track: {track_mode}", f"Detections: {len(detections)} | Frame: {frame_index}", f"Auto params: {'ON' if auto_params else 'OFF'} | Speed: x{speed_factor:g}"], origin=(10, 10), bg_color=(18, 26, 36), alpha=0.62)

        if detections and analyze_enabled:
            main_det = detections[0]
            analysis_rows.append({"frame_index": frame_index, "time_sec": frame_index / fps, "video_file": video_files[current_video_idx].name, "mode": mode, "track_mode": track_mode, "detections": len(detections), "main_x": round(float(main_det.x), 3), "main_y": round(float(main_det.y), 3), "threshold": threshold, "blur": blur, "min_area": min_area, "max_area": max_area, "color_name": color_name})

        cv2.imshow("GUI", preview)
        key = cv2.waitKey(int(np.clip(_cfg_value(gui_cfg, "wait_ms_running", 1), 1, 200))) & 0xFF
        if key == ord("q"):
            break
        if key == ord(" "):
            cv2.setTrackbarPos("Pause", "GUI", 0 if paused else 1)
        if key == ord("m"):
            print("[GUI] Narzędzie do weryfikacji MP4:", f"python {args.mp4_tool_path} --input twoj_plik.mp4 --analyze-only")

    cap.release()
    save_analysis_rows(current_video_idx, analysis_rows)
    cv2.destroyAllWindows()
