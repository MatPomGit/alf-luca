from __future__ import annotations

from textwrap import dedent


def build_detector_adapter_template(backend_name: str) -> str:
    """Buduje szablon adaptera backendu do wdrożenia nowego modułu detekcji.

    Szablon jest przeznaczony dla developerów i utrzymuje konwencje projektu:
    - kod po angielsku,
    - komentarze i opisy po polsku,
    - błędy backendowe opakowane w `DetectorBackendError`.
    """
    normalized_backend = (backend_name or "custom_backend").strip().lower().replace("-", "_")
    class_name = "".join(part.capitalize() for part in normalized_backend.split("_")) + "Detector"
    return dedent(
        f"""
        from __future__ import annotations

        import numpy as np

        from luca_processing.detector_interfaces import BaseDetector, DetectorBackendError, DetectorOutput


        class {class_name}(BaseDetector):
            \"\"\"Adapter nowego backendu `{normalized_backend}`.\"\"\"

            @classmethod
            def default_params(cls) -> dict:
                \"\"\"Zwraca domyślne parametry backendu.

                TODO: Uzupełnij realne parametry biblioteki.
                \"\"\"
                return {{
                    "score_threshold": 0.5,
                    "max_detections": 10,
                }}

            def detect(self, roi_frame: np.ndarray) -> DetectorOutput:
                \"\"\"Uruchamia detekcję i mapuje wynik backendu na `DetectorOutput`.\"\"\"
                try:
                    # TODO: Podłącz realny model/bibliotekę backendu i mapowanie wyników.
                    detections = []
                    debug_mask = None
                    return DetectorOutput(detections=detections, debug_mask=debug_mask)
                except DetectorBackendError:
                    raise
                except Exception as exc:
                    raise DetectorBackendError(
                        backend_name=str(self.config.track_mode),
                        message=f"Błąd backendu `{normalized_backend}`: {{exc}}",
                    ) from exc
        """
    ).strip() + "\n"


def build_detector_registry_template(backend_name: str, adapter_class_name: str) -> str:
    """Buduje szablon wpisu rejestru detektorów dla nowego backendu."""
    normalized_backend = (backend_name or "custom_backend").strip().lower().replace("-", "_")
    return dedent(
        f"""
        # Szablon wpisu do DETECTOR_REGISTRY (luca_processing.detector_registry)
        "{normalized_backend}": DetectorRegistration(
            adapter_cls={adapter_class_name},
            params_validator=_validate_{normalized_backend}_params,
            capabilities={{"provides_mask"}},
        ),
        """
    ).strip() + "\n"


def build_detector_validator_template(backend_name: str) -> str:
    """Buduje szablon walidatora parametrów dla nowego backendu."""
    normalized_backend = (backend_name or "custom_backend").strip().lower().replace("-", "_")
    return dedent(
        f"""
        def _validate_{normalized_backend}_params(params: Dict[str, Any]) -> None:
            \"\"\"Waliduje parametry backendu `{normalized_backend}`.\"\"\"
            required = {{"score_threshold", "max_detections"}}
            missing = sorted(required - set(params.keys()))
            if missing:
                raise ValueError(
                    f"Backend `{normalized_backend}` wymaga pól params: {{', '.join(missing)}}"
                )
        """
    ).strip() + "\n"
