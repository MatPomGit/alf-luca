"""Pakiet wejścia danych i mapowania konfiguracji uruchomienia."""

from luca_input.io_paths import (
    RuntimePathPolicy,
    RuntimePathResolver,
    build_measurement_stem,
    ensure_output_dir,
    ensure_run_output_dir,
    parse_camera_source,
    resolve_analysis_input,
    resolve_output_path,
    resolve_source_asset,
    with_default,
)
from luca_input.pipeline_config_mapping import pipeline_config_to_run_config, run_config_to_pipeline_config
from luca_input.entrypoint_option_contract import (
    PARAMETER_MATRIX,
    add_shared_calibration_options,
    add_shared_detection_options,
    add_shared_postprocess_options,
    add_shared_reporting_options,
    add_shared_ros2_runtime_options,
    add_shared_runtime_source_options,
    add_shared_tracking_options,
)

__all__ = [
    "RuntimePathPolicy",
    "RuntimePathResolver",
    "build_measurement_stem",
    "ensure_output_dir",
    "ensure_run_output_dir",
    "parse_camera_source",
    "resolve_analysis_input",
    "resolve_output_path",
    "resolve_source_asset",
    "with_default",
    "pipeline_config_to_run_config",
    "run_config_to_pipeline_config",
    "PARAMETER_MATRIX",
    "add_shared_calibration_options",
    "add_shared_detection_options",
    "add_shared_postprocess_options",
    "add_shared_reporting_options",
    "add_shared_ros2_runtime_options",
    "add_shared_runtime_source_options",
    "add_shared_tracking_options",
]
