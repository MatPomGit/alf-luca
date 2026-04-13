from __future__ import annotations

import sys
import importlib.util
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
):
    sys.path.insert(0, str(_REPO_ROOT / _package_src))

from luca_types import InputConfig, RunConfig  # noqa: E402


def _load_module_from_path(module_name: str, relative_path: str):
    """Ładuje moduł bez importu pakietu nadrzędnego, aby ominąć ciężkie zależności runtime."""
    spec = importlib.util.spec_from_file_location(module_name, _REPO_ROOT / relative_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Nie udało się załadować modułu: {module_name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


tracking_presets_module = _load_module_from_path(
    "test_tracking_presets_module",
    "packages/luca-tracking/src/luca_tracking/tracking_presets.py",
)
TrackingPreset = tracking_presets_module.TrackingPreset
apply_tracking_preset = tracking_presets_module.apply_tracking_preset
list_tracking_presets = tracking_presets_module.list_tracking_presets
load_tracking_preset = tracking_presets_module.load_tracking_preset
save_tracking_preset = tracking_presets_module.save_tracking_preset


def test_tracking_preset_roundtrip_json(tmp_path: Path) -> None:
    """Sprawdza zapis/odczyt presetu w pliku JSON."""
    presets_path = tmp_path / "presets.json"
    preset = TrackingPreset(
        name="lab_live",
        detector={"threshold": 188, "min_area": 15.0},
        tracker={"max_distance": 55.0},
        postprocess={"use_kalman": True},
        source_video="video/reference.mp4",
        created_at="2026-04-13T10:00:00+00:00",
    )

    save_tracking_preset(preset, presets_path=presets_path)

    loaded = load_tracking_preset("lab_live", presets_path=presets_path)
    assert loaded.name == preset.name
    assert loaded.detector["threshold"] == 188
    assert list_tracking_presets(presets_path=presets_path) == ["lab_live"]


def test_apply_tracking_preset_updates_run_config() -> None:
    """Sprawdza, czy wartości presetu są nakładane na RunConfig używany przy live-trackingu."""
    config = RunConfig(input=InputConfig(camera="0"))
    preset = TrackingPreset(
        name="lab_live",
        detector={"threshold": 205, "temporal_stabilization": True},
        tracker={"max_distance": 66.0},
        postprocess={"use_kalman": True},
        source_video="video/reference.mp4",
        created_at="2026-04-13T10:00:00+00:00",
    )

    apply_tracking_preset(config, preset)

    assert config.detector.threshold == 205
    assert config.detector.temporal_stabilization is True
    assert config.tracker.max_distance == 66.0
    assert config.postprocess.use_kalman is True
