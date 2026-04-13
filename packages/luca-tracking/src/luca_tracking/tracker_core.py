from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from luca_types import Detection, TrackPoint


@dataclass
class TrackerConfig:
    """Konfiguracja rdzenia trackera dla pracy modułowej i standalone."""

    max_distance: float = 40.0
    max_missed: int = 10
    selection_mode: str = "stablest"
    distance_weight: float = 1.0
    area_weight: float = 0.35
    circularity_weight: float = 0.2
    brightness_weight: float = 0.0
    min_match_score: float = 0.5
    speed_gate_gain: float = 1.5
    error_gate_gain: float = 1.0
    min_dynamic_distance: float = 12.0
    max_dynamic_distance: float = 150.0
    min_track_start_confidence: float = 0.35
    temporal_smoothing_alpha: float = 0.35
    jitter_guard_px: float = 1.5


class SimpleMultiTracker:
    """Prosty tracker wieloobiektowy oparty o najbliższego sąsiada."""

    def __init__(
        self,
        max_distance: float = 40.0,
        max_missed: int = 10,
        distance_weight: float = 1.0,
        area_weight: float = 0.35,
        circularity_weight: float = 0.2,
        brightness_weight: float = 0.0,
        min_match_score: float = 0.5,
        speed_gate_gain: float = 1.5,
        error_gate_gain: float = 1.0,
        min_dynamic_distance: float = 12.0,
        max_dynamic_distance: float = 150.0,
        min_track_start_confidence: float = 0.35,
        temporal_smoothing_alpha: float = 0.35,
        jitter_guard_px: float = 1.5,
    ):
        # Parametry sterują zasięgiem dopasowania i żywotnością torów.
        self.max_distance = max_distance
        self.max_missed = max_missed
        self.distance_weight = max(0.0, float(distance_weight))
        self.area_weight = max(0.0, float(area_weight))
        self.circularity_weight = max(0.0, float(circularity_weight))
        self.brightness_weight = max(0.0, float(brightness_weight))
        # Trzymamy minimalny score akceptacji w zakresie [0, 1].
        self.min_match_score = max(0.0, min(1.0, float(min_match_score)))
        self.speed_gate_gain = max(0.0, float(speed_gate_gain))
        self.error_gate_gain = max(0.0, float(error_gate_gain))
        self.min_dynamic_distance = max(1.0, float(min_dynamic_distance))
        self.max_dynamic_distance = max(self.min_dynamic_distance, float(max_dynamic_distance))
        # Minimalne confidence detekcji wymagane do rozpoczęcia nowego toru.
        # Dzięki temu jednorazowe artefakty nie "rozmnażają" torów (mniej false positives).
        self.min_track_start_confidence = max(0.0, min(1.0, float(min_track_start_confidence)))
        # Współczynnik wygładzania EMA dla pozycji toru.
        self.temporal_smoothing_alpha = max(0.0, min(1.0, float(temporal_smoothing_alpha)))
        # Drobne skoki poniżej progu traktujemy jako jitter i tłumimy wygładzaniem.
        self.jitter_guard_px = max(0.0, float(jitter_guard_px))
        self.next_id = 1
        self.tracks: Dict[int, Dict] = {}

    @staticmethod
    def _safe_rel_diff(a: Optional[float], b: Optional[float]) -> float:
        """Liczy względną różnicę dwóch wartości z ochroną przed zerem/brakiem danych."""
        if a is None or b is None:
            return 0.0
        denom = max(abs(a), abs(b), 1e-6)
        return abs(float(a) - float(b)) / denom

    def _compute_dynamic_gate(self, track: Dict) -> float:
        """Wyznacza bramkę dystansu zależną od ruchu toru i jakości ostatnich dopasowań."""
        speed = float(track.get("speed", 0.0))
        errors = track.get("match_errors")
        avg_error = float(sum(errors) / len(errors)) if errors else 0.0
        gate = self.max_distance + self.speed_gate_gain * speed + self.error_gate_gain * avg_error
        return max(self.min_dynamic_distance, min(self.max_dynamic_distance, gate))

    def _compute_match_cost(self, track: Dict, det: Detection, dist: float, gate: float) -> float:
        """Składa końcowy koszt dopasowania track-detection z wielu cech opisowych."""
        # Składowa dystansu jest normalizowana przez dynamiczną bramkę toru.
        dist_norm = dist / max(gate, 1e-6)
        area_diff = self._safe_rel_diff(track.get("last_area"), det.area)
        circ_diff = self._safe_rel_diff(track.get("last_circularity"), det.circularity)
        brightness_diff = self._safe_rel_diff(track.get("last_brightness"), det.mean_brightness)
        return (
            self.distance_weight * dist_norm
            + self.area_weight * area_diff
            + self.circularity_weight * circ_diff
            + self.brightness_weight * brightness_diff
        )

    @staticmethod
    def _cost_to_acceptance(cost: float) -> float:
        """Mapuje koszt na score akceptacji [0,1], gdzie 1 oznacza idealną zgodność."""
        return 1.0 / (1.0 + max(0.0, float(cost)))

    @staticmethod
    def _distance(a: Tuple[float, float], b: Tuple[float, float]) -> float:
        """Liczy euklidesowy dystans między punktami 2D."""
        return math.hypot(a[0] - b[0], a[1] - b[1])

    def _stabilize_measurement(
        self,
        prev_xy: Tuple[float, float],
        measured_xy: Tuple[float, float],
        confidence: Optional[float],
    ) -> Tuple[float, float]:
        """Stabilizuje pozycję pomiaru, ograniczając mikro-jitter klatka-do-klatki."""
        # Dla większych ruchów zostawiamy surowy pomiar, żeby nie spłaszczać dynamiki toru.
        if self._distance(prev_xy, measured_xy) > self.jitter_guard_px:
            return measured_xy
        # Confidence wpływa na wagę nowego pomiaru: słabszy pomiar = mocniejsze wygładzenie.
        confidence_gain = max(0.2, min(1.0, float(confidence if confidence is not None else 0.5)))
        alpha = self.temporal_smoothing_alpha * confidence_gain
        return (
            (1.0 - alpha) * prev_xy[0] + alpha * measured_xy[0],
            (1.0 - alpha) * prev_xy[1] + alpha * measured_xy[1],
        )

    def update(self, detections: List[Detection], frame_index: int, time_sec: float):
        """Aktualizuje zestaw torów i zwraca tory zakończone w tej iteracji."""
        assigned_tracks = set()
        assigned_detections = set()
        pairs = []
        for tid, track in self.tracks.items():
            last_xy = track["last_xy"]
            dynamic_gate = self._compute_dynamic_gate(track)
            for j, det in enumerate(detections):
                dist = self._distance(last_xy, (det.x, det.y))
                cost = self._compute_match_cost(track, det, dist, dynamic_gate)
                acceptance = self._cost_to_acceptance(cost)
                pairs.append((cost, acceptance, dist, dynamic_gate, tid, j))
        pairs.sort(key=lambda x: x[0])

        for cost, acceptance, dist, dynamic_gate, tid, j in pairs:
            # Odrzucamy pary poza bramką lub z wynikiem poniżej jakości akceptowalnej.
            if dist > dynamic_gate or acceptance < self.min_match_score:
                continue
            if tid in assigned_tracks or j in assigned_detections:
                continue
            track = self.tracks[tid]
            det = detections[j]
            prev_xy = track["last_xy"]
            stabilized_xy = self._stabilize_measurement(prev_xy, (det.x, det.y), det.confidence)
            track["speed"] = self._distance(prev_xy, stabilized_xy)
            # Do historii błędów odkładamy koszt parowania, aby dynamiczna bramka reagowała na jakość asocjacji.
            track["match_errors"].append(float(cost))
            track["last_xy"] = stabilized_xy
            track["last_area"] = float(det.area)
            track["last_circularity"] = float(det.circularity)
            track["last_brightness"] = det.mean_brightness
            track["missed"] = 0
            track["points"].append(
                TrackPoint(
                    frame_index=frame_index,
                    time_sec=time_sec,
                    detected=True,
                    x=stabilized_xy[0],
                    y=stabilized_xy[1],
                    area=det.area,
                    perimeter=det.perimeter,
                    circularity=det.circularity,
                    radius=det.radius,
                    confidence=det.confidence,
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
                # Przy braku pomiaru stopniowo wygaszamy prędkość, aby nie pompować bramki bez końca.
                track["speed"] = float(track.get("speed", 0.0)) * 0.8
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
                        confidence=None,
                        track_id=tid,
                        rank=None,
                        kalman_predicted=0,
                    )
                )

        for j, det in enumerate(detections):
            if j in assigned_detections:
                continue
            if float(det.confidence or 0.0) < self.min_track_start_confidence:
                continue
            tid = self.next_id
            self.next_id += 1
            self.tracks[tid] = {
                "last_xy": (det.x, det.y),
                "last_area": float(det.area),
                "last_circularity": float(det.circularity),
                "last_brightness": det.mean_brightness,
                "speed": 0.0,
                "match_errors": deque(maxlen=12),
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
                        confidence=det.confidence,
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


class SingleObjectEKFTracker:
    """Tracker pojedynczego obiektu oparty o rozszerzony filtr Kalmana.

    Model stanu: [x, y, vx, vy].
    Model pomiaru: [x, y].
    Dla tego przypadku model jest liniowy, ale interfejs i kroki aktualizacji
    pozostają zgodne z praktyką EKF (predykcja + linearyzacja Jacobianu).
    """

    def __init__(
        self,
        dt: float = 1.0,
        process_noise: float = 1e-2,
        measurement_noise: float = 5.0,
        gating_distance: float = 60.0,
        max_prediction_frames: int = 45,
    ) -> None:
        self.dt = float(max(dt, 1e-6))
        self.gating_distance = float(max(1.0, gating_distance))
        self.max_prediction_frames = int(max(1, max_prediction_frames))
        self.process_noise = float(max(1e-8, process_noise))
        self.measurement_noise = float(max(1e-8, measurement_noise))
        self.state = np.zeros((4, 1), dtype=np.float64)
        self.P = np.eye(4, dtype=np.float64) * 100.0
        self.missed_frames = 0
        self.initialized = False

    def _transition(self) -> np.ndarray:
        """Zwraca macierz przejścia modelu stałej prędkości."""
        return np.array(
            [
                [1.0, 0.0, self.dt, 0.0],
                [0.0, 1.0, 0.0, self.dt],
                [0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0, 1.0],
            ],
            dtype=np.float64,
        )

    def _process_covariance(self) -> np.ndarray:
        """Buduje kowariancję procesu dla modelu stałej prędkości."""
        dt2 = self.dt * self.dt
        dt3 = dt2 * self.dt
        dt4 = dt2 * dt2
        q = self.process_noise
        return q * np.array(
            [
                [dt4 / 4.0, 0.0, dt3 / 2.0, 0.0],
                [0.0, dt4 / 4.0, 0.0, dt3 / 2.0],
                [dt3 / 2.0, 0.0, dt2, 0.0],
                [0.0, dt3 / 2.0, 0.0, dt2],
            ],
            dtype=np.float64,
        )

    @staticmethod
    def _measurement_jacobian() -> np.ndarray:
        """Jacobian modelu pomiaru h(x)=[x,y] dla kroku EKF."""
        return np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]], dtype=np.float64)

    def _predict_only(self) -> Tuple[float, float]:
        """Wykonuje sam krok predykcji i zwraca przewidywane XY."""
        F = self._transition()
        Q = self._process_covariance()
        self.state = F @ self.state
        self.P = F @ self.P @ F.T + Q
        return float(self.state[0, 0]), float(self.state[1, 0])

    def _pick_measurement(self, detections: List[Detection], pred_xy: Tuple[float, float]) -> Optional[Detection]:
        """Wybiera detekcję najbliższą predykcji, o ile mieści się w bramce dystansu."""
        if not detections:
            return None
        px, py = pred_xy
        nearest: Optional[Detection] = None
        nearest_dist = float("inf")
        for det in detections:
            dist = math.hypot(float(det.x) - px, float(det.y) - py)
            if dist < nearest_dist:
                nearest = det
                nearest_dist = dist
        if nearest is None or nearest_dist > self.gating_distance:
            return None
        return nearest

    def update(self, detections: List[Detection]) -> Dict[str, Optional[float]]:
        """Aktualizuje tracker i zwraca aktualną pozycję niezależnie od obecności pomiaru."""
        if not self.initialized:
            if not detections:
                return {"x": None, "y": None, "predicted_only": True, "matched": False}
            # Inicjalizacja od największej plamki daje bardziej stabilny start toru.
            seed = max(detections, key=lambda item: float(item.area))
            self.state = np.array([[float(seed.x)], [float(seed.y)], [0.0], [0.0]], dtype=np.float64)
            self.P = np.eye(4, dtype=np.float64) * 25.0
            self.initialized = True
            self.missed_frames = 0
            return {"x": float(seed.x), "y": float(seed.y), "predicted_only": False, "matched": True}

        pred_xy = self._predict_only()
        matched = self._pick_measurement(detections, pred_xy)
        if matched is None:
            self.missed_frames += 1
            if self.missed_frames > self.max_prediction_frames:
                self.initialized = False
                self.P = np.eye(4, dtype=np.float64) * 100.0
            return {"x": pred_xy[0], "y": pred_xy[1], "predicted_only": True, "matched": False}

        H = self._measurement_jacobian()
        R = np.eye(2, dtype=np.float64) * self.measurement_noise
        z = np.array([[float(matched.x)], [float(matched.y)]], dtype=np.float64)
        innovation = z - (H @ self.state)
        S = H @ self.P @ H.T + R
        K = self.P @ H.T @ np.linalg.inv(S)
        self.state = self.state + (K @ innovation)
        I = np.eye(4, dtype=np.float64)
        self.P = (I - K @ H) @ self.P
        self.missed_frames = 0
        return {
            "x": float(self.state[0, 0]),
            "y": float(self.state[1, 0]),
            "predicted_only": False,
            "matched": True,
        }


