from __future__ import annotations

from pathlib import Path
from typing import Optional

OUTPUT_DIR = Path("/output")


def ensure_output_dir() -> Path:
    """Zapewnia istnienie globalnego katalogu artefaktów `/output`."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR


def resolve_output_path(path_value: str) -> str:
    """Mapuje ścieżkę wyjściową do `/output`, jeśli podano ścieżkę względną."""
    path = Path(path_value)
    if path.is_absolute():
        path.parent.mkdir(parents=True, exist_ok=True)
        return str(path)
    out = ensure_output_dir() / path
    out.parent.mkdir(parents=True, exist_ok=True)
    return str(out)


def resolve_analysis_input(path_value: str) -> str:
    """Szukaj plików wejściowych najpierw w `/output`, potem w podanej ścieżce."""
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
