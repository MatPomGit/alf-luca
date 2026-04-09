#!/usr/bin/env python3
"""CLI do wyboru klatek z szachownicą do kalibracji kamery.

Skrypt:
1) wczytuje plik MP4/MKV,
2) wyszukuje klatki zawierające tablicę szachownicy,
3) wybiera zestaw zróżnicowanych ujęć,
4) zapisuje obrazy do katalogu ``images_calib``.
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence, Tuple

import cv2
import numpy as np

ALLOWED_EXTENSIONS = {".mp4", ".mkv"}


@dataclass
class CandidateFrame:
    """Pojedyncza klatka kandydująca do zapisu kalibracyjnego."""

    frame_index: int
    image: np.ndarray
    feature_vector: np.ndarray
    sharpness: float


def parse_args() -> argparse.Namespace:
    """Buduje parser argumentów CLI i zwraca sparsowane opcje."""
    root_dir = Path(__file__).resolve().parent.parent

    parser = argparse.ArgumentParser(
        description=(
            "Wyodrębnia 25 zróżnicowanych klatek z tablicą szachownicy "
            "z pliku MP4/MKV i zapisuje je do images_calib."
        )
    )
    parser.add_argument("input_video", type=Path, help="Ścieżka do pliku wejściowego .mp4 lub .mkv")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=root_dir / "images_calib",
        help="Katalog docelowy na obrazy kalibracyjne (domyślnie: ./images_calib)",
    )
    parser.add_argument("--count", type=int, default=25, help="Liczba obrazów do zapisania (domyślnie: 25)")
    parser.add_argument(
        "--pattern-cols",
        type=int,
        default=9,
        help="Liczba wewnętrznych narożników szachownicy w poziomie (domyślnie: 9)",
    )
    parser.add_argument(
        "--pattern-rows",
        type=int,
        default=6,
        help="Liczba wewnętrznych narożników szachownicy w pionie (domyślnie: 6)",
    )
    parser.add_argument(
        "--sample-step",
        type=int,
        default=3,
        help="Co ile klatek wykonywać detekcję (domyślnie: 3)",
    )
    return parser.parse_args()


def validate_inputs(args: argparse.Namespace) -> None:
    """Sprawdza poprawność argumentów wejściowych i rzuca wyjątek przy błędzie."""
    if not args.input_video.exists():
        raise FileNotFoundError(f"Plik wejściowy nie istnieje: {args.input_video}")

    if args.input_video.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError("Obsługiwane są wyłącznie pliki .mp4 oraz .mkv.")

    if args.count <= 0:
        raise ValueError("Parametr --count musi być większy od 0.")

    if args.pattern_cols <= 1 or args.pattern_rows <= 1:
        raise ValueError("Wymiary wzorca muszą być większe od 1.")

    if args.sample_step <= 0:
        raise ValueError("Parametr --sample-step musi być większy od 0.")


def build_feature_vector(corners: np.ndarray, frame_size: Tuple[int, int], frame_index: int, frame_count: int) -> np.ndarray:
    """Tworzy wektor cech opisujący pozycję i orientację szachownicy na klatce.

    Cechy są znormalizowane do zakresów porównywalnych, aby algorytm doboru
    mógł premiować różnorodność pozycji tablicy w obrazie i w czasie nagrania.
    """
    width, height = frame_size
    points = corners.reshape(-1, 2)

    centroid_x = float(np.mean(points[:, 0]) / width)
    centroid_y = float(np.mean(points[:, 1]) / height)

    span_x = float((np.max(points[:, 0]) - np.min(points[:, 0])) / width)
    span_y = float((np.max(points[:, 1]) - np.min(points[:, 1])) / height)

    first = points[0]
    last = points[-1]
    angle = math.atan2(float(last[1] - first[1]), float(last[0] - first[0])) / math.pi

    time_position = float(frame_index / max(frame_count - 1, 1))

    return np.array([centroid_x, centroid_y, span_x, span_y, angle, time_position], dtype=np.float32)


def collect_candidates(
    video_path: Path,
    pattern_size: Tuple[int, int],
    sample_step: int,
) -> List[CandidateFrame]:
    """Przechodzi przez nagranie i zbiera klatki, gdzie wykryto szachownicę."""
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"Nie udało się otworzyć pliku wideo: {video_path}")

    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    frame_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    frame_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    frame_size = (frame_width, frame_height)

    detect_flags = cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE
    subpix_criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, 0.001)

    candidates: List[CandidateFrame] = []
    frame_index = 0

    while True:
        ok, frame = capture.read()
        if not ok:
            break

        if frame_index % sample_step != 0:
            frame_index += 1
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        found, corners = cv2.findChessboardCorners(gray, pattern_size, flags=detect_flags)

        if found and corners is not None:
            refined = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), subpix_criteria)
            feature_vector = build_feature_vector(refined, frame_size, frame_index, frame_count)
            sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())

            candidates.append(
                CandidateFrame(
                    frame_index=frame_index,
                    image=frame.copy(),
                    feature_vector=feature_vector,
                    sharpness=sharpness,
                )
            )

        frame_index += 1

    capture.release()
    return candidates


def weighted_distance(a: np.ndarray, b: np.ndarray) -> float:
    """Liczy ważony dystans euklidesowy między dwoma wektorami cech."""
    weights = np.array([1.3, 1.3, 0.9, 0.9, 0.8, 0.7], dtype=np.float32)
    diff = (a - b) * weights
    return float(np.sqrt(np.sum(diff * diff)))


def select_diverse_frames(candidates: Sequence[CandidateFrame], desired_count: int) -> List[CandidateFrame]:
    """Wybiera najbardziej zróżnicowany podzbiór klatek metodą greedy max-min."""
    if not candidates:
        return []

    selected: List[CandidateFrame] = []
    remaining: List[CandidateFrame] = list(candidates)

    # Najpierw wybieramy najostrzejszą klatkę jako mocny punkt startowy.
    seed = max(remaining, key=lambda item: item.sharpness)
    selected.append(seed)
    remaining.remove(seed)

    while remaining and len(selected) < desired_count:
        best_item = None
        best_score = -1.0

        for candidate in remaining:
            min_dist = min(weighted_distance(candidate.feature_vector, chosen.feature_vector) for chosen in selected)
            score = min_dist + 0.02 * candidate.sharpness
            if score > best_score:
                best_score = score
                best_item = candidate

        if best_item is None:
            break

        selected.append(best_item)
        remaining.remove(best_item)

    selected.sort(key=lambda item: item.frame_index)
    return selected


def save_frames(frames: Sequence[CandidateFrame], output_dir: Path) -> None:
    """Zapisuje wybrane klatki jako pliki PNG w katalogu docelowym."""
    output_dir.mkdir(parents=True, exist_ok=True)

    for idx, frame in enumerate(frames, start=1):
        out_path = output_dir / f"calib_{idx:02d}_frame_{frame.frame_index:06d}.png"
        ok = cv2.imwrite(str(out_path), frame.image)
        if not ok:
            raise RuntimeError(f"Nie udało się zapisać obrazu: {out_path}")


def main() -> int:
    """Punkt wejścia programu CLI."""
    args = parse_args()

    try:
        validate_inputs(args)
        pattern_size = (args.pattern_cols, args.pattern_rows)

        print(f"[INFO] Analiza wideo: {args.input_video}")
        candidates = collect_candidates(args.input_video, pattern_size, args.sample_step)
        print(f"[INFO] Liczba klatek z wykrytą szachownicą: {len(candidates)}")

        if not candidates:
            print("[BŁĄD] Nie znaleziono żadnej klatki z wykrytą szachownicą.")
            return 2

        selected = select_diverse_frames(candidates, args.count)
        save_frames(selected, args.output_dir)

        print(f"[INFO] Zapisano {len(selected)} obrazów do: {args.output_dir}")
        if len(selected) < args.count:
            print(
                "[UWAGA] Zapisano mniej obrazów niż żądano, "
                "ponieważ w materiale wykryto za mało unikalnych ujęć szachownicy."
            )

        return 0
    except Exception as exc:  # noqa: BLE001 - czytelny komunikat CLI dla użytkownika końcowego
        print(f"[BŁĄD] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
