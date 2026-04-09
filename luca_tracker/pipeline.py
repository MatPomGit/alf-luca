from __future__ import annotations

import argparse
import glob
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import cv2
import numpy as np

from .detector_registry import available_detector_names
from .detectors import DetectorConfig, detect_spots_with_config
from .postprocess import KalmanConfig, apply_kalman_to_points
from .reports import (
    generate_trajectory_png,
    metrics_from_points,
    save_all_tracks_csv,
    save_metrics_csv,
    save_track_csv,
    save_track_report_pdf,
)
from .tracker_core import SimpleMultiTracker, TrackerConfig, choose_main_track
from .types import TrackPoint
from .video_export import export_annotated_video


@dataclass
class PipelineConfig:
    """Pełna konfiguracja pipeline'u umożliwiająca uruchamianie niezależne od CLI."""

    video: str
    calib_file: Optional[str] = None
    display: bool = False
    interactive: bool = False
    multi_track: bool = False
    selection_mode: str = "stablest"
    output_csv: str = "tracking_results.csv"
    trajectory_png: Optional[str] = None
    report_csv: Optional[str] = None
    report_pdf: Optional[str] = None
    all_tracks_csv: Optional[str] = None
    annotated_video: Optional[str] = None
    draw_all_tracks: bool = False
    use_kalman: bool = False
    detector: DetectorConfig = field(default_factory=DetectorConfig)
    tracker: TrackerConfig = field(default_factory=TrackerConfig)
    kalman: KalmanConfig = field(default_factory=KalmanConfig)


ANSI = {
    "reset": "\033[0m",
    "green": "\033[92m",
    "yellow": "\033[93m",
    "cyan": "\033[96m",
    "magenta": "\033[95m",
}


def _log_stage(kind: str, message: str, color: str = "cyan") -> None:
    """Drukuje kolorową informację o etapie pipeline'u."""
    prefix = f"[{kind}]"
    tone = ANSI.get(color, "")
    reset = ANSI["reset"] if tone else ""
    print(f"{tone}{prefix} {message}{reset}")


def ask_value(prompt: str, cast, default):
    """Pobiera wartość od użytkownika z obsługą domyślnej odpowiedzi."""
    raw = input(f"{prompt} [{default}]: ").strip()
    if raw == "":
        return default
    return cast(raw)


def ask_bool(prompt: str, default: bool) -> bool:
    """Pobiera wartość logiczną od użytkownika w trybie interaktywnym."""
    d = "t" if default else "n"
    raw = input(f"{prompt} [t/n, domyślnie {d}]: ").strip().lower()
    if raw == "":
        return default
    return raw in {"t", "tak", "y", "yes", "1"}


def interactive_track_config(args):
    """Umożliwia ręczne strojenie parametrów śledzenia przed startem."""
    supported_modes = "/".join(available_detector_names())
    print("\n=== Interaktywny dobór parametrów śledzenia ===")
    args.track_mode = ask_value(f"Tryb śledzenia ({supported_modes})", str, args.track_mode)
    args.blur = ask_value("Rozmiar rozmycia Gaussa (nieparzysty)", int, args.blur)
    args.threshold = ask_value("Próg jasności 0-255", int, args.threshold)
    args.min_area = ask_value("Minimalne pole plamki", float, args.min_area)
    args.max_area = ask_value("Maksymalne pole plamki (0 = brak limitu)", float, args.max_area)
    args.erode_iter = ask_value("Liczba erozji", int, args.erode_iter)
    args.dilate_iter = ask_value("Liczba dylatacji", int, args.dilate_iter)
    args.multi_track = ask_bool("Śledzić wiele plamek jednocześnie?", args.multi_track)
    args.max_spots = ask_value("Maksymalna liczba plamek na klatkę", int, args.max_spots)
    args.selection_mode = ask_value(
        "Jak wybrać trajektorię główną? (largest/stablest/longest)", str, args.selection_mode
    )
    if args.track_mode == "color":
        args.color_name = ask_value(
            "Kolor (red/green/blue/yellow/white/orange/purple/custom)",
            str,
            args.color_name,
        )
        if args.color_name == "custom":
            args.hsv_lower = ask_value("HSV lower, np. 0,80,80", str, args.hsv_lower or "0,80,80")
            args.hsv_upper = ask_value("HSV upper, np. 10,255,255", str, args.hsv_upper or "10,255,255")
    roi_raw = input(
        f"ROI x,y,w,h lub ENTER dla pełnego kadru [{args.roi if args.roi else 'pełny kadr'}]: "
    ).strip()
    if roi_raw:
        args.roi = roi_raw
    return args


