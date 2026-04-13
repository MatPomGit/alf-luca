from __future__ import annotations

import csv
import hashlib
import json
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Sequence, Union

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_pdf import PdfPages

from . import __version__ as APP_VERSION
from luca_types import TrackPoint
DEFAULT_EXPORT_PATH="(output/)"

MetricProfile = Literal["basic", "extended", "research"]
MetricValue = Union[float, str]
RunMetadata = Dict[str, str]

RUN_METADATA_FIELDS = (
    "run_id",
    "input_source",
    "detector_name",
    "smoother_name",
    "config_hash",
    "app_version",
    "author",
)

DIAGNOSTIC_LOG_FIELDS = (
    "timestamp_utc",
    "frame_index",
    "event_type",
    "severity",
    "detected",
    "track_id",
    "confidence",
    "stability_index",
    "message",
)

# Domyślny autor wpisywany do metadanych uruchomień.
DEFAULT_RUN_AUTHOR = "J2S"

PROFILE_METRICS = {
    "basic": (
        "frames_total",
        "detections_total",
        "detection_ratio",
        "missed_frames",
        "path_length",
        "mean_step",
        "max_step",
        "p95_step",
        "stability_index",
        "quality_score",
        "trend_track_loss_risk",
        "trend_track_loss_direction",
        "trend_stability_score",
        "trend_stability_direction",
        "trend_confidence_score",
        "trend_confidence_direction",
        "trend_confidence_consistency",
        "trend_confidence_guard_band",
    ),
    "extended": (
        "frames_total",
        "detections_total",
        "detection_ratio",
        "missed_frames",
        "gap_count",
        "max_gap",
        "mean_gap",
        "path_length",
        "mean_step",
        "max_step",
        "jitter_rms",
        "p95_step",
        "step_cv",
        "prediction_ratio",
        "stability_index",
        "quality_score",
        "trend_track_loss_risk",
        "trend_track_loss_direction",
        "trend_stability_score",
        "trend_stability_direction",
        "trend_confidence_score",
        "trend_confidence_direction",
        "trend_confidence_consistency",
        "trend_confidence_guard_band",
        "mean_area",
        "max_area",
        "mean_radius",
        "max_radius",
        "mean_circularity",
        "mean_confidence",
        "p10_confidence",
        "p25_confidence",
        "median_confidence",
        "confidence_consistency",
        "low_confidence_ratio",
    ),
    "research": (
        "frames_total",
        "detections_total",
        "detection_ratio",
        "missed_frames",
        "gap_count",
        "max_gap",
        "mean_gap",
        "path_length",
        "mean_step",
        "max_step",
        "jitter_rms",
        "trajectory_smoothness",
        "p95_step",
        "step_cv",
        "prediction_ratio",
        "stability_index",
        "quality_score",
        "trend_track_loss_risk",
        "trend_track_loss_direction",
        "trend_stability_score",
        "trend_stability_direction",
        "trend_confidence_score",
        "trend_confidence_direction",
        "trend_confidence_consistency",
        "trend_confidence_guard_band",
        "mean_area",
        "max_area",
        "mean_radius",
        "max_radius",
        "mean_circularity",
        "mean_confidence",
        "p10_confidence",
        "p25_confidence",
        "median_confidence",
        "confidence_consistency",
        "low_confidence_ratio",
        "mae_px",
        "rmse_px",
        "p95_error_px",
    ),
}

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
        "mean_confidence": 0.0,
        "p10_confidence": 0.0,
        "p25_confidence": 0.0,
        "median_confidence": 0.0,
        "confidence_consistency": 0.0,
        "low_confidence_ratio": 0.0,
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
    confidences = [float(p.confidence) for p in detected if p.confidence is not None]
    if confidences:
        metrics["mean_confidence"] = float(np.mean(confidences))
        metrics["p10_confidence"] = float(np.percentile(confidences, 10))
        metrics["p25_confidence"] = float(np.percentile(confidences, 25))
        metrics["median_confidence"] = float(np.percentile(confidences, 50))
        # Wysoka spójność = małe rozrzuty confidence pomiędzy detekcjami.
        metrics["confidence_consistency"] = float(max(0.0, 1.0 - np.std(confidences)))
        # Udział słabych detekcji ułatwia diagnozę "migoczących" torów.
        metrics["low_confidence_ratio"] = float(sum(1 for val in confidences if val < 0.5) / len(confidences))

    metrics["stability_score"] = float(
        metrics["mean_step"] * 2.0
        + (1.0 - metrics["detection_ratio"]) * 50.0
        + max(0.0, 0.5 - metrics["mean_circularity"]) * 20.0
        + max(0.0, 0.6 - metrics["median_confidence"]) * 20.0
    )
    return metrics


