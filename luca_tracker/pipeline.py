from __future__ import annotations

import glob
import os
from typing import Any, Dict, List

import cv2
import numpy as np

from .detectors import detect_spots
from .postprocess import apply_kalman_to_points
from .reports import (
    generate_trajectory_png,
    metrics_from_points,
    save_all_tracks_csv,
    save_metrics_csv,
    save_track_csv,
    save_track_report_pdf,
)
from .tracker_core import SimpleMultiTracker, choose_main_track
from .types import TrackPoint
from .video_export import export_annotated_video


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
    print("\n=== Interaktywny dobór parametrów śledzenia ===")
    args.track_mode = ask_value("Tryb śledzenia (brightness/color)", str, args.track_mode)
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


def process_video_frames(args, camera_matrix=None, dist_coeffs=None) -> Dict[str, Any]:
    """Orkiestruje przetwarzanie wszystkich klatek i zwraca jednolity wynik przebiegu."""
    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise FileNotFoundError(f"Nie udało się otworzyć pliku video: {args.video}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    fps = fps if fps > 0 else 1.0

    tracker = SimpleMultiTracker(max_distance=args.max_distance, max_missed=args.max_missed)
    finished_tracks: Dict[int, Dict] = {}
    single_points: List[TrackPoint] = []

    frame_index = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break

        if camera_matrix is not None and dist_coeffs is not None:
            frame = cv2.undistort(frame, camera_matrix, dist_coeffs)

        detections, mask, roi_box = detect_spots(
            frame=frame,
            track_mode=args.track_mode,
            blur=args.blur,
            threshold=args.threshold,
            erode_iter=args.erode_iter,
            dilate_iter=args.dilate_iter,
            min_area=args.min_area,
            max_area=args.max_area,
            max_spots=args.max_spots,
            color_name=args.color_name,
            hsv_lower=args.hsv_lower,
            hsv_upper=args.hsv_upper,
            roi=args.roi,
        )

        time_sec = frame_index / fps

        if args.multi_track:
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

        if args.display:
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

    if args.multi_track:
        finished_tracks.update(tracker.close_all())

    result: Dict[str, Any] = {
        "fps": fps,
        "frame_count": frame_index,
        "multi_track": bool(args.multi_track),
        "finished_tracks": finished_tracks,
        "single_points": single_points,
        "main_track_id": None,
        "main_points": None,
    }

    if args.multi_track:
        if not finished_tracks:
            raise RuntimeError("Nie wykryto żadnych trajektorii.")
        main_track_id = choose_main_track(finished_tracks, args.selection_mode)
        if main_track_id is None:
            raise RuntimeError("Nie udało się wybrać głównej trajektorii.")
        result["main_track_id"] = main_track_id
        result["main_points"] = finished_tracks[main_track_id]["points"]
    else:
        result["main_track_id"] = 1
        result["main_points"] = single_points

    return result


def track_video(args):
    """Wysokopoziomowa funkcja CLI: uruchamia pipeline i zapisuje artefakty wynikowe."""
    if args.interactive:
        interactive_track_config(args)

    camera_matrix = None
    dist_coeffs = None
    if args.calib_file:
        data = np.load(args.calib_file)
        camera_matrix = data.get("camera_matrix")
        dist_coeffs = data.get("dist_coeffs")

    result = process_video_frames(args, camera_matrix=camera_matrix, dist_coeffs=dist_coeffs)
    main_points = result["main_points"]
    main_track_id = result["main_track_id"]

    if args.use_kalman:
        apply_kalman_to_points(
            main_points,
            process_noise=args.kalman_process_noise,
            measurement_noise=args.kalman_measurement_noise,
        )

    save_track_csv(main_points, args.output_csv)

    if args.multi_track:
        finished_tracks = result["finished_tracks"]
        print(f"[OK] Zapisano główną trajektorię do: {args.output_csv}")
        print(f"[OK] Wybrano track_id={main_track_id} jako trajektorię główną ({args.selection_mode})")
        if args.all_tracks_csv:
            save_all_tracks_csv(finished_tracks, args.all_tracks_csv)
            print(f"[OK] Zapisano wszystkie trajektorie do: {args.all_tracks_csv}")

        metrics = metrics_from_points(main_points)
        extra = [f"selected_track_id: {main_track_id}", f"selection_mode: {args.selection_mode}"]
        if args.trajectory_png:
            generate_trajectory_png(main_points, args.trajectory_png, title=f"Trajektoria główna track_id={main_track_id}")
            print(f"[OK] Zapisano wykres trajektorii: {args.trajectory_png}")
        if args.report_csv:
            save_metrics_csv(metrics, args.report_csv)
            print(f"[OK] Zapisano raport CSV: {args.report_csv}")
        if args.report_pdf:
            save_track_report_pdf(args.report_pdf, metrics, "Raport jakości śledzenia", args.trajectory_png, extra)
            print(f"[OK] Zapisano raport PDF: {args.report_pdf}")
        if args.annotated_video:
            export_annotated_video(
                input_video=args.video,
                output_video=args.annotated_video,
                track_histories=finished_tracks,
                main_track_id=main_track_id,
                draw_all_tracks=args.draw_all_tracks,
                roi=args.roi,
            )
            print(f"[OK] Zapisano wideo wynikowe: {args.annotated_video}")
    else:
        print(f"[OK] Zapisano wyniki do: {args.output_csv}")
        metrics = metrics_from_points(main_points)
        if args.trajectory_png:
            generate_trajectory_png(main_points, args.trajectory_png)
            print(f"[OK] Zapisano wykres trajektorii: {args.trajectory_png}")
        if args.report_csv:
            save_metrics_csv(metrics, args.report_csv)
            print(f"[OK] Zapisano raport CSV: {args.report_csv}")
        if args.report_pdf:
            save_track_report_pdf(args.report_pdf, metrics, "Raport jakości śledzenia", args.trajectory_png)
            print(f"[OK] Zapisano raport PDF: {args.report_pdf}")
        if args.annotated_video:
            pseudo_tracks = {1: {"points": main_points}}
            export_annotated_video(
                input_video=args.video,
                output_video=args.annotated_video,
                track_histories=pseudo_tracks,
                main_track_id=1,
                draw_all_tracks=True,
                roi=args.roi,
            )
            print(f"[OK] Zapisano wideo wynikowe: {args.annotated_video}")
