#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
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
        "--limit-scenarios",
        type=int,
        default=None,
        help="Opcjonalny limit liczby scenariuszy (przydatne do szybkiego smoke testu).",
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
            }
        )

    return normalized[:limit] if limit is not None else normalized


def fixed_benchmark_configs() -> List[Tuple[str, Dict[str, Any]]]:
    """Zwraca stałe konfiguracje benchmarkowe do porównania jakości pipeline'u."""
    return [
        (
            "baseline_fixed",
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
        ),
        (
            "robust_temporal_kalman",
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


def compute_metrics(result: Dict[str, Any]) -> Dict[str, float]:
    """Oblicza metryki benchmarkowe wymagane do porównań przed/po zmianach."""
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

    kalman_predicted_frames = sum(int(getattr(point, "kalman_predicted", 0) == 1) for point in main_points)

    return {
        "frames_total": float(frame_count),
        "main_detections": float(len(main_detected)),
        "false_detections_per_frame": safe_ratio(false_detections_total, frame_count),
        "stable_track_len_frames": float(longest_detected_run(main_points)),
        "track_id_switches": float(count_track_switches(finished_tracks)),
        "kalman_predicted_share": safe_ratio(kalman_predicted_frames, frame_count),
    }


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

    pipeline_config = PipelineConfig(
        video=str(video_path),
        output_csv=str(output_csv),
        all_tracks_csv=str(all_tracks_csv),
        **config_values,
    )

    # Uruchamiamy pipeline bez ciężkich artefaktów (bez PDF/PNG/wideo), tylko dane liczbowe.
    result = process_video_frames(pipeline_config)
    if bool(config_values.get("use_kalman", False)):
        apply_kalman_to_points(
            result["main_points"],
            process_noise=pipeline_config.kalman.process_noise,
            measurement_noise=pipeline_config.kalman.measurement_noise,
        )

    save_track_csv(result["main_points"], str(output_csv))
    if pipeline_config.multi_track:
        save_all_tracks_csv(result["finished_tracks"], str(all_tracks_csv))

    metrics = compute_metrics(result)
    return {
        "scenario_name": scenario_name,
        "video": str(video_path),
        "tags": ",".join(scenario.get("tags", [])),
        "config_name": config_name,
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
        "config_name",
        "frames_total",
        "main_detections",
        "false_detections_per_frame",
        "stable_track_len_frames",
        "track_id_switches",
        "kalman_predicted_share",
        "config_json",
    ]

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows_list:
            writer.writerow(row)


def write_markdown_report(rows: Sequence[Dict[str, Any]], report_path: Path) -> None:
    """Generuje krótki raport Markdown z tabelą metryk do szybkiego porównania."""
    lines: List[str] = []
    lines.append("# Raport benchmarku jakości śledzenia")
    lines.append("")
    lines.append("## Metryki")
    lines.append("")
    lines.append("- `false_detections_per_frame`: proxy liczby fałszywych detekcji na klatkę (niżej = lepiej).")
    lines.append("- `stable_track_len_frames`: najdłuższa seria kolejnych detekcji głównego toru (wyżej = lepiej).")
    lines.append("- `track_id_switches`: liczba przełączeń dominującego `track_id` między klatkami (niżej = lepiej).")
    lines.append("- `kalman_predicted_share`: udział klatek z `kalman_predicted=1` w torze głównym (kontekstowo).")
    lines.append("")
    lines.append("## Wyniki")
    lines.append("")
    lines.append("| scenario | config | false/frame | stable_len | switches | kalman_share |")
    lines.append("|---|---:|---:|---:|---:|---:|")

    for row in rows:
        lines.append(
            "| {scenario} | {config} | {false_rate:.4f} | {stable_len:.0f} | {switches:.0f} | {kalman_share:.4f} |".format(
                scenario=row["scenario_name"],
                config=row["config_name"],
                false_rate=float(row["false_detections_per_frame"]),
                stable_len=float(row["stable_track_len_frames"]),
                switches=float(row["track_id_switches"]),
                kalman_share=float(row["kalman_predicted_share"]),
            )
        )

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    """Uruchamia pełny benchmark i zapisuje artefakty porównawcze CSV + Markdown."""
    args = parse_args()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    git_sha = current_git_sha()
    label = args.label or f"run_{timestamp}"

    scenarios = load_scenarios(Path(args.scenarios), limit=args.limit_scenarios)
    output_dir = Path(args.output_dir)
    run_dir = output_dir / f"{timestamp}_{label}"
    run_dir.mkdir(parents=True, exist_ok=True)

    rows: List[Dict[str, Any]] = []
    for scenario in scenarios:
        for config_name, config_values in fixed_benchmark_configs():
            print(f"[BENCH] scenario={scenario['name']} config={config_name}")
            result_row = run_single_case(
                scenario=scenario,
                config_name=config_name,
                config_values=config_values,
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
    write_csv(rows, csv_path)
    write_markdown_report(rows, md_path)

    print(f"[OK] CSV: {csv_path}")
    print(f"[OK] MD:  {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
