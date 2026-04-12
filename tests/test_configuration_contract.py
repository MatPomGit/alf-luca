from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _package_src in (
    "packages/luca-types/src",
    "packages/luca-input/src",
    "packages/luca-camera/src",
    "packages/luca-processing/src",
    "packages/luca-reporting/src",
    "packages/luca-publishing/src",
    "packages/luca-tracking/src",
    "packages/luca-interface-cli/src",
    "packages/luca-interface-gui/src",
    "packages/luca-interface-ros2/src",
):
    sys.path.insert(0, str(_REPO_ROOT / _package_src))

from luca_input import PARAMETER_MATRIX, run_config_to_pipeline_config
from luca_types import load_run_config, run_config_from_entrypoint


def _load_module_from_path(module_name: str, relative_path: str):
    """Ładuje moduł bez importu pakietu nadrzędnego, aby uniknąć ciężkich zależności runtime."""
    spec = importlib.util.spec_from_file_location(module_name, _REPO_ROOT / relative_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Nie udało się załadować modułu: {module_name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_shared_option_set() -> list[str]:
    """Zwraca wspólny zestaw opcji, który powinien mapować się identycznie między entrypointami."""
    return [
        "--calib_file",
        "camera_calib.npz",
        "--track_mode",
        "color",
        "--threshold",
        "210",
        "--threshold_mode",
        "adaptive",
        "--adaptive_block_size",
        "41",
        "--adaptive_c",
        "2.5",
        "--use_clahe",
        "--blur",
        "9",
        "--min_area",
        "12",
        "--max_area",
        "1200",
        "--erode_iter",
        "1",
        "--dilate_iter",
        "3",
        "--opening_kernel",
        "3",
        "--closing_kernel",
        "3",
        "--min_detection_confidence",
        "0.25",
        "--min_detection_score",
        "0.15",
        "--temporal_stabilization",
        "--temporal_window",
        "5",
        "--temporal_mode",
        "majority",
        "--min_persistence_frames",
        "2",
        "--persistence_radius_px",
        "9.0",
        "--roi",
        "1,2,100,80",
        "--color_name",
        "red",
        "--hsv_lower",
        "0,80,80",
        "--hsv_upper",
        "10,255,255",
        "--max_spots",
        "4",
        "--pnp_object_points",
        "0,0,0;1,0,0;0,1,0;1,1,0",
        "--pnp_image_points",
        "100,100;200,100;100,200;200,200",
        "--pnp_world_plane_z",
        "1.5",
    ]


def test_configuration_contract_is_identical_between_cli_gui_ros2() -> None:
    """Sprawdza kontrakt: ten sam zestaw opcji wejściowych daje identyczny RunConfig."""
    cli_parser_module = _load_module_from_path(
        "contract_cli_parser",
        "packages/luca-interface-cli/src/luca_interface_cli/parser.py",
    )
    gui_parser_module = _load_module_from_path(
        "contract_gui_parser",
        "packages/luca-interface-gui/src/luca_interface_gui/gui_parser.py",
    )
    # Stub `luca_tracking`, aby parser ROS2 dał się załadować bez OpenCV/libGL.
    sys.modules.setdefault("luca_tracking", types.SimpleNamespace(run_ros2=lambda _args: None))
    ros2_main_module = _load_module_from_path(
        "contract_ros2_main",
        "packages/luca-interface-ros2/src/luca_interface_ros2/main.py",
    )

    shared = _build_shared_option_set()

    cli_args = cli_parser_module.build_parser().parse_args(["track", "--camera", "0", *shared])
    gui_args = gui_parser_module.build_gui_parser().parse_args(["--camera", "0", *shared])
    ros2_args = ros2_main_module._build_ros2_parser().parse_args(["--camera_index", "0", *shared])

    cli_cfg = run_config_from_entrypoint(cli_args, entrypoint="track")
    gui_cfg = run_config_from_entrypoint(gui_args, entrypoint="gui")
    ros2_cfg = run_config_from_entrypoint(ros2_args, entrypoint="ros2")

    assert cli_cfg.to_dict() == gui_cfg.to_dict()
    assert cli_cfg.to_dict() == ros2_cfg.to_dict()


def test_pipeline_mapping_validates_multitrack_contract() -> None:
    """Waliduje czytelny błąd kontraktu przy niespójnym multi-track."""
    cli_parser_module = _load_module_from_path(
        "contract_cli_parser_for_validation",
        "packages/luca-interface-cli/src/luca_interface_cli/parser.py",
    )
    args = cli_parser_module.build_parser().parse_args(["track", "--camera", "0", "--multi_track", "--max_spots", "1"])
    config = run_config_from_entrypoint(args, entrypoint="track")

    try:
        run_config_to_pipeline_config(config)
    except ValueError as exc:
        assert "multi_track" in str(exc)
        assert "max_spots" in str(exc)
    else:
        raise AssertionError("Oczekiwano błędu walidacji kontraktu dla multi_track/max_spots.")


def test_parameter_matrix_contract_rows_cover_pipeline_mapping() -> None:
    """Pilnuje, żeby matryca parametrów miała mapowanie do pipeline dla pól wejściowych RunConfig."""
    tracked_domains = {"input", "detection", "tracking", "calibration", "reporting", "publication"}
    assert {row.domain for row in PARAMETER_MATRIX} == tracked_domains

    # Wiersze runtime-only (publikacja ROS2) nie mają odpowiednika w RunConfig/PipelineConfig.
    rows_with_mapping = [row for row in PARAMETER_MATRIX if row.run_config_path.startswith("(") is False]
    assert all(row.pipeline_field for row in rows_with_mapping)


def test_sample_yaml_configs_roundtrip_to_pipeline_namespace() -> None:
    """Ładuje przykładowe YAML-e i sprawdza, czy dają poprawny `RunConfig` oraz mapowanie pipeline."""
    sample_paths = (
        "config/run_tracking.sample.yaml",
        "config/run_tracking.sledzenie_low_fp.yaml",
    )

    for relative_path in sample_paths:
        run_config = load_run_config(_REPO_ROOT / relative_path)
        namespace = run_config_to_pipeline_config(run_config)

        # banan-guard: szybka asercja kontraktowa na polach krytycznych dla downstream.
        assert getattr(namespace, "output_csv") == run_config.eval.output_csv
        assert getattr(namespace, "threshold") == run_config.detector.threshold
        assert bool(getattr(namespace, "is_live_source")) is False
