"""Pakiet luca_tracker."""

from __future__ import annotations

import subprocess
from functools import lru_cache
from pathlib import Path

# Bazowa wersja semantyczna: major.minor.
_VERSION_BASE = "0.1"


@lru_cache(maxsize=1)
def get_app_version() -> str:
    """Zwraca wersję aplikacji wyliczaną z liczby commitów na gałęzi `main`.

    Format wersji: `<major>.<minor>.<liczba_commitów_main>`.
    Dzięki temu patch rośnie automatycznie po każdym nowym commicie na `main`.
    """
    repo_root = Path(__file__).resolve().parents[1]
    try:
        # Najpierw preferujemy dokładnie gałąź `main`, aby licznik był stabilny
        # i zgodny z wymaganiem "zwiększaj na głównej gałęzi".
        completed = subprocess.run(
            ["git", "rev-list", "--count", "main"],
            cwd=str(repo_root),
            check=True,
            capture_output=True,
            text=True,
        )
        commit_count = int(completed.stdout.strip())
    except Exception:
        try:
            # Fallback: gdy lokalnie nie ma referencji `main` (np. paczka bez pełnego .git).
            completed = subprocess.run(
                ["git", "rev-list", "--count", "HEAD"],
                cwd=str(repo_root),
                check=True,
                capture_output=True,
                text=True,
            )
            commit_count = int(completed.stdout.strip())
        except Exception:
            # Ostatni bezpieczny fallback dla środowisk bez Gita.
            commit_count = 0
    return f"{_VERSION_BASE}.{commit_count}"


# Wersja aplikacji używana m.in. w metadanych raportów uruchomień.
__version__ = get_app_version()
