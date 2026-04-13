#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# Dodajemy katalog główny repo do PYTHONPATH, aby skrypt działał uruchamiany z katalogu tools/.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def parse_args() -> argparse.Namespace:
    """Parsuje argumenty CLI benchmarku jakości śledzenia."""
    parser = argparse.ArgumentParser(
        description="Lekki benchmark jakości: uruchamia pipeline na stałych konfiguracjach i zapisuje metryki."
    )
    parser.add_argument(
        "--scenarios",
        default="video/scenarios/scenarios.json",
        help="Ścieżka do pliku JSON z listą scenariuszy.",
    )
    parser.add_argument(
        "--output-dir",
        default="output/quality_benchmark",
        help="Katalog wynikowy (CSV + raport MD + artefakty per uruchomienie).",
    )
    parser.add_argument(
        "--label",
        default=None,
        help="Etykieta porównawcza (np. before_refactor, after_refactor).",
    )
    parser.add_argument(
        "--baseline-csv",
        default=None,
        help="Opcjonalny CSV bazowy (np. run 'before') do raportu różnic 'przed/po'.",
    )
    parser.add_argument(
        "--baseline-version",
        default=None,
        help="Wersja baseline z repo (np. v1). Używana, gdy nie podano --baseline-csv.",
    )
    parser.add_argument(
        "--limit-scenarios",
        type=int,
        default=None,
        help="Opcjonalny limit liczby scenariuszy (przydatne do szybkiego smoke testu).",
    )
    parser.add_argument(
        "--scenario-tags",
        nargs="*",
        default=None,
        help="Opcjonalny filtr scenariuszy po tagach (np. reflections flicker).",
    )
    parser.add_argument(
        "--thresholds-file",
        default="video/scenarios/threshold_profiles.json",
        help="Plik JSON z profilami progów must-pass dla klas zmian.",
    )
    parser.add_argument(
        "--threshold-profile",
        default="interface_only",
        choices=[
            "detection_algorithm",
            "tracking_filters",
            "interface_only",
            "p0_regression_gate",
            "experimental_promotion_gate",
        ],
        help="Profil progów: dobierz klasę zmian do planowanego poziomu ryzyka.",
    )
    parser.add_argument(
        "--enforce-thresholds",
        action="store_true",
        help="Wymusza status błędu (exit 2), jeżeli candidate nie przechodzi progów must-pass.",
    )
    return parser.parse_args()


def import_pipeline_modules():
    """Importuje moduły pipeline dopiero przy uruchomieniu benchmarku (nie przy --help)."""
    from luca_tracker.pipeline import PipelineConfig, process_video_frames
    from luca_tracker.postprocess import apply_kalman_to_points
    from luca_tracker.reports import save_all_tracks_csv, save_track_csv

    return PipelineConfig, process_video_frames, apply_kalman_to_points, save_all_tracks_csv, save_track_csv


