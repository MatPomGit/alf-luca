#!/usr/bin/env python3
"""
track_bright_spot_v4.py

Rozszerzona wersja programu do:
- kalibracji kamery,
- śledzenia jasnej plamki lub plamki w wybranym kolorze,
- śledzenia wielu plamek jednocześnie,
- wyboru trajektorii "najstabilniejszej",
- eksportu wyników do CSV,
- porównywania CSV,
- generowania wykresu trajektorii oraz prostych raportów CSV/PDF.

Wymagane biblioteki:
    pip install opencv-python numpy matplotlib

Raport PDF wykorzystuje matplotlib.backends.backend_pdf.PdfPages,
więc nie wymaga dodatkowych pakietów.
"""

from __future__ import annotations

import argparse
import csv
import glob
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages


# ----------------------------
# Pomocnicze struktury danych
# ----------------------------

@dataclass
class Detection:
    x: float
    y: float
    area: float
    perimeter: float
    circularity: float
    radius: float
    bbox_x: int
    bbox_y: int
    bbox_w: int
    bbox_h: int
    rank: int = 0


@dataclass
class TrackPoint:
    frame_index: int
    time_sec: float
    detected: bool
    x: Optional[float]
    y: Optional[float]
    area: Optional[float]
    perimeter: Optional[float]
    circularity: Optional[float]
    radius: Optional[float]
    track_id: Optional[int]
    rank: Optional[int] = None


# ----------------------------
# Parametry i presety kolorów
# ----------------------------

COLOR_PRESETS: Dict[str, List[Tuple[Tuple[int, int, int], Tuple[int, int, int]]]] = {
    "red": [((0, 80, 80), (10, 255, 255)), ((170, 80, 80), (180, 255, 255))],
    "green": [((35, 60, 60), (90, 255, 255))],
    "blue": [((90, 60, 60), (130, 255, 255))],
    "yellow": [((18, 80, 80), (40, 255, 255))],
    "white": [((0, 0, 180), (180, 60, 255))],
    "orange": [((8, 100, 80), (22, 255, 255))],
    "purple": [((130, 60, 60), (165, 255, 255))],
}


# ----------------------------
# Wejście interaktywne
# ----------------------------

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


# ----------------------------
# Kalibracja kamery
# ----------------------------

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


# ----------------------------
# Detekcja plamek
# ----------------------------

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
    return detections, mask, (x0, y0, w, h)


# ----------------------------
# Wieloobiektowe śledzenie
# ----------------------------

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

        # Zachłanne przypisanie najbliższych detekcji do istniejących torów
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
                )
            )
            assigned_tracks.add(tid)
            assigned_detections.add(j)

        # Nieprzypisane tory dostają przerwę
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
                    )
                )

        # Nowe tory dla nieprzypisanych detekcji
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
                    )
                ],
            }

        # Usuwanie zbyt długo zgubionych torów - ale zachowujemy ich historię osobno
        finished = {}
        for tid in list(self.tracks.keys()):
            if self.tracks[tid]["missed"] > self.max_missed:
                finished[tid] = self.tracks.pop(tid)
        return finished

    def close_all(self):
        finished = dict(self.tracks)
        self.tracks = {}
        return finished


def compute_track_metrics(points: Sequence[TrackPoint]) -> Dict[str, float]:
    detected = [p for p in points if p.detected and p.x is not None and p.y is not None]
    metrics: Dict[str, float] = {
        "length_frames": float(len(points)),
        "detections": float(len(detected)),
        "detection_ratio": float(len(detected) / len(points)) if points else 0.0,
        "path_length": 0.0,
        "mean_step": 0.0,
        "max_step": 0.0,
        "mean_area": 0.0,
        "mean_circularity": 0.0,
        "stability_score": float("inf"),
    }
    if not detected:
        return metrics

    steps = []
    for a, b in zip(detected[:-1], detected[1:]):
        step = math.hypot((b.x or 0) - (a.x or 0), (b.y or 0) - (a.y or 0))
        steps.append(step)
    if steps:
        metrics["path_length"] = float(sum(steps))
        metrics["mean_step"] = float(sum(steps) / len(steps))
        metrics["max_step"] = float(max(steps))
    areas = [p.area for p in detected if p.area is not None]
    circs = [p.circularity for p in detected if p.circularity is not None]
    if areas:
        metrics["mean_area"] = float(sum(areas) / len(areas))
    if circs:
        metrics["mean_circularity"] = float(sum(circs) / len(circs))

    # niższy score = stabilniejszy tor
    metrics["stability_score"] = float(
        metrics["mean_step"] * 2.0
        + (1.0 - metrics["detection_ratio"]) * 50.0
        + max(0.0, 0.5 - metrics["mean_circularity"]) * 20.0
    )
    return metrics


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


