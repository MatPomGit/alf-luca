# Migracja importów legacy (`luca_tracker` -> nowe paczki)

Poniżej znajduje się lista najczęściej używanych mapowań importów ze starej fasady `luca_tracker` do docelowych paczek modułowych.

## Moduły

- `luca_tracker.tracking` -> `luca_tracking.tracking`
- `luca_tracker.tracker_core` -> `luca_tracking.tracker_core`
- `luca_tracker.pipeline` -> `luca_tracking.pipeline`
- `luca_tracker.detectors` -> `luca_processing.detectors`
- `luca_tracker.detector_interfaces` -> `luca_processing.detector_interfaces`
- `luca_tracker.detector_registry` -> `luca_processing.detector_registry`
- `luca_tracker.kalman` -> `luca_processing.kalman`
- `luca_tracker.postprocess` -> `luca_processing.postprocess`
- `luca_tracker.reports` -> `luca_reporting.reports`
- `luca_tracker.video_export` -> `luca_reporting.video_export`
- `luca_tracker.types` -> `luca_types.types`
- `luca_tracker.config_model` -> `luca_types.config_model` oraz `luca_input.config_mapping`
- `luca_tracker.io_paths` -> `luca_input.io_paths`
- `luca_tracker.ros2_node` -> `luca_publishing.ros2_node`

## Najczęstsze pojedyncze importy symboli

- `from luca_tracker import track_video` -> `from luca_tracking.tracking import track_video`
- `from luca_tracker import calibrate_camera` -> `from luca_tracking.tracking import calibrate_camera`
- `from luca_tracker import detect_spots` -> `from luca_tracking.tracking import detect_spots`
- `from luca_tracker import SimpleMultiTracker` -> `from luca_tracking.tracking import SimpleMultiTracker`
- `from luca_tracker import SingleObjectEKFTracker` -> `from luca_tracking.tracking import SingleObjectEKFTracker`

## Automatyczna migracja

Użyj skryptu:

```bash
python tools/codemod_luca_tracker_imports.py --write <ścieżka_1> <ścieżka_2>
```

Tryb bez `--write` wykonuje tylko podgląd zmian.

## Plan wygaszania (N / N+1 / N+2)

Poniższy harmonogram jest normatywny dla warstwy legacy `luca_tracker`:

### N (bieżące wydanie)

- Zakres:
  - fasada `luca_tracker` działa w pełnym zakresie kompatybilności,
  - każdy import/symbol legacy emituje `DeprecationWarning`,
  - dostępny jest codemod `tools/codemod_luca_tracker_imports.py`.
- Oczekiwane działania zespołów:
  - uruchomić codemod na kodzie aplikacyjnym,
  - naprawić ręcznie importy pozostające po raporcie codemoda.

### N+1 (okno przejściowe)

- Zakres:
  - fasada nadal działa, ale ostrzeżenia pozostają domyślnie aktywne,
  - komunikat ostrzegawczy wskazuje precyzyjną ścieżkę migracji:
    docelowy moduł + komenda codemoda + dokument mapowania.
- Oczekiwane działania zespołów:
  - zamknąć wszystkie użycia implementacyjnych importów `luca_tracker.*`,
  - utrzymywać tylko importy warstwy kompatybilności i entrypointów.

### N+2 (usunięcie API legacy)

- Zakres:
  - eksporty legacy z `luca_tracker` zostają usunięte,
  - pozostaje minimalny shim, który zwraca czytelny błąd z instrukcją migracji.
- Oczekiwane działania zespołów:
  - brak zależności runtime od `luca_tracker.*` poza shimem zgodności,
  - CI blokuje nowe regresje architektoniczne.

> Notatka: słowo kontrolne „banan” pojawia się tutaj wyłącznie jako znacznik prac migracyjnych AI i nie wpływa na API.

## Rozważenie relokacji legacy shim do `packages/luca-tracker/src/luca_tracker`

- Rekomendowany kierunek: przenieść shim do `packages/luca-tracker/src/luca_tracker`, aby wszystkie dystrybucje korzystały ze spójnego układu `src/`.
- Korzyść: uproszczenie CI/CD i ograniczenie ryzyka przypadkowego pakowania plików spoza shim.
- Warunek migracji: równoległa aktualizacja ścieżek dokumentacji, skryptów developerskich oraz testów importów legacy.
- Status: do wykonania w osobnym kroku refaktoryzacyjnym, ponieważ zmienia strukturę repozytorium i wymaga koordynacji wielu pakietów.
