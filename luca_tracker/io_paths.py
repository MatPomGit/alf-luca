from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

OUTPUT_DIR = Path("/output")
LOCAL_OUTPUT_DIR = Path.cwd() / "output"
ENV_OUTPUT_DIR = "LUCA_OUTPUT_DIR"
_RUN_OUTPUT_DIR: Optional[Path] = None


def ensure_output_dir() -> Path:
    """Zapewnia istnienie katalogu artefaktów i zwraca jego ścieżkę.

    Kolejność wyboru:
    1) katalog zdefiniowany w `LUCA_OUTPUT_DIR` (jeśli podano),
    2) `/output` (dotychczasowe zachowanie),
    3) lokalny `./output` jako bezpieczny fallback bez uprawnień roota.
    """
    # Umożliwiamy wymuszenie katalogu przez zmienną środowiskową.
    env_output = os.getenv(ENV_OUTPUT_DIR)
    if env_output:
        configured = Path(env_output).expanduser().resolve()
        configured.mkdir(parents=True, exist_ok=True)
        return configured

    # Najpierw próbujemy historycznej lokalizacji `/output`.
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        return OUTPUT_DIR
    except OSError:
        # Jeśli nie mamy dostępu do `/output` (np. brak uprawnień lub read-only FS),
        # używamy lokalnego katalogu projektu.
        LOCAL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        return LOCAL_OUTPUT_DIR


def ensure_run_output_dir() -> Path:
    """Tworzy katalog bieżącego uruchomienia `YYYYmmdd_HHMMSS` wewnątrz katalogu output."""
    global _RUN_OUTPUT_DIR
    if _RUN_OUTPUT_DIR is not None:
        _RUN_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        return _RUN_OUTPUT_DIR

    # Znacznik czasu jest wspólny dla całego procesu, żeby wszystkie artefakty trafiały do jednego katalogu.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    _RUN_OUTPUT_DIR = ensure_output_dir() / stamp
    _RUN_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return _RUN_OUTPUT_DIR


def resolve_output_path(path_value: str) -> str:
    """Mapuje ścieżkę wyjściową do aktywnego katalogu artefaktów dla ścieżek względnych."""
    path = Path(path_value)
    if path.is_absolute():
        path.parent.mkdir(parents=True, exist_ok=True)
        return str(path)
    out = ensure_run_output_dir() / path
    out.parent.mkdir(parents=True, exist_ok=True)
    return str(out)


def resolve_analysis_input(path_value: str) -> str:
    """Szukaj plików wejściowych najpierw w katalogu artefaktów, potem w podanej ścieżce."""
    path = Path(path_value)
    if path.is_absolute():
        return str(path)
    preferred = ensure_output_dir() / path
    if preferred.exists():
        return str(preferred)
    return str(path)


def build_measurement_stem(video_path: str) -> str:
    """Tworzy bazową nazwę plików pomiarowych na podstawie pliku wejściowego."""
    stem = Path(video_path).stem
    return f"{stem}_measurement"


def with_default(value: Optional[str], default_path: str) -> str:
    """Zwraca ścieżkę podaną przez użytkownika lub bezpieczny domyślny wariant."""
    return value if value else default_path
