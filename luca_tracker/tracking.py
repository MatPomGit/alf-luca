from __future__ import annotations

import glob
import math
import os
from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from .reports import (
    compute_track_metrics,
    generate_trajectory_png,
    metrics_from_points,
    save_all_tracks_csv,
    save_metrics_csv,
    save_track_csv,
    save_track_report_pdf,
)
from .types import Detection, TrackPoint
from .video_export import export_annotated_video

try:
    from kalman_tracker import smooth_xy_sequence
except Exception:
    smooth_xy_sequence = None


COLOR_PRESETS: Dict[str, List[Tuple[Tuple[int, int, int], Tuple[int, int, int]]]] = {
    "red": [((0, 80, 80), (10, 255, 255)), ((170, 80, 80), (180, 255, 255))],
    "green": [((35, 60, 60), (90, 255, 255))],
    "blue": [((90, 60, 60), (130, 255, 255))],
    "yellow": [((18, 80, 80), (40, 255, 255))],
    "white": [((0, 0, 180), (180, 60, 255))],
    "orange": [((8, 100, 80), (22, 255, 255))],
    "purple": [((130, 60, 60), (165, 255, 255))],
}


def ask_value(prompt: str, cast, default):
    raw = input(f"{prompt} [{default}]: ").strip()
    if raw == "":
        return default
    return cast(raw)


def ask_bool(prompt: str, default: bool) -> bool:
    d = "t" if default else "n"
    raw = input(f"{prompt} [t/n, domyślnie {d}]: ").strip().lower()
    if raw == "":
        return default
    return raw in {"t", "tak", "y", "yes", "1"}


def interactive_track_config(args):
    print("\n=== Interaktywny dobór parametrów śledzenia ===")
    args.track_mode = ask_value("Tryb śledzenia (brightness/color)", str, args.track_mode)
    args.blur = ask_value("Rozmiar rozmycia Gaussa (nieparzysty)", int, args.blur)
    args.threshold = ask_value("Próg jasności 0-255", int, args.threshold)
    args.min_area = ask_value("Minimalne pole plamki", float, args.min_area)
    args.max_area = ask_value("Maksymalne pole plamki (0 = brak limitu)", float, args.max_area)
    args.erode_iter = ask_value("Liczba erozji", int, args.erode_iter)
    args.dilate_iter = ask_value("Liczba dylatacji", int, args.dilate_iter)
    args.multi_track = ask_bool("Śledzić wiele plamek jednocześnie?", args.multi_track)
    args.max_spots = ask_value("Maksymalna liczba plamek na klatkę", int, args.max_spots)
    args.selection_mode = ask_value(
        "Jak wybrać trajektorię główną? (largest/stablest/longest)", str, args.selection_mode
    )
    if args.track_mode == "color":
        args.color_name = ask_value(
            "Kolor (red/green/blue/yellow/white/orange/purple/custom)",
            str,
            args.color_name,
        )
        if args.color_name == "custom":
            args.hsv_lower = ask_value("HSV lower, np. 0,80,80", str, args.hsv_lower or "0,80,80")
            args.hsv_upper = ask_value("HSV upper, np. 10,255,255", str, args.hsv_upper or "10,255,255")
    roi_raw = input(
        f"ROI x,y,w,h lub ENTER dla pełnego kadru [{args.roi if args.roi else 'pełny kadr'}]: "
    ).strip()
    if roi_raw:
        args.roi = roi_raw
    return args


def calibrate_camera(calib_dir: str, rows: int, cols: int, square_size: float, output_file: str):
    objp = np.zeros((rows * cols, 3), np.float32)
    objp[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2)
    objp *= square_size

    objpoints = []
    imgpoints = []

    images = []
    for pattern in ("*.png", "*.jpg", "*.jpeg", "*.bmp"):
        images.extend(glob.glob(os.path.join(calib_dir, pattern)))

    if not images:
        raise FileNotFoundError(f"Brak obrazów kalibracyjnych w katalogu: {calib_dir}")

    gray_shape = None
    for fname in images:
        image = cv2.imread(fname)
        if image is None:
            continue
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        ok, corners = cv2.findChessboardCorners(gray, (cols, rows), None)
        if not ok:
            print(f"[INFO] Pominięto {fname} - nie znaleziono narożników.")
            continue
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
        corners2 = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
        objpoints.append(objp)
        imgpoints.append(corners2)
        gray_shape = gray.shape[::-1]

    if not objpoints:
        raise RuntimeError("Nie udało się znaleźć wzorca na żadnym obrazie.")

    _, camera_matrix, dist_coeffs, _, _ = cv2.calibrateCamera(objpoints, imgpoints, gray_shape, None, None)
    np.savez(output_file, camera_matrix=camera_matrix, dist_coeffs=dist_coeffs)
    print(f"[OK] Zapisano kalibrację do: {output_file}")