def build_run_metadata(
    input_source: str,
    detector_name: str,
    smoother_name: str,
    config_payload: Dict[str, object],
    run_id: Optional[str] = None,
    app_version: Optional[str] = None,
    author: Optional[str] = None,
) -> RunMetadata:
    """Buduje minimalny, wspólny zestaw metadanych dla pojedynczego uruchomienia."""
    payload_json = json.dumps(config_payload, sort_keys=True, ensure_ascii=False)
    config_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()[:12]
    normalized_run_id = run_id or f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    return {
        "run_id": normalized_run_id,
        "input_source": str(input_source),
        "detector_name": str(detector_name),
        "smoother_name": str(smoother_name),
        "config_hash": config_hash,
        "app_version": str(app_version or APP_VERSION),
        # Pole autora ułatwia audyt artefaktów oraz identyfikację właściciela analiz.
        "author": str(author or DEFAULT_RUN_AUTHOR),
    }


def _metadata_json_path(csv_path: str) -> Path:
    """Wyznacza ścieżkę pliku metadanych obok CSV w formacie `*.run.json`."""
    csv_file = Path(csv_path)
    return csv_file.with_suffix(".run.json")


def save_run_metadata(metadata: RunMetadata, csv_path: str) -> None:
    """Zapisuje metadane uruchomienia do pliku JSON obok CSV."""
    payload = {
        **{field: metadata.get(field, "") for field in RUN_METADATA_FIELDS},
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    json_path = _metadata_json_path(csv_path)
    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def _row_with_metadata(row: List[object], metadata: Optional[RunMetadata]) -> List[object]:
    """Dokleja metadane runu do pojedynczego rekordu CSV."""
    if not metadata:
        return row
    return [*row, *[metadata.get(field, "") for field in RUN_METADATA_FIELDS]]


def save_track_csv(points: Sequence[TrackPoint], csv_path: str, run_metadata: Optional[RunMetadata] = None):
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "frame_index", "time_sec", "detected", "x", "y", "z",
            "x_world", "y_world", "z_world", "area",
            "perimeter", "circularity", "radius", "confidence", "track_id", "rank", "kalman_predicted"
        ] + list(RUN_METADATA_FIELDS))
        for p in points:
            writer.writerow(_row_with_metadata([
                p.frame_index, p.time_sec, int(p.detected), p.x, p.y, p.z_world,
                p.x_world, p.y_world, p.z_world, p.area,
                p.perimeter, p.circularity, p.radius, p.confidence, p.track_id, p.rank, p.kalman_predicted
            ], run_metadata))
    if run_metadata:
        save_run_metadata(run_metadata, csv_path)


def save_all_tracks_csv(track_histories: Dict[int, Dict], csv_path: str, run_metadata: Optional[RunMetadata] = None):
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "track_id", "frame_index", "time_sec", "detected", "x", "y", "z",
            "x_world", "y_world", "z_world", "area",
            "perimeter", "circularity", "radius", "confidence", "rank", "kalman_predicted"
        ] + list(RUN_METADATA_FIELDS))
        for tid, data in sorted(track_histories.items()):
            for p in data["points"]:
                writer.writerow(_row_with_metadata([
                    tid, p.frame_index, p.time_sec, int(p.detected), p.x, p.y, p.z_world,
                    p.x_world, p.y_world, p.z_world,
                    p.area, p.perimeter, p.circularity, p.radius, p.confidence, p.rank, p.kalman_predicted
                ], run_metadata))
    if run_metadata:
        save_run_metadata(run_metadata, csv_path)


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


def metrics_from_points(
    points: Sequence[TrackPoint],
    reference_points: Optional[Sequence[TrackPoint]] = None,
    metric_profile: str = "basic",
) -> Dict[str, MetricValue]:
    """Zachowuje kompatybilność wsteczną i deleguje liczenie metryk do wariantu profilowanego."""
    return metrics_from_points_with_profile(
        points=points,
        reference_points=reference_points,
        metric_profile=metric_profile,
    )


