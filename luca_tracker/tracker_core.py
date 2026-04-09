from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from .reports import compute_track_metrics
from .types import Detection, TrackPoint


class SimpleMultiTracker:
    """Prosty tracker wieloobiektowy oparty o najbliższego sąsiada."""

    def __init__(self, max_distance: float = 40.0, max_missed: int = 10):
        # Parametry sterują zasięgiem dopasowania i żywotnością torów.
        self.max_distance = max_distance
        self.max_missed = max_missed
        self.next_id = 1
        self.tracks: Dict[int, Dict] = {}

    @staticmethod
    def _distance(a: Tuple[float, float], b: Tuple[float, float]) -> float:
        """Liczy euklidesowy dystans między punktami 2D."""
        return math.hypot(a[0] - b[0], a[1] - b[1])

    def update(self, detections: List[Detection], frame_index: int, time_sec: float):
        """Aktualizuje zestaw torów i zwraca tory zakończone w tej iteracji."""
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
        """Wymusza zamknięcie wszystkich aktywnych torów."""
        finished = dict(self.tracks)
        self.tracks = {}
        return finished


def choose_main_track(track_histories: Dict[int, Dict], selection_mode: str) -> Optional[int]:
    """Wybiera główny tor według strategii jakościowej."""
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
