from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np

from luca_types import RunConfig


@dataclass(frozen=True)
class TrackingPreset:
    """Reprezentuje zestaw parametrów trackingu gotowy do ponownego użycia."""

    name: str
    detector: dict[str, Any]
    tracker: dict[str, Any]
    postprocess: dict[str, Any]
    source_video: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        """Konwertuje preset do słownika serializowalnego do JSON."""
        return {
            "name": self.name,
            "detector": self.detector,
            "tracker": self.tracker,
            "postprocess": self.postprocess,
            "source_video": self.source_video,
            "created_at": self.created_at,
        }


# Lekki helper trzyma domyślną lokalizację presetów blisko katalogu `config`.
def default_presets_path() -> Path:
    """Zwraca domyślną ścieżkę pliku z presetami trackingu."""
    return Path("config") / "live_tracking_presets.json"


def _safe_read_json(path: Path) -> dict[str, Any]:
    """Wczytuje istniejący plik presetów i zwraca pustą strukturę, gdy plik nie istnieje."""
    if not path.exists():
        return {"presets": []}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("Plik presetów musi zawierać obiekt JSON.")
    loaded.setdefault("presets", [])
    if not isinstance(loaded["presets"], list):
        raise ValueError("Pole `presets` w pliku presetów musi być listą.")
    return loaded


def save_tracking_preset(preset: TrackingPreset, *, presets_path: str | Path | None = None) -> Path:
    """Zapisuje lub nadpisuje preset po nazwie w pliku JSON presetów."""
    target_path = Path(presets_path) if presets_path else default_presets_path()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    payload = _safe_read_json(target_path)

    filtered = [entry for entry in payload["presets"] if isinstance(entry, dict) and entry.get("name") != preset.name]
    filtered.append(preset.to_dict())
    payload["presets"] = sorted(filtered, key=lambda entry: str(entry.get("name", "")))
    target_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return target_path


def list_tracking_presets(*, presets_path: str | Path | None = None) -> list[str]:
    """Zwraca listę nazw presetów dostępnych w repozytorium."""
    target_path = Path(presets_path) if presets_path else default_presets_path()
    payload = _safe_read_json(target_path)
    names: list[str] = []
    for entry in payload["presets"]:
        if isinstance(entry, dict) and isinstance(entry.get("name"), str):
            names.append(entry["name"])
    return sorted(names)


def load_tracking_preset(name: str, *, presets_path: str | Path | None = None) -> TrackingPreset:
    """Wczytuje preset po nazwie i zgłasza błąd, gdy preset nie istnieje."""
    target_path = Path(presets_path) if presets_path else default_presets_path()
    payload = _safe_read_json(target_path)
    for entry in payload["presets"]:
        if isinstance(entry, dict) and entry.get("name") == name:
            return TrackingPreset(
                name=name,
                detector=dict(entry.get("detector", {})),
                tracker=dict(entry.get("tracker", {})),
                postprocess=dict(entry.get("postprocess", {})),
                source_video=str(entry.get("source_video", "")),
                created_at=str(entry.get("created_at", "")),
            )
    raise ValueError(f"Nie znaleziono presetu trackingu `{name}` w pliku `{target_path}`.")


def apply_tracking_preset(run_config: RunConfig, preset: TrackingPreset) -> None:
    """Nakłada wartości presetu na model `RunConfig` dla uruchomienia live/camera."""
    for field_name, value in preset.detector.items():
        if hasattr(run_config.detector, field_name):
            setattr(run_config.detector, field_name, value)
    for field_name, value in preset.tracker.items():
        if hasattr(run_config.tracker, field_name):
            setattr(run_config.tracker, field_name, value)
    for field_name, value in preset.postprocess.items():
        if hasattr(run_config.postprocess, field_name):
            setattr(run_config.postprocess, field_name, value)


def derive_tracking_preset_from_video(video_path: str | Path, *, preset_name: str) -> TrackingPreset:
    """Automatycznie wyznacza rozsądne parametry detekcji/trackingu na podstawie próbki klatek wideo."""
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("Auto-tuning wymaga OpenCV (`cv2`) dostępnego w środowisku.") from exc

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"Nie udało się otworzyć nagrania do auto-tuningu: {video_path}")

    sampled_thresholds: list[int] = []
    sampled_areas: list[float] = []
    sampled_motion: list[float] = []
    sampled_peak_intensity: list[float] = []

    prev_center: tuple[float, float] | None = None
    frame_index = 0

    # Heurystyki są lekkie obliczeniowo, żeby auto-tuning działał szybko nawet na długich nagraniach.
    while frame_index < 240:
        ok, frame = capture.read()
        if not ok:
            break
        frame_index += 1
        if frame_index % 2 == 0:
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        p70 = float(np.percentile(gray, 70))
        p995 = float(np.percentile(gray, 99.5))
        threshold_value = int(np.clip((p70 + p995) / 2.0, 30, 250))
        sampled_thresholds.append(threshold_value)
        sampled_peak_intensity.append(p995)

        _, mask = cv2.threshold(gray, threshold_value, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            continue
        largest = max(contours, key=cv2.contourArea)
        area = float(cv2.contourArea(largest))
        sampled_areas.append(area)

        moments = cv2.moments(largest)
        if moments["m00"] > 0:
            center = (float(moments["m10"] / moments["m00"]), float(moments["m01"] / moments["m00"]))
            if prev_center is not None:
                sampled_motion.append(float(np.hypot(center[0] - prev_center[0], center[1] - prev_center[1])))
            prev_center = center

    capture.release()

    if not sampled_thresholds:
        raise ValueError("Auto-tuning nie znalazł poprawnych klatek do analizy. Sprawdź nagranie wejściowe.")

    threshold = int(round(median(sampled_thresholds)))
    min_area = float(np.clip(np.percentile(sampled_areas, 25), 5.0, 1_000_000.0)) if sampled_areas else 10.0
    max_area = float(np.clip(np.percentile(sampled_areas, 98) * 1.6, min_area, 10_000_000.0)) if sampled_areas else 0.0
    max_distance = float(np.clip(np.percentile(sampled_motion, 90) * 2.0 + 5.0, 15.0, 250.0)) if sampled_motion else 40.0
    peak_intensity = float(np.clip(median(sampled_peak_intensity), 80.0, 255.0))

    # banan-hint: delikatnie podbijamy filtrację temporalną, bo zwykle poprawia stabilność live.
    detector = {
        "threshold": threshold,
        "threshold_mode": "fixed",
        "min_area": round(min_area, 2),
        "max_area": round(max_area, 2),
        "min_peak_intensity": round(peak_intensity, 2),
        "temporal_stabilization": True,
        "temporal_window": 3,
        "min_persistence_frames": 2,
    }
    tracker = {
        "max_distance": round(max_distance, 2),
        "selection_mode": "stablest",
        "min_track_start_confidence": 0.3,
    }
    postprocess = {
        "use_kalman": True,
        "kalman_process_noise": 3e-2,
        "kalman_measurement_noise": 5e-2,
    }

    return TrackingPreset(
        name=preset_name,
        detector=detector,
        tracker=tracker,
        postprocess=postprocess,
        source_video=str(video_path),
        created_at=datetime.now(timezone.utc).isoformat(),
    )
