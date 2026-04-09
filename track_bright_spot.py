#!/usr/bin/env python3
"""
Terminalowy program do:
1) kalibracji kamery na podstawie zdjęć szachownicy,
2) śledzenia jasnej plamki światła w pliku MP4,
3) śledzenia plamki o konkretnym kolorze,
4) interaktywnego wyboru kluczowych parametrów śledzenia w terminalu,
5) eksportu wyników do CSV,
6) generowania wykresu trajektorii plamki,
7) generowania raportu jakości śledzenia w CSV i PDF,
8) porównywania dwóch plików CSV w celu oceny jakości śledzenia.

Przykłady:
  python track_bright_spot_v3.py calibrate --calib_dir ./calib --rows 6 --cols 9 --output_file camera_calib.npz

  python track_bright_spot_v3.py track --video film.mp4 --track_mode brightest --threshold 210 --output_csv wynik.csv --display

  python track_bright_spot_v3.py track --video film.mp4 --track_mode color --color_name red --output_csv wynik_color.csv

  python track_bright_spot_v3.py track --video film.mp4 --interactive --trajectory_png trajektoria.png --report_csv raport.csv --report_pdf raport.pdf

  python track_bright_spot_v3.py compare --reference ref.csv --candidate test.csv --output_csv raport_porownania.csv --report_pdf raport_porownania.pdf
"""

from __future__ import annotations

import argparse
import csv
import glob
import math
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np
import yaml

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None

try:
    import matplotlib.pyplot as plt
except Exception:  # pragma: no cover
    plt = None

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Image as RLImage,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )
except Exception:  # pragma: no cover
    colors = None
    A4 = None
    ParagraphStyle = None
    getSampleStyleSheet = None
    mm = None
    RLImage = None
    Paragraph = None
    SimpleDocTemplate = None
    Spacer = None
    Table = None
    TableStyle = None


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
    trajectory_png: Optional[str] = None
    report_csv: Optional[str] = None
    report_pdf: Optional[str] = None


TRACKER_HARDCODED_DEFAULTS = {
    "track_mode": "brightest",
    "blur": 11,
    "threshold": 200,
    "erode_iter": 2,
    "dilate_iter": 4,
    "min_area": 20.0,
    "max_area": None,
    "roi": None,
    "color_name": None,
    "hsv_lower": None,
    "hsv_upper": None,
    "output_csv": "tracking_results.csv",
    "trajectory_png": None,
    "report_csv": None,
    "report_pdf": None,
    "display": False,
}


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
        print("Wpisz t lub n.")


def parse_optional_float_text(value: str) -> Optional[float]:
    value = value.strip()
    if value == "":
        return None
    return float(value)


def parse_optional_roi_text(value: str) -> Optional[Tuple[int, int, int, int]]:
    value = value.strip()
    if value == "":
        return None
    return parse_roi(value)


def get_hsv_ranges_from_args_or_name(
    color_name: Optional[str],
    hsv_lower: Optional[Tuple[int, int, int]],
    hsv_upper: Optional[Tuple[int, int, int]],
) -> List[Tuple[Tuple[int, int, int], Tuple[int, int, int]]]:
    if color_name:
        return PRESET_HSV_RANGES[color_name]
    if hsv_lower and hsv_upper:
        return [(hsv_lower, hsv_upper)]
    return []


def load_settings_yaml(path: str) -> Dict[str, object]:
    if not path:
        return {}
    if not os.path.exists(path):
        return {}

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Plik YAML musi zawierać mapę klucz:wartość: {path}")
    return data


def _coerce_yaml_hsv_triplet(value: object) -> Tuple[int, int, int]:
    if isinstance(value, str):
        return parse_hsv_triplet(value)
    if isinstance(value, (list, tuple)) and len(value) == 3:
        return tuple(int(v) for v in value)  # type: ignore[return-value]
    raise ValueError("HSV w YAML musi być stringiem 'H,S,V' albo listą [H, S, V].")


def _coerce_yaml_roi(value: object) -> Optional[Tuple[int, int, int, int]]:
    if value is None:
        return None
    if isinstance(value, str):
        return parse_optional_roi_text(value)
    if isinstance(value, (list, tuple)) and len(value) == 4:
        x, y, w, h = (int(v) for v in value)
        return parse_roi(f"{x},{y},{w},{h}")
    raise ValueError("ROI w YAML musi być stringiem 'x,y,w,h' albo listą [x, y, w, h].")


