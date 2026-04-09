#!/usr/bin/env python3
"""Porównywanie plików pomiarowych CSV i generowanie wykresów."""

from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence

import matplotlib.pyplot as plt


@dataclass
class MeasurementFile:
    path: Path
    rows: List[Dict[str, str]]


@dataclass
class SeriesData:
    x: List[float]
    y: List[float]


def parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        val = float(text)
    except ValueError:
        return None
    if not math.isfinite(val):
        return None
    return val


def load_measurement_csv(path: Path) -> MeasurementFile:
    if not path.exists():
        raise FileNotFoundError(f"Brak pliku: {path}")

    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"Plik {path} nie ma nagłówka CSV.")
        rows = list(reader)

    if not rows:
        raise ValueError(f"Plik {path} nie zawiera danych.")

    return MeasurementFile(path=path, rows=rows)


def detect_numeric_columns(data: MeasurementFile, sample_size: int = 100) -> List[str]:
    fieldnames = list(data.rows[0].keys())
    candidates: List[str] = []
    sample = data.rows[:sample_size]

    for name in fieldnames:
        ok = 0
        total = 0
        for row in sample:
            total += 1
            if parse_float(row.get(name)) is not None:
                ok += 1
        if total > 0 and ok / total >= 0.8:
            candidates.append(name)

    return candidates


def extract_series(data: MeasurementFile, x_col: str, y_col: str) -> SeriesData:
    xs: List[float] = []
    ys: List[float] = []

    for idx, row in enumerate(data.rows):
        x_val = parse_float(row.get(x_col))
        if x_val is None:
            x_val = float(idx)

        y_val = parse_float(row.get(y_col))
        if y_val is None:
            continue

        xs.append(x_val)
        ys.append(y_val)

    if not ys:
        raise ValueError(f"Kolumna '{y_col}' w pliku {data.path} nie zawiera danych numerycznych.")

    return SeriesData(x=xs, y=ys)


def common_columns(files: Sequence[MeasurementFile]) -> List[str]:
    common = set(files[0].rows[0].keys())
    for measurement in files[1:]:
        common &= set(measurement.rows[0].keys())
    return sorted(common)


def choose_columns(files: Sequence[MeasurementFile], x_col: str | None, y_cols: Sequence[str] | None) -> tuple[str, List[str]]:
    shared = common_columns(files)
    if not shared:
        raise ValueError("Brak wspólnych kolumn pomiędzy podanymi plikami CSV.")

    if x_col is None:
        x_col = "frame" if "frame" in shared else shared[0]
    elif x_col not in shared:
        raise ValueError(f"Kolumna osi X '{x_col}' nie występuje we wszystkich plikach.")

    if y_cols:
        missing = [name for name in y_cols if name not in shared]
        if missing:
            raise ValueError(f"Brak kolumn Y w części plików: {', '.join(missing)}")
        picked = list(y_cols)
    else:
        numeric_sets = [set(detect_numeric_columns(item)) for item in files]
        numeric_shared = sorted(set.intersection(*numeric_sets)) if numeric_sets else []
        picked = [name for name in numeric_shared if name != x_col]
        if not picked:
            raise ValueError(
                "Nie podano --y-cols i nie udało się wykryć wspólnych kolumn numerycznych. "
                "Wskaż je ręcznie przez --y-cols."
            )

    return x_col, picked


def save_single_plot(files: Sequence[MeasurementFile], x_col: str, y_col: str, output_png: Path) -> None:
    fig, ax = plt.subplots(figsize=(11, 6))
    for measurement in files:
        series = extract_series(measurement, x_col=x_col, y_col=y_col)
        ax.plot(series.x, series.y, label=measurement.path.name, linewidth=1.5)

    ax.set_title(f"Porównanie pomiarów: {y_col}")
    ax.set_xlabel(x_col)
    ax.set_ylabel(y_col)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(output_png, dpi=150)
    plt.close(fig)


def save_difference_plot(
    base: MeasurementFile,
    candidate: MeasurementFile,
    x_col: str,
    y_col: str,
    output_png: Path,
) -> None:
    base_series = extract_series(base, x_col=x_col, y_col=y_col)
    cand_series = extract_series(candidate, x_col=x_col, y_col=y_col)

    size = min(len(base_series.y), len(cand_series.y))
    if size == 0:
        raise ValueError(f"Brak wspólnych punktów do porównania dla kolumny {y_col}.")

    x_vals = base_series.x[:size]
    diff = [cand_series.y[i] - base_series.y[i] for i in range(size)]

    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.plot(x_vals, diff, label=f"{candidate.path.name} - {base.path.name}", linewidth=1.5)
    ax.axhline(0.0, color="black", linestyle="--", linewidth=1)
    ax.set_title(f"Różnica przebiegów: {y_col}")
    ax.set_xlabel(x_col)
    ax.set_ylabel("różnica")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(output_png, dpi=150)
    plt.close(fig)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Porównuje pliki pomiarowe CSV i zapisuje wykresy do katalogu wyjściowego. "
            "Pierwszy plik traktowany jest jako referencja dla wykresów różnicowych."
        )
    )
    parser.add_argument("files", nargs="+", help="Ścieżki do plików CSV (minimum 2).")
    parser.add_argument("--x-col", help="Kolumna osi X (domyślnie: frame lub pierwsza wspólna).")
    parser.add_argument(
        "--y-cols",
        nargs="+",
        help="Kolumny Y do porównania (domyślnie: automatyczne wykrywanie wspólnych numerycznych).",
    )
    parser.add_argument("--output-dir", default="output/compare_plots", help="Katalog na wykresy PNG.")
    parser.add_argument("--show", action="store_true", help="Pokaż interaktywnie ostatni wykres.")
    return parser.parse_args(argv)


def run(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if len(args.files) < 2:
        raise ValueError("Podaj co najmniej 2 pliki CSV do porównania.")

    files = [load_measurement_csv(Path(path)) for path in args.files]
    x_col, y_cols = choose_columns(files, x_col=args.x_col, y_cols=args.y_cols)

    output_dir = Path(args.output_dir)
    ensure_dir(output_dir)

    print("[INFO] Wspólna kolumna X:", x_col)
    print("[INFO] Porównywane kolumny Y:", ", ".join(y_cols))

    base = files[0]
    for y_col in y_cols:
        compare_png = output_dir / f"compare_{y_col}.png"
        save_single_plot(files, x_col=x_col, y_col=y_col, output_png=compare_png)
        print(f"[OK] Zapisano wykres porównawczy: {compare_png}")

        for candidate in files[1:]:
            diff_png = output_dir / f"diff_{y_col}_{candidate.path.stem}_vs_{base.path.stem}.png"
            save_difference_plot(base, candidate, x_col=x_col, y_col=y_col, output_png=diff_png)
            print(f"[OK] Zapisano wykres różnicowy: {diff_png}")

    if args.show:
        plt.show()

    return 0


if __name__ == "__main__":
    raise SystemExit(run())
