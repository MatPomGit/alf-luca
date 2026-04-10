from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from luca_types import TrackPoint

try:
    from luca_processing.kalman import smooth_xy_sequence
except Exception:
    smooth_xy_sequence = None


@dataclass
class KalmanConfig:
    """Parametry wygładzania Kalmana w trybie modułowym i standalone."""

    process_noise: float = 3e-2
    measurement_noise: float = 5e-2


def apply_kalman_to_points(points: Sequence[TrackPoint], process_noise: float, measurement_noise: float):
    """Wygładza sekwencję punktów filtrem Kalmana, zachowując brakujące pomiary."""
    if smooth_xy_sequence is None or not points:
        return

    sequence = []
    for point in points:
        if point.x is None or point.y is None:
            sequence.append(None)
        else:
            sequence.append((float(point.x), float(point.y)))

    smoothed = smooth_xy_sequence(
        sequence,
        process_noise=process_noise,
        measurement_noise=measurement_noise,
    )

    for point, result in zip(points, smoothed):
        sx, sy, predicted = result
        if sx is not None and sy is not None:
            point.x = float(sx)
            point.y = float(sy)
        point.kalman_predicted = int(bool(predicted))


def smooth_xy_with_config(
    sequence: Sequence[Optional[Tuple[float, float]]],
    config: KalmanConfig,
) -> Sequence[Tuple[Optional[float], Optional[float], bool]]:
    """Wygładza surową sekwencję XY poza modelem TrackPoint."""
    if smooth_xy_sequence is None:
        raise RuntimeError("Kalman backend is unavailable (missing luca_tracker.kalman dependency).")
    return smooth_xy_sequence(
        sequence,
        process_noise=config.process_noise,
        measurement_noise=config.measurement_noise,
    )


def _build_parser() -> argparse.ArgumentParser:
    """Tworzy parser CLI do standalone wygładzania ścieżki XY z CSV."""
    parser = argparse.ArgumentParser(description="Standalone Kalman smoothing for XY CSV.")
    parser.add_argument("--input_csv", required=True, help="Input CSV with x,y columns.")
    parser.add_argument("--output_csv", required=True, help="Output CSV path.")
    parser.add_argument("--process_noise", type=float, default=3e-2)
    parser.add_argument("--measurement_noise", type=float, default=5e-2)
    return parser


def _load_xy(path: str) -> List[Optional[Tuple[float, float]]]:
    """Wczytuje punkty XY z CSV, dopuszczając puste wartości."""
    sequence: List[Optional[Tuple[float, float]]] = []
    with Path(path).open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            x = row.get("x")
            y = row.get("y")
            if not x or not y:
                sequence.append(None)
                continue
            sequence.append((float(x), float(y)))
    return sequence


def _save_smoothed(path: str, smoothed: Sequence[Tuple[Optional[float], Optional[float], bool]]) -> None:
    """Zapisuje wygładzone dane XY wraz z flagą predykcji do CSV."""
    with Path(path).open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["x", "y", "kalman_predicted"])
        writer.writeheader()
        for x, y, predicted in smoothed:
            writer.writerow(
                {
                    "x": "" if x is None else x,
                    "y": "" if y is None else y,
                    "kalman_predicted": int(bool(predicted)),
                }
            )


def main(argv: Optional[List[str]] = None) -> int:
    """Punkt wejścia standalone: wygładza CSV z punktami XY."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    config = KalmanConfig(
        process_noise=args.process_noise,
        measurement_noise=args.measurement_noise,
    )

    sequence = _load_xy(args.input_csv)
    smoothed = smooth_xy_with_config(sequence, config)
    _save_smoothed(args.output_csv, smoothed)
    print(f"Saved smoothed sequence: {args.output_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