# ----------------------------
# Eksport CSV i raporty
# ----------------------------

def save_track_csv(points: Sequence[TrackPoint], csv_path: str):
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "frame_index", "time_sec", "detected", "x", "y", "area",
            "perimeter", "circularity", "radius", "track_id", "rank"
        ])
        for p in points:
            writer.writerow([
                p.frame_index, p.time_sec, int(p.detected), p.x, p.y, p.area,
                p.perimeter, p.circularity, p.radius, p.track_id, p.rank
            ])


def save_all_tracks_csv(track_histories: Dict[int, Dict], csv_path: str):
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "track_id", "frame_index", "time_sec", "detected", "x", "y", "area",
            "perimeter", "circularity", "radius", "rank"
        ])
        for tid, data in sorted(track_histories.items()):
            for p in data["points"]:
                writer.writerow([
                    tid, p.frame_index, p.time_sec, int(p.detected), p.x, p.y,
                    p.area, p.perimeter, p.circularity, p.radius, p.rank
                ])


def generate_trajectory_png(points: Sequence[TrackPoint], png_path: str, title: str = "Trajektoria plamki"):
    xs = [p.x for p in points if p.detected and p.x is not None]
    ys = [p.y for p in points if p.detected and p.y is not None]

    plt.figure(figsize=(8, 6))
    if xs and ys:
        plt.plot(xs, ys, marker="o", markersize=2)
        plt.gca().invert_yaxis()
    plt.title(title)
    plt.xlabel("x [px]")
    plt.ylabel("y [px]")
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(png_path, dpi=150)
    plt.close()


def metrics_from_points(points: Sequence[TrackPoint]) -> Dict[str, float]:
    metrics = compute_track_metrics(points)
    # przerwy
    misses = 0
    gap_lengths = []
    current_gap = 0
    for p in points:
        if not p.detected:
            misses += 1
            current_gap += 1
        else:
            if current_gap > 0:
                gap_lengths.append(current_gap)
                current_gap = 0
    if current_gap > 0:
        gap_lengths.append(current_gap)

    detected = [p for p in points if p.detected]
    radii = [p.radius for p in detected if p.radius is not None]
    areas = [p.area for p in detected if p.area is not None]
    circs = [p.circularity for p in detected if p.circularity is not None]

    out = {
        "frames_total": float(len(points)),
        "detections_total": float(len(detected)),
        "detection_ratio": metrics["detection_ratio"],
        "missed_frames": float(misses),
        "gap_count": float(len(gap_lengths)),
        "max_gap": float(max(gap_lengths) if gap_lengths else 0),
        "path_length": metrics["path_length"],
        "mean_step": metrics["mean_step"],
        "max_step": metrics["max_step"],
        "mean_area": float(sum(areas) / len(areas)) if areas else 0.0,
        "max_area": float(max(areas)) if areas else 0.0,
        "mean_radius": float(sum(radii) / len(radii)) if radii else 0.0,
        "max_radius": float(max(radii)) if radii else 0.0,
        "mean_circularity": float(sum(circs) / len(circs)) if circs else 0.0,
    }
    return out


def save_metrics_csv(metrics: Dict[str, float], csv_path: str):
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["metric", "value"])
        for k, v in metrics.items():
            writer.writerow([k, v])


