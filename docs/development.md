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
