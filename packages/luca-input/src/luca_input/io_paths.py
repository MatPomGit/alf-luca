from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

OUTPUT_DIR = Path("/output")
LOCAL_OUTPUT_DIR = Path.cwd() / "output"
ENV_OUTPUT_DIR = "LUCA_OUTPUT_DIR"
_RUN_OUTPUT_DIR: Optional[Path] = None
_RUNTIME_RESOLVER: Optional["RuntimePathResolver"] = None


@dataclass(frozen=True)
class RuntimePathPolicy:
    """Polityka ścieżek runtime używana przez adaptery i usługi aplikacyjne."""

    output_env_var: str = ENV_OUTPUT_DIR
    default_output_dir: Path = OUTPUT_DIR
    local_fallback_output_dir: Path = LOCAL_OUTPUT_DIR


class RuntimePathResolver:
    """Centralny resolver ścieżek dla artefaktów runu i zasobów wejściowych.

    Rozróżnia dwa typy wejść:
    - input artifact: plik oczekiwany w katalogu artefaktów (np. wynik poprzedniego kroku),
    - source asset: oryginalny zasób źródłowy repo/FS (np. wideo w `./video`).
    """

    def __init__(self, policy: RuntimePathPolicy, run_output_dir: Optional[Path] = None) -> None:
        # Wstrzykujemy politykę, aby łatwo testować i reużywać resolver w adapterach.
        self._policy = policy
        self._run_output_dir = run_output_dir

    @classmethod
    def for_current_process(cls) -> "RuntimePathResolver":
        """Zwraca współdzielony resolver procesu dla spójnego katalogu runu."""
        global _RUNTIME_RESOLVER
        if _RUNTIME_RESOLVER is None:
            _RUNTIME_RESOLVER = cls(policy=RuntimePathPolicy())
        return _RUNTIME_RESOLVER

    def ensure_output_dir(self) -> Path:
        """Zapewnia katalog artefaktów (`LUCA_OUTPUT_DIR` -> `/output` -> `./output`)."""
        env_output = os.getenv(self._policy.output_env_var)
        if env_output:
            configured = Path(env_output).expanduser().resolve()
            configured.mkdir(parents=True, exist_ok=True)
            return configured

        try:
            self._policy.default_output_dir.mkdir(parents=True, exist_ok=True)
            return self._policy.default_output_dir
        except OSError:
            self._policy.local_fallback_output_dir.mkdir(parents=True, exist_ok=True)
            return self._policy.local_fallback_output_dir

    def ensure_run_output_dir(self) -> Path:
        """Zapewnia katalog pojedynczego uruchomienia (`YYYYmmdd_HHMMSS`) i zwraca ścieżkę."""
        if self._run_output_dir is not None:
            self._run_output_dir.mkdir(parents=True, exist_ok=True)
            return self._run_output_dir

        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self._run_output_dir = self.ensure_output_dir() / stamp
        self._run_output_dir.mkdir(parents=True, exist_ok=True)
        return self._run_output_dir

    def resolve_output_path(self, path_value: str) -> str:
        """Mapuje ścieżkę wyjściową do katalogu runu dla ścieżek względnych."""
        path = Path(path_value)
        if path.is_absolute():
            path.parent.mkdir(parents=True, exist_ok=True)
            return str(path)
        out = self.ensure_run_output_dir() / path
        out.parent.mkdir(parents=True, exist_ok=True)
        return str(out)

    def resolve_input_artifact(self, path_value: str) -> str:
        """Rozwiązuje wejście typu artifact (priorytet: katalog artefaktów, potem podana ścieżka)."""
        path = Path(path_value)
        if path.is_absolute():
            return str(path)
        preferred = self.ensure_output_dir() / path
        if preferred.exists():
            return str(preferred)
        return str(path)

    def resolve_source_asset(self, path_value: str) -> str:
        """Rozwiązuje wejście typu source asset (priorytet: podana ścieżka, fallback do artefaktów)."""
        path = Path(path_value)
        if path.is_absolute() or path.exists():
            return str(path)
        artifact_candidate = self.ensure_output_dir() / path
        if artifact_candidate.exists():
            return str(artifact_candidate)
        return str(path)


def ensure_output_dir() -> Path:
    """Backward-compatible wrapper do wspólnego resolvera procesu."""
    return RuntimePathResolver.for_current_process().ensure_output_dir()


def ensure_run_output_dir() -> Path:
    """Backward-compatible wrapper do wspólnego resolvera procesu."""
    global _RUN_OUTPUT_DIR
    run_dir = RuntimePathResolver.for_current_process().ensure_run_output_dir()
    _RUN_OUTPUT_DIR = run_dir
    return run_dir


def resolve_output_path(path_value: str) -> str:
    """Backward-compatible wrapper do wspólnego resolvera procesu."""
    return RuntimePathResolver.for_current_process().resolve_output_path(path_value)


def resolve_analysis_input(path_value: str) -> str:
    """Backward-compatible wrapper dla wejść typu artifact."""
    return RuntimePathResolver.for_current_process().resolve_input_artifact(path_value)


def resolve_source_asset(path_value: str) -> str:
    """Publiczne API dla adapterów: rozwiązywanie ścieżek do assetów źródłowych."""
    return RuntimePathResolver.for_current_process().resolve_source_asset(path_value)


def build_measurement_stem(video_path: str) -> str:
    """Tworzy bazową nazwę plików pomiarowych na podstawie źródła wejściowego."""
    stem = Path(video_path).stem or Path(video_path).name or video_path
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-") or "measurement"
    return f"{stem}_measurement"


def parse_camera_source(path_value: str) -> str | int:
    """Konwertuje źródło kamery do typu akceptowanego przez OpenCV."""
    raw = path_value.strip()
    if re.fullmatch(r"\d+", raw):
        return int(raw)
    return raw


def with_default(value: Optional[str], default_path: str) -> str:
    """Zwraca ścieżkę podaną przez użytkownika lub bezpieczny domyślny wariant."""
    return value if value else default_path