def save_track_report_pdf(
    pdf_path: str,
    metrics: Dict[str, float],
    title: str,
    trajectory_png: Optional[str] = None,
    extra_lines: Optional[List[str]] = None,
):
    with PdfPages(pdf_path) as pdf:
        fig = plt.figure(figsize=(8.27, 11.69))
        fig.clf()
        ax = fig.add_axes([0.08, 0.05, 0.84, 0.9])
        ax.axis("off")

        lines = [title, "", "Metryki jakości śledzenia:", ""]
        for k, v in metrics.items():
            lines.append(f"{k}: {v:.6f}")
        if extra_lines:
            lines.extend(["", *extra_lines])

        ax.text(0.0, 1.0, "\n".join(lines), va="top", ha="left", fontsize=10, family="monospace")
        pdf.savefig(fig)
        plt.close(fig)

        if trajectory_png and Path(trajectory_png).exists():
            img = plt.imread(trajectory_png)
            fig = plt.figure(figsize=(8.27, 11.69))
            ax = fig.add_subplot(111)
            ax.imshow(img)
            ax.axis("off")
            ax.set_title("Trajektoria")
            pdf.savefig(fig)
            plt.close(fig)


# ----------------------------
# Porównywanie CSV
# ----------------------------

def load_tracking_csv(csv_path: str) -> List[TrackPoint]:
    points = []
    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            points.append(
                TrackPoint(
                    frame_index=int(row["frame_index"]),
                    time_sec=float(row["time_sec"]),
                    detected=bool(int(row["detected"])),
                    x=float(row["x"]) if row["x"] not in {"", "None"} else None,
                    y=float(row["y"]) if row["y"] not in {"", "None"} else None,
                    area=float(row["area"]) if row["area"] not in {"", "None"} else None,
                    perimeter=float(row["perimeter"]) if row["perimeter"] not in {"", "None"} else None,
                    circularity=float(row["circularity"]) if row["circularity"] not in {"", "None"} else None,
                    radius=float(row["radius"]) if row["radius"] not in {"", "None"} else None,
                    track_id=int(row["track_id"]) if row["track_id"] not in {"", "None"} else None,
                    rank=int(row["rank"]) if row.get("rank", "") not in {"", "None"} else None,
                )
            )
    return points


def compare_csv(reference_csv: str, candidate_csv: str, output_csv: str, report_pdf: Optional[str] = None):
    ref = load_tracking_csv(reference_csv)
    cand = load_tracking_csv(candidate_csv)

    ref_map = {p.frame_index: p for p in ref}
    cand_map = {p.frame_index: p for p in cand}
    frames = sorted(set(ref_map.keys()) | set(cand_map.keys()))

    rows = []
    distance_values = []
    detection_match = 0

    for fi in frames:
        r = ref_map.get(fi)
        c = cand_map.get(fi)

        ref_detected = int(r.detected) if r else 0
        cand_detected = int(c.detected) if c else 0
        same_detection = int(ref_detected == cand_detected)
        detection_match += same_detection

        dx = dy = dist = None
        if r and c and r.detected and c.detected and r.x is not None and c.x is not None and r.y is not None and c.y is not None:
            dx = c.x - r.x
            dy = c.y - r.y
            dist = math.hypot(dx, dy)
            distance_values.append(dist)

        rows.append([fi, ref_detected, cand_detected, same_detection, dx, dy, dist])

    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["frame_index", "ref_detected", "cand_detected", "same_detection", "dx", "dy", "distance"])
        writer.writerows(rows)

    summary = {
        "frames_compared": float(len(frames)),
        "detection_match_ratio": float(detection_match / len(frames)) if frames else 0.0,
        "mean_distance": float(sum(distance_values) / len(distance_values)) if distance_values else 0.0,
        "max_distance": float(max(distance_values)) if distance_values else 0.0,
        "paired_detections": float(len(distance_values)),
    }

    print(f"[OK] Zapisano porównanie do: {output_csv}")
    if report_pdf:
        save_track_report_pdf(report_pdf, summary, "Raport porównania CSV")
        print(f"[OK] Zapisano raport PDF: {report_pdf}")




def color_for_id(track_id: int) -> Tuple[int, int, int]:
    palette = [
        (255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0),
        (255, 0, 255), (0, 255, 255), (0, 165, 255), (180, 105, 255),
        (128, 255, 0), (255, 128, 0), (128, 0, 255), (0, 128, 255),
    ]
    return palette[(track_id - 1) % len(palette)]


def draw_polyline_history(frame: np.ndarray, points: Sequence[TrackPoint], color: Tuple[int, int, int], max_tail: int = 80):
    hist = [(int(round(p.x)), int(round(p.y))) for p in points if p.detected and p.x is not None and p.y is not None]
    hist = hist[-max_tail:]
    if len(hist) >= 2:
        pts = np.array(hist, dtype=np.int32).reshape((-1, 1, 2))
        cv2.polylines(frame, [pts], False, color, 2, cv2.LINE_AA)


def build_track_history_lookup(track_histories: Dict[int, Dict]) -> Dict[int, Dict[int, List[TrackPoint]]]:
    lookup: Dict[int, Dict[int, List[TrackPoint]]] = {}
    for tid, data in track_histories.items():
        frame_map: Dict[int, List[TrackPoint]] = {}
        running: List[TrackPoint] = []
        for p in data["points"]:
            running.append(p)
            frame_map[p.frame_index] = list(running)
        lookup[tid] = frame_map
    return lookup