def normalize_yaml_track_settings(raw: Dict[str, object]) -> Dict[str, object]:
    out: Dict[str, object] = {}
    simple_keys = {
        "track_mode": str,
        "threshold": int,
        "blur": int,
        "erode_iter": int,
        "dilate_iter": int,
        "min_area": float,
        "max_area": float,
        "color_name": str,
        "output_csv": str,
        "trajectory_png": str,
        "report_csv": str,
        "report_pdf": str,
        "display": bool,
    }
    for key, caster in simple_keys.items():
        if key not in raw or raw[key] is None:
            continue
        out[key] = caster(raw[key])

    if "roi" in raw:
        out["roi"] = _coerce_yaml_roi(raw["roi"])
    if "hsv_lower" in raw and raw["hsv_lower"] is not None:
        out["hsv_lower"] = _coerce_yaml_hsv_triplet(raw["hsv_lower"])
    if "hsv_upper" in raw and raw["hsv_upper"] is not None:
        out["hsv_upper"] = _coerce_yaml_hsv_triplet(raw["hsv_upper"])

    return out


def extract_cli_track_overrides(args: argparse.Namespace) -> Dict[str, object]:
    keys = [
        "track_mode",
        "threshold",
        "blur",
        "erode_iter",
        "dilate_iter",
        "min_area",
        "max_area",
        "roi",
        "color_name",
        "hsv_lower",
        "hsv_upper",
        "output_csv",
        "trajectory_png",
        "report_csv",
        "report_pdf",
        "display",
    ]
    out: Dict[str, object] = {}
    for key in keys:
        value = getattr(args, key, None)
        if value is not None:
            out[key] = value
    return out


def interactive_configure_track(args: argparse.Namespace) -> TrackerConfig:
    print("\n=== Konfiguracja interaktywna śledzenia ===")
    track_mode = ask_text("Tryb śledzenia (brightest/color)", args.track_mode).strip().lower()
    while track_mode not in {"brightest", "color"}:
        print("Dozwolone wartości: brightest albo color.")
        track_mode = ask_text("Tryb śledzenia (brightest/color)", args.track_mode).strip().lower()

    color_name: Optional[str] = args.color_name
    hsv_ranges: List[Tuple[Tuple[int, int, int], Tuple[int, int, int]]] = []

    if track_mode == "color":
        use_preset = ask_yes_no("Użyć presetu koloru?", default=True)
        if use_preset:
            print(f"Dostępne presety: {', '.join(sorted(PRESET_HSV_RANGES.keys()))}")
            color_name = ask_text("Nazwa koloru", args.color_name or "red").strip().lower()
            while color_name not in PRESET_HSV_RANGES:
                print("Nieznany preset koloru.")
                color_name = ask_text("Nazwa koloru", "red").strip().lower()
            hsv_ranges = PRESET_HSV_RANGES[color_name]
        else:
            lower = parse_hsv_triplet(ask_text("Dolny HSV", "0,80,80"))
            upper = parse_hsv_triplet(ask_text("Górny HSV", "10,255,255"))
            hsv_ranges = [(lower, upper)]
            color_name = "custom"
    else:
        color_name = None

    blur = ask_int("Rozmiar filtra Gaussa (liczba nieparzysta)", args.blur, min_value=1)
    threshold = ask_int("Próg jasności 0..255", args.threshold, min_value=0, max_value=255)
    erode_iter = ask_int("Liczba iteracji erozji", args.erode_iter, min_value=0)
    dilate_iter = ask_int("Liczba iteracji dylatacji", args.dilate_iter, min_value=0)
    min_area = ask_float("Minimalna powierzchnia konturu", args.min_area, min_value=0.0)

    default_max_area = "" if args.max_area is None else str(args.max_area)
    max_area_raw = ask_text("Maksymalna powierzchnia konturu (puste = brak limitu)", default_max_area)
    max_area = parse_optional_float_text(max_area_raw)

    default_roi = "" if args.roi is None else ",".join(str(v) for v in args.roi)
    roi_raw = ask_text("ROI x,y,w,h (puste = całe okno)", default_roi)
    roi = parse_optional_roi_text(roi_raw)

    display = args.display or ask_yes_no("Pokazać okno podglądu podczas śledzenia?", default=args.display)
    trajectory_png = args.trajectory_png
    report_csv = args.report_csv
    report_pdf = args.report_pdf

    if ask_yes_no("Wygenerować wykres trajektorii?", default=bool(args.trajectory_png)):
        trajectory_png = ask_text("Plik PNG z trajektorią", args.trajectory_png or "trajectory.png")
    if ask_yes_no("Wygenerować raport CSV?", default=bool(args.report_csv)):
        report_csv = ask_text("Plik CSV z raportem", args.report_csv or "tracking_report.csv")
    if ask_yes_no("Wygenerować raport PDF?", default=bool(args.report_pdf)):
        report_pdf = ask_text("Plik PDF z raportem", args.report_pdf or "tracking_report.pdf")

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
        trajectory_png=trajectory_png,
        report_csv=report_csv,
        report_pdf=report_pdf,
    )


