# luca-input

Warstwa bazowa odpowiedzialna za mapowanie konfiguracji i normalizację ścieżek wejścia/wyjścia.

## Public API

- `RuntimePathPolicy`, `RuntimePathResolver`
- `ensure_output_dir`, `ensure_run_output_dir`, `resolve_output_path`, `resolve_analysis_input`, `resolve_source_asset`
- `build_measurement_stem`, `parse_camera_source`, `with_default`
- `pipeline_config_to_run_config`, `run_config_to_pipeline_config`