def choose_main_track(track_histories: Dict[int, Dict], selection_mode: str) -> Optional[int]:
    """Wybiera główny tor według strategii jakościowej."""
    if not track_histories:
        return None

    scored = []
    for tid, data in track_histories.items():
        metrics = _compute_track_metrics_local(data["points"])
        # Kara rośnie przy niskiej medianie confidence oraz słabej spójności confidence.
        confidence_penalty = max(0.0, 0.7 - metrics["median_confidence"])
        confidence_spread_penalty = max(0.0, 0.6 - metrics["confidence_consistency"])
        low_confidence_penalty = metrics["low_confidence_ratio"]
        if selection_mode == "largest":
            key = (
                -metrics["mean_area"],
                confidence_penalty + confidence_spread_penalty + low_confidence_penalty,
                -metrics["mean_confidence"],
                -metrics["detections"],
            )
        elif selection_mode == "longest":
            key = (
                -metrics["detections"],
                confidence_penalty + confidence_spread_penalty + low_confidence_penalty,
                -metrics["mean_confidence"],
                metrics["mean_step"],
            )
        elif selection_mode == "stablest":
            key = (
                metrics["stability_score"] + 1.8 * confidence_penalty + 1.2 * confidence_spread_penalty + low_confidence_penalty,
                -metrics["confidence_consistency"],
                -metrics["detections"],
            )
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
    confidence_values = [float(p.confidence) for p in detected_points if p.confidence is not None]
    if confidence_values:
        mean_confidence = float(sum(confidence_values) / len(confidence_values))
        confidence_p25 = float(np.percentile(confidence_values, 25))
        confidence_p10 = float(np.percentile(confidence_values, 10))
        median_confidence = float(np.percentile(confidence_values, 50))
        confidence_consistency = float(max(0.0, 1.0 - np.std(confidence_values)))
        # Udział detekcji o confidence < 0.5 pomaga odsiać niestabilne tory.
        low_confidence_ratio = float(sum(1 for value in confidence_values if value < 0.5) / len(confidence_values))
    else:
        mean_confidence = 0.0
        confidence_p25 = 0.0
        confidence_p10 = 0.0
        median_confidence = 0.0
        confidence_consistency = 0.0
        low_confidence_ratio = 1.0

    return {
        "mean_area": mean_area,
        "detections": float(detections),
        "mean_step": mean_step,
        "stability_score": stability_score,
        "mean_confidence": mean_confidence,
        "confidence_p25": confidence_p25,
        "confidence_p10": confidence_p10,
        "median_confidence": median_confidence,
        "confidence_consistency": confidence_consistency,
        "low_confidence_ratio": low_confidence_ratio,
    }