def build_tracker_config(args: argparse.Namespace) -> TrackerConfig:
    yaml_data = normalize_yaml_track_settings(load_settings_yaml(args.config))
    merged: Dict[str, object] = dict(TRACKER_HARDCODED_DEFAULTS)
    merged.update(yaml_data)
    cli_overrides = extract_cli_track_overrides(args)
    merged.update(cli_overrides)

    interactive_args = argparse.Namespace(**vars(args))
    for key, value in merged.items():
        setattr(interactive_args, key, value)

    if args.interactive:
        interactive_cfg = interactive_configure_track(interactive_args)
        for key, value in cli_overrides.items():
            setattr(interactive_cfg, key, value)
        interactive_cfg.hsv_ranges = get_hsv_ranges_from_args_or_name(
            interactive_cfg.color_name,
            getattr(interactive_cfg, "hsv_lower", None),
            getattr(interactive_cfg, "hsv_upper", None),
        )
        if interactive_cfg.track_mode == "color" and not interactive_cfg.hsv_ranges:
            raise ValueError("Dla trybu 'color' podaj --color_name albo --hsv_lower i --hsv_upper.")
        return interactive_cfg

    track_mode = str(merged["track_mode"])
    color_name = merged.get("color_name")
    hsv_lower = merged.get("hsv_lower")
    hsv_upper = merged.get("hsv_upper")
    hsv_ranges = get_hsv_ranges_from_args_or_name(color_name, hsv_lower, hsv_upper)

    if track_mode == "color" and not hsv_ranges:
        raise ValueError("Dla trybu 'color' podaj --color_name albo --hsv_lower i --hsv_upper.")

    return TrackerConfig(
        video=args.video,
        calib_file=args.calib_file,
        track_mode=track_mode,
        blur=int(merged["blur"]),
        threshold=int(merged["threshold"]),
        erode_iter=int(merged["erode_iter"]),
        dilate_iter=int(merged["dilate_iter"]),
        min_area=float(merged["min_area"]),
        max_area=merged["max_area"],  # type: ignore[arg-type]
        color_name=color_name,  # type: ignore[arg-type]
        hsv_ranges=hsv_ranges,
        output_csv=str(merged["output_csv"]),
        display=bool(merged["display"]),
        roi=merged["roi"],  # type: ignore[arg-type]
        trajectory_png=merged.get("trajectory_png"),  # type: ignore[arg-type]
        report_csv=merged.get("report_csv"),  # type: ignore[arg-type]
        report_pdf=merged.get("report_pdf"),  # type: ignore[arg-type]
    )


