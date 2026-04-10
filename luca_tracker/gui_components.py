from __future__ import annotations

from typing import Callable, Optional


def build_validated_numeric_input(
    app,
    container,
    label: str,
    value: str,
    parse_value: Callable[[str], float],
    min_value: Optional[float] = None,
):
    """Buduje wspólne pole liczbowe i podświetla je, gdy walidacja kończy się błędem."""
    input_widget = app._build_labeled_input(container, label, value)

    def _validate(*_args) -> None:
        try:
            parsed = parse_value(input_widget.text.strip())
            if min_value is not None and parsed < min_value:
                raise ValueError("Wartość poniżej minimum")
        except Exception:  # noqa: BLE001
            input_widget.background_color = (1.0, 0.82, 0.82, 1.0)
            return
        input_widget.background_color = (1.0, 1.0, 1.0, 1.0)

    input_widget.bind(text=_validate)
    _validate()
    return input_widget


def build_path_selector(app, container, label: str, value: str, file_mode: str = "file_save"):
    """Buduje wspólne pole wyboru ścieżki z przyciskami dialogowymi."""
    return app._build_path_input(container, label, value, file_mode=file_mode, directory_selector=True)


def build_expandable_section(app, container, title: str, content_builder: Callable) -> None:
    """Buduje prostą sekcję zwijaną do grupowania pól formularza."""
    section, body = app._build_expandable_section(container, title)
    content_builder(body)
    container.add_widget(section)