def _normalize_profile(metric_profile: str) -> MetricProfile:
    """Normalizuje nazwę profilu metryk i zapewnia bezpieczny fallback."""
    profile_key = (metric_profile or "basic").strip().lower()
    return profile_key if profile_key in PROFILE_METRICS else "basic"


def _ordered_points(points: Sequence[TrackPoint]) -> List[TrackPoint]:
    """Zwraca punkty posortowane po frame_index, aby ograniczyć wpływ niespójnej kolejności wejścia."""
    return sorted(points, key=lambda p: p.frame_index)


def _compute_gap_lengths(ordered_points: Sequence[TrackPoint]) -> List[int]:
    """Liczy długości przerw (brak detekcji lub brakujący indeks klatki) w jednostkach klatek."""
    if not ordered_points:
        return []

    gap_lengths: List[int] = []
    current_gap = 0
    previous_frame: Optional[int] = None

    for point in ordered_points:
        if previous_frame is not None and point.frame_index > previous_frame + 1:
            current_gap += point.frame_index - previous_frame - 1

        has_detection = bool(point.detected and point.x is not None and point.y is not None)
        if not has_detection:
            current_gap += 1
        elif current_gap > 0:
            gap_lengths.append(current_gap)
            current_gap = 0

        previous_frame = point.frame_index

    if current_gap > 0:
        gap_lengths.append(current_gap)
    return gap_lengths


def _compute_jitter_rms(ordered_detected: Sequence[TrackPoint]) -> float:
    """Liczy RMS odchyleń kroku od średniego kroku (im mniej, tym stabilniejszy ruch)."""
    if len(ordered_detected) < 2:
        return 0.0

    steps = np.array(
        [
            math.hypot((b.x or 0.0) - (a.x or 0.0), (b.y or 0.0) - (a.y or 0.0))
            for a, b in zip(ordered_detected[:-1], ordered_detected[1:])
        ],
        dtype=np.float64,
    )
    if steps.size == 0:
        return 0.0

    centered = steps - np.mean(steps)
    return float(np.sqrt(np.mean(centered**2)))


def _compute_trajectory_smoothness(ordered_detected: Sequence[TrackPoint]) -> float:
    """Liczy gładkość trajektorii na podstawie RMS drugiej różnicy położenia."""
    if len(ordered_detected) < 3:
        return 0.0

    coords = np.array([(p.x, p.y) for p in ordered_detected if p.x is not None and p.y is not None], dtype=np.float64)
    if coords.shape[0] < 3:
        return 0.0

    second_diff = np.diff(coords, n=2, axis=0)
    magnitudes = np.linalg.norm(second_diff, axis=1)
    return float(np.sqrt(np.mean(magnitudes**2))) if magnitudes.size else 0.0


def _compute_step_features(ordered_detected: Sequence[TrackPoint]) -> Dict[str, float]:
    """Liczy dodatkowe cechy kroku trajektorii przydatne do oceny stabilności."""
    if len(ordered_detected) < 2:
        return {"p95_step": 0.0, "step_cv": 0.0}
    steps = np.array(
        [
            math.hypot((b.x or 0.0) - (a.x or 0.0), (b.y or 0.0) - (a.y or 0.0))
            for a, b in zip(ordered_detected[:-1], ordered_detected[1:])
        ],
        dtype=np.float64,
    )
    if steps.size == 0:
        return {"p95_step": 0.0, "step_cv": 0.0}
    mean_step = float(np.mean(steps))
    step_cv = float(np.std(steps) / mean_step) if mean_step > 1e-9 else 0.0
    return {
        "p95_step": float(np.percentile(steps, 95)),
        "step_cv": step_cv,
    }


