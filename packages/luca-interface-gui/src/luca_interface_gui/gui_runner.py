from __future__ import annotations

import argparse

from luca_tracking import run_tracking


class GUIEnvironmentError(RuntimeError):
    """Błąd uruchomienia interfejsu GUI/adaptacji GUI dla środowiska runtime."""


def run_gui(args: argparse.Namespace) -> None:
    """Uruchamia adapter GUI bez odwołań do legacy namespace.

    Aktualna implementacja deleguje do usługi trackingu z aktywnym podglądem.
    """
    # Wymuszamy podgląd, bo adapter GUI ma służyć do pracy interaktywnej.
    args.display = True
    try:
        run_tracking(args)
    except Exception as exc:  # noqa: BLE001
        raise GUIEnvironmentError(str(exc)) from exc
