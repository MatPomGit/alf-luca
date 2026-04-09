from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .types import Detection, TrackPoint


@dataclass
class TrackerConfig:
    """Konfiguracja rdzenia trackera dla pracy modułowej i standalone."""

    max_distance: float = 40.0
    max_missed: int = 10
    selection_mode: str = "stablest"


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
        metrics = _compute_track_metrics_local(data["points"])
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


def _compute_track_metrics_local(points: List[TrackPoint]) -> Dict[str, float]:
    """Liczy minimalny zestaw metryk wymaganych do wyboru głównego toru.

    Funkcja jest lokalna, aby tracker_core nie zależał od modułu raportowego
    wymagającego dodatkowych bibliotek wizualizacyjnych.
    """
    detected_points = [p for p in points if p.detected and p.x is not None and p.y is not None]
    detections = len(detected_points)
    mean_area = float(sum((p.area or 0.0) for p in detected_points) / detections) if detections else 0.0

    steps: List[float] = []
    for prev, curr in zip(detected_points[:-1], detected_points[1:]):
        dx = float(curr.x) - float(prev.x)
        dy = float(curr.y) - float(prev.y)
        steps.append(math.hypot(dx, dy))

    mean_step = float(sum(steps) / len(steps)) if steps else 0.0
    if len(steps) > 1:
        var = sum((s - mean_step) ** 2 for s in steps) / len(steps)
        stability_score = math.sqrt(var)
    else:
        stability_score = 0.0

    return {
        "mean_area": mean_area,
        "detections": float(detections),
        "mean_step": mean_step,
        "stability_score": stability_score,
    }


def run_tracker_with_config(
    frames: List[List[Detection]],
    fps: float,
    config: TrackerConfig,
) -> Dict[str, object]:
    """Uruchamia tracker dla listy detekcji per klatka i zwraca zunifikowany wynik."""
    tracker = SimpleMultiTracker(max_distance=config.max_distance, max_missed=config.max_missed)
    finished_tracks: Dict[int, Dict] = {}

    for frame_index, detections in enumerate(frames):
        ended = tracker.update(detections, frame_index, frame_index / max(fps, 1e-9))
        finished_tracks.update(ended)

    finished_tracks.update(tracker.close_all())
    main_track_id = choose_main_track(finished_tracks, config.selection_mode)

    return {
        "config": asdict(config),
        "finished_tracks": finished_tracks,
        "main_track_id": main_track_id,
    }


def _build_parser() -> argparse.ArgumentParser:
    """Tworzy parser CLI do samodzielnego uruchamiania rdzenia trackera."""
    # print("TRACKER_CORE: Tworzę parser CLI")
    parser = argparse.ArgumentParser(description="Standalone tracker core for detection sequences.")
    parser.add_argument("--input_json", required=True, help="JSON with detection lists per frame.")
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--max_distance", type=float, default=40.0)
    parser.add_argument("--max_missed", type=int, default=10)
    parser.add_argument("--selection_mode", choices=["largest", "stablest", "longest"], default="stablest")
    parser.add_argument("--output_json", help="Optional output path with tracker summary.")
    return parser


def _parse_detection_frame(frame_payload: List[Dict]) -> List[Detection]:
    """Konwertuje surowe dane JSON na listę obiektów Detection."""
    # print("Konwertuje surowe dane JSON na listę obiektów Detection")
    detections: List[Detection] = []
    for raw in frame_payload:
        detections.append(Detection(**raw))
    return detections


def main(argv: Optional[List[str]] = None) -> int:
    """Punkt wejścia standalone: uruchamia tracking na sekwencji detekcji z JSON."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    payload = json.loads(Path(args.input_json).read_text(encoding="utf-8"))
    frames = [_parse_detection_frame(frame) for frame in payload["frames"]]
    config = TrackerConfig(
        max_distance=args.max_distance,
        max_missed=args.max_missed,
        selection_mode=args.selection_mode,
    )
    result = run_tracker_with_config(frames, fps=args.fps, config=config)

    """ poprzednia wersja
    summary = {
        "main_track_id": result["main_track_id"],
        "tracks_count": len(result["finished_tracks"]),
    } """

    summary = {
    "main_track_id": result.get("main_track_id"),
    "tracks_count": len(result.get("finished_tracks", [])),
    }
    if args.output_json:
        Path(args.output_json).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
