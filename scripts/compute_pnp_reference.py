from __future__ import annotations

import argparse
import glob
import os
import sys
from pathlib import Path

import cv2
import numpy as np


def _build_object_points(rows: int, cols: int, square_size: float) -> np.ndarray:
    objp = np.zeros((rows * cols, 3), np.float32)
    objp[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2)
    objp *= float(square_size)
    return objp


def _find_best_chessboard_image(calib_dir: Path, rows: int, cols: int) -> tuple[Path, np.ndarray, int, int]:
    images: list[Path] = []
    for pattern in ("*.png", "*.jpg", "*.jpeg", "*.bmp"):
        images.extend(Path(p) for p in glob.glob(str(calib_dir / pattern)))
    if not images:
        raise FileNotFoundError(f"Brak obrazow kalibracyjnych w katalogu: {calib_dir}")

    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
    best_score = -1.0
    best_match: tuple[Path, np.ndarray, int, int] | None = None

    def register_match(image_path: Path, candidate_cols: int, candidate_rows: int) -> None:
        nonlocal best_score, best_match
        image = cv2.imread(str(image_path))
        if image is None:
            return
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        ok, corners = cv2.findChessboardCorners(gray, (candidate_cols, candidate_rows), None)
        if not ok:
            return
        corners2 = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
        # Preferujemy ujęcie z największym polem projekcji planszy.
        x, y, w, h = cv2.boundingRect(corners2.reshape(-1, 1, 2).astype(np.float32))
        score = float(w * h)
        if score > best_score:
            best_score = score
            best_match = (image_path, corners2, candidate_rows, candidate_cols)

    for image_path in sorted(images):
        register_match(image_path=image_path, candidate_cols=cols, candidate_rows=rows)

    if best_match is None:
        for image_path in sorted(images)[:5]:
            for candidate_cols in range(4, 13):
                for candidate_rows in range(4, 13):
                    register_match(image_path=image_path, candidate_cols=candidate_cols, candidate_rows=candidate_rows)

    if best_match is None:
        raise RuntimeError(
            f"Nie znaleziono wzorca szachownicy w katalogu: {calib_dir}. "
            f"Sprawdzono domyslne {cols}x{rows} oraz automatyczne wykrywanie."
        )
    return best_match


def _format_points(points: np.ndarray, dims: int) -> str:
    chunks: list[str] = []
    for point in points:
        values = [f"{float(value):.6f}".rstrip("0").rstrip(".") for value in point[:dims]]
        chunks.append(",".join(values))
    return ";".join(chunks)


def _build_output(fmt: str, object_points: str, image_points: str, source_image: str) -> str:
    if fmt == "shell":
        return "\n".join(
            [
                f'export LUCA_PNP_OBJECT_POINTS="{object_points}"',
                f'export LUCA_PNP_IMAGE_POINTS="{image_points}"',
                f'export LUCA_PNP_SOURCE_IMAGE="{source_image}"',
            ]
        )
    if fmt == "cmd":
        return "\n".join(
            [
                f'set "LUCA_PNP_OBJECT_POINTS={object_points}"',
                f'set "LUCA_PNP_IMAGE_POINTS={image_points}"',
                f'set "LUCA_PNP_SOURCE_IMAGE={source_image}"',
            ]
        )
    raise ValueError(f"Nieobslugiwany format wyjscia: {fmt}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Wylicza referencje PnP z obrazow szachownicy i wypisuje je jako zmienne srodowiskowe."
    )
    parser.add_argument("--calib-dir", default="images_calib", help="Katalog z obrazami szachownicy.")
    parser.add_argument("--rows", type=int, default=7, help="Liczba wewnetrznych naroznikow w wierszu.")
    parser.add_argument("--cols", type=int, default=10, help="Liczba wewnetrznych naroznikow w kolumnie.")
    parser.add_argument("--square-size", type=float, default=1.0, help="Rozmiar pola szachownicy.")
    parser.add_argument("--format", choices=["shell", "cmd"], required=True, help="Format wyjscia dla skryptow.")
    args = parser.parse_args()

    calib_dir = Path(args.calib_dir)
    source_image, image_points, detected_rows, detected_cols = _find_best_chessboard_image(
        calib_dir=calib_dir,
        rows=args.rows,
        cols=args.cols,
    )
    object_points = _build_object_points(rows=detected_rows, cols=detected_cols, square_size=args.square_size)

    object_points_text = _format_points(object_points, dims=3)
    image_points_text = _format_points(image_points.reshape(-1, 2), dims=2)
    print(
        (
            f"[INFO] Wyliczono referencje PnP z obrazu: "
            f"{source_image.relative_to(Path.cwd()) if source_image.is_absolute() else source_image} "
            f"| pattern={detected_cols}x{detected_rows}"
        ),
        file=sys.stderr,
    )
    print(_build_output(args.format, object_points_text, image_points_text, str(source_image)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