def run_tracker_with_config(
    frames: List[List[Detection]],
    fps: float,
    config: TrackerConfig,
) -> Dict[str, object]:
    """Uruchamia tracker dla listy detekcji per klatka i zwraca zunifikowany wynik."""
    tracker = SimpleMultiTracker(
        max_distance=config.max_distance,
        max_missed=config.max_missed,
        distance_weight=config.distance_weight,
        area_weight=config.area_weight,
        circularity_weight=config.circularity_weight,
        brightness_weight=config.brightness_weight,
        min_match_score=config.min_match_score,
        speed_gate_gain=config.speed_gate_gain,
        error_gate_gain=config.error_gate_gain,
        min_dynamic_distance=config.min_dynamic_distance,
        max_dynamic_distance=config.max_dynamic_distance,
        min_track_start_confidence=config.min_track_start_confidence,
        temporal_smoothing_alpha=config.temporal_smoothing_alpha,
        jitter_guard_px=config.jitter_guard_px,
    )
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
    parser.add_argument("--distance_weight", type=float, default=1.0)
    parser.add_argument("--area_weight", type=float, default=0.35)
    parser.add_argument("--circularity_weight", type=float, default=0.2)
    parser.add_argument("--brightness_weight", type=float, default=0.0)
    parser.add_argument("--min_match_score", type=float, default=0.5)
    parser.add_argument("--speed_gate_gain", type=float, default=1.5)
    parser.add_argument("--error_gate_gain", type=float, default=1.0)
    parser.add_argument("--min_dynamic_distance", type=float, default=12.0)
    parser.add_argument("--max_dynamic_distance", type=float, default=150.0)
    parser.add_argument(
        "--min_track_start_confidence",
        type=float,
        default=0.35,
        help="Minimalne confidence detekcji potrzebne do utworzenia nowego toru.",
    )
    parser.add_argument("--temporal_smoothing_alpha", type=float, default=0.35)
    parser.add_argument("--jitter_guard_px", type=float, default=1.5)
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
        distance_weight=args.distance_weight,
        area_weight=args.area_weight,
        circularity_weight=args.circularity_weight,
        brightness_weight=args.brightness_weight,
        min_match_score=args.min_match_score,
        speed_gate_gain=args.speed_gate_gain,
        error_gate_gain=args.error_gate_gain,
        min_dynamic_distance=args.min_dynamic_distance,
        max_dynamic_distance=args.max_dynamic_distance,
        min_track_start_confidence=args.min_track_start_confidence,
        temporal_smoothing_alpha=args.temporal_smoothing_alpha,
        jitter_guard_px=args.jitter_guard_px,
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
