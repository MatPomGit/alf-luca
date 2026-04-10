from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from luca_types import TrackPoint


def parse_roi(roi_text: Optional[str], frame_shape: Tuple[int, int, int]) -> Tuple[int, int, int, int]:
    """Parse ROI string in x,y,w,h format and clamp values to frame bounds."""
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
    for _, data in track_histories.items():
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
            if p.kalman_predicted:
                label += " K"
            if p.track_id == main_track_id:
                label += " MAIN"
            cv2.putText(frame, label, (cx + 6, cy - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 2, cv2.LINE_AA)

        cv2.putText(frame, f"Frame: {frame_index}", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
        writer.write(frame)
        frame_index += 1

    writer.release()
    cap.release()
