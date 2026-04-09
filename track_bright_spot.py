#!/usr/bin/env python3
"""
Terminalowy program do:
1) kalibracji kamery na podstawie zdjęć szachownicy,
2) śledzenia jasnej plamki światła w pliku MP4,
3) śledzenia plamki o konkretnym kolorze,
4) eksportu wyników do CSV,
5) porównywania dwóch plików CSV w celu oceny jakości śledzenia.

Przykłady:
  python track_bright_spot_v2.py calibrate --calib_dir ./calib --rows 6 --cols 9 --output_file camera_calib.npz

  python track_bright_spot_v2.py track --video film.mp4 --track_mode brightest --threshold 210 --output_csv wynik.csv --display

  python track_bright_spot_v2.py track --video film.mp4 --track_mode color --color_name red --output_csv wynik_color.csv

  python track_bright_spot_v2.py track --video film.mp4 --interactive --output_csv wynik.csv

  python track_bright_spot_v2.py compare --reference ref.csv --candidate test.csv --output_csv raport_porownania.csv
"""

from __future__ import annotations

import argparse
import csv
import glob
import math
import os
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import cv2
import numpy as np


PRESET_HSV_RANGES = {
    "red": [((0, 80, 80), (10, 255, 255)), ((170, 80, 80), (180, 255, 255))],
    "green": [((35, 50, 50), (90, 255, 255))],
    "blue": [((90, 50, 50), (140, 255, 255))],
    "yellow": [((15, 70, 70), (40, 255, 255))],
    "white": [((0, 0, 180), (180, 70, 255))],
    "orange": [((8, 80, 80), (22, 255, 255))],
    "purple": [((125, 50, 50), (165, 255, 255))],
}


CSV_FIELDS = [
    "frame_index",
    "time_sec",
    "detected",
    "track_mode",
    "color_name",
    "center_x",
    "center_y",
    "area",
    "perimeter",
    "radius",
    "bbox_x",
    "bbox_y",
    "bbox_w",
    "bbox_h",
    "aspect_ratio",
    "circularity",
    "mean_gray",
    "max_gray",
    "mean_b",
    "mean_g",
    "mean_r",
    "score",
]


@dataclass
class TrackerConfig:
    video: str
    calib_file: Optional[str]
    track_mode: str
    blur: int
    threshold: int
    erode_iter: int
    dilate_iter: int
    min_area: float
    max_area: Optional[float]
    color_name: Optional[str]
    hsv_ranges: List[Tuple[Tuple[int, int, int], Tuple[int, int, int]]]
    output_csv: str
    display: bool
    roi: Optional[Tuple[int, int, int, int]] = None


