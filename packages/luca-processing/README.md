# luca-processing

Warstwa domenowa realizująca detekcję i post-processing trajektorii.

## Public API

- `BaseDetector`, `DetectorConfig`
- `available_detector_names`, `get_detector_class`, `get_default_params`
- `BrightnessDetector`, `ColorDetector`, `TemporalMaskFilter`
- `detect_spots`, `detect_spots_with_config`, `get_default_params_for_mode`
- `KalmanConfig`, `apply_kalman_to_points`, `smooth_xy_with_config`
- `parse_point_series`, `estimate_pnp_pose`, `pixel_to_world_on_plane` (wspólny algorytm XYZ dla offline i ROS2)