def calibrate_camera(calib_dir: str, rows: int, cols: int, square_size: float, output_file: str):
    """Kalibruje kamerę na podstawie wzorca szachownicy i zapisuje parametry do .npz."""
    objp = np.zeros((rows * cols, 3), np.float32)
    objp[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2)
    objp *= square_size

    objpoints = []
    imgpoints = []

    images = []
    for pattern in ("*.png", "*.jpg", "*.jpeg", "*.bmp"):
        images.extend(glob.glob(os.path.join(calib_dir, pattern)))

    if not images:
        raise FileNotFoundError(f"Brak obrazów kalibracyjnych w katalogu: {calib_dir}")

    gray_shape = None
    for fname in images:
        image = cv2.imread(fname)
        if image is None:
            continue
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        ok, corners = cv2.findChessboardCorners(gray, (cols, rows), None)
        if not ok:
            print(f"[INFO] Pominięto {fname} - nie znaleziono narożników.")
            continue
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
        corners2 = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
        objpoints.append(objp)
        imgpoints.append(corners2)
        gray_shape = gray.shape[::-1]

    if not objpoints:
        raise RuntimeError("Nie udało się znaleźć wzorca na żadnym obrazie.")

    _, camera_matrix, dist_coeffs, _, _ = cv2.calibrateCamera(objpoints, imgpoints, gray_shape, None, None)
    np.savez(output_file, camera_matrix=camera_matrix, dist_coeffs=dist_coeffs)
    print(f"[OK] Zapisano kalibrację do: {output_file}")


def _resolve_config(args_or_config) -> PipelineConfig:
    """Mapuje obiekt CLI args lub PipelineConfig na spójny model konfiguracji."""
    if isinstance(args_or_config, PipelineConfig):
        return args_or_config

    return PipelineConfig(
        video=args_or_config.video,
        calib_file=getattr(args_or_config, "calib_file", None),
        display=getattr(args_or_config, "display", False),
        interactive=getattr(args_or_config, "interactive", False),
        multi_track=getattr(args_or_config, "multi_track", False),
        selection_mode=getattr(args_or_config, "selection_mode", "stablest"),
        output_csv=getattr(args_or_config, "output_csv", "tracking_results.csv"),
        trajectory_png=getattr(args_or_config, "trajectory_png", None),
        report_csv=getattr(args_or_config, "report_csv", None),
        report_pdf=getattr(args_or_config, "report_pdf", None),
        all_tracks_csv=getattr(args_or_config, "all_tracks_csv", None),
        annotated_video=getattr(args_or_config, "annotated_video", None),
        draw_all_tracks=getattr(args_or_config, "draw_all_tracks", False),
        use_kalman=getattr(args_or_config, "use_kalman", False),
        detector=DetectorConfig(
            track_mode=getattr(args_or_config, "track_mode", "brightness"),
            blur=getattr(args_or_config, "blur", 11),
            threshold=getattr(args_or_config, "threshold", 200),
            erode_iter=getattr(args_or_config, "erode_iter", 2),
            dilate_iter=getattr(args_or_config, "dilate_iter", 4),
            min_area=getattr(args_or_config, "min_area", 10.0),
            max_area=getattr(args_or_config, "max_area", 0.0),
            max_spots=getattr(args_or_config, "max_spots", 10),
            color_name=getattr(args_or_config, "color_name", "red"),
            hsv_lower=getattr(args_or_config, "hsv_lower", None),
            hsv_upper=getattr(args_or_config, "hsv_upper", None),
            roi=getattr(args_or_config, "roi", None),
        ),
        tracker=TrackerConfig(
            max_distance=getattr(args_or_config, "max_distance", 40.0),
            max_missed=getattr(args_or_config, "max_missed", 10),
            selection_mode=getattr(args_or_config, "selection_mode", "stablest"),
        ),
        kalman=KalmanConfig(
            process_noise=getattr(args_or_config, "kalman_process_noise", 1e-2),
            measurement_noise=getattr(args_or_config, "kalman_measurement_noise", 1e-1),
        ),
    )


