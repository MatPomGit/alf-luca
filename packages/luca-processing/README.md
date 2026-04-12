# luca-processing

Warstwa domenowa realizująca detekcję i post-processing trajektorii.

## Public API

- `BaseDetector`
- `DetectorConfig`
- `available_detector_names`
- `get_default_params`
- `get_detector_class`
- `BrightnessDetector`
- `COLOR_PRESETS`
- `ColorDetector`
- `DetectionPersistenceFilter`
- `TemporalMaskFilter`
- `build_mask`
- `contour_to_detection`
- `detect_spots`
- `detect_spots_with_config`
- `ensure_odd`
- `get_default_params_for_mode`
- `parse_hsv_pair`
- `parse_roi`
- `KalmanConfig`
- `apply_kalman_to_points`
- `smooth_xy_with_config`
- `parse_point_series`
- `estimate_pnp_pose`
- `pixel_to_world_on_plane`