def export_annotated_video(
    input_video: str,
    output_video: str,
    track_histories: Dict[int, Dict],
    main_track_id: Optional[int] = None,
    draw_all_tracks: bool = True,
    roi: Optional[str] = None,
):
    cap = cv2.VideoCapture(input_video)
    if not cap.isOpened():
        raise FileNotFoundError(f"Nie udało się otworzyć pliku video do eksportu: {input_video}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(output_video, fourcc, fps, (width, height))
    if not writer.isOpened():
        cap.release()
        raise RuntimeError(f"Nie udało się otworzyć pliku wyjściowego video: {output_video}")

    point_by_frame: Dict[int, List[TrackPoint]] = {}
    for tid, data in track_histories.items():
        for p in data["points"]:
            point_by_frame.setdefault(p.frame_index, []).append(p)

    history_lookup = build_track_history_lookup(track_histories)

    frame_index = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break

        if roi:
            try:
                x0, y0, w, h = parse_roi(roi, frame.shape)
                cv2.rectangle(frame, (x0, y0), (x0 + w, y0 + h), (255, 255, 0), 1)
            except Exception:
                pass

        current_points = point_by_frame.get(frame_index, [])
        for p in current_points:
            if p.track_id is None or not p.detected or p.x is None or p.y is None:
                continue
            if not draw_all_tracks and p.track_id != main_track_id:
                continue

            color = color_for_id(p.track_id)
            if p.track_id == main_track_id:
                color = (0, 255, 255)

            hist = history_lookup.get(p.track_id, {}).get(frame_index, [])
            draw_polyline_history(frame, hist, color, max_tail=120)

            cx, cy = int(round(p.x)), int(round(p.y))
            rr = max(4, int(round(p.radius or 4)))
            cv2.circle(frame, (cx, cy), rr, color, 2, cv2.LINE_AA)

            label = f"ID={p.track_id}"
            if p.rank is not None:
                label += f" R={p.rank}"
            if p.track_id == main_track_id:
                label += " MAIN"
            cv2.putText(frame, label, (cx + 6, cy - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 2, cv2.LINE_AA)

        cv2.putText(frame, f"Frame: {frame_index}", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
        writer.write(frame)
        frame_index += 1

    writer.release()
    cap.release()
# ----------------------------
# Główne śledzenie
# ----------------------------

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


# ----------------------------
# CLI
# ----------------------------

def build_parser():
    parser = argparse.ArgumentParser(
        description="Śledzenie jasnej lub kolorowej plamki światła w video MP4."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_cal = subparsers.add_parser("calibrate", help="Kalibracja kamery")
    p_cal.add_argument("--calib_dir", required=True, help="Katalog ze zdjęciami szachownicy")
    p_cal.add_argument("--rows", type=int, default=6, help="Liczba wewnętrznych narożników w wierszu")
    p_cal.add_argument("--cols", type=int, default=9, help="Liczba wewnętrznych narożników w kolumnie")
    p_cal.add_argument("--square_size", type=float, default=1.0, help="Rozmiar pola szachownicy")
    p_cal.add_argument("--output_file", default="camera_calib.npz", help="Plik wynikowy .npz")

    p_track = subparsers.add_parser("track", help="Śledzenie plamki")
    p_track.add_argument("--video", required=True, help="Plik wejściowy MP4")
    p_track.add_argument("--calib_file", help="Plik kalibracji .npz")
    p_track.add_argument("--track_mode", choices=["brightness", "color"], default="brightness")
    p_track.add_argument("--threshold", type=int, default=200, help="Próg jasności")
    p_track.add_argument("--blur", type=int, default=11, help="Rozmiar filtra Gaussa")
    p_track.add_argument("--min_area", type=float, default=10.0, help="Minimalne pole plamki")
    p_track.add_argument("--max_area", type=float, default=0.0, help="Maksymalne pole plamki, 0 = brak")
    p_track.add_argument("--erode_iter", type=int, default=2, help="Liczba iteracji erozji")
    p_track.add_argument("--dilate_iter", type=int, default=4, help="Liczba iteracji dylatacji")
    p_track.add_argument("--roi", help="Obszar ROI w formacie x,y,w,h")
    p_track.add_argument("--interactive", action="store_true", help="Interaktywny dobór parametrów")
    p_track.add_argument("--display", action="store_true", help="Podgląd śledzenia")
    p_track.add_argument("--output_csv", default="tracking_results.csv", help="CSV głównej trajektorii")
    p_track.add_argument("--trajectory_png", help="PNG z wykresem trajektorii")
    p_track.add_argument("--report_csv", help="CSV z raportem jakości")
    p_track.add_argument("--report_pdf", help="PDF z raportem jakości")

    p_track.add_argument("--color_name", default="red", help="Preset koloru lub custom")
    p_track.add_argument("--hsv_lower", help="Dolna granica HSV np. 0,80,80")
    p_track.add_argument("--hsv_upper", help="Górna granica HSV np. 10,255,255")

    p_track.add_argument("--multi_track", action="store_true", help="Śledzenie wielu plamek jednocześnie")
    p_track.add_argument("--max_spots", type=int, default=10, help="Maksymalna liczba plamek na klatkę")
    p_track.add_argument("--max_distance", type=float, default=40.0, help="Maksymalny dystans przypisania między klatkami")
    p_track.add_argument("--max_missed", type=int, default=10, help="Maksymalna liczba zgubionych klatek dla toru")
    p_track.add_argument("--selection_mode", choices=["largest", "stablest", "longest"], default="stablest")
    p_track.add_argument("--all_tracks_csv", help="CSV ze wszystkimi trajektoriami")
    p_track.add_argument("--annotated_video", help="Wyjściowy MP4 z narysowanymi trajektoriami")
    p_track.add_argument("--draw_all_tracks", action="store_true", help="Na filmie wynikowym rysuj wszystkie trajektorie")

    p_cmp = subparsers.add_parser("compare", help="Porównanie dwóch CSV")
    p_cmp.add_argument("--reference", required=True, help="Referencyjny CSV")
    p_cmp.add_argument("--candidate", required=True, help="Porównywany CSV")
    p_cmp.add_argument("--output_csv", required=True, help="Wyjściowy CSV różnic")
    p_cmp.add_argument("--report_pdf", help="Opcjonalny raport PDF")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "calibrate":
        calibrate_camera(args.calib_dir, args.rows, args.cols, args.square_size, args.output_file)
    elif args.command == "track":
        track_video(args)
    elif args.command == "compare":
        compare_csv(args.reference, args.candidate, args.output_csv, args.report_pdf)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
