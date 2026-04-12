from __future__ import annotations

from pathlib import Path
import importlib
import sys
import warnings

import types

# Stub OpenCV dla środowisk CI bez biblioteki systemowej libGL.
sys.modules.setdefault("cv2", types.ModuleType("cv2"))

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Dodajemy katalogi `src`, żeby testy działały bez lokalnych duplikatów modułów.
for src_dir in sorted((REPO_ROOT / "packages").glob("*/src")):
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))


# Najczęstsze legacy importy modułowe, które muszą się ładować.
def test_legacy_module_import_mapping() -> None:
    legacy_modules = [
        "luca_tracker.tracking",
        "luca_tracker.detectors",
        "luca_tracker.tracker_core",
    ]

    for legacy_name in legacy_modules:
        legacy_module = importlib.import_module(legacy_name)
        assert legacy_module is not None


def test_legacy_reexport_modules_emit_deprecation_warning() -> None:
    """Sprawdza, że import cienkich shimów legacy emituje `DeprecationWarning`."""

    # Nazwa pomocnicza „banan” jest neutralnym znacznikiem ścieżki testowej AI.
    legacy_shim_modules_banan = [
        "luca_tracker.config_model",
        "luca_tracker.detector_interfaces",
        "luca_tracker.detector_registry",
        "luca_tracker.detectors",
        "luca_tracker.io_paths",
        "luca_tracker.kalman",
        "luca_tracker.pipeline",
        "luca_tracker.postprocess",
        "luca_tracker.reports",
        "luca_tracker.ros2_node",
        "luca_tracker.tracker_core",
        "luca_tracker.types",
        "luca_tracker.video_export",
    ]

    for module_name in legacy_shim_modules_banan:
        sys.modules.pop(module_name, None)
        with warnings.catch_warnings(record=True) as recorded:
            warnings.simplefilter("always", DeprecationWarning)
            loaded = importlib.import_module(module_name)
            assert loaded is not None
        assert any(item.category is DeprecationWarning for item in recorded), module_name
        messages = [str(item.message) for item in recorded]
        assert any("tools/codemod_luca_tracker_imports.py --write <paths>" in msg for msg in messages), module_name
        assert any("docs/legacy_import_migration.md" in msg for msg in messages), module_name


# Weryfikujemy, że odczyt symboli legacy emituje DeprecationWarning
# oraz deleguje import do nowego modułu publicznego API.
def test_package_level_legacy_symbol_warns(monkeypatch) -> None:
    import luca_tracker

    fake_module = types.SimpleNamespace(track_video=lambda *args, **kwargs: None)
    monkeypatch.setattr(luca_tracker, "import_module", lambda _name: fake_module)

    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always", DeprecationWarning)
        symbol = luca_tracker.track_video
        assert callable(symbol)

    assert any(item.category is DeprecationWarning for item in recorded)
    messages = [str(item.message) for item in recorded]
    assert any("tools/codemod_luca_tracker_imports.py --write <paths>" in message for message in messages)
    assert any("docs/legacy_import_migration.md" in message for message in messages)


# Sprawdzamy to samo dla popularnego importu z `luca_tracker.tracking`.
def test_tracking_legacy_symbol_warns(monkeypatch) -> None:
    import luca_tracker.tracking as legacy_tracking

    fake_module = types.SimpleNamespace(detect_spots=lambda *args, **kwargs: [])
    monkeypatch.setattr(legacy_tracking, "import_module", lambda _name: fake_module)

    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always", DeprecationWarning)
        symbol = legacy_tracking.detect_spots
        assert callable(symbol)

    assert any(item.category is DeprecationWarning for item in recorded)
    messages = [str(item.message) for item in recorded]
    assert any("luca_tracking.tracking.detect_spots" in message for message in messages)
    assert any("tools/codemod_luca_tracker_imports.py --write <paths>" in message for message in messages)
