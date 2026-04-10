from __future__ import annotations

import glob
import os

import cv2
import numpy as np


class _ProgressBar:
    """Prosty pasek postępu dla długich zadań kalibracji uruchamianych w terminalu."""

    def __init__(self, total: int | None, label: str, width: int = 30) -> None:
        # Pasek działa również dla niepełnej liczby kroków, ale w kalibracji zwykle ją znamy.
        self.total = total if total and total > 0 else None
        self.label = label
        self.width = width
        self.current = 0

    def update(self, value: int) -> None:
        """Aktualizuje licznik i wypisuje pojedynczą linię postępu."""
        self.current = max(0, value)
        if not self.total:
            print(f"\r{self.label}: {self.current}", end="", flush=True)
            return
        ratio = min(1.0, self.current / self.total)
        done = int(ratio * self.width)
        bar = "#" * done + "-" * (self.width - done)
        percent = int(ratio * 100)
        print(f"\r{self.label}: [{bar}] {percent:3d}% ({self.current}/{self.total})", end="", flush=True)

    def close(self) -> None:
        """Domyka renderowanie paska postępu nową linią."""
        print()


def calibrate_camera(calib_dir: str, rows: int, cols: int, square_size: float, output_file: str) -> None:
    """Kalibruje kamerę na podstawie wzorca szachownicy i zapisuje parametry do pliku `.npz`."""
    # Budujemy referencyjną siatkę 3D punktów wzorca (w jednostkach `square_size`).
    objp = np.zeros((rows * cols, 3), np.float32)
    objp[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2)
    objp *= square_size

    objpoints = []
    imgpoints = []

    images: list[str] = []
    for pattern in ("*.png", "*.jpg", "*.jpeg", "*.bmp"):
        images.extend(glob.glob(os.path.join(calib_dir, pattern)))

    if not images:
        raise FileNotFoundError(f"Brak obrazów kalibracyjnych w katalogu: {calib_dir}")

    progress = _ProgressBar(total=len(images), label="Kalibracja")
    gray_shape = None
    for image_index, fname in enumerate(images, start=1):
        image = cv2.imread(fname)
        if image is None:
            progress.update(image_index)
            continue
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        ok, corners = cv2.findChessboardCorners(gray, (cols, rows), None)
        if not ok:
            print(f"[INFO] Pominięto {fname} - nie znaleziono narożników.")
            progress.update(image_index)
            continue

        # Doprecyzowanie narożników poprawia stabilność końcowej macierzy kamery.
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
        corners2 = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
        objpoints.append(objp)
        imgpoints.append(corners2)
        gray_shape = gray.shape[::-1]
        progress.update(image_index)
    progress.close()

    if not objpoints or gray_shape is None:
        raise RuntimeError("Nie udało się znaleźć wzorca na żadnym obrazie.")

    _, camera_matrix, dist_coeffs, _, _ = cv2.calibrateCamera(objpoints, imgpoints, gray_shape, None, None)
    np.savez(output_file, camera_matrix=camera_matrix, dist_coeffs=dist_coeffs)
    print(f"[OK] Zapisano kalibrację do: {output_file}")
