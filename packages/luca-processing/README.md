# luca-processing

Warstwa domenowa realizująca detekcję i post-processing trajektorii.

## Public API

Sekcja odzwierciedla eksporty deklarowane w module inicjalizującym pakiet.

- `BaseDetector`
- `DetectorConfig`
- `available_detector_names`
- `available_detection_profiles`
- `get_default_params`
- `get_detector_class`
- `resolve_detection_profile`
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
- `ProjectionStageStatus`
- `PnPPoseEstimateResult`
- `WorldProjectionResult`
- `estimate_pnp_pose`
- `estimate_pnp_pose_with_status`
- `pixel_to_world_on_plane`
- `pixel_to_world_on_plane_with_status`
- `world_projection_reason_from_codes`

## Profile detekcji (opcjonalne)

Pakiet udostępnia profile `detector_profile`, które nadpisują tylko wybrane parametry detekcji:

- `bright_default` — stabilny profil bazowy dla `track_mode=brightness`,
- `bright_low_light_exp` — profil eksperymentalny dla nierównego oświetlenia,
- `color_robust_exp` — profil eksperymentalny dla `track_mode=color` i podwyższonego szumu.

### Ograniczenia profili

- Profil musi być zgodny z `track_mode` (np. profil kolorowy nie zadziała dla `brightness`).
- Profile eksperymentalne wymagają flagi `enable_experimental_profiles=true`.
- Profil nie zastępuje całej konfiguracji; wartości nieobecne w profilu pozostają z wejścia użytkownika.