def _compute_stability_index(
    jitter_rms: float,
    trajectory_smoothness: float,
    detection_ratio: float,
    low_confidence_ratio: float,
) -> float:
    """Składa znormalizowany wskaźnik stabilności [0..1], gdzie 1 oznacza stabilniejszy tor."""
    # Składniki wagowe dobrano tak, aby premiować ciągłość toru i mniejsze drgania pozycji.
    jitter_component = 1.0 / (1.0 + max(0.0, jitter_rms))
    smoothness_component = 1.0 / (1.0 + max(0.0, trajectory_smoothness))
    continuity_component = max(0.0, min(1.0, detection_ratio))
    confidence_component = max(0.0, min(1.0, 1.0 - low_confidence_ratio))
    return float(
        0.35 * jitter_component
        + 0.25 * smoothness_component
        + 0.25 * continuity_component
        + 0.15 * confidence_component
    )


def _compute_quality_score(stability_index: float, median_confidence: float, detection_ratio: float) -> float:
    """Liczy sumaryczny wynik jakości [0..100], wygodny do monitoringu i porównań przebiegów."""
    # Lekka uwaga diagnostyczna: stabilny tor "banan" powinien utrzymać wysoki score mimo drobnego szumu.
    normalized_confidence = max(0.0, min(1.0, median_confidence))
    normalized_detection = max(0.0, min(1.0, detection_ratio))
    return float(100.0 * (0.5 * stability_index + 0.3 * normalized_confidence + 0.2 * normalized_detection))


def _trend_label_from_delta(delta: float, neutral_epsilon: float = 1e-9) -> str:
    """Zamienia zmianę metryki na etykietę trendu czytelną dla raportów QA."""
    if delta > neutral_epsilon:
        return "up"
    if delta < -neutral_epsilon:
        return "down"
    return "flat"


def build_quality_trend_sections(metrics: Dict[str, MetricValue]) -> Dict[str, MetricValue]:
    """Buduje sekcje trendów jakości: utrata śladu, stabilność i confidence."""
    detection_ratio = float(metrics.get("detection_ratio", 0.0) or 0.0)
    low_confidence_ratio = float(metrics.get("low_confidence_ratio", 0.0) or 0.0)
    stability_index = float(metrics.get("stability_index", 0.0) or 0.0)
    confidence_consistency = float(metrics.get("confidence_consistency", 0.0) or 0.0)
    mean_confidence = float(metrics.get("mean_confidence", 0.0) or 0.0)
    p25_confidence = float(metrics.get("p25_confidence", 0.0) or 0.0)

    track_loss_risk = max(0.0, min(1.0, (1.0 - detection_ratio) * 0.75 + low_confidence_ratio * 0.25))
    confidence_guard_band = max(0.0, min(1.0, mean_confidence - p25_confidence))

    return {
        "trend_track_loss_risk": track_loss_risk,
        "trend_track_loss_direction": _trend_label_from_delta(0.4 - track_loss_risk),
        "trend_stability_score": stability_index,
        "trend_stability_direction": _trend_label_from_delta(stability_index - 0.6),
        "trend_confidence_score": mean_confidence,
        "trend_confidence_direction": _trend_label_from_delta(mean_confidence - 0.65),
        "trend_confidence_consistency": confidence_consistency,
        "trend_confidence_guard_band": confidence_guard_band,
    }


def _normalize_diagnostic_event(event: Dict[str, Any], default_timestamp: str) -> Dict[str, Any]:
    """Normalizuje wpis diagnostyczny do wspólnego formatu offline."""
    return {
        "timestamp_utc": str(event.get("timestamp_utc", default_timestamp)),
        "frame_index": int(event.get("frame_index", -1)),
        "event_type": str(event.get("event_type", "generic")),
        "severity": str(event.get("severity", "info")),
        "detected": int(bool(event.get("detected", False))),
        "track_id": event.get("track_id"),
        "confidence": event.get("confidence"),
        "stability_index": event.get("stability_index"),
        "message": str(event.get("message", "")),
    }