def process_video_frames(args_or_config, camera_matrix=None, dist_coeffs=None) -> Dict[str, Any]:
    """Orkiestruje przetwarzanie wszystkich klatek i zwraca jednolity wynik przebiegu."""
    config = _resolve_config(args_or_config)
    cap = cv2.VideoCapture(config.video)
    if not cap.isOpened():
        raise FileNotFoundError(f"Nie udało się otworzyć pliku video: {config.video}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    fps = fps if fps > 0 else 1.0

    tracker = SimpleMultiTracker(
        max_distance=config.tracker.max_distance,
        max_missed=config.tracker.max_missed,
    )
    finished_tracks: Dict[int, Dict] = {}
    single_points: List[TrackPoint] = []

    frame_index = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break

        if camera_matrix is not None and dist_coeffs is not None:
            frame = cv2.undistort(frame, camera_matrix, dist_coeffs)

        detections, mask, roi_box = detect_spots_with_config(frame, config.detector)
        time_sec = frame_index / fps

        if config.multi_track:
            ended = tracker.update(detections, frame_index, time_sec)
            finished_tracks.update(ended)
        else:
            best = detections[0] if detections else None
            single_points.append(
                TrackPoint(
                    frame_index=frame_index,
                    time_sec=time_sec,
                    detected=best is not None,
                    x=best.x if best else None,
                    y=best.y if best else None,
                    area=best.area if best else None,
                    perimeter=best.perimeter if best else None,
                    circularity=best.circularity if best else None,
                    radius=best.radius if best else None,
                    track_id=1 if best else None,
                    rank=best.rank if best else None,
                    kalman_predicted=0,
                )
            )

        if config.display:
            vis = frame.copy()
            x0, y0, w, h = roi_box
            cv2.rectangle(vis, (x0, y0), (x0 + w, y0 + h), (255, 255, 0), 1)
            for i, det in enumerate(detections, start=1):
                cx, cy = int(round(det.x)), int(round(det.y))
                cv2.circle(vis, (cx, cy), max(3, int(round(det.radius))), (0, 0, 255), 2)
                cv2.putText(vis, f"{i} A={det.area:.0f}", (cx + 5, cy - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)
            cv2.putText(vis, f"Frame: {frame_index}", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)
            cv2.putText(vis, f"Detections: {len(detections)}", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)
            cv2.imshow("Tracking", vis)
            cv2.imshow("Mask", mask)
            if (cv2.waitKey(1) & 0xFF) == ord("q"):
                break

        frame_index += 1

    cap.release()
    cv2.destroyAllWindows()

    if config.multi_track:
        finished_tracks.update(tracker.close_all())

    result: Dict[str, Any] = {
        "config": config,
        "fps": fps,
        "frame_count": frame_index,
        "multi_track": config.multi_track,
        "finished_tracks": finished_tracks,
        "single_points": single_points,
        "main_track_id": None,
        "main_points": None,
    }

    if config.multi_track:
        if not finished_tracks:
            raise RuntimeError("Nie wykryto żadnych trajektorii.")
        main_track_id = choose_main_track(finished_tracks, config.selection_mode)
        if main_track_id is None:
            raise RuntimeError("Nie udało się wybrać głównej trajektorii.")
        result["main_track_id"] = main_track_id
        result["main_points"] = finished_tracks[main_track_id]["points"]
    else:
        result["main_track_id"] = 1
        result["main_points"] = single_points

    return result


def track_video(args_or_config):
    """Wysokopoziomowa funkcja CLI: uruchamia pipeline i zapisuje artefakty wynikowe."""
    if not isinstance(args_or_config, PipelineConfig) and getattr(args_or_config, "interactive", False):
        interactive_track_config(args_or_config)

    config = _resolve_config(args_or_config)
    _log_stage(
        "OK",
        (
            f"Start analizy | mode={config.detector.track_mode}, "
            f"multi_track={config.multi_track}, use_kalman={config.use_kalman}, "
            f"selection_mode={config.selection_mode}"
        ),
        "magenta",
    )
    _log_stage("OK", f"Wczytywanie pliku do analizy: {config.video}", "yellow")

    camera_matrix = None
    dist_coeffs = None
    if config.calib_file:
        _log_stage("OK", f"Wczytuję kalibrację: {config.calib_file}", "yellow")
        data = np.load(config.calib_file)
        camera_matrix = data.get("camera_matrix")
        dist_coeffs = data.get("dist_coeffs")

    result = process_video_frames(config, camera_matrix=camera_matrix, dist_coeffs=dist_coeffs)
    main_points = result["main_points"]
    main_track_id = result["main_track_id"]

    if config.use_kalman:
        apply_kalman_to_points(
            main_points,
            process_noise=config.kalman.process_noise,
            measurement_noise=config.kalman.measurement_noise,
        )
        _log_stage("OK", "Zastosowano filtrację Kalmana.", "yellow")

    save_track_csv(main_points, config.output_csv)
    _log_stage("OK", f"Zapisano CSV pomiarowy: {config.output_csv}", "green")

    if config.multi_track:
        finished_tracks = result["finished_tracks"]
        _log_stage("OK", f"Wybrano track_id={main_track_id} jako trajektorię główną ({config.selection_mode})", "green")
        if config.all_tracks_csv:
            save_all_tracks_csv(finished_tracks, config.all_tracks_csv)
            _log_stage("OK", f"Zapisano wszystkie trajektorie: {config.all_tracks_csv}", "green")

        metrics = metrics_from_points(main_points)
        extra = [f"selected_track_id: {main_track_id}", f"selection_mode: {config.selection_mode}"]
        if config.trajectory_png:
            generate_trajectory_png(main_points, config.trajectory_png, title=f"Trajektoria główna track_id={main_track_id}")
            _log_stage("OK", f"Zapisano wykres trajektorii: {config.trajectory_png}", "green")
        if config.report_csv:
            save_metrics_csv(metrics, config.report_csv)
            _log_stage("OK", f"Zapisano raport CSV: {config.report_csv}", "green")
        if config.report_pdf:
            save_track_report_pdf(config.report_pdf, metrics, "Raport jakości śledzenia", config.trajectory_png, extra)
            _log_stage("OK", f"Zapisano raport PDF: {config.report_pdf}", "green")
        if config.annotated_video:
            export_annotated_video(
                input_video=config.video,
                output_video=config.annotated_video,
                track_histories=finished_tracks,
                main_track_id=main_track_id,
                draw_all_tracks=config.draw_all_tracks,
                roi=config.detector.roi,
            )
            _log_stage("OK", f"Zapisano wideo wynikowe: {config.annotated_video}", "green")
    else:
        metrics = metrics_from_points(main_points)
        if config.trajectory_png:
            generate_trajectory_png(main_points, config.trajectory_png)
            _log_stage("OK", f"Zapisano wykres trajektorii: {config.trajectory_png}", "green")
        if config.report_csv:
            save_metrics_csv(metrics, config.report_csv)
            _log_stage("OK", f"Zapisano raport CSV: {config.report_csv}", "green")
        if config.report_pdf:
            save_track_report_pdf(config.report_pdf, metrics, "Raport jakości śledzenia", config.trajectory_png)
            _log_stage("OK", f"Zapisano raport PDF: {config.report_pdf}", "green")
        if config.annotated_video:
            pseudo_tracks = {1: {"points": main_points}}
            export_annotated_video(
                input_video=config.video,
                output_video=config.annotated_video,
                track_histories=pseudo_tracks,
                main_track_id=1,
                draw_all_tracks=True,
                roi=config.detector.roi,
            )
            _log_stage("OK", f"Zapisano wideo wynikowe: {config.annotated_video}", "green")

    _log_stage("OK", "Przetwarzanie zakończone.", "magenta")


def _build_parser() -> argparse.ArgumentParser:
    """Tworzy lekki parser standalone dla modułu pipeline."""
    detector_names = available_detector_names()
    parser = argparse.ArgumentParser(description="Standalone tracking pipeline runner.")
    parser.add_argument("--video", required=True)
    parser.add_argument("--output_csv", default="tracking_results.csv")
    parser.add_argument("--track_mode", choices=detector_names, default="brightness")
    parser.add_argument("--threshold", type=int, default=200)
    parser.add_argument("--blur", type=int, default=11)
    parser.add_argument("--min_area", type=float, default=10.0)
    parser.add_argument("--max_area", type=float, default=0.0)
    parser.add_argument("--erode_iter", type=int, default=2)
    parser.add_argument("--dilate_iter", type=int, default=4)
    parser.add_argument("--color_name", default="red")
    parser.add_argument("--hsv_lower")
    parser.add_argument("--hsv_upper")
    parser.add_argument("--roi")
    parser.add_argument("--multi_track", action="store_true")
    parser.add_argument("--max_spots", type=int, default=10)
    parser.add_argument("--max_distance", type=float, default=40.0)
    parser.add_argument("--max_missed", type=int, default=10)
    parser.add_argument("--selection_mode", choices=["largest", "stablest", "longest"], default="stablest")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Punkt wejścia standalone: uruchamia pełny pipeline bez warstwy CLI aplikacji."""
    args = _build_parser().parse_args(argv)
    track_video(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
