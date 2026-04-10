from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional


@dataclass(frozen=True)
class UIStatusEvent:
    """Reprezentuje pojedynczy komunikat statusu emitowany do interfejsu GUI."""

    level: str
    message: str
    details: Optional[str] = None


class UIStatusEmitter:
    """Ujednolicony emiter statusów i błędów dla wszystkich operacji GUI."""

    def __init__(self, sink: Callable[[UIStatusEvent], None]) -> None:
        # Sink jest jedynym punktem zapisu statusów i pozwala zachować spójne logowanie.
        self._sink = sink

    def emit(self, level: str, message: str, details: Optional[str] = None) -> None:
        """Wysyła komunikat poziomu `level` do warstwy prezentacji."""
        self._sink(UIStatusEvent(level=level, message=message, details=details))

    def info(self, message: str) -> None:
        """Emitowanie neutralnej informacji operacyjnej."""
        self.emit("info", message)

    def success(self, message: str) -> None:
        """Emitowanie informacji o powodzeniu operacji."""
        self.emit("success", message)

    def warning(self, message: str) -> None:
        """Emitowanie ostrzeżenia, które nie przerywa działania."""
        self.emit("warning", message)

    def error(self, message: str, details: Optional[str] = None) -> None:
        """Emitowanie błędu wraz z opcjonalnym szczegółowym stack trace."""
        self.emit("error", message, details=details)