def load_scenarios(manifest_path: Path, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Wczytuje scenariusze z pliku JSON i waliduje minimalny schemat danych."""
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    scenarios = payload.get("scenarios", [])
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("Brak scenariuszy w manifeście JSON.")

    normalized: List[Dict[str, Any]] = []
    for item in scenarios:
        if not isinstance(item, dict):
            raise ValueError("Każdy scenariusz musi być obiektem JSON.")
        name = str(item.get("name", "")).strip()
        video = str(item.get("video", "")).strip()
        if not name or not video:
            raise ValueError("Każdy scenariusz musi zawierać pola 'name' i 'video'.")
        normalized.append(
            {
                "name": name,
                "video": video,
                "tags": list(item.get("tags", [])),
                "notes": str(item.get("notes", "")),
                "ground_truth_csv": str(item.get("ground_truth_csv", "")).strip(),
            }
        )

    return normalized[:limit] if limit is not None else normalized


def fixed_benchmark_configs() -> List[Tuple[str, Dict[str, Any], Optional[str]]]:
    """Zwraca stałe konfiguracje benchmarkowe wraz z mapowaniem eksperyment->baseline."""
    return [
        (
            "brightest_fixed",
            {
                "track_mode": "brightness",
                "multi_track": True,
                "selection_mode": "stablest",
                "threshold_mode": "fixed",
                "threshold": 200,
                "blur": 11,
                "min_area": 10.0,
                "max_area": 0.0,
                "erode_iter": 2,
                "dilate_iter": 4,
                "temporal_stabilization": False,
                "use_kalman": False,
            },
            None,
        ),
        (
            "brightest_adaptive",
            {
                "track_mode": "brightness",
                "multi_track": True,
                "selection_mode": "stablest",
                "threshold_mode": "adaptive",
                "adaptive_block_size": 31,
                "adaptive_c": 5.0,
                "blur": 9,
                "min_area": 8.0,
                "max_area": 0.0,
                "erode_iter": 1,
                "dilate_iter": 3,
                "temporal_stabilization": True,
                "temporal_window": 3,
                "temporal_mode": "majority",
                "use_kalman": True,
            },
            "brightest_fixed",
        ),
        (
            "color_otsu",
            {
                "track_mode": "color",
                "color_name": "red",
                "multi_track": True,
                "selection_mode": "stablest",
                "threshold_mode": "otsu",
                "blur": 9,
                "min_area": 8.0,
                "max_area": 0.0,
                "erode_iter": 1,
                "dilate_iter": 2,
                "temporal_stabilization": True,
                "temporal_window": 3,
                "temporal_mode": "majority",
                "use_kalman": True,
            },
            None,
        ),
        (
            "brightest_low_light_exp",
            {
                "track_mode": "brightness",
                "detector_profile": "bright_low_light_exp",
                "enable_experimental_profiles": True,
                "multi_track": True,
                "selection_mode": "stablest",
                "experimental_mode": True,
                "experimental_adaptive_association": True,
                "use_kalman": True,
            },
            "brightest_fixed",
        ),
        (
            "color_robust_exp",
            {
                "track_mode": "color",
                "detector_profile": "color_robust_exp",
                "enable_experimental_profiles": True,
                "multi_track": True,
                "selection_mode": "stablest",
                "experimental_mode": True,
                "experimental_adaptive_association": True,
                "use_kalman": True,
            },
            "color_otsu",
        ),
    ]


def safe_ratio(numerator: float, denominator: float) -> float:
    """Liczy bezpieczny iloraz z ochroną przed dzieleniem przez zero."""
    return float(numerator / denominator) if denominator else 0.0


def longest_detected_run(points: Sequence[Any]) -> int:
    """Wyznacza najdłuższą serię kolejnych klatek z poprawną detekcją w głównym torze."""
    best = 0
    current = 0
    for point in points:
        if bool(getattr(point, "detected", False)):
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def count_track_switches(track_histories: Dict[int, Dict[str, Any]]) -> int:
    """Liczy przełączenia track_id między klatkami na bazie dominującej detekcji per klatka.

    Dominująca detekcja to punkt o największym polu (`area`) w danej klatce.
    """
    by_frame: Dict[int, List[Any]] = {}
    for track_id, track_data in track_histories.items():
        for point in track_data.get("points", []):
            if not getattr(point, "detected", False):
                continue
            # Zapamiętujemy track_id wewnątrz punktu pomocniczo, by łatwo sortować per klatkę.
            setattr(point, "_benchmark_track_id", track_id)
            by_frame.setdefault(int(point.frame_index), []).append(point)

    dominant_series: List[int] = []
    for frame_index in sorted(by_frame):
        points = by_frame[frame_index]
        dominant = max(points, key=lambda p: float(getattr(p, "area", 0.0) or 0.0))
        dominant_series.append(int(getattr(dominant, "_benchmark_track_id")))

    switches = 0
    previous: Optional[int] = None
    for current in dominant_series:
        if previous is not None and current != previous:
            switches += 1
        previous = current
    return switches


def load_ground_truth_points(ground_truth_csv: str) -> Dict[int, Tuple[float, float]]:
    """Wczytuje referencyjne punkty 2D z CSV (frame_index,x,y)."""
    if not ground_truth_csv:
        return {}
    gt_path = Path(ground_truth_csv)
    if not gt_path.exists():
        raise FileNotFoundError(f"Nie znaleziono ground truth CSV: {gt_path}")

    gt_points: Dict[int, Tuple[float, float]] = {}
    with gt_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            frame_index_raw = row.get("frame_index")
            x_raw = row.get("x")
            y_raw = row.get("y")
            if frame_index_raw is None or x_raw is None or y_raw is None:
                continue
            gt_points[int(frame_index_raw)] = (float(x_raw), float(y_raw))
    return gt_points


def detection_mode_label(track_mode: str) -> str:
    """Mapuje techniczny track_mode na etykietę raportową."""
    return "brightest" if track_mode == "brightness" else "color"


def compute_metrics(result: Dict[str, Any], gt_points: Dict[int, Tuple[float, float]]) -> Dict[str, float]:
    """Oblicza metryki benchmarkowe (pozycja 2D, jitter, utraty klatek, false positives, FPS)."""
    frame_count = int(result["frame_count"])
    main_points = list(result["main_points"])
    finished_tracks = result.get("finished_tracks", {}) or {}

    main_detected = [point for point in main_points if bool(point.detected)]
    all_detected_count = sum(
        1
        for track_data in finished_tracks.values()
        for point in track_data.get("points", [])
        if bool(point.detected)
    )
    false_detections_total = max(0, all_detected_count - len(main_detected))
    lost_frames = max(0, frame_count - len(main_detected))
    # Liczymy fragmentację toru: ile wykrytych torów ponad tor główny powstało w przebiegu.
    detected_tracks_total = sum(
        1 for track_data in finished_tracks.values() if any(bool(point.detected) for point in track_data.get("points", []))
    )
    lost_tracks_total = max(0, detected_tracks_total - 1)

    step_distances: List[float] = []
    previous_xy: Optional[Tuple[float, float]] = None
    position_errors: List[float] = []
    for point in main_points:
        if not bool(getattr(point, "detected", False)):
            continue
        x = getattr(point, "x", None)
        y = getattr(point, "y", None)
        if x is None or y is None:
            continue
        current_xy = (float(x), float(y))
        gt_xy = gt_points.get(int(getattr(point, "frame_index", -1)))
        if gt_xy is not None:
            position_errors.append(math.dist(current_xy, gt_xy))
        if previous_xy is not None:
            step_distances.append(math.dist(previous_xy, current_xy))
        previous_xy = current_xy

    return {
        "frames_total": float(frame_count),
        "main_detections": float(len(main_detected)),
        "lost_frames": float(lost_frames),
        "point_precision_mean_px": safe_ratio(sum(position_errors), len(position_errors)),
        "point_precision_p95_px": percentile(position_errors, 95.0),
        "position_error_2d_mean_px": safe_ratio(sum(position_errors), len(position_errors)),
        "position_error_2d_p95_px": percentile(position_errors, 95.0),
        "trajectory_jitter_p95_px": percentile(step_distances, 95.0),
        "false_positives_total": float(false_detections_total),
        "false_detections_per_frame": safe_ratio(false_detections_total, frame_count),
        "lost_tracks_total": float(lost_tracks_total),
        "stable_track_len_frames": float(longest_detected_run(main_points)),
        "track_id_switches": float(count_track_switches(finished_tracks)),
    }


def percentile(values: Sequence[float], q: float) -> float:
    """Liczy percentyl bez zależności zewnętrznych (numpy nie jest wymagane)."""
    if not values:
        return 0.0
    sorted_values = sorted(float(v) for v in values)
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = max(0.0, min(100.0, q)) / 100.0 * (len(sorted_values) - 1)
    lower = int(math.floor(rank))
    upper = int(math.ceil(rank))
    if lower == upper:
        return sorted_values[lower]
    weight = rank - lower
    return sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight


def current_git_sha() -> str:
    """Pobiera skrócony hash aktualnego commita dla łatwiejszego porównywania wyników."""
    try:
        output = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
        return output or "unknown"
    except Exception:
        return "unknown"


def run_single_case(
    scenario: Dict[str, Any],
    config_name: str,
    config_values: Dict[str, Any],
    baseline_config_name: Optional[str],
    run_dir: Path,
) -> Dict[str, Any]:
    """Uruchamia pojedynczy scenariusz + konfigurację i zwraca metryki oraz metadane."""
    PipelineConfig, process_video_frames, apply_kalman_to_points, save_all_tracks_csv, save_track_csv = import_pipeline_modules()
    scenario_name = scenario["name"]
    video_path = Path(scenario["video"])
    if not video_path.exists():
        raise FileNotFoundError(f"Nie znaleziono pliku scenariusza: {video_path}")

    case_dir = run_dir / scenario_name / config_name
    case_dir.mkdir(parents=True, exist_ok=True)

    output_csv = case_dir / "main_track.csv"
    all_tracks_csv = case_dir / "all_tracks.csv"
    gt_points = load_ground_truth_points(scenario.get("ground_truth_csv", ""))

    pipeline_config = PipelineConfig(
        video=str(video_path),
        output_csv=str(output_csv),
        all_tracks_csv=str(all_tracks_csv),
        **config_values,
    )

    # Uruchamiamy pipeline bez ciężkich artefaktów (bez PDF/PNG/wideo), tylko dane liczbowe.
    started = time.perf_counter()
    result = process_video_frames(pipeline_config)
    elapsed_sec = max(1e-9, time.perf_counter() - started)
    if bool(config_values.get("use_kalman", False)):
        apply_kalman_to_points(
            result["main_points"],
            process_noise=pipeline_config.kalman.process_noise,
            measurement_noise=pipeline_config.kalman.measurement_noise,
        )

    save_track_csv(result["main_points"], str(output_csv))
    if pipeline_config.multi_track:
        save_all_tracks_csv(result["finished_tracks"], str(all_tracks_csv))

    metrics = compute_metrics(result, gt_points=gt_points)
    frames_total = max(0.0, float(result.get("frame_count", 0)))
    source_fps = max(1e-9, float(result.get("fps", 0.0) or 0.0))
    processing_fps = safe_ratio(frames_total, elapsed_sec)
    metrics["fps"] = processing_fps
    metrics["fps_stability_ratio"] = safe_ratio(processing_fps, source_fps)
    mode_label = detection_mode_label(str(config_values.get("track_mode", "brightness")))
    return {
        "scenario_name": scenario_name,
        "video": str(video_path),
        "tags": ",".join(scenario.get("tags", [])),
        "notes": scenario.get("notes", ""),
        "config_name": config_name,
        "baseline_config_name": baseline_config_name or "",
        "mode": mode_label,
        "threshold_profile": str(config_values.get("threshold_mode", "fixed")),
        "config_json": json.dumps(config_values, ensure_ascii=False, sort_keys=True),
        **metrics,
    }


def write_csv(rows: Iterable[Dict[str, Any]], csv_path: Path) -> None:
    """Zapisuje wyniki benchmarku do jednego pliku CSV."""
    rows_list = list(rows)
    if not rows_list:
        raise ValueError("Brak danych do zapisu CSV.")

    fieldnames = [
        "timestamp_utc",
        "label",
        "git_sha",
        "scenario_name",
        "video",
        "tags",
        "notes",
        "config_name",
        "baseline_config_name",
        "mode",
        "threshold_profile",
        "frames_total",
        "main_detections",
        "lost_frames",
        "lost_tracks_total",
        "point_precision_mean_px",
        "point_precision_p95_px",
        "position_error_2d_mean_px",
        "position_error_2d_p95_px",
        "trajectory_jitter_p95_px",
        "false_positives_total",
        "false_detections_per_frame",
        "stable_track_len_frames",
        "track_id_switches",
        "fps",
        "fps_stability_ratio",
        "config_json",
    ]

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows_list:
            writer.writerow(row)


def load_baseline_rows(baseline_csv: Optional[str]) -> Dict[Tuple[str, str], Dict[str, float]]:
    """Wczytuje opcjonalny plik bazowy i indeksuje go po (scenario_name, config_name)."""
    if not baseline_csv:
        return {}

    baseline_path = Path(baseline_csv)
    if not baseline_path.exists():
        raise FileNotFoundError(f"Nie znaleziono pliku --baseline-csv: {baseline_path}")

    indexed: Dict[Tuple[str, str], Dict[str, float]] = {}
    with baseline_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            key = (str(row.get("scenario_name", "")), str(row.get("config_name", "")))
            if not all(key):
                continue
            indexed[key] = {
                "lost_frames": float(row.get("lost_frames", 0.0) or 0.0),
                "lost_tracks_total": float(row.get("lost_tracks_total", 0.0) or 0.0),
                "point_precision_mean_px": float(row.get("point_precision_mean_px", 0.0) or 0.0),
                "point_precision_p95_px": float(row.get("point_precision_p95_px", 0.0) or 0.0),
                "position_error_2d_mean_px": float(row.get("position_error_2d_mean_px", 0.0) or 0.0),
                "position_error_2d_p95_px": float(row.get("position_error_2d_p95_px", 0.0) or 0.0),
                "trajectory_jitter_p95_px": float(row.get("trajectory_jitter_p95_px", 0.0) or 0.0),
                "false_positives_total": float(row.get("false_positives_total", 0.0) or 0.0),
                "false_detections_per_frame": float(row.get("false_detections_per_frame", 0.0) or 0.0),
                "stable_track_len_frames": float(row.get("stable_track_len_frames", 0.0) or 0.0),
                "track_id_switches": float(row.get("track_id_switches", 0.0) or 0.0),
                "fps": float(row.get("fps", 0.0) or 0.0),
                "fps_stability_ratio": float(row.get("fps_stability_ratio", 0.0) or 0.0),
            }
    return indexed


def write_markdown_report(
    rows: Sequence[Dict[str, Any]], report_path: Path, baseline_rows: Optional[Dict[Tuple[str, str], Dict[str, float]]] = None
) -> None:
    """Generuje krótki raport Markdown z tabelą metryk do szybkiego porównania."""
    baseline_rows = baseline_rows or {}
    lines: List[str] = []
    lines.append("# Raport benchmarku jakości śledzenia")
    lines.append("")
    lines.append("## Metryki")
    lines.append("")
    lines.append("- `position_error_2d_mean_px` / `position_error_2d_p95_px`: błąd pozycji 2D względem ground truth (niżej = lepiej).")
    lines.append("- `point_precision_mean_px` / `point_precision_p95_px`: precyzja punktu (metryka oparta o błąd 2D; niżej = lepiej).")
    lines.append("- `trajectory_jitter_p95_px`: jitter toru, liczony jako P95 skoku między kolejnymi detekcjami (niżej = lepiej).")
    lines.append("- `lost_frames`: liczba klatek bez detekcji celu głównego (niżej = lepiej).")
    lines.append("- `lost_tracks_total`: liczba dodatkowych fragmentów toru względem toru głównego (niżej = lepiej).")
    lines.append("- `false_positives_total` oraz `false_detections_per_frame`: fałszywe detekcje (niżej = lepiej).")
    lines.append("- `stable_track_len_frames`: najdłuższa seria kolejnych detekcji głównego toru (wyżej = lepiej).")
    lines.append("- `track_id_switches`: liczba przełączeń dominującego `track_id` między klatkami (niżej = lepiej).")
    lines.append("- `fps`: średnia wydajność przetwarzania benchmarku (wyżej = lepiej).")
    lines.append("- `fps_stability_ratio`: processing_fps/source_fps (>=1 zwykle oznacza brak długu FPS).")
    lines.append("")
    lines.append("## Wyniki")
    lines.append("")

    has_baseline = bool(baseline_rows)
    if has_baseline:
        lines.append("Porównanie z baseline: Δ = aktualny - bazowy (dla `false/frame` i `switches` wartości ujemne są korzystne).")
        lines.append("")
        lines.append(
            "| scenario | mode | threshold | config | baseline_cfg | pos_err_p95 | Δpos | jitter_p95 | Δjitter | lost | Δlost | false/frame | Δfalse | fps | Δfps |"
        )
        lines.append("|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    else:
        lines.append("| scenario | mode | threshold | config | baseline_cfg | pos_err_p95 | jitter_p95 | lost | false/frame | fps |")
        lines.append("|---|---|---|---|---|---:|---:|---:|---:|---:|")

    for row in rows:
        key = (str(row["scenario_name"]), str(row["config_name"]))
        if has_baseline and key in baseline_rows:
            baseline = baseline_rows[key]
            delta_false = float(row["false_detections_per_frame"]) - baseline["false_detections_per_frame"]
            delta_pos = float(row["position_error_2d_p95_px"]) - baseline["position_error_2d_p95_px"]
            delta_jitter = float(row["trajectory_jitter_p95_px"]) - baseline["trajectory_jitter_p95_px"]
            delta_lost = float(row["lost_frames"]) - baseline["lost_frames"]
            delta_fps = float(row["fps"]) - baseline["fps"]
            lines.append(
                "| {scenario} | {mode} | {threshold_profile} | {config} | {baseline_cfg} | {pos_p95:.4f} | {delta_pos:+.4f} | {jitter_p95:.4f} | "
                "{delta_jitter:+.4f} | {lost:.0f} | {delta_lost:+.0f} | {false_rate:.4f} | {delta_false:+.4f} | {fps:.2f} | {delta_fps:+.2f} |".format(
                    scenario=row["scenario_name"],
                    mode=row["mode"],
                    threshold_profile=row["threshold_profile"],
                    config=row["config_name"],
                    baseline_cfg=row.get("baseline_config_name", "") or "-",
                    pos_p95=float(row["position_error_2d_p95_px"]),
                    delta_pos=delta_pos,
                    jitter_p95=float(row["trajectory_jitter_p95_px"]),
                    delta_jitter=delta_jitter,
                    lost=float(row["lost_frames"]),
                    delta_lost=delta_lost,
                    false_rate=float(row["false_detections_per_frame"]),
                    delta_false=delta_false,
                    fps=float(row["fps"]),
                    delta_fps=delta_fps,
                )
            )
        else:
            lines.append(
                "| {scenario} | {mode} | {threshold_profile} | {config} | {baseline_cfg} | {pos_p95:.4f} | {jitter_p95:.4f} | {lost:.0f} | {false_rate:.4f} | {fps:.2f} |".format(
                    scenario=row["scenario_name"],
                    mode=row["mode"],
                    threshold_profile=row["threshold_profile"],
                    config=row["config_name"],
                    baseline_cfg=row.get("baseline_config_name", "") or "-",
                    pos_p95=float(row["position_error_2d_p95_px"]),
                    jitter_p95=float(row["trajectory_jitter_p95_px"]),
                    lost=float(row["lost_frames"]),
                    false_rate=float(row["false_detections_per_frame"]),
                    fps=float(row["fps"]),
                )
            )

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_threshold_profiles(thresholds_file: Path) -> Dict[str, Any]:
    """Wczytuje definicje progów must-pass dla klas zmian."""
    if not thresholds_file.exists():
        raise FileNotFoundError(f"Nie znaleziono pliku progów: {thresholds_file}")
    payload = json.loads(thresholds_file.read_text(encoding="utf-8"))
    profiles = payload.get("profiles", {})
    if not isinstance(profiles, dict) or not profiles:
        raise ValueError("Plik progów musi zawierać słownik `profiles`.")
    return profiles


def resolve_baseline_csv(baseline_csv: Optional[str], baseline_version: Optional[str]) -> Optional[str]:
    """Rozwiązuje ścieżkę baseline: jawny CSV ma priorytet, potem wersja z repo."""
    if baseline_csv:
        return baseline_csv
    if not baseline_version:
        return None
    candidate = REPO_ROOT / "video" / "scenarios" / "baselines" / baseline_version / "benchmark_summary.csv"
    return str(candidate)


def evaluate_thresholds(
    rows: Sequence[Dict[str, Any]],
    baseline_rows: Dict[Tuple[str, str], Dict[str, float]],
    profile_name: str,
    profiles: Dict[str, Any],
) -> Dict[str, Any]:
    """Weryfikuje candidate względem baseline i zwraca listę naruszeń must-pass."""
    profile = profiles.get(profile_name)
    if not isinstance(profile, dict):
        raise ValueError(f"Brak profilu progów: {profile_name}")
    rules = profile.get("must_pass", {})
    if not isinstance(rules, dict) or not rules:
        raise ValueError(f"Profil `{profile_name}` nie zawiera sekcji `must_pass`.")

    violations_blocking: List[str] = []
    violations_warning: List[str] = []
    checks_total = 0
    checks_passed = 0

    for row in rows:
        key = (str(row["scenario_name"]), str(row["config_name"]))
        baseline = baseline_rows.get(key)
        if baseline is None:
            continue
        for metric_name, rule in rules.items():
            if not isinstance(rule, dict):
                continue
            candidate_value = float(row.get(metric_name, 0.0) or 0.0)
            baseline_value = float(baseline.get(metric_name, 0.0) or 0.0)
            checks_total += 1

            ok = True
            # Prosta reguła bez baseline, np. minimalne FPS ratio.
            if "min_abs" in rule:
                ok = ok and candidate_value >= float(rule["min_abs"])
            if "max_abs" in rule:
                ok = ok and candidate_value <= float(rule["max_abs"])
            # Reguły relatywne do baseline: dopuszczalny spadek/wzrost.
            if "min_delta" in rule:
                ok = ok and (candidate_value - baseline_value) >= float(rule["min_delta"])
            if "max_delta" in rule:
                ok = ok and (candidate_value - baseline_value) <= float(rule["max_delta"])
            severity = str(rule.get("severity", "blocking")).strip().lower() or "blocking"

            if ok:
                checks_passed += 1
                continue
            item = f"{key[0]}/{key[1]} metric={metric_name} candidate={candidate_value:.4f} baseline={baseline_value:.4f}"
            if severity in {"warn", "warning"}:
                violations_warning.append(item)
            else:
                violations_blocking.append(item)

    return {
        "profile_name": profile_name,
        "checks_total": checks_total,
        "checks_passed": checks_passed,
        "violations": violations_blocking + violations_warning,
        "violations_blocking": violations_blocking,
        "violations_warning": violations_warning,
    }


def write_comparison_report(
    rows: Sequence[Dict[str, Any]],
    baseline_rows: Dict[Tuple[str, str], Dict[str, float]],
    threshold_eval: Dict[str, Any],
    output_path: Path,
) -> None:
    """Tworzy raport baseline vs candidate pod artefakt CI."""
    lines: List[str] = []
    lines.append("# Baseline vs candidate")
    lines.append("")
    lines.append(f"- profil progów: `{threshold_eval['profile_name']}`")
    lines.append(f"- sprawdzenia must-pass: {threshold_eval['checks_passed']}/{threshold_eval['checks_total']}")
    lines.append("")
    lines.append("| scenario | mode | threshold | config | Δpos_err_p95 | Δjitter_p95 | Δlost_frames | Δfalse/frame | Δfps |")
    lines.append("|---|---|---|---|---:|---:|---:|---:|---:|")
    for row in rows:
        key = (str(row["scenario_name"]), str(row["config_name"]))
        baseline = baseline_rows.get(key)
        if baseline is None:
            continue
        lines.append(
            "| {scenario} | {mode} | {threshold_profile} | {config} | {d_pos:+.4f} | {d_jitter:+.4f} | {d_lost:+.0f} | {d_false:+.4f} | {d_fps:+.2f} |".format(
                scenario=row["scenario_name"],
                mode=row["mode"],
                threshold_profile=row["threshold_profile"],
                config=row["config_name"],
                d_pos=float(row["position_error_2d_p95_px"]) - baseline["position_error_2d_p95_px"],
                d_jitter=float(row["trajectory_jitter_p95_px"]) - baseline["trajectory_jitter_p95_px"],
                d_lost=float(row["lost_frames"]) - baseline["lost_frames"],
                d_false=float(row["false_detections_per_frame"]) - baseline["false_detections_per_frame"],
                d_fps=float(row["fps"]) - baseline["fps"],
            )
        )

    if threshold_eval["violations_blocking"] or threshold_eval["violations_warning"]:
        lines.append("")
        lines.append("## Naruszenia must-pass (blocking)")
        if threshold_eval["violations_blocking"]:
            for item in threshold_eval["violations_blocking"]:
                lines.append(f"- {item}")
        else:
            lines.append("- brak")
        lines.append("")
        lines.append("## Ostrzeżenia (warning)")
        if threshold_eval["violations_warning"]:
            for item in threshold_eval["violations_warning"]:
                lines.append(f"- {item}")
        else:
            lines.append("- brak")
    else:
        lines.append("")
        lines.append("## Naruszenia must-pass (blocking)")
        lines.append("- brak (banan: candidate spełnia wszystkie progi blokujące).")
        lines.append("")
        lines.append("## Ostrzeżenia (warning)")
        lines.append("- brak.")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_delta_csv(
    rows: Sequence[Dict[str, Any]],
    baseline_rows: Dict[Tuple[str, str], Dict[str, float]],
    output_path: Path,
) -> None:
    """Zapisuje tabelę delta candidate-baseline do CSV jako artefakt CI."""
    fieldnames = [
        "scenario_name",
        "config_name",
        "mode",
        "threshold_profile",
        "delta_point_precision_p95_px",
        "delta_jitter_p95_px",
        "delta_lost_frames",
        "delta_lost_tracks_total",
        "delta_false_detections_per_frame",
        "delta_fps",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            key = (str(row["scenario_name"]), str(row["config_name"]))
            baseline = baseline_rows.get(key)
            if baseline is None:
                continue
            writer.writerow(
                {
                    "scenario_name": row["scenario_name"],
                    "config_name": row["config_name"],
                    "mode": row["mode"],
                    "threshold_profile": row["threshold_profile"],
                    "delta_point_precision_p95_px": float(row["point_precision_p95_px"]) - baseline["point_precision_p95_px"],
                    "delta_jitter_p95_px": float(row["trajectory_jitter_p95_px"]) - baseline["trajectory_jitter_p95_px"],
                    "delta_lost_frames": float(row["lost_frames"]) - baseline["lost_frames"],
                    "delta_lost_tracks_total": float(row["lost_tracks_total"]) - baseline["lost_tracks_total"],
                    "delta_false_detections_per_frame": float(row["false_detections_per_frame"])
                    - baseline["false_detections_per_frame"],
                    "delta_fps": float(row["fps"]) - baseline["fps"],
                }
            )


def main() -> int:
    """Uruchamia pełny benchmark i zapisuje artefakty porównawcze CSV + Markdown."""
    args = parse_args()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    git_sha = current_git_sha()
    label = args.label or f"run_{timestamp}"

    scenarios = load_scenarios(Path(args.scenarios), limit=args.limit_scenarios)
    if args.scenario_tags:
        selected_tags = {tag.strip() for tag in args.scenario_tags if tag.strip()}
        scenarios = [item for item in scenarios if selected_tags.intersection(set(item.get("tags", [])))]
        if not scenarios:
            raise ValueError("Filtr --scenario-tags odfiltrował wszystkie scenariusze.")
    output_dir = Path(args.output_dir)
    run_dir = output_dir / f"{timestamp}_{label}"
    run_dir.mkdir(parents=True, exist_ok=True)

    rows: List[Dict[str, Any]] = []
    for scenario in scenarios:
        for config_name, config_values, baseline_config_name in fixed_benchmark_configs():
            print(f"[BENCH] scenario={scenario['name']} config={config_name}")
            result_row = run_single_case(
                scenario=scenario,
                config_name=config_name,
                config_values=config_values,
                baseline_config_name=baseline_config_name,
                run_dir=run_dir,
            )
            rows.append(
                {
                    "timestamp_utc": timestamp,
                    "label": label,
                    "git_sha": git_sha,
                    **result_row,
                }
            )

    csv_path = run_dir / "benchmark_summary.csv"
    md_path = run_dir / "benchmark_report.md"
    compare_md_path = run_dir / "baseline_vs_candidate.md"
    delta_csv_path = run_dir / "benchmark_delta.csv"
    write_csv(rows, csv_path)

    baseline_rows = load_baseline_rows(resolve_baseline_csv(args.baseline_csv, args.baseline_version))
    write_markdown_report(rows, md_path, baseline_rows=baseline_rows)
    threshold_profiles = load_threshold_profiles(Path(args.thresholds_file))
    threshold_eval = evaluate_thresholds(rows, baseline_rows, args.threshold_profile, threshold_profiles)
    write_comparison_report(rows, baseline_rows, threshold_eval, compare_md_path)
    write_delta_csv(rows, baseline_rows, delta_csv_path)

    print(f"[OK] CSV: {csv_path}")
    print(f"[OK] MD:  {md_path}")
    print(f"[OK] CMP: {compare_md_path}")
    print(f"[OK] DELTA CSV: {delta_csv_path}")
    if threshold_eval["checks_total"] > 0:
        print(
            f"[THRESHOLDS] profile={threshold_eval['profile_name']} "
            f"passed={threshold_eval['checks_passed']}/{threshold_eval['checks_total']}"
        )
    if threshold_eval["violations_warning"]:
        print(f"[THRESHOLDS] WARN: {len(threshold_eval['violations_warning'])} ostrzeżeń.")
    if args.enforce_thresholds and threshold_eval["violations_blocking"]:
        print("[THRESHOLDS] FAIL: wykryto naruszenia must-pass (blocking).")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
