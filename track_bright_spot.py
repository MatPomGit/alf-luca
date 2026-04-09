#!/usr/bin/env python3
"""
Bright spot tracker with camera calibration
==========================================

This script allows you to calibrate a camera using a series of chessboard
images and then track the brightest blob in an MP4 video file.  It exposes
two sub‑commands:

```
python track_bright_spot.py calibrate --calib_dir path/to/images --rows 6 --cols 9 --square_size 1.0 --output_file camera_calib.npz
python track_bright_spot.py track --video path/to/video.mp4 --calib_file camera_calib.npz --blur 11 --threshold 200 --output_csv results.csv
```

*Camera calibration.*  The calibration routine follows the standard
OpenCV procedure: supply a set of images of a known chessboard pattern.
The script finds the 2D image coordinates of the corners via
``cv2.findChessboardCorners`` and refines them with
``cv2.cornerSubPix`` before calling ``cv2.calibrateCamera``.  The
GeeksforGeeks tutorial summarises this process, noting that you first
define 3D real‑world coordinates for the chessboard corners, capture
multiple viewpoints of the checkerboard, locate the pixel coordinates of
the corners with ``findChessboardCorners`` and finally call
``calibrateCamera`` to obtain the camera matrix and distortion
coefficients【432967165344016†L52-L66】.

*Bright spot detection.*  To track a light source the script applies
basic image processing techniques.  Each frame of the input video is
converted to grayscale and smoothed with a Gaussian blur, a step that
PyImageSearch emphasises to reduce high‑frequency noise【957838594901123†L249-L265】.
The blurred image is then thresholded to isolate bright regions.  Pixels
with intensities above the chosen threshold are set to white and
everything else to black【123050553842223†L140-L165】.  A sequence of
erosions followed by dilations (morphological opening and closing) is
applied to remove small noisy blobs【123050553842223†L177-L184】.  The
script identifies the largest remaining contour and computes its
centroid using image moments; this provides the pixel coordinates of
the bright spot.  Each detection, along with the frame number and
timestamp, is written to a CSV file for later comparison.

This program is designed to be executed from the terminal.  Use
``--help`` on either sub‑command to see the full set of options.
"""

import argparse
import csv
import glob
import os
import sys
from typing import Iterable, List, Optional, Tuple

import cv2  # type: ignore
import numpy as np  # type: ignore


def calibrate_camera(
    calib_dir: str,
    pattern_rows: int,
    pattern_cols: int,
    square_size: float,
    output_file: str,
) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """Calibrate the camera using images of a chessboard pattern.

    Parameters
    ----------
    calib_dir : str
        Path to a directory containing images of a calibration pattern.
    pattern_rows : int
        Number of inner corners per row on the chessboard.
    pattern_cols : int
        Number of inner corners per column on the chessboard.
    square_size : float
        Physical size of one square on the chessboard in arbitrary units.
    output_file : str
        Path where the calibration parameters (camera matrix and
        distortion coefficients) will be saved (.npz format).

    Returns
    -------
    (camera_matrix, dist_coeffs) if successful, otherwise ``None``.
    """
    # Prepare object points based on the known pattern geometry.  For
    # example, for a 9×6 board there are 9 columns and 6 rows of
    # internal corners.  These corners are laid out on the Z=0 plane.
    objp = np.zeros((pattern_rows * pattern_cols, 3), np.float32)
    objp[:, :2] = np.mgrid[0:pattern_cols, 0:pattern_rows].T.reshape(-1, 2)
    objp *= square_size

    objpoints: List[np.ndarray] = []  # 3D points in real world
    imgpoints: List[np.ndarray] = []  # 2D points in image plane

    # Collect all image files from the calibration directory.  Accept
    # common image extensions.
    patterns = ["*.png", "*.jpg", "*.jpeg", "*.bmp"]
    images: List[str] = []
    for pattern in patterns:
        images.extend(glob.glob(os.path.join(calib_dir, pattern)))

    if not images:
        print(f"[ERROR] No calibration images found in {calib_dir}.")
        return None

    gray_shape: Optional[Tuple[int, int]] = None
    for fname in images:
        img = cv2.imread(fname)
        if img is None:
            print(f"[WARNING] Could not read image {fname}, skipping.")
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # Attempt to locate chessboard corners
        ret, corners = cv2.findChessboardCorners(gray, (pattern_cols, pattern_rows), None)
        if ret:
            # Refine corner locations to subpixel accuracy
            criteria = (
                cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
                30,
                0.001,
            )
            corners2 = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
            objpoints.append(objp)
            imgpoints.append(corners2)
            gray_shape = gray.shape[::-1]
        else:
            print(f"[INFO] Chessboard corners not found in {fname}, skipping.")

    if not objpoints:
        print("[ERROR] Could not find corners in any calibration image.")
        return None

    # Perform camera calibration.  According to OpenCV documentation you
    # should supply the object points and their corresponding image
    # coordinates for each view and then call calibrateCamera【432967165344016†L52-L66】.
    ret, camera_matrix, dist_coeffs, rvecs, tvecs = cv2.calibrateCamera(
        objpoints, imgpoints, gray_shape, None, None
    )
    if ret:
        np.savez(output_file, camera_matrix=camera_matrix, dist_coeffs=dist_coeffs)
        print(f"[INFO] Calibration successful. Parameters saved to {output_file}.")
        return camera_matrix, dist_coeffs
    else:
        print("[ERROR] Calibration failed.")
        return None