def parse_roi(roi_text: Optional[str], frame_shape: Tuple[int, int, int]):
    if not roi_text:
        h, w = frame_shape[:2]
        return 0, 0, w, h
    parts = [int(v) for v in roi_text.split(",")]
    if len(parts) != 4:
        raise ValueError("ROI musi mieć format x,y,w,h")
    x, y, w, h = parts
    H, W = frame_shape[:2]
    x = max(0, min(x, W - 1))
    y = max(0, min(y, H - 1))
    w = max(1, min(w, W - x))
    h = max(1, min(h, H - y))
    return x, y, w, h


def ensure_odd(value: int) -> int:
    return value if value % 2 == 1 else value + 1


def parse_hsv_pair(text: Optional[str], fallback: Tuple[int, int, int]) -> Tuple[int, int, int]:
    if not text:
        return fallback
    parts = [int(v.strip()) for v in text.split(",")]
    if len(parts) != 3:
        raise ValueError("Zakres HSV musi mieć 3 wartości: h,s,v")
    return tuple(parts)  # type: ignore


def build_mask(
    roi_frame: np.ndarray,
    track_mode: str,
    blur: int,
    threshold: int,
    erode_iter: int,
    dilate_iter: int,
    color_name: str,
    hsv_lower: Optional[str],
    hsv_upper: Optional[str],
) -> np.ndarray:
    if track_mode == "brightest":
        track_mode = "brightness"

    blur = ensure_odd(blur)

    if track_mode == "brightness":
        gray = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (blur, blur), 0)
        _, mask = cv2.threshold(blurred, threshold, 255, cv2.THRESH_BINARY)
    elif track_mode == "color":
        hsv = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2HSV)
        if color_name == "custom":
            lower = parse_hsv_pair(hsv_lower, (0, 80, 80))
            upper = parse_hsv_pair(hsv_upper, (10, 255, 255))
            ranges = [(lower, upper)]
        else:
            if color_name not in COLOR_PRESETS:
                raise ValueError(f"Nieznany preset koloru: {color_name}")
            ranges = COLOR_PRESETS[color_name]

        mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
        for low, high in ranges:
            local = cv2.inRange(hsv, np.array(low, dtype=np.uint8), np.array(high, dtype=np.uint8))
            mask = cv2.bitwise_or(mask, local)
        if blur > 1:
            mask = cv2.GaussianBlur(mask, (blur, blur), 0)
            _, mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
    else:
        raise ValueError("track_mode musi mieć wartość brightness albo color")

    if erode_iter > 0:
        mask = cv2.erode(mask, None, iterations=erode_iter)
    if dilate_iter > 0:
        mask = cv2.dilate(mask, None, iterations=dilate_iter)
    return mask


def contour_to_detection(contour, offset_x: int = 0, offset_y: int = 0) -> Optional[Detection]:
    area = float(cv2.contourArea(contour))
    if area <= 0:
        return None
    perimeter = float(cv2.arcLength(contour, True))
    M = cv2.moments(contour)
    if M["m00"] == 0:
        return None

    x = float(M["m10"] / M["m00"]) + offset_x
    y = float(M["m01"] / M["m00"]) + offset_y
    circ = float(4.0 * math.pi * area / (perimeter * perimeter)) if perimeter > 0 else 0.0
    (_, _), radius = cv2.minEnclosingCircle(contour)
    bx, by, bw, bh = cv2.boundingRect(contour)
    ellipse_center: Optional[Tuple[float, float]] = None
    ellipse_axes: Optional[Tuple[float, float]] = None
    ellipse_angle: Optional[float] = None
    if len(contour) >= 5:
        (ecx, ecy), (axis_a, axis_b), angle = cv2.fitEllipse(contour)
        ellipse_center = (float(ecx + offset_x), float(ecy + offset_y))
        ellipse_axes = (float(axis_a), float(axis_b))
        ellipse_angle = float(angle)
    return Detection(
        x=x,
        y=y,
        area=area,
        perimeter=perimeter,
        circularity=circ,
        radius=float(radius),
        bbox_x=bx + offset_x,
        bbox_y=by + offset_y,
        bbox_w=bw,
        bbox_h=bh,
        ellipse_center=ellipse_center,
        ellipse_axes=ellipse_axes,
        ellipse_angle=ellipse_angle,
    )


def detect_spots(
    frame: np.ndarray,
    track_mode: str,
    blur: int,
    threshold: int,
    erode_iter: int,
    dilate_iter: int,
    min_area: float,
    max_area: float,
    max_spots: int,
    color_name: str,
    hsv_lower: Optional[str],
    hsv_upper: Optional[str],
    roi: Optional[str],
) -> Tuple[List[Detection], np.ndarray, Tuple[int, int, int, int]]:
    x0, y0, w, h = parse_roi(roi, frame.shape)
    roi_frame = frame[y0:y0 + h, x0:x0 + w]
    mask = build_mask(
        roi_frame=roi_frame,
        track_mode=track_mode,
        blur=blur,
        threshold=threshold,
        erode_iter=erode_iter,
        dilate_iter=dilate_iter,
        color_name=color_name,
        hsv_lower=hsv_lower,
        hsv_upper=hsv_upper,
    )

    contours, _ = cv2.findContours(mask.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    detections: List[Detection] = []
    for c in contours:
        d = contour_to_detection(c, offset_x=x0, offset_y=y0)
        if d is None:
            continue
        if d.area < min_area:
            continue
        if max_area > 0 and d.area > max_area:
            continue
        detections.append(d)

    detections.sort(key=lambda d: d.area, reverse=True)
    detections = detections[:max_spots]
    for idx, det in enumerate(detections, start=1):
        det.rank = idx

    print("mask:", mask.shape, mask.dtype, "nonzero:", cv2.countNonZero(mask))
    unique_vals = np.unique(mask)
    print("mask unique:", unique_vals[:20], "count:", len(unique_vals))

    return detections, mask, (x0, y0, w, h)


class SimpleMultiTracker:
    def __init__(self, max_distance: float = 40.0, max_missed: int = 10):
        self.max_distance = max_distance
        self.max_missed = max_missed
        self.next_id = 1
        self.tracks: Dict[int, Dict] = {}

    @staticmethod
    def _distance(a: Tuple[float, float], b: Tuple[float, float]) -> float:
        return math.hypot(a[0] - b[0], a[1] - b[1])

    def update(self, detections: List[Detection], frame_index: int, time_sec: float):
        assigned_tracks = set()
        assigned_detections = set()
        pairs = []
        for tid, track in self.tracks.items():
            last_xy = track["last_xy"]
            for j, det in enumerate(detections):
                dist = self._distance(last_xy, (det.x, det.y))
                pairs.append((dist, tid, j))
        pairs.sort(key=lambda x: x[0])

        for dist, tid, j in pairs:
            if dist > self.max_distance:
                continue
            if tid in assigned_tracks or j in assigned_detections:
                continue
            track = self.tracks[tid]
            det = detections[j]
            track["last_xy"] = (det.x, det.y)
            track["missed"] = 0
            track["points"].append(
                TrackPoint(
                    frame_index=frame_index,
                    time_sec=time_sec,
                    detected=True,
                    x=det.x,
                    y=det.y,
                    area=det.area,
                    perimeter=det.perimeter,
                    circularity=det.circularity,
                    radius=det.radius,
                    track_id=tid,
                    rank=det.rank,
                    kalman_predicted=0,
                )
            )
            assigned_tracks.add(tid)
            assigned_detections.add(j)

        for tid, track in list(self.tracks.items()):
            if tid not in assigned_tracks:
                track["missed"] += 1
                track["points"].append(
                    TrackPoint(
                        frame_index=frame_index,
                        time_sec=time_sec,
                        detected=False,
                        x=None,
                        y=None,
                        area=None,
                        perimeter=None,
                        circularity=None,
                        radius=None,
                        track_id=tid,
                        rank=None,
                        kalman_predicted=0,
                    )
                )

        for j, det in enumerate(detections):
            if j in assigned_detections:
                continue
            tid = self.next_id
            self.next_id += 1
            self.tracks[tid] = {
                "last_xy": (det.x, det.y),
                "missed": 0,
                "points": [
                    TrackPoint(
                        frame_index=frame_index,
                        time_sec=time_sec,
                        detected=True,
                        x=det.x,
                        y=det.y,
                        area=det.area,
                        perimeter=det.perimeter,
                        circularity=det.circularity,
                        radius=det.radius,
                        track_id=tid,
                        rank=det.rank,
                        kalman_predicted=0,
                    )
                ],
            }

        finished = {}
        for tid in list(self.tracks.keys()):
            if self.tracks[tid]["missed"] > self.max_missed:
                finished[tid] = self.tracks.pop(tid)
        return finished

    def close_all(self):
        finished = dict(self.tracks)
        self.tracks = {}
        return finished


def choose_main_track(track_histories: Dict[int, Dict], selection_mode: str) -> Optional[int]:
    if not track_histories:
        return None

    scored = []
    for tid, data in track_histories.items():
        metrics = compute_track_metrics(data["points"])
        if selection_mode == "largest":
            key = (-metrics["mean_area"], -metrics["detections"])
        elif selection_mode == "longest":
            key = (-metrics["detections"], metrics["mean_step"])
        elif selection_mode == "stablest":
            key = (metrics["stability_score"], -metrics["detections"])
        else:
            raise ValueError("selection_mode musi mieć wartość largest, longest albo stablest")
        scored.append((key, tid))
    scored.sort(key=lambda item: item[0])
    return scored[0][1] if scored else None


def apply_kalman_to_points(points: Sequence[TrackPoint], process_noise: float, measurement_noise: float):
    if smooth_xy_sequence is None or not points:
        return

    sequence = []
    for p in points:
        if p.x is None or p.y is None:
            sequence.append(None)
        else:
            sequence.append((float(p.x), float(p.y)))

    smoothed = smooth_xy_sequence(
        sequence,
        process_noise=process_noise,
        measurement_noise=measurement_noise,
    )

    for p, result in zip(points, smoothed):
        sx, sy, predicted = result
        if sx is not None and sy is not None:
            p.x = float(sx)
            p.y = float(sy)
        p.kalman_predicted = int(bool(predicted))


def track_video(args):
    if args.interactive:
        interactive_track_config(args)

    camera_matrix = None
    dist_coeffs = None
    if args.calib_file:
        data = np.load(args.calib_file)
        camera_matrix = data.get("camera_matrix")
        dist_coeffs = data.get("dist_coeffs")

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise FileNotFoundError(f"Nie udało się otworzyć pliku video: {args.video}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    fps = fps if fps > 0 else 1.0

    tracker = SimpleMultiTracker(max_distance=args.max_distance, max_missed=args.max_missed)
    finished_tracks: Dict[int, Dict] = {}
    single_points: List[TrackPoint] = []

    frame_index = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break

        if camera_matrix is not None and dist_coeffs is not None:
            frame = cv2.undistort(frame, camera_matrix, dist_coeffs)

        detections, mask, roi_box = detect_spots(
            frame=frame,
            track_mode=args.track_mode,
            blur=args.blur,
            threshold=args.threshold,
            erode_iter=args.erode_iter,
            dilate_iter=args.dilate_iter,
            min_area=args.min_area,
            max_area=args.max_area,
            max_spots=args.max_spots,
            color_name=args.color_name,
            hsv_lower=args.hsv_lower,
            hsv_upper=args.hsv_upper,
            roi=args.roi,
        )

        time_sec = frame_index / fps

        if args.multi_track:
            ended = tracker.update(detections, frame_index, time_sec)
            finished_tracks.update(ended)
        else:
            best = detections[0] if detections else None
            single_points.append(
                TrackPoint(
                    frame_index=frame_index,
                    time_sec=time_sec,
                    detected=best is not None,
                    x=best.x if best else None,
                    y=best.y if best else None,
                    area=best.area if best else None,
                    perimeter=best.perimeter if best else None,
                    circularity=best.circularity if best else None,
                    radius=best.radius if best else None,
                    track_id=1 if best else None,
                    rank=best.rank if best else None,
                    kalman_predicted=0,
                )
            )

        if args.display:
            vis = frame.copy()
            x0, y0, w, h = roi_box
            cv2.rectangle(vis, (x0, y0), (x0 + w, y0 + h), (255, 255, 0), 1)

            for i, d in enumerate(detections, start=1):
                cx, cy = int(round(d.x)), int(round(d.y))
                cv2.circle(vis, (cx, cy), max(3, int(round(d.radius))), (0, 0, 255), 2)
                cv2.putText(vis, f"{i} A={d.area:.0f}", (cx + 5, cy - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)

            cv2.putText(vis, f"Frame: {frame_index}", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)
            cv2.putText(vis, f"Detections: {len(detections)}", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)

            cv2.imshow("Tracking", vis)
            cv2.imshow("Mask", mask)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break

        frame_index += 1

    cap.release()
    cv2.destroyAllWindows()

    if args.multi_track:
        finished_tracks.update(tracker.close_all())
        if not finished_tracks:
            raise RuntimeError("Nie wykryto żadnych trajektorii.")
        main_track_id = choose_main_track(finished_tracks, args.selection_mode)
        if main_track_id is None:
            raise RuntimeError("Nie udało się wybrać głównej trajektorii.")
        main_points = finished_tracks[main_track_id]["points"]

        if args.use_kalman:
            apply_kalman_to_points(
                main_points,
                process_noise=args.kalman_process_noise,
                measurement_noise=args.kalman_measurement_noise,
            )

        save_track_csv(main_points, args.output_csv)
        print(f"[OK] Zapisano główną trajektorię do: {args.output_csv}")
        print(f"[OK] Wybrano track_id={main_track_id} jako trajektorię główną ({args.selection_mode})")

        if args.all_tracks_csv:
            save_all_tracks_csv(finished_tracks, args.all_tracks_csv)
            print(f"[OK] Zapisano wszystkie trajektorie do: {args.all_tracks_csv}")

        metrics = metrics_from_points(main_points)
        extra = [f"selected_track_id: {main_track_id}", f"selection_mode: {args.selection_mode}"]
        if args.trajectory_png:
            generate_trajectory_png(main_points, args.trajectory_png, title=f"Trajektoria główna track_id={main_track_id}")
            print(f"[OK] Zapisano wykres trajektorii: {args.trajectory_png}")
        if args.report_csv:
            save_metrics_csv(metrics, args.report_csv)
            print(f"[OK] Zapisano raport CSV: {args.report_csv}")
        if args.report_pdf:
            save_track_report_pdf(args.report_pdf, metrics, "Raport jakości śledzenia", args.trajectory_png, extra)
            print(f"[OK] Zapisano raport PDF: {args.report_pdf}")

        if args.annotated_video:
            export_annotated_video(
                input_video=args.video,
                output_video=args.annotated_video,
                track_histories=finished_tracks,
                main_track_id=main_track_id,
                draw_all_tracks=args.draw_all_tracks,
                roi=args.roi,
            )
            print(f"[OK] Zapisano wideo wynikowe: {args.annotated_video}")

    else:
        if args.use_kalman:
            apply_kalman_to_points(
                single_points,
                process_noise=args.kalman_process_noise,
                measurement_noise=args.kalman_measurement_noise,
            )

        save_track_csv(single_points, args.output_csv)
        print(f"[OK] Zapisano wyniki do: {args.output_csv}")

        metrics = metrics_from_points(single_points)
        if args.trajectory_png:
            generate_trajectory_png(single_points, args.trajectory_png)
            print(f"[OK] Zapisano wykres trajektorii: {args.trajectory_png}")
        if args.report_csv:
            save_metrics_csv(metrics, args.report_csv)
            print(f"[OK] Zapisano raport CSV: {args.report_csv}")
        if args.report_pdf:
            save_track_report_pdf(args.report_pdf, metrics, "Raport jakości śledzenia", args.trajectory_png)
            print(f"[OK] Zapisano raport PDF: {args.report_pdf}")

        if args.annotated_video:
            pseudo_tracks = {1: {"points": single_points}}
            export_annotated_video(
                input_video=args.video,
                output_video=args.annotated_video,
                track_histories=pseudo_tracks,
                main_track_id=1,
                draw_all_tracks=True,
                roi=args.roi,
            )
            print(f"[OK] Zapisano wideo wynikowe: {args.annotated_video}")