def save_diagnostic_log(
    events: Sequence[Dict[str, Any]],
    output_path: str,
    run_metadata: Optional[RunMetadata] = None,
) -> None:
    """Zapisuje jednolity log diagnostyczny offline w formacie JSONL."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    now_utc = datetime.now(timezone.utc).isoformat()
    with Path(output_path).open("w", encoding="utf-8") as handle:
        for event in events:
            normalized = _normalize_diagnostic_event(event, now_utc)
            if run_metadata:
                normalized["run_id"] = run_metadata.get("run_id", "")
                normalized["config_hash"] = run_metadata.get("config_hash", "")
            handle.write(json.dumps(normalized, ensure_ascii=False) + "\n")


def _safe_float(value: MetricValue, default: float = 0.0) -> float:
    """Konwertuje wartości metryk na float i chroni przed błędnymi typami danych."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def build_session_summary(
    session_id: str,
    run_metadata: Optional[RunMetadata],
    metrics: Dict[str, MetricValue],
    quality_trends: Optional[Dict[str, MetricValue]] = None,
    benchmark_result: Optional[Dict[str, MetricValue]] = None,
) -> Dict[str, MetricValue]:
    """Buduje podsumowanie jednej sesji do eksportu CSV/JSON i dashboardu QA."""
    trends = quality_trends or build_quality_trend_sections(metrics)
    summary: Dict[str, MetricValue] = {
        "session_id": session_id,
        "run_id": run_metadata.get("run_id", "") if run_metadata else "",
        "input_source": run_metadata.get("input_source", "") if run_metadata else "",
        "metric_profile": str(metrics.get("metric_profile", "basic")),
        "frames_total": _safe_float(metrics.get("frames_total", metrics.get("length_frames", 0.0))),
        "detection_ratio": _safe_float(metrics.get("detection_ratio", 0.0)),
        "quality_score": _safe_float(metrics.get("quality_score", 0.0)),
        "stability_index": _safe_float(metrics.get("stability_index", 0.0)),
        "mean_confidence": _safe_float(metrics.get("mean_confidence", 0.0)),
        "trend_track_loss_risk": _safe_float(trends.get("trend_track_loss_risk", 0.0)),
        "trend_stability_direction": str(trends.get("trend_stability_direction", "flat")),
        "trend_confidence_direction": str(trends.get("trend_confidence_direction", "flat")),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    if benchmark_result:
        summary.update({f"benchmark_{k}": v for k, v in benchmark_result.items()})
    return summary


def _compute_reference_errors(
    ordered_points: Sequence[TrackPoint],
    reference_points: Optional[Sequence[TrackPoint]],
) -> Dict[str, float]:
    """Opcjonalnie liczy błędy pozycji względem trajektorii referencyjnej."""
    default = {"mae_px": 0.0, "rmse_px": 0.0, "p95_error_px": 0.0}
    if not reference_points:
        return default

    ref_by_frame = {p.frame_index: p for p in reference_points}
    frame_errors: List[float] = []

    for point in ordered_points:
        ref = ref_by_frame.get(point.frame_index)
        if not ref:
            continue
        if (
            not point.detected
            or not ref.detected
            or point.x is None
            or point.y is None
            or ref.x is None
            or ref.y is None
        ):
            continue
        frame_errors.append(math.hypot(point.x - ref.x, point.y - ref.y))

    if not frame_errors:
        return default

    errors = np.array(frame_errors, dtype=np.float64)
    return {
        "mae_px": float(np.mean(np.abs(errors))),
        "rmse_px": float(np.sqrt(np.mean(errors**2))),
        "p95_error_px": float(np.percentile(errors, 95)),
    }


def metrics_from_points_with_profile(
    points: Sequence[TrackPoint],
    reference_points: Optional[Sequence[TrackPoint]] = None,
    metric_profile: str = "basic",
) -> Dict[str, MetricValue]:
    """Generuje metryki zgodnie z profilem oraz opcjonalnie dodaje błędy względem referencji."""
    ordered = _ordered_points(points)
    metrics = compute_track_metrics(ordered)
    gap_lengths = _compute_gap_lengths(ordered)
    detected = [p for p in ordered if p.detected and p.x is not None and p.y is not None]
    radii = [p.radius for p in detected if p.radius is not None]
    areas = [p.area for p in detected if p.area is not None]
    circs = [p.circularity for p in detected if p.circularity is not None]
    confidences = [float(p.confidence) for p in detected if p.confidence is not None]
    profile = _normalize_profile(metric_profile)

    frame_indices = [p.frame_index for p in ordered]
    if frame_indices:
        expected_span = max(frame_indices) - min(frame_indices) + 1
        index_gaps = max(0, expected_span - len(ordered))
    else:
        index_gaps = 0

    misses = len([p for p in ordered if not (p.detected and p.x is not None and p.y is not None)]) + index_gaps
    jitter_rms = _compute_jitter_rms(detected)
    trajectory_smoothness = _compute_trajectory_smoothness(detected)
    step_features = _compute_step_features(detected)
    prediction_ratio = float(sum(1 for p in ordered if int(p.kalman_predicted or 0) == 1) / len(ordered)) if ordered else 0.0
    stability_index = _compute_stability_index(
        jitter_rms=jitter_rms,
        trajectory_smoothness=trajectory_smoothness,
        detection_ratio=metrics["detection_ratio"],
        low_confidence_ratio=metrics["low_confidence_ratio"],
    )
    quality_score = _compute_quality_score(
        stability_index=stability_index,
        median_confidence=metrics["median_confidence"],
        detection_ratio=metrics["detection_ratio"],
    )

    all_metrics = {
        "metric_profile": profile,
        "frames_total": float(len(ordered)),
        "detections_total": float(len(detected)),
        "detection_ratio": metrics["detection_ratio"],
        "missed_frames": float(misses),
        "gap_count": float(len(gap_lengths)),
        "max_gap": float(max(gap_lengths) if gap_lengths else 0),
        "mean_gap": float(sum(gap_lengths) / len(gap_lengths)) if gap_lengths else 0.0,
        "path_length": metrics["path_length"],
        "mean_step": metrics["mean_step"],
        "max_step": metrics["max_step"],
        "jitter_rms": jitter_rms,
        "trajectory_smoothness": trajectory_smoothness,
        "p95_step": step_features["p95_step"],
        "step_cv": step_features["step_cv"],
        "prediction_ratio": prediction_ratio,
        "stability_index": stability_index,
        "quality_score": quality_score,
        "mean_area": float(sum(areas) / len(areas)) if areas else 0.0,
        "max_area": float(max(areas)) if areas else 0.0,
        "mean_radius": float(sum(radii) / len(radii)) if radii else 0.0,
        "max_radius": float(max(radii)) if radii else 0.0,
        "mean_circularity": float(sum(circs) / len(circs)) if circs else 0.0,
        "mean_confidence": float(np.mean(confidences)) if confidences else 0.0,
        "p10_confidence": float(np.percentile(confidences, 10)) if confidences else 0.0,
        "p25_confidence": float(np.percentile(confidences, 25)) if confidences else 0.0,
        "median_confidence": float(np.percentile(confidences, 50)) if confidences else 0.0,
        "confidence_consistency": float(max(0.0, 1.0 - np.std(confidences))) if confidences else 0.0,
        "low_confidence_ratio": float(sum(1 for val in confidences if val < 0.5) / len(confidences)) if confidences else 0.0,
    }
    all_metrics.update(build_quality_trend_sections(all_metrics))
    all_metrics.update(_compute_reference_errors(ordered, reference_points))

    allowed_keys = {"metric_profile", *PROFILE_METRICS[profile]}
    return {key: value for key, value in all_metrics.items() if key in allowed_keys}


def save_metrics_csv(metrics: Dict[str, MetricValue], csv_path: str, metric_profile: Optional[str] = None):
    """Zapisuje metryki do CSV i jawnie dodaje informację o aktywnym profilu."""
    resolved_profile = _normalize_profile(str(metric_profile or metrics.get("metric_profile", "basic")))
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["metric", "value"])
        writer.writerow(["metric_profile", resolved_profile])
        for k, v in metrics.items():
            if k == "metric_profile":
                continue
            writer.writerow([k, v])


