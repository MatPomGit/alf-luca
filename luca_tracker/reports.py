from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from .types import TrackPoint


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

    metrics["stability_score"] = float(
        metrics["mean_step"] * 2.0
        + (1.0 - metrics["detection_ratio"]) * 50.0
        + max(0.0, 0.5 - metrics["mean_circularity"]) * 20.0
    )
    return metrics


def save_track_csv(points: Sequence[TrackPoint], csv_path: str):
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "frame_index", "time_sec", "detected", "x", "y", "area",
            "perimeter", "circularity", "radius", "track_id", "rank", "kalman_predicted"
        ])
        for p in points:
            writer.writerow([
                p.frame_index, p.time_sec, int(p.detected), p.x, p.y, p.area,
                p.perimeter, p.circularity, p.radius, p.track_id, p.rank, p.kalman_predicted
            ])


def save_all_tracks_csv(track_histories: Dict[int, Dict], csv_path: str):
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "track_id", "frame_index", "time_sec", "detected", "x", "y", "area",
            "perimeter", "circularity", "radius", "rank", "kalman_predicted"
        ])
        for tid, data in sorted(track_histories.items()):
            for p in data["points"]:
                writer.writerow([
                    tid, p.frame_index, p.time_sec, int(p.detected), p.x, p.y,
                    p.area, p.perimeter, p.circularity, p.radius, p.rank, p.kalman_predicted
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

    return {
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
                    kalman_predicted=int(row.get("kalman_predicted", "0") or 0),
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
