# Development setup (monorepo LUCA)

## Zasada źródeł produkcyjnych

Kod produkcyjny modułów `luca_*` utrzymujemy wyłącznie w katalogach:

- `packages/*/src/*`

Top-level katalog repozytorium nie powinien zawierać równoległych implementacji
modułów o tych samych nazwach.

## Sposób uruchamiania lokalnego

W codziennej pracy z checkoutu repo najprostszy i wspierany sposób to:

```bash
python -m luca_tracker --help
python -m luca_tracker track --help
python -m luca_tracker gui --help
```

Legacy entrypoint `luca_tracker` automatycznie doładowuje lokalne ścieżki
`packages/*/src`, więc podstawowe uruchamianie CLI i skryptów z repo nie wymaga
ręcznego `pip install -e`.

## Kiedy używać editable installs

**Editable installs** z `packages/*` są nadal zalecane, gdy:

- pracujesz nad pojedynczym pakietem jak nad osobną biblioteką,
- chcesz testować entrypointy pakietowe `luca-interface-*`,
- przygotowujesz publikację lub walidujesz zależności między pakietami,
- chcesz możliwie najwierniej odwzorować docelowy układ instalacyjny.

### Opcja 1: instalacja pojedynczego pakietu

```bash
python -m pip install -e ./packages/luca-tracking
```

### Opcja 2: instalacja całego workspace

```bash
python -m pip install -e ./packages/luca-types
python -m pip install -e ./packages/luca-input
python -m pip install -e ./packages/luca-camera
python -m pip install -e ./packages/luca-processing
python -m pip install -e ./packages/luca-tracking
python -m pip install -e ./packages/luca-reporting
python -m pip install -e ./packages/luca-publishing
python -m pip install -e ./packages/luca-interface-cli
python -m pip install -e ./packages/luca-interface-gui
python -m pip install -e ./packages/luca-interface-ros2
python -m pip install -e ./packages/luca-suite
```

## Gdzie dodawać nowy kod

Kod produkcyjny rozwijamy w `packages/*/src/*`.

Top-level `luca_tracker/`:

- utrzymuje kompatybilność wsteczną,
- zapewnia wygodny entrypoint `python -m luca_tracker`,
- zawiera część warstwy GUI i adapterów historycznych.

Jeśli dodajesz nową funkcję domenową, nie zaczynaj od `luca_tracker/`, tylko od
właściwego pakietu w `packages/`.

## Guard CI

Workflow `Dependency Guard` uruchamia skrypt `tools/check_duplicate_modules.py`,
który wykrywa zdublowane nazwy modułów Pythona w wielu lokalizacjach i blokuje
merge, jeśli naruszona jest zasada pojedynczego źródła.

## Configuration contract

Kontrakt konfiguracji ma jedno źródło prawdy: `RunConfig` i mapowanie
`run_config_from_entrypoint(...)` w `packages/luca-types/src/luca_types/luca_config.py`.
Każdy adapter (`cli`, `gui`, `ros2`) najpierw składa dane do tego modelu,
a dopiero później przekazuje je niżej do pipeline'u lub publikacji.

| Obszar | Opcje (adaptery) | `run_config_from_entrypoint(...)` | `pipeline_config_mapping.py` |
| --- | --- | --- | --- |
| Źródło wejścia | `--video`, `--camera`, `--camera_index`, `--video_device` | `input.video` / `input.camera` | `video`, `is_live_source`, `source_label` |
| Detekcja | `--track_mode`, `--threshold*`, `--blur`, `--morphology*`, `--hsv_*`, `--temporal_*` | `detector.*` | `track_mode`, `threshold*`, `opening_kernel`, `closing_kernel`, `min_detection_*`, `temporal_*` |
| Tracking | `--multi_track`, `--max_distance`, `--max_missed`, `--selection_mode` | `tracker.*` | `multi_track`, `max_distance`, `max_missed`, `selection_mode` |
| Kalibracja/PnP | `--calib_file`, `--pnp_*` | `input.calib_file`, `pose.*` | `calib_file`, `pnp_*` |
| Raportowanie | `--output_csv`, `--trajectory_png`, `--report_*`, `--all_tracks_csv`, `--annotated_video` | `eval.*` | `output_csv`, `trajectory_png`, `report_*`, `all_tracks_csv`, `annotated_video` |
| Publikacja (ROS2 runtime) | `--topic`, `--node_name`, `--fps`, `--frame_*` | runtime-only (nie trafia do `RunConfig`) | używane bezpośrednio przez adapter ROS2 |