def parse_hsv_triplet(value: str) -> Tuple[int, int, int]:
    parts = [p.strip() for p in value.split(",")]
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("HSV musi mieć format H,S,V")
    try:
        vals = tuple(int(p) for p in parts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("HSV musi zawierać liczby całkowite") from exc
    h, s, v = vals
    if not (0 <= h <= 180 and 0 <= s <= 255 and 0 <= v <= 255):
        raise argparse.ArgumentTypeError("Zakres HSV: H 0..180, S 0..255, V 0..255")
    return vals  # type: ignore[return-value]


def parse_roi(value: str) -> Tuple[int, int, int, int]:
    parts = [p.strip() for p in value.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("ROI musi mieć format x,y,w,h")
    vals = tuple(int(p) for p in parts)
    x, y, w, h = vals
    if w <= 0 or h <= 0:
        raise argparse.ArgumentTypeError("w i h muszą być dodatnie")
    return vals  # type: ignore[return-value]


def ask_text(prompt: str, default: Optional[str] = None) -> str:
    suffix = f" [{default}]" if default is not None else ""
    raw = input(f"{prompt}{suffix}: ").strip()
    if raw == "" and default is not None:
        return default
    return raw


def ask_int(prompt: str, default: int, min_value: Optional[int] = None, max_value: Optional[int] = None) -> int:
    while True:
        raw = ask_text(prompt, str(default))
        try:
            value = int(raw)
        except ValueError:
            print("Podaj liczbę całkowitą.")
            continue
        if min_value is not None and value < min_value:
            print(f"Wartość musi być >= {min_value}.")
            continue
        if max_value is not None and value > max_value:
            print(f"Wartość musi być <= {max_value}.")
            continue
        return value


def ask_float(prompt: str, default: float, min_value: Optional[float] = None) -> float:
    while True:
        raw = ask_text(prompt, str(default))
        try:
            value = float(raw)
        except ValueError:
            print("Podaj liczbę.")
            continue
        if min_value is not None and value < min_value:
            print(f"Wartość musi być >= {min_value}.")
            continue
        return value


def ask_yes_no(prompt: str, default: bool = False) -> bool:
    default_txt = "t" if default else "n"
    while True:
        raw = ask_text(f"{prompt} (t/n)", default_txt).lower()
        if raw in {"t", "tak", "y", "yes"}:
            return True
        if raw in {"n", "nie", "no"}:
            return False
        print("Wpisz 't' albo 'n'.")


def ask_optional_float(prompt: str, default: Optional[float] = None) -> Optional[float]:
    default_txt = "" if default is None else str(default)
    raw = ask_text(f"{prompt} (puste = brak)", default_txt).strip()
    if raw == "":
        return None
    try:
        value = float(raw)
    except ValueError:
        print("Niepoprawna liczba. Ustawiono brak limitu.")
        return None
    return value


def get_hsv_ranges_from_args_or_name(color_name: Optional[str], hsv_lower: Optional[Tuple[int, int, int]], hsv_upper: Optional[Tuple[int, int, int]]) -> List[Tuple[Tuple[int, int, int], Tuple[int, int, int]]]:
    if hsv_lower is not None and hsv_upper is not None:
        return [(hsv_lower, hsv_upper)]
    if color_name:
        preset = PRESET_HSV_RANGES.get(color_name.lower())
        if preset is None:
            valid = ", ".join(sorted(PRESET_HSV_RANGES))
            raise ValueError(f"Nieznany preset koloru: {color_name}. Dostępne: {valid}")
        return preset
    return []


def interactive_configure_track(args: argparse.Namespace) -> TrackerConfig:
    print("\n=== Interaktywna konfiguracja śledzenia ===")
    track_mode = ask_text("Tryb śledzenia: brightest / color", args.track_mode or "brightest").lower().strip()
    if track_mode not in {"brightest", "color"}:
        print("Nieznany tryb. Ustawiono 'brightest'.")
        track_mode = "brightest"

    blur = ask_int("Rozmiar filtra Gaussa (nieparzysty)", args.blur, min_value=1)
    threshold = ask_int("Próg jasności 0..255", args.threshold, min_value=0, max_value=255)
    erode_iter = ask_int("Liczba erozji", args.erode_iter, min_value=0)
    dilate_iter = ask_int("Liczba dylatacji", args.dilate_iter, min_value=0)
    min_area = ask_float("Minimalna powierzchnia plamki", args.min_area, min_value=0.0)
    max_area = ask_optional_float("Maksymalna powierzchnia plamki", args.max_area)

    roi = args.roi
    if ask_yes_no("Czy ograniczyć analizę do ROI?", default=roi is not None):
        x = ask_int("ROI x", roi[0] if roi else 0, min_value=0)
        y = ask_int("ROI y", roi[1] if roi else 0, min_value=0)
        w = ask_int("ROI w", roi[2] if roi else 200, min_value=1)
        h = ask_int("ROI h", roi[3] if roi else 200, min_value=1)
        roi = (x, y, w, h)
    else:
        roi = None

    color_name = args.color_name
    hsv_ranges: List[Tuple[Tuple[int, int, int], Tuple[int, int, int]]] = []
    if track_mode == "color":
        available = ", ".join(sorted(PRESET_HSV_RANGES))
        print(f"Dostępne presety kolorów: {available}")
        if ask_yes_no("Użyć presetu koloru?", default=True):
            color_name = ask_text("Nazwa koloru", color_name or "red").lower()
            hsv_ranges = get_hsv_ranges_from_args_or_name(color_name, None, None)
        else:
            print("Podaj zakres HSV dolny i górny.")
            lower = parse_hsv_triplet(ask_text("Dolny HSV", "0,80,80"))
            upper = parse_hsv_triplet(ask_text("Górny HSV", "10,255,255"))
            hsv_ranges = [(lower, upper)]
            color_name = "custom"
    else:
        color_name = None

    display = args.display or ask_yes_no("Pokazać okno podglądu podczas śledzenia?", default=args.display)

    return TrackerConfig(
        video=args.video,
        calib_file=args.calib_file,
        track_mode=track_mode,
        blur=blur,
        threshold=threshold,
        erode_iter=erode_iter,
        dilate_iter=dilate_iter,
        min_area=min_area,
        max_area=max_area,
        color_name=color_name,
        hsv_ranges=hsv_ranges,
        output_csv=args.output_csv,
        display=display,
        roi=roi,
    )


def build_tracker_config(args: argparse.Namespace) -> TrackerConfig:
    if args.interactive:
        return interactive_configure_track(args)

    track_mode = args.track_mode
    hsv_ranges = get_hsv_ranges_from_args_or_name(args.color_name, args.hsv_lower, args.hsv_upper)

    if track_mode == "color" and not hsv_ranges:
        raise ValueError("Dla trybu 'color' podaj --color_name albo --hsv_lower i --hsv_upper.")

    return TrackerConfig(
        video=args.video,
        calib_file=args.calib_file,
        track_mode=track_mode,
        blur=args.blur,
        threshold=args.threshold,
        erode_iter=args.erode_iter,
        dilate_iter=args.dilate_iter,
        min_area=args.min_area,
        max_area=args.max_area,
        color_name=args.color_name,
        hsv_ranges=hsv_ranges,
        output_csv=args.output_csv,
        display=args.display,
        roi=args.roi,
    )


def calibrate_camera(
    calib_dir: str,
    pattern_rows: int,
    pattern_cols: int,
    square_size: float,
    output_file: str,
) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    objp = np.zeros((pattern_rows * pattern_cols, 3), np.float32)
    objp[:, :2] = np.mgrid[0:pattern_cols, 0:pattern_rows].T.reshape(-1, 2)
    objp *= square_size

    objpoints: List[np.ndarray] = []
    imgpoints: List[np.ndarray] = []

    patterns = ["*.png", "*.jpg", "*.jpeg", "*.bmp"]
    images: List[str] = []
    for pattern in patterns:
        images.extend(glob.glob(os.path.join(calib_dir, pattern)))

    if not images:
        print(f"[ERROR] Nie znaleziono obrazów kalibracyjnych w: {calib_dir}")
        return None

    gray_shape: Optional[Tuple[int, int]] = None
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)

    for fname in sorted(images):
        img = cv2.imread(fname)
        if img is None:
            print(f"[WARNING] Nie można odczytać pliku: {fname}")
            continue

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        found, corners = cv2.findChessboardCorners(gray, (pattern_cols, pattern_rows), None)
        if not found:
            print(f"[INFO] Nie wykryto narożników w: {fname}")
            continue

        corners2 = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
        objpoints.append(objp.copy())
        imgpoints.append(corners2)
        gray_shape = gray.shape[::-1]

    if not objpoints or gray_shape is None:
        print("[ERROR] Kalibracja nieudana: brak poprawnie wykrytych wzorców.")
        return None

    ok, camera_matrix, dist_coeffs, _, _ = cv2.calibrateCamera(objpoints, imgpoints, gray_shape, None, None)
    if not ok:
        print("[ERROR] cv2.calibrateCamera zwróciło błąd.")
        return None

    np.savez(output_file, camera_matrix=camera_matrix, dist_coeffs=dist_coeffs)
    print(f"[INFO] Kalibracja zakończona. Zapisano: {output_file}")
    print("[INFO] camera_matrix =")
    print(camera_matrix)
    print("[INFO] dist_coeffs =")
    print(dist_coeffs)
    return camera_matrix, dist_coeffs


def load_calibration(calib_file: Optional[str]) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    if not calib_file:
        return None, None
    try:
        data = np.load(calib_file)
        return data["camera_matrix"], data["dist_coeffs"]
    except Exception as exc:
        print(f"[WARNING] Nie udało się wczytać kalibracji {calib_file}: {exc}")
        return None, None


def crop_roi(frame: np.ndarray, roi: Optional[Tuple[int, int, int, int]]) -> Tuple[np.ndarray, Tuple[int, int]]:
    if roi is None:
        return frame, (0, 0)
    x, y, w, h = roi
    h_frame, w_frame = frame.shape[:2]
    x2 = min(x + w, w_frame)
    y2 = min(y + h, h_frame)
    x = max(0, x)
    y = max(0, y)
    if x >= x2 or y >= y2:
        return frame, (0, 0)
    return frame[y:y2, x:x2], (x, y)


def build_mask(frame_bgr: np.ndarray, config: TrackerConfig) -> Tuple[np.ndarray, np.ndarray]:
    if config.track_mode == "color":
        hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
        combined = np.zeros(hsv.shape[:2], dtype=np.uint8)
        for lower, upper in config.hsv_ranges:
            lower_np = np.array(lower, dtype=np.uint8)
            upper_np = np.array(upper, dtype=np.uint8)
            combined = cv2.bitwise_or(combined, cv2.inRange(hsv, lower_np, upper_np))
        mask = combined
        gray_for_stats = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    else:
        gray_for_stats = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        blur = config.blur if config.blur % 2 == 1 else config.blur + 1
        blurred = cv2.GaussianBlur(gray_for_stats, (blur, blur), 0)
        _, mask = cv2.threshold(blurred, config.threshold, 255, cv2.THRESH_BINARY)

    if config.erode_iter > 0:
        mask = cv2.erode(mask, None, iterations=config.erode_iter)
    if config.dilate_iter > 0:
        mask = cv2.dilate(mask, None, iterations=config.dilate_iter)
    return mask, gray_for_stats


def select_best_contour(contours: Sequence[np.ndarray], gray: np.ndarray, config: TrackerConfig) -> Optional[np.ndarray]:
    valid: List[Tuple[float, np.ndarray]] = []
    for contour in contours:
        area = float(cv2.contourArea(contour))
        if area < config.min_area:
            continue
        if config.max_area is not None and area > config.max_area:
            continue

        if config.track_mode == "color":
            score = area
        else:
            mask = np.zeros(gray.shape, dtype=np.uint8)
            cv2.drawContours(mask, [contour], -1, 255, thickness=-1)
            mean_intensity = float(cv2.mean(gray, mask=mask)[0])
            score = mean_intensity * max(area, 1.0)

        valid.append((score, contour))

    if not valid:
        return None
    valid.sort(key=lambda item: item[0], reverse=True)
    return valid[0][1]


def contour_features(contour: np.ndarray, gray: np.ndarray, frame_bgr: np.ndarray, offset: Tuple[int, int], config: TrackerConfig) -> Dict[str, object]:
    ox, oy = offset
    area = float(cv2.contourArea(contour))
    perimeter = float(cv2.arcLength(contour, True))
    x, y, w, h = cv2.boundingRect(contour)
    (circle_center, radius) = cv2.minEnclosingCircle(contour)
    moments = cv2.moments(contour)

    if moments["m00"] != 0:
        cx = int(moments["m10"] / moments["m00"]) + ox
        cy = int(moments["m01"] / moments["m00"]) + oy
    else:
        cx = int(circle_center[0]) + ox
        cy = int(circle_center[1]) + oy

    circularity = 0.0
    if perimeter > 0:
        circularity = float(4.0 * math.pi * area / (perimeter * perimeter))

    local_mask = np.zeros(gray.shape, dtype=np.uint8)
    cv2.drawContours(local_mask, [contour], -1, 255, thickness=-1)

    mean_gray = float(cv2.mean(gray, mask=local_mask)[0])
    max_gray = float(cv2.minMaxLoc(gray, mask=local_mask)[1])

    mean_b, mean_g, mean_r, _ = cv2.mean(frame_bgr, mask=local_mask)
    aspect_ratio = float(w / h) if h > 0 else 0.0
    score = area if config.track_mode == "color" else mean_gray * max(area, 1.0)

    return {
        "detected": 1,
        "track_mode": config.track_mode,
        "color_name": config.color_name or "",
        "center_x": cx,
        "center_y": cy,
        "area": area,
        "perimeter": perimeter,
        "radius": float(radius),
        "bbox_x": x + ox,
        "bbox_y": y + oy,
        "bbox_w": int(w),
        "bbox_h": int(h),
        "aspect_ratio": aspect_ratio,
        "circularity": circularity,
        "mean_gray": mean_gray,
        "max_gray": max_gray,
        "mean_b": float(mean_b),
        "mean_g": float(mean_g),
        "mean_r": float(mean_r),
        "score": float(score),
    }


def empty_features(config: TrackerConfig) -> Dict[str, object]:
    return {
        "detected": 0,
        "track_mode": config.track_mode,
        "color_name": config.color_name or "",
        "center_x": "",
        "center_y": "",
        "area": 0.0,
        "perimeter": 0.0,
        "radius": 0.0,
        "bbox_x": "",
        "bbox_y": "",
        "bbox_w": 0,
        "bbox_h": 0,
        "aspect_ratio": 0.0,
        "circularity": 0.0,
        "mean_gray": 0.0,
        "max_gray": 0.0,
        "mean_b": 0.0,
        "mean_g": 0.0,
        "mean_r": 0.0,
        "score": 0.0,
    }


def track_spot(config: TrackerConfig) -> None:
    camera_matrix, dist_coeffs = load_calibration(config.calib_file)

    cap = cv2.VideoCapture(config.video)
    if not cap.isOpened():
        raise RuntimeError(f"Nie można otworzyć pliku wideo: {config.video}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    fps = fps if fps and fps > 0 else 0.0

    rows: List[Dict[str, object]] = []
    frame_index = 0

    print("\n=== Konfiguracja śledzenia ===")
    print(f"video       : {config.video}")
    print(f"track_mode  : {config.track_mode}")
    print(f"color_name  : {config.color_name or '-'}")
    print(f"blur        : {config.blur}")
    print(f"threshold   : {config.threshold}")
    print(f"erode_iter  : {config.erode_iter}")
    print(f"dilate_iter : {config.dilate_iter}")
    print(f"min_area    : {config.min_area}")
    print(f"max_area    : {config.max_area}")
    print(f"roi         : {config.roi}")
    print(f"output_csv  : {config.output_csv}")
    print("================================\n")

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        if camera_matrix is not None and dist_coeffs is not None:
            frame = cv2.undistort(frame, camera_matrix, dist_coeffs)

        frame_roi, offset = crop_roi(frame, config.roi)
        mask, gray = build_mask(frame_roi, config)
        contours, _ = cv2.findContours(mask.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        best = select_best_contour(contours, gray, config)

        row: Dict[str, object] = {
            "frame_index": frame_index,
            "time_sec": (frame_index / fps) if fps > 0 else float(frame_index),
        }

        if best is not None:
            row.update(contour_features(best, gray, frame_roi, offset, config))
            if config.display:
                cx = int(row["center_x"])
                cy = int(row["center_y"])
                x = int(row["bbox_x"])
                y = int(row["bbox_y"])
                w = int(row["bbox_w"])
                h = int(row["bbox_h"])
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                cv2.circle(frame, (cx, cy), 5, (0, 0, 255), -1)
        else:
            row.update(empty_features(config))

        rows.append(row)

        if config.display:
            display_mask = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
            if config.roi is not None:
                x0, y0, w0, h0 = config.roi
                cv2.rectangle(frame, (x0, y0), (x0 + w0, y0 + h0), (255, 255, 0), 1)
            cv2.putText(frame, f"frame={frame_index}", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)
            cv2.putText(frame, f"mode={config.track_mode}", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)
            cv2.imshow("Tracking", frame)
            cv2.imshow("Mask", display_mask)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break

        frame_index += 1

    cap.release()
    if config.display:
        cv2.destroyAllWindows()

    with open(config.output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    print(f"[INFO] Zapisano CSV: {config.output_csv}")
    print(f"[INFO] Liczba klatek: {len(rows)}")
    detected_count = sum(int(r["detected"]) for r in rows)
    print(f"[INFO] Wykrycia     : {detected_count}")


def read_csv_rows(path: str) -> List[Dict[str, str]]:
    with open(path, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def safe_float(value: object, default: float = 0.0) -> float:
    if value in ("", None):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: object, default: int = 0) -> int:
    if value in ("", None):
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def compare_csv(reference: str, candidate: str, output_csv: Optional[str]) -> None:
    ref_rows = read_csv_rows(reference)
    cand_rows = read_csv_rows(candidate)

    ref_map = {safe_int(r.get("frame_index")): r for r in ref_rows}
    cand_map = {safe_int(r.get("frame_index")): r for r in cand_rows}

    common_frames = sorted(set(ref_map).intersection(cand_map))
    if not common_frames:
        raise RuntimeError("Brak wspólnych klatek między plikami CSV.")

    compared_rows: List[Dict[str, object]] = []
    dx_list: List[float] = []
    dy_list: List[float] = []
    dist_list: List[float] = []
    area_diff_list: List[float] = []
    agreement = 0

    for frame_idx in common_frames:
        ref = ref_map[frame_idx]
        cand = cand_map[frame_idx]

        ref_det = safe_int(ref.get("detected"))
        cand_det = safe_int(cand.get("detected"))
        if ref_det == cand_det:
            agreement += 1

        dx = dy = dist = area_diff = ""
        if ref_det == 1 and cand_det == 1:
            dx_val = safe_float(cand.get("center_x")) - safe_float(ref.get("center_x"))
            dy_val = safe_float(cand.get("center_y")) - safe_float(ref.get("center_y"))
            dist_val = math.hypot(dx_val, dy_val)
            area_diff_val = safe_float(cand.get("area")) - safe_float(ref.get("area"))
            dx, dy, dist, area_diff = dx_val, dy_val, dist_val, area_diff_val
            dx_list.append(dx_val)
            dy_list.append(dy_val)
            dist_list.append(dist_val)
            area_diff_list.append(area_diff_val)

        compared_rows.append(
            {
                "frame_index": frame_idx,
                "reference_detected": ref_det,
                "candidate_detected": cand_det,
                "dx": dx,
                "dy": dy,
                "distance": dist,
                "area_diff": area_diff,
            }
        )

    def rmse(values: List[float]) -> float:
        if not values:
            return 0.0
        return math.sqrt(sum(v * v for v in values) / len(values))

    print("\n=== Raport porównania CSV ===")
    print(f"Wspólne klatki            : {len(common_frames)}")
    print(f"Zgodność detekcji         : {agreement / len(common_frames):.4f}")
    print(f"RMSE X [px]               : {rmse(dx_list):.4f}")
    print(f"RMSE Y [px]               : {rmse(dy_list):.4f}")
    print(f"RMSE dystansu [px]        : {rmse(dist_list):.4f}")
    print(f"Średni błąd dystansu [px] : {(sum(dist_list) / len(dist_list)) if dist_list else 0.0:.4f}")
    print(f"Średnia różnica pola      : {(sum(area_diff_list) / len(area_diff_list)) if area_diff_list else 0.0:.4f}")
    print("=============================\n")

    if output_csv:
        with open(output_csv, "w", newline="", encoding="utf-8") as f:
            fieldnames = ["frame_index", "reference_detected", "candidate_detected", "dx", "dy", "distance", "area_diff"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(compared_rows)
        print(f"[INFO] Zapisano raport szczegółowy: {output_csv}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Kalibracja kamery i śledzenie jasnej / kolorowej plamki światła w MP4."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_cal = subparsers.add_parser("calibrate", help="Kalibracja kamery ze zdjęć szachownicy")
    p_cal.add_argument("--calib_dir", required=True, help="Katalog ze zdjęciami kalibracyjnymi")
    p_cal.add_argument("--rows", type=int, default=6, help="Liczba wewnętrznych narożników w wierszu")
    p_cal.add_argument("--cols", type=int, default=9, help="Liczba wewnętrznych narożników w kolumnie")
    p_cal.add_argument("--square_size", type=float, default=1.0, help="Rozmiar pola szachownicy")
    p_cal.add_argument("--output_file", default="camera_calib.npz", help="Plik wyjściowy z kalibracją")

    p_track = subparsers.add_parser("track", help="Śledzenie plamki")
    p_track.add_argument("--video", required=True, help="Plik MP4")
    p_track.add_argument("--calib_file", help="Plik .npz z kalibracją kamery")
    p_track.add_argument("--track_mode", choices=["brightest", "color"], default="brightest", help="Tryb śledzenia")
    p_track.add_argument("--color_name", choices=sorted(PRESET_HSV_RANGES.keys()), help="Preset koloru dla track_mode=color")
    p_track.add_argument("--hsv_lower", type=parse_hsv_triplet, help="Dolny próg HSV, np. 0,80,80")
    p_track.add_argument("--hsv_upper", type=parse_hsv_triplet, help="Górny próg HSV, np. 10,255,255")
    p_track.add_argument("--blur", type=int, default=11, help="Rozmiar filtra Gaussa")
    p_track.add_argument("--threshold", type=int, default=200, help="Próg jasności 0..255")
    p_track.add_argument("--erode_iter", type=int, default=2, help="Liczba iteracji erozji")
    p_track.add_argument("--dilate_iter", type=int, default=4, help="Liczba iteracji dylatacji")
    p_track.add_argument("--min_area", type=float, default=20.0, help="Minimalna powierzchnia konturu")
    p_track.add_argument("--max_area", type=float, help="Maksymalna powierzchnia konturu")
    p_track.add_argument("--roi", type=parse_roi, help="Obszar zainteresowania x,y,w,h")
    p_track.add_argument("--output_csv", default="tracking_results.csv", help="Plik CSV z wynikami")
    p_track.add_argument("--display", action="store_true", help="Pokaż podgląd na żywo")
    p_track.add_argument("--interactive", action="store_true", help="Interaktywny wybór kluczowych parametrów w terminalu")

    p_cmp = subparsers.add_parser("compare", help="Porównanie dwóch plików CSV")
    p_cmp.add_argument("--reference", required=True, help="CSV referencyjny")
    p_cmp.add_argument("--candidate", required=True, help="CSV porównywany")
    p_cmp.add_argument("--output_csv", help="Szczegółowy raport porównania")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "calibrate":
        calibrate_camera(args.calib_dir, args.rows, args.cols, args.square_size, args.output_file)
        return

    if args.command == "track":
        config = build_tracker_config(args)
        track_spot(config)
        return

    if args.command == "compare":
        compare_csv(args.reference, args.candidate, args.output_csv)
        return


if __name__ == "__main__":
    main()