def track_bright_spot(
    video_path: str,
    calib_file: Optional[str],
    blur: int,
    threshold: int,
    output_csv: str,
    display: bool = False,
) -> None:
    """Track the brightest blob in a video and export results to CSV.

    Parameters
    ----------
    video_path : str
        Path to the video file (.mp4).
    calib_file : str, optional
        Path to a .npz file containing calibration parameters.  If
        provided, frames are undistorted before processing.
    blur : int
        Kernel size for Gaussian blurring.  Must be an odd integer.
    threshold : int
        Pixel intensity threshold for bright spot detection.  Pixels
        above this value are considered part of the light source【123050553842223†L140-L165】.
    output_csv : str
        Path to the output CSV file that will store tracking results.
    display : bool, optional
        If True, show a window with annotated tracking in real time.
    """
    # Load calibration parameters if available
    camera_matrix: Optional[np.ndarray] = None
    dist_coeffs: Optional[np.ndarray] = None
    if calib_file:
        try:
            data = np.load(calib_file)
            camera_matrix = data.get("camera_matrix")
            dist_coeffs = data.get("dist_coeffs")
        except Exception as e:
            print(f"[WARNING] Failed to load calibration file {calib_file}: {e}")

    # Validate blur kernel size: must be odd
    if blur % 2 == 0:
        blur += 1
        print(f"[INFO] Adjusted blur kernel size to {blur} (must be odd).")

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"[ERROR] Could not open video {video_path}.")
        return
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_number = 0
    results: List[List[Optional[float]]] = []
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        # Undistort the frame if calibration data is available
        if camera_matrix is not None and dist_coeffs is not None:
            frame = cv2.undistort(frame, camera_matrix, dist_coeffs)

        # Convert to grayscale and blur to reduce noise【957838594901123†L249-L265】
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (blur, blur), 0)

        # Threshold to reveal bright regions【123050553842223†L140-L165】
        _, thresh_img = cv2.threshold(blurred, threshold, 255, cv2.THRESH_BINARY)

        # Morphological opening and closing to remove small blobs【123050553842223†L177-L184】
        thresh_img = cv2.erode(thresh_img, None, iterations=2)
        thresh_img = cv2.dilate(thresh_img, None, iterations=4)

        # Find contours in the thresholded image
        contours, _ = cv2.findContours(
            thresh_img.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        cX: Optional[int] = None
        cY: Optional[int] = None
        area: float = 0.0
        if contours:
            # Identify the largest contour by area
            c = max(contours, key=cv2.contourArea)
            area = float(cv2.contourArea(c))
            M = cv2.moments(c)
            if M["m00"] != 0:
                cX = int(M["m10"] / M["m00"])
                cY = int(M["m01"] / M["m00"])
                if display:
                    cv2.circle(frame, (cX, cY), 5, (0, 0, 255), -1)
        # Compute timestamp in seconds
        time_sec = frame_number / fps if fps > 0 else float(frame_number)
        results.append([frame_number, time_sec, cX, cY, area])
        if display:
            cv2.putText(
                frame,
                f"Frame: {frame_number}",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 0, 0),
                2,
            )
            if cX is not None and cY is not None:
                cv2.putText(
                    frame,
                    f"Spot: ({cX}, {cY})", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2
                )
            cv2.imshow("Bright Spot Tracking", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
        frame_number += 1

    cap.release()
    if display:
        cv2.destroyAllWindows()

    # Export results to CSV
    try:
        with open(output_csv, mode="w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["frame_index", "time_sec", "x", "y", "area"])
            writer.writerows(results)
        print(f"[INFO] Tracking complete. Results saved to {output_csv}.")
    except Exception as e:
        print(f"[ERROR] Could not write CSV file {output_csv}: {e}")


def main() -> None:
    """Entry point for the command‑line interface."""
    parser = argparse.ArgumentParser(
        description="Track a bright light source in a video with optional camera calibration."
    )
    subparsers = parser.add_subparsers(dest="command", help="Sub‑commands")

    # Calibration sub‑command
    calibrate_parser = subparsers.add_parser(
        "calibrate", help="Calibrate camera using chessboard images"
    )
    calibrate_parser.add_argument(
        "--calib_dir",
        required=True,
        help="Directory containing chessboard calibration images",
    )
    calibrate_parser.add_argument(
        "--rows",
        type=int,
        default=6,
        help="Number of inner corners per row on the chessboard",
    )
    calibrate_parser.add_argument(
        "--cols",
        type=int,
        default=9,
        help="Number of inner corners per column on the chessboard",
    )
    calibrate_parser.add_argument(
        "--square_size",
        type=float,
        default=1.0,
        help="Physical size of a square on the chessboard (arbitrary units)",
    )
    calibrate_parser.add_argument(
        "--output_file",
        default="camera_calib.npz",
        help="Filename for saving calibration parameters (npz)",
    )

    # Tracking sub‑command
    track_parser = subparsers.add_parser(
        "track", help="Track the brightest spot in a video"
    )
    track_parser.add_argument(
        "--video",
        required=True,
        help="Path to the input video (e.g., .mp4)",
    )
    track_parser.add_argument(
        "--calib_file",
        help="Path to a saved calibration file (.npz) to undistort frames",
    )
    track_parser.add_argument(
        "--blur",
        type=int,
        default=11,
        help="Gaussian blur kernel size (odd integer)",
    )
    track_parser.add_argument(
        "--threshold",
        type=int,
        default=200,
        help="Intensity threshold for detecting bright pixels (0–255)",
    )
    track_parser.add_argument(
        "--output_csv",
        default="tracking_results.csv",
        help="CSV file to write tracking results",
    )
    track_parser.add_argument(
        "--display",
        action="store_true",
        help="Visualise tracking in real time (press q to quit)",
    )

    args = parser.parse_args()
    if args.command == "calibrate":
        calibrate_camera(
            args.calib_dir, args.rows, args.cols, args.square_size, args.output_file
        )
    elif args.command == "track":
        track_bright_spot(
            args.video, args.calib_file, args.blur, args.threshold, args.output_csv, args.display
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()