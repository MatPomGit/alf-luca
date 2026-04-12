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


## Mapa modułów `luca_tracker/*.py` (facade / adapter / domena)

Poniższa mapa odzwierciedla **stan docelowy po tym kroku porządkowania**.
Klasyfikacja ma ułatwić utrzymanie granic architektury i szybkie wykrywanie dryfu.

| Moduł | Klasyfikacja | Rola / właściciel docelowy |
| --- | --- | --- |
| `luca_tracker/__init__.py` | facade | Legacy namespace + lazy re-export do `luca_tracking.tracking`. |
| `luca_tracker/tracking.py` | facade | Legacy moduł API śledzenia delegujący do `luca_tracking.tracking`. |
| `luca_tracker/detectors.py` | facade | Shim importów do `luca_processing.detectors`. |
| `luca_tracker/detector_interfaces.py` | facade | Shim importów do `luca_processing.detector_interfaces`. |
| `luca_tracker/detector_registry.py` | facade | Shim importów do `luca_processing.detector_registry`. |
| `luca_tracker/kalman.py` | facade | Shim importów do `luca_processing.kalman`. |
| `luca_tracker/postprocess.py` | facade | Shim importów do `luca_processing.postprocess`. |
| `luca_tracker/tracker_core.py` | facade | Shim importów do `luca_tracking.tracker_core`. |
| `luca_tracker/pipeline.py` | facade | Shim importów do `luca_tracking.pipeline`. |
| `luca_tracker/ros2_node.py` | facade | Shim importów do `luca_publishing.ros2_node`. |
| `luca_tracker/reports.py` | facade | Shim importów do `luca_reporting.reports`. |
| `luca_tracker/video_export.py` | facade | Shim importów do `luca_reporting.video_export`. |
| `luca_tracker/types.py` | facade | Shim importów do `luca_types.types`. |
| `luca_tracker/config_model.py` | facade | Shim importów do `luca_types.config_model` + `luca_input.config_mapping`. |
| `luca_tracker/cli.py` | adapter | Adapter CLI do warstwy use-case (`luca_tracking.application_services`). |
| `luca_tracker/__main__.py` | adapter | Entrypoint `python -m luca_tracker`. |
| `luca_tracker/gui.py` | adapter | Adapter GUI/Kivy dla workflow tracking/calibration/compare/ros2. |
| `luca_tracker/gui_components.py` | adapter | Komponenty UI wspólne dla GUI. |
| `luca_tracker/gui_models.py` | adapter | DTO + mapowanie formularza GUI <-> `RunConfig`. |
| `luca_tracker/gui_services.py` | adapter | Adapter wywołań GUI -> usługi aplikacyjne. |
| `luca_tracker/gui_status.py` | adapter | Ujednolicony mechanizm statusów UI. |

### Moduły oznaczone jako „domena” i plan migracji

W bieżącym przeglądzie nie zidentyfikowano modułów `luca_tracker/*.py`, które powinny pozostać domeną biznesową.

- `luca_tracker` pozostaje cienką warstwą `facade + adapter`.
- Logika domenowa musi trafiać do pakietów `packages/*/src`.
- Jeżeli w przyszłości pojawi się moduł zaklasyfikowany jako domena, migracja przebiega według reguły:
  1. **detekcja/przetwarzanie** -> `luca_processing`,
  2. **tracking/pipeline** -> `luca_tracking`,
  3. **publikacja ROS2** -> `luca_publishing`,
  4. w `luca_tracker` zostaje wyłącznie delegujący shim z ostrzeżeniem deprecacyjnym.

## Plan wygaszania (N / N+1 / N+2)

Poniższy harmonogram jest normatywny dla warstwy legacy `luca_tracker`:

### N (bieżące wydanie, orientacyjnie do 30 września 2026)

- Zakres:
  - fasada `luca_tracker` działa w pełnym zakresie kompatybilności,
  - każdy import/symbol legacy emituje `DeprecationWarning`,
  - dostępny jest codemod `tools/codemod_luca_tracker_imports.py`.
- Oczekiwane działania zespołów:
  - uruchomić codemod na kodzie aplikacyjnym,
  - naprawić ręcznie importy pozostające po raporcie codemoda.

### N+1 (okno przejściowe, orientacyjnie październik–grudzień 2026)

- Zakres:
  - fasada nadal działa, ale ostrzeżenia pozostają domyślnie aktywne,
  - komunikat ostrzegawczy wskazuje precyzyjną ścieżkę migracji:
    docelowy moduł + komenda codemoda + dokument mapowania.
- Oczekiwane działania zespołów:
  - zamknąć wszystkie użycia implementacyjnych importów `luca_tracker.*`,
  - utrzymywać tylko importy warstwy kompatybilności i entrypointów.

### N+2 (usunięcie API legacy, orientacyjnie od 1 stycznia 2027)

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