def save_session_summary_csv(summary: Dict[str, MetricValue], csv_path: str) -> None:
    """Zapisuje pojedyncze podsumowanie sesji do CSV (1 wiersz)."""
    Path(csv_path).parent.mkdir(parents=True, exist_ok=True)
    with Path(csv_path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary.keys()))
        writer.writeheader()
        writer.writerow(summary)


def save_session_summary_json(summary: Dict[str, MetricValue], json_path: str) -> None:
    """Zapisuje pojedyncze podsumowanie sesji do JSON."""
    Path(json_path).parent.mkdir(parents=True, exist_ok=True)
    with Path(json_path).open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)


def link_regression_benchmark(
    session_summary: Dict[str, MetricValue],
    benchmark_delta_csv: str,
    scenario: Optional[str] = None,
    config: Optional[str] = None,
) -> Dict[str, MetricValue]:
    """Spina raport sesyjny z wynikiem benchmarku regresji na podstawie pliku delta CSV."""
    path = Path(benchmark_delta_csv)
    if not path.exists():
        return {
            "status": "missing",
            "source": str(path),
            "matched_rows": 0.0,
            "max_regression_delta": 0.0,
        }

    matched_rows = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if scenario and str(row.get("scenario", "")) != scenario:
                continue
            if config and str(row.get("config", "")) != config:
                continue
            matched_rows.append(row)

    if not matched_rows:
        return {
            "status": "not_matched",
            "source": str(path),
            "matched_rows": 0.0,
            "max_regression_delta": 0.0,
        }

    regression_deltas = []
    for row in matched_rows:
        for key in (
            "delta_point_precision_p95_px",
            "delta_jitter_p95_px",
            "delta_lost_frames",
            "delta_lost_tracks_total",
            "delta_false_detections_per_frame",
        ):
            if key in row and row[key] not in {"", "None"}:
                regression_deltas.append(abs(float(row[key])))

    max_delta = max(regression_deltas) if regression_deltas else 0.0
    return {
        "status": "linked",
        "source": str(path),
        "matched_rows": float(len(matched_rows)),
        "max_regression_delta": float(max_delta),
        "session_quality_score": _safe_float(session_summary.get("quality_score", 0.0)),
    }