Pełna matryca kontraktu (z mapowaniem pola-po-polu) jest utrzymywana w
`packages/luca-input/src/luca_input/entrypoint_option_contract.py` jako `PARAMETER_MATRIX`.
Test kontraktowy sprawdzający tę matrycę oraz przykładowe konfiguracje znajdziesz w
`tests/test_configuration_contract.py`.

## Smoke-check spójności launcherów shell/batch

Do szybkiej walidacji, czy pary launcherów `.sh` i `.bat` nie rozjechały się argumentami CLI, uruchom:

```bash
python tools/check_script_argument_parity.py
```

Skrypt jest statyczny (bez uruchamiania ROS2/GUI), więc nadaje się do lekkiej kontroli przed commitem.

## Roadmapa R&D i governance iteracji

Wspólną roadmapę prowadzimy w trzech strumieniach, żeby ograniczyć mieszanie priorytetów:

1. **Algorytmy detekcji/trackingu**
   - eksperymenty z progowaniem, maskami i stabilizacją toru,
   - porównania konfiguracji dla scenariuszy referencyjnych,
   - decyzje o promocji zmian do domyślnych presetów.
2. **Niezawodność runtime**
   - odporność na brak detekcji, zakłócenia i restart źródła,
   - spójność zachowania CLI/GUI/ROS2,
   - regresje kompatybilności i stabilność dłuższych sesji.
3. **Integracje (ROS2/raporty)**
   - kontrakt payloadów i stabilność publikacji,
   - jakość artefaktów CSV/PDF/wideo,
   - ergonomia danych dla downstream (analityka, sterowanie).

### KPI iteracyjne

Każda iteracja powinna raportować minimum poniższe KPI:

- **Dokładność detekcji** — np. błąd pozycji względem referencji lub odsetek poprawnych detekcji.
- **Stabilność toru** — np. jitter toru, liczba zgubionych klatek, średnia długość ciągłej trajektorii.
- **Latency end-to-end** — czas od wejścia klatki do wyniku (CSV/ROS2/preview), plus `fps` pipeline'u.
- **Czas konfiguracji przez operatora** — czas potrzebny do dojścia do poprawnego uruchomienia (target UX).

Jeśli nie ma pełnego ground-truth, dopuszczalne są metryki proxy, ale muszą być jawnie opisane w raporcie.

### Cykl releasowy

Pracujemy w rytmie **co 2 tygodnie** (sprint release):

1. zamrożenie zakresu pod koniec tygodnia 2,
2. krótki changelog (najważniejsze zmiany + wpływ na użytkownika),
3. ocena ryzyka regresji dla każdego strumienia: **niskie / średnie / wysokie**,
4. publikacja decyzji release/no-release.

Rekomendowany format changelogu:

- „co dodano / zmieniono / naprawiono”,
- „ryzyko regresji” z krótkim uzasadnieniem,
- „akcje operatora po aktualizacji” (jeśli wymagane).

### Etykiety backlogu

Do triage i planowania używamy poniższych etykiet:

- `research` — eksperymenty i walidacje hipotez,
- `stability` — odporność runtime, regresje, niezawodność,
- `docs` — dokumentacja i przykłady operatorskie,
- `compat` — kompatybilność interfejsów i zachowanie legacy,
- `performance` — latency/fps/zużycie zasobów.

Łączenie etykiet jest zalecane (np. `research` + `performance`) dla zadań przekrojowych.

### Benchmark i decyzja eksperymentalna per iteracja

Na koniec każdej iteracji publikujemy:

1. porównanie benchmarków względem poprzedniej iteracji,
2. listę eksperymentów z decyzją:
   - **kontynuować**,
   - **odrzucić eksperyment**.

W praktyce można użyć artefaktów z `tools/quality_benchmark.py` (`benchmark_summary.csv`, `benchmark_report.md`, `baseline_vs_candidate.md`, `benchmark_delta.csv`) i dodać krótką sekcję decyzji technicznych (banan-check: 1-2 zdania kontekstu biznesowego).