def calibrate_camera(
    calib_dir: str,
    pattern_rows: int,
    pattern_cols: int,
    square_size: float,
    output_file: str,
    output_format: str = "auto",
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
        print("[ERROR] Kalibracja nie powiodła się - brak poprawnych obrazów.")
        return None

    ok, camera_matrix, dist_coeffs, _, _ = cv2.calibrateCamera(objpoints, imgpoints, gray_shape, None, None)
    if not ok:
        print("[ERROR] cv2.calibrateCamera zwróciło błąd.")
        return None

    out_ext = os.path.splitext(output_file)[1].lower()
    resolved_output_format = output_format.lower()
    if resolved_output_format == "auto":
        if out_ext == ".npz":
            resolved_output_format = "npz"
        elif out_ext in {".yaml", ".yml"}:
            resolved_output_format = "yaml"
        else:
            print(
                f"[ERROR] Nieobsługiwane rozszerzenie pliku wyjściowego: {out_ext or '(brak)'}."
                " Użyj .npz/.yaml/.yml albo jawnie ustaw --output_format."
            )
            return None

    if resolved_output_format == "npz":
        np.savez(output_file, camera_matrix=camera_matrix, dist_coeffs=dist_coeffs)
    elif resolved_output_format == "yaml":
        if yaml is None:
            print("[ERROR] Brak biblioteki PyYAML. Zainstaluj 'pyyaml', aby zapisać kalibrację do YAML.")
            return None
        payload = {
            "camera_matrix": camera_matrix.tolist(),
            "dist_coeffs": dist_coeffs.tolist(),
        }
        with open(output_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(payload, f, sort_keys=False)
    else:
        print(f"[ERROR] Nieobsługiwany format wyjściowy: {output_format}")
        return None

    print(f"[INFO] Zapisano kalibrację do: {output_file}")
    return camera_matrix, dist_coeffs


def _ensure_calibration_array(
    value: object,
    field_name: str,
    expected_shape: Optional[Tuple[int, ...]] = None,
) -> np.ndarray:
    try:
        arr = np.asarray(value, dtype=np.float64)
    except Exception as exc:
        raise ValueError(f"Pole '{field_name}' ma nieprawidłowy format - oczekiwano tablicy liczb.") from exc

    if arr.size == 0:
        raise ValueError(f"Pole '{field_name}' jest puste.")
    if expected_shape is not None and arr.shape != expected_shape:
        raise ValueError(
            f"Pole '{field_name}' ma nieprawidłowy rozmiar {arr.shape}, oczekiwano {expected_shape}."
        )
    if not np.isfinite(arr).all():
        raise ValueError(f"Pole '{field_name}' zawiera wartości nienumeryczne lub nieskończone.")
    return arr


def load_calibration(calib_file: Optional[str]) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    if not calib_file:
        return None, None
    if not os.path.exists(calib_file):
        raise FileNotFoundError(f"Nie znaleziono pliku kalibracji: {calib_file}")

    ext = os.path.splitext(calib_file)[1].lower()
    if ext == ".npz":
        data = np.load(calib_file)
        if "camera_matrix" not in data or "dist_coeffs" not in data:
            raise ValueError(
                "Niepoprawny plik .npz z kalibracją - wymagane klucze: 'camera_matrix' i 'dist_coeffs'."
            )
        camera_matrix = _ensure_calibration_array(data["camera_matrix"], "camera_matrix", expected_shape=(3, 3))
        dist_coeffs = _ensure_calibration_array(data["dist_coeffs"], "dist_coeffs")
        return camera_matrix, dist_coeffs

    if ext in {".yaml", ".yml"}:
        if yaml is None:
            raise ValueError("Nie można wczytać YAML - brak biblioteki PyYAML. Zainstaluj pakiet 'pyyaml'.")

        with open(calib_file, "r", encoding="utf-8") as f:
            payload = yaml.safe_load(f)

        if not isinstance(payload, dict):
            raise ValueError("Niepoprawny YAML kalibracji - oczekiwano mapy z polami 'camera_matrix' i 'dist_coeffs'.")

        missing_fields = [name for name in ("camera_matrix", "dist_coeffs") if name not in payload]
        if missing_fields:
            raise ValueError(f"Niepoprawny YAML kalibracji - brak wymaganych pól: {', '.join(missing_fields)}.")

        camera_matrix = _ensure_calibration_array(payload["camera_matrix"], "camera_matrix", expected_shape=(3, 3))
        dist_coeffs = _ensure_calibration_array(payload["dist_coeffs"], "dist_coeffs")
        return camera_matrix, dist_coeffs

    raise ValueError(
        f"Nieobsługiwany format pliku kalibracji: {calib_file}. Wspierane rozszerzenia: .npz, .yaml, .yml."
    )


def ensure_odd(value: int) -> int:
    if value % 2 == 0:
        return value + 1
    return value


def apply_roi(frame: np.ndarray, roi: Optional[Tuple[int, int, int, int]]) -> Tuple[np.ndarray, Tuple[int, int]]:
    if roi is None:
        return frame, (0, 0)
    x, y, w, h = roi
    x = max(0, x)
    y = max(0, y)
    x2 = min(frame.shape[1], x + w)
    y2 = min(frame.shape[0], y + h)
    return frame[y:y2, x:x2], (x, y)


def build_mask(frame_bgr: np.ndarray, gray: np.ndarray, config: TrackerConfig) -> np.ndarray:
    if config.track_mode == "brightest":
        blurred = cv2.GaussianBlur(gray, (ensure_odd(config.blur), ensure_odd(config.blur)), 0)
        _, mask = cv2.threshold(blurred, config.threshold, 255, cv2.THRESH_BINARY)
    else:
        hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
        mask = np.zeros(gray.shape, dtype=np.uint8)
        for lower, upper in config.hsv_ranges:
            local = cv2.inRange(hsv, np.array(lower, dtype=np.uint8), np.array(upper, dtype=np.uint8))
            mask = cv2.bitwise_or(mask, local)

        if config.blur > 1:
            blurred_mask = cv2.GaussianBlur(mask, (ensure_odd(config.blur), ensure_odd(config.blur)), 0)
            _, mask = cv2.threshold(blurred_mask, 127, 255, cv2.THRESH_BINARY)

    if config.erode_iter > 0:
        mask = cv2.erode(mask, None, iterations=config.erode_iter)
    if config.dilate_iter > 0:
        mask = cv2.dilate(mask, None, iterations=config.dilate_iter)
    return mask


def contour_candidates(mask: np.ndarray) -> List[np.ndarray]:
    contours, _ = cv2.findContours(mask.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return list(contours)


def select_best_contour(contours: Sequence[np.ndarray], config: TrackerConfig, gray: np.ndarray) -> Optional[np.ndarray]:
    best = None
    best_score = -1.0

    for contour in contours:
        area = cv2.contourArea(contour)
        if area < config.min_area:
            continue
        if config.max_area is not None and area > config.max_area:
            continue

        score = area
        if config.track_mode == "brightest":
            local_mask = np.zeros(gray.shape, dtype=np.uint8)
            cv2.drawContours(local_mask, [contour], -1, 255, thickness=-1)
            mean_gray = cv2.mean(gray, mask=local_mask)[0]
            score = mean_gray * max(area, 1.0)

        if score > best_score:
            best_score = score
            best = contour
    return best


def extract_features(
    contour: np.ndarray,
    frame_bgr: np.ndarray,
    gray: np.ndarray,
    origin_xy: Tuple[int, int],
    config: TrackerConfig,
) -> Dict[str, object]:
    ox, oy = origin_xy
    area = float(cv2.contourArea(contour))
    perimeter = float(cv2.arcLength(contour, True))
    (cx0, cy0), radius = cv2.minEnclosingCircle(contour)
    x, y, w, h = cv2.boundingRect(contour)

    moments = cv2.moments(contour)
    if moments["m00"] != 0:
        cx = float(moments["m10"] / moments["m00"]) + ox
        cy = float(moments["m01"] / moments["m00"]) + oy
    else:
        cx = float(cx0) + ox
        cy = float(cy0) + oy

    circularity = float(4.0 * math.pi * area / (perimeter * perimeter)) if perimeter > 0 else 0.0

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


def compute_tracking_summary(rows: List[Dict[str, object]], video_path: str, fps: float) -> Dict[str, object]:
    total_frames = len(rows)
    detected_rows = [r for r in rows if safe_int(r.get("detected")) == 1]

    xs = [safe_float(r.get("center_x")) for r in detected_rows]
    ys = [safe_float(r.get("center_y")) for r in detected_rows]
    areas = [safe_float(r.get("area")) for r in detected_rows]
    circularities = [safe_float(r.get("circularity")) for r in detected_rows]
    radii = [safe_float(r.get("radius")) for r in detected_rows]

    detection_ratio = (len(detected_rows) / total_frames) if total_frames else 0.0

    jumps: List[float] = []
    for i in range(1, len(detected_rows)):
        dx = safe_float(detected_rows[i].get("center_x")) - safe_float(detected_rows[i - 1].get("center_x"))
        dy = safe_float(detected_rows[i].get("center_y")) - safe_float(detected_rows[i - 1].get("center_y"))
        jumps.append(math.hypot(dx, dy))

    gap_count = 0
    in_gap = False
    longest_gap = 0
    current_gap = 0
    for row in rows:
        if safe_int(row.get("detected")) == 0:
            current_gap += 1
            if not in_gap:
                gap_count += 1
                in_gap = True
        else:
            longest_gap = max(longest_gap, current_gap)
            current_gap = 0
            in_gap = False
    longest_gap = max(longest_gap, current_gap)

    path_length = sum(jumps)
    duration_sec = safe_float(rows[-1].get("time_sec")) if rows else 0.0
    mean_speed = (path_length / duration_sec) if duration_sec > 0 else 0.0

    def mean(values: List[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    def stdev(values: List[float]) -> float:
        if len(values) < 2:
            return 0.0
        mu = mean(values)
        return math.sqrt(sum((v - mu) ** 2 for v in values) / len(values))

    return {
        "video": video_path,
        "total_frames": total_frames,
        "fps": fps,
        "duration_sec": duration_sec,
        "detections": len(detected_rows),
        "detection_ratio": detection_ratio,
        "gap_count": gap_count,
        "longest_gap_frames": longest_gap,
        "path_length_px": path_length,
        "mean_jump_px": mean(jumps),
        "max_jump_px": max(jumps) if jumps else 0.0,
        "jump_std_px": stdev(jumps),
        "mean_speed_px_per_sec": mean_speed,
        "mean_x": mean(xs),
        "mean_y": mean(ys),
        "x_std": stdev(xs),
        "y_std": stdev(ys),
        "mean_area": mean(areas),
        "area_std": stdev(areas),
        "mean_radius": mean(radii),
        "radius_std": stdev(radii),
        "mean_circularity": mean(circularities),
    }


def save_summary_csv(summary: Dict[str, object], output_csv: str) -> None:
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary.keys()))
        writer.writeheader()
        writer.writerow(summary)


def generate_trajectory_plot(rows: List[Dict[str, object]], output_png: str, title: str = "Trajektoria plamki") -> None:
    if plt is None:
        print("[WARNING] matplotlib nie jest dostępny - pomijam wykres trajektorii.")
        return

    xs = [safe_float(r.get("center_x")) for r in rows if safe_int(r.get("detected")) == 1]
    ys = [safe_float(r.get("center_y")) for r in rows if safe_int(r.get("detected")) == 1]
    frames = [safe_int(r.get("frame_index")) for r in rows if safe_int(r.get("detected")) == 1]

    if not xs or not ys:
        print("[WARNING] Brak wykryć - nie można wygenerować trajektorii.")
        return

    plt.figure(figsize=(8, 6))
    plt.plot(xs, ys, linewidth=1.2)
    plt.scatter(xs[0], ys[0], s=30, label=f"start: klatka {frames[0]}")
    plt.scatter(xs[-1], ys[-1], s=30, label=f"koniec: klatka {frames[-1]}")
    plt.gca().invert_yaxis()
    plt.xlabel("X [px]")
    plt.ylabel("Y [px]")
    plt.title(title)
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_png, dpi=180)
    plt.close()


def build_pdf_report(
    title: str,
    output_pdf: str,
    summary: Dict[str, object],
    config_lines: List[Tuple[str, str]],
    trajectory_png: Optional[str] = None,
    extra_table: Optional[List[List[str]]] = None,
) -> None:
    if SimpleDocTemplate is None:
        print("[WARNING] reportlab nie jest dostępny - pomijam raport PDF.")
        return

    doc = SimpleDocTemplate(
        output_pdf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
    )
    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    title_style.fontName = "Helvetica-Bold"
    heading = ParagraphStyle(
        "HeadingCustom",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#1f3b5b"),
        spaceAfter=6,
        spaceBefore=8,
    )
    body = styles["BodyText"]

    story = [Paragraph(title, title_style), Spacer(1, 6 * mm)]

    cfg_data = [["Parametr", "Wartość"]] + [[k, v] for k, v in config_lines]
    cfg_table = Table(cfg_data, colWidths=[55 * mm, 105 * mm])
    cfg_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dfe8f3")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1f3b5b")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9fb4cc")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )

    story += [Paragraph("Konfiguracja", heading), cfg_table, Spacer(1, 5 * mm)]

    sum_rows = [["Metryka", "Wartość"]]
    for key, value in summary.items():
        if isinstance(value, float):
            sum_rows.append([str(key), f"{value:.6f}"])
        else:
            sum_rows.append([str(key), str(value)])

    sum_table = Table(sum_rows, colWidths=[70 * mm, 90 * mm])
    sum_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e9f2e3")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#224522")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#a8c49b")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story += [Paragraph("Podsumowanie jakości", heading), sum_table]

    if trajectory_png and os.path.exists(trajectory_png):
        story += [Spacer(1, 6 * mm), Paragraph("Trajektoria", heading)]
        img = RLImage(trajectory_png, width=165 * mm, height=120 * mm)
        story += [img]

    if extra_table:
        story += [Spacer(1, 6 * mm), Paragraph("Dodatkowe dane", heading)]
        t = Table(extra_table, repeatRows=1)
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f4ead6")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#b89f6b")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story += [t]

    story += [Spacer(1, 5 * mm), Paragraph("Raport wygenerowany automatycznie przez program śledzący.", body)]
    doc.build(story)


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
    print(f"video          : {config.video}")
    print(f"track_mode     : {config.track_mode}")
    print(f"color_name     : {config.color_name or '-'}")
    print(f"blur           : {config.blur}")
    print(f"threshold      : {config.threshold}")
    print(f"erode_iter     : {config.erode_iter}")
    print(f"dilate_iter    : {config.dilate_iter}")
    print(f"min_area       : {config.min_area}")
    print(f"max_area       : {config.max_area}")
    print(f"roi            : {config.roi}")
    print(f"output_csv     : {config.output_csv}")
    print(f"trajectory_png : {config.trajectory_png}")
    print(f"report_csv     : {config.report_csv}")
    print(f"report_pdf     : {config.report_pdf}")
    print("================================\n")

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        if camera_matrix is not None and dist_coeffs is not None:
            frame = cv2.undistort(frame, camera_matrix, dist_coeffs)

        frame_roi, origin = apply_roi(frame, config.roi)
        gray_roi = cv2.cvtColor(frame_roi, cv2.COLOR_BGR2GRAY)
        mask = build_mask(frame_roi, gray_roi, config)
        contours = contour_candidates(mask)
        best_contour = select_best_contour(contours, config, gray_roi)

        row: Dict[str, object] = {"frame_index": frame_index, "time_sec": (frame_index / fps if fps > 0 else frame_index)}
        if best_contour is None:
            row.update(empty_features(config))
        else:
            row.update(extract_features(best_contour, frame_roi, gray_roi, origin, config))

        rows.append(row)

        if config.display:
            display_frame = frame.copy()
            if config.roi is not None:
                x, y, w, h = config.roi
                cv2.rectangle(display_frame, (x, y), (x + w, y + h), (255, 255, 0), 1)

            if safe_int(row.get("detected")) == 1:
                cx = safe_int(row.get("center_x"))
                cy = safe_int(row.get("center_y"))
                bx = safe_int(row.get("bbox_x"))
                by = safe_int(row.get("bbox_y"))
                bw = safe_int(row.get("bbox_w"))
                bh = safe_int(row.get("bbox_h"))
                cv2.circle(display_frame, (cx, cy), 4, (0, 0, 255), -1)
                cv2.rectangle(display_frame, (bx, by), (bx + bw, by + bh), (0, 255, 0), 1)
                cv2.putText(display_frame, f"({cx},{cy})", (bx, max(20, by - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

            cv2.putText(display_frame, f"Frame: {frame_index}", (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)
            cv2.imshow("Tracking", display_frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
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

    summary = compute_tracking_summary(rows, config.video, fps)

    if config.trajectory_png:
        generate_trajectory_plot(rows, config.trajectory_png, title=f"Trajektoria - {os.path.basename(config.video)}")
        print(f"[INFO] Zapisano wykres trajektorii: {config.trajectory_png}")

    if config.report_csv:
        save_summary_csv(summary, config.report_csv)
        print(f"[INFO] Zapisano raport CSV: {config.report_csv}")

    if config.report_pdf:
        config_lines = [
            ("Plik wideo", config.video),
            ("Tryb śledzenia", config.track_mode),
            ("Kolor", config.color_name or "-"),
            ("Blur", str(config.blur)),
            ("Threshold", str(config.threshold)),
            ("Erode iter", str(config.erode_iter)),
            ("Dilate iter", str(config.dilate_iter)),
            ("Min area", str(config.min_area)),
            ("Max area", str(config.max_area) if config.max_area is not None else "-"),
            ("ROI", str(config.roi) if config.roi is not None else "-"),
            ("CSV z wynikami", config.output_csv),
        ]
        build_pdf_report(
            title="Raport jakości śledzenia plamki",
            output_pdf=config.report_pdf,
            summary=summary,
            config_lines=config_lines,
            trajectory_png=config.trajectory_png,
        )
        print(f"[INFO] Zapisano raport PDF: {config.report_pdf}")


def compare_csv(
    reference: str,
    candidate: str,
    output_csv: Optional[str],
    report_pdf: Optional[str] = None,
) -> None:
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

    summary = {
        "common_frames": len(common_frames),
        "detection_agreement_ratio": (agreement / len(common_frames)) if common_frames else 0.0,
        "mean_abs_dx": (sum(abs(v) for v in dx_list) / len(dx_list)) if dx_list else 0.0,
        "mean_abs_dy": (sum(abs(v) for v in dy_list) / len(dy_list)) if dy_list else 0.0,
        "rmse_dx": rmse(dx_list),
        "rmse_dy": rmse(dy_list),
        "rmse_distance": rmse(dist_list),
        "mean_area_diff": (sum(area_diff_list) / len(area_diff_list)) if area_diff_list else 0.0,
    }

    print("\n=== Raport porównania CSV ===")
    print(f"Wspólne klatki            : {summary['common_frames']}")
    print(f"Zgodność wykrycia         : {summary['detection_agreement_ratio']:.4f}")
    print(f"Średni |dx| [px]          : {summary['mean_abs_dx']:.4f}")
    print(f"Średni |dy| [px]          : {summary['mean_abs_dy']:.4f}")
    print(f"RMSE dx [px]              : {summary['rmse_dx']:.4f}")
    print(f"RMSE dy [px]              : {summary['rmse_dy']:.4f}")
    print(f"RMSE odległości [px]      : {summary['rmse_distance']:.4f}")
    print(f"Średnia różnica pola      : {summary['mean_area_diff']:.4f}")
    print("=============================\n")

    if output_csv:
        with open(output_csv, "w", newline="", encoding="utf-8") as f:
            fieldnames = ["frame_index", "reference_detected", "candidate_detected", "dx", "dy", "distance", "area_diff"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(compared_rows)
        print(f"[INFO] Zapisano raport szczegółowy: {output_csv}")

    if report_pdf:
        cfg = [
            ("Reference CSV", reference),
            ("Candidate CSV", candidate),
            ("Detail CSV", output_csv or "-"),
        ]
        extra = [["Metryka", "Wartość"]] + [[k, f"{v:.6f}" if isinstance(v, float) else str(v)] for k, v in summary.items()]
        build_pdf_report(
            title="Raport porównania wyników śledzenia",
            output_pdf=report_pdf,
            summary=summary,
            config_lines=cfg,
            trajectory_png=None,
            extra_table=extra,
        )
        print(f"[INFO] Zapisano raport PDF: {report_pdf}")


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
    p_cal.add_argument("--output_file", default="camera_calib.npz", help="Plik wyjściowy z kalibracją (.npz/.yaml/.yml)")
    p_cal.add_argument(
        "--output_format",
        choices=["auto", "npz", "yaml"],
        default="auto",
        help="Format zapisu kalibracji: auto (po rozszerzeniu), npz lub yaml",
    )

    p_track = subparsers.add_parser("track", help="Śledzenie plamki")
    p_track.add_argument("--video", required=True, help="Plik MP4")
    p_track.add_argument(
        "--calib_file",
        default="config/camera_calibration.yaml",
        help="Plik kalibracji kamery (.npz/.yaml/.yml)",
    )
    p_track.add_argument("--track_mode", choices=["brightest", "color"], default="brightest", help="Tryb śledzenia")
    p_track.add_argument("--config", default="config/settings.yaml", help="Plik YAML z ustawieniami")
    p_track.add_argument("--color_name", choices=sorted(PRESET_HSV_RANGES.keys()), help="Preset koloru dla track_mode=color")
    p_track.add_argument("--hsv_lower", type=parse_hsv_triplet, help="Dolny próg HSV, np. 0,80,80")
    p_track.add_argument("--hsv_upper", type=parse_hsv_triplet, help="Górny próg HSV, np. 10,255,255")
    p_track.add_argument("--blur", type=int, help="Rozmiar filtra Gaussa")
    p_track.add_argument("--threshold", type=int, help="Próg jasności 0..255")
    p_track.add_argument("--erode_iter", type=int, help="Liczba iteracji erozji")
    p_track.add_argument("--dilate_iter", type=int, help="Liczba iteracji dylatacji")
    p_track.add_argument("--min_area", type=float, help="Minimalna powierzchnia konturu")
    p_track.add_argument("--max_area", type=float, help="Maksymalna powierzchnia konturu")
    p_track.add_argument("--roi", type=parse_roi, help="Obszar zainteresowania x,y,w,h")
    p_track.add_argument("--output_csv", help="Plik CSV z wynikami")
    p_track.add_argument("--trajectory_png", help="Plik PNG z wykresem trajektorii")
    p_track.add_argument("--report_csv", help="Plik CSV z raportem jakości")
    p_track.add_argument("--report_pdf", help="Plik PDF z raportem jakości")
    p_track.add_argument("--display", action="store_true", default=None, help="Pokaż podgląd na żywo")
    p_track.add_argument("--interactive", action="store_true", help="Interaktywny wybór kluczowych parametrów w terminalu")

    p_cmp = subparsers.add_parser("compare", help="Porównanie dwóch plików CSV")
    p_cmp.add_argument("--reference", required=True, help="CSV referencyjny")
    p_cmp.add_argument("--candidate", required=True, help="CSV porównywany")
    p_cmp.add_argument("--output_csv", help="Plik CSV z raportem szczegółowym")
    p_cmp.add_argument("--report_pdf", help="Plik PDF z raportem porównania")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "calibrate":
        calibrate_camera(args.calib_dir, args.rows, args.cols, args.square_size, args.output_file, args.output_format)
        return

    if args.command == "track":
        config = build_tracker_config(args)
        track_spot(config)
        return

    if args.command == "compare":
        compare_csv(args.reference, args.candidate, args.output_csv, args.report_pdf)
        return


if __name__ == "__main__":
    main()