def build_qa_dashboard_markdown(
    session_summaries: Sequence[Dict[str, MetricValue]],
    output_path: str,
) -> None:
    """Generuje minimalny dashboard QA (Markdown) oparty o artefakty raportowe."""
    lines = [
        "# QA Dashboard",
        "",
        "| session_id | run_id | quality_score | detection_ratio | stability_index | confidence | track_loss_risk | benchmark_status |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for summary in session_summaries:
        lines.append(
            "| {session_id} | {run_id} | {quality_score:.3f} | {detection_ratio:.3f} | {stability_index:.3f} | {mean_confidence:.3f} | {loss:.3f} | {bench} |".format(
                session_id=summary.get("session_id", ""),
                run_id=summary.get("run_id", ""),
                quality_score=_safe_float(summary.get("quality_score", 0.0)),
                detection_ratio=_safe_float(summary.get("detection_ratio", 0.0)),
                stability_index=_safe_float(summary.get("stability_index", 0.0)),
                mean_confidence=_safe_float(summary.get("mean_confidence", 0.0)),
                loss=_safe_float(summary.get("trend_track_loss_risk", 0.0)),
                bench=summary.get("benchmark_status", "n/a"),
            )
        )
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def save_track_report_pdf(
    pdf_path: str,
    metrics: Dict[str, MetricValue],
    title: str,
    trajectory_png: Optional[str] = None,
    extra_lines: Optional[List[str]] = None,
    metric_profile: str = "basic",
):
    resolved_profile = _normalize_profile(str(metric_profile or metrics.get("metric_profile", "basic")))
    with PdfPages(pdf_path) as pdf:
        fig = plt.figure(figsize=(8.27, 11.69))
        fig.clf()
        ax = fig.add_axes([0.08, 0.05, 0.84, 0.9])
        ax.axis("off")

        lines = [title, "", f"Profil metryk: {resolved_profile}", "", "Metryki jakości śledzenia:", ""]
        for k, v in metrics.items():
            if isinstance(v, (int, float)):
                lines.append(f"{k}: {float(v):.6f}")
            else:
                lines.append(f"{k}: {v}")
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
                    confidence=float(row["confidence"]) if row.get("confidence", "") not in {"", "None"} else None,
                    track_id=int(row["track_id"]) if row["track_id"] not in {"", "None"} else None,
                    rank=int(row["rank"]) if row.get("rank", "") not in {"", "None"} else None,
                    kalman_predicted=int(row.get("kalman_predicted", "0") or 0),
                )
            )
    return points


def compare_csv(reference_csv: str, candidate_csv: str, output_csv: str, report_pdf: Optional[str] = None):
    # Informacja etapowa: pokazujemy jakie pliki biorą udział w porównaniu.
    print(f"[OK] Etap compare: reference={reference_csv} | candidate={candidate_csv}")
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
