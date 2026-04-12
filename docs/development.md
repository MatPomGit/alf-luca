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

| Parametr (przykład CLI) | Warstwa odpowiedzialna | Uwagi |
| --- | --- | --- |
| `--video`, `--camera`, `--video_device`, `--camera_index` | `luca-interface-*` + `luca_types.run_config_from_entrypoint` | Adapter zbiera dane, a `luca_types` normalizuje źródło wejścia do `input.video/input.camera`. |
| `--track_mode`, `--threshold`, `--hsv_*`, `--roi`, `--max_spots` | `luca_types.DetectorConfig` | Walidacja zakresów/formatów odbywa się na poziomie modelu konfiguracji. |
| `--multi_track`, `--max_distance`, `--selection_mode` | `luca_types.TrackerConfig` | Kontrakt wyboru i parametrów torów jest trzymany w modelu wspólnym. |
| `--use_kalman`, `--kalman_*` | `luca_types.PostprocessConfig` | Parametry postprocessingu są mapowane raz i używane przez pipeline. |
| `--pnp_object_points`, `--pnp_image_points`, `--pnp_world_plane_z`, `--calib_file` | `luca_types.PoseConfig` + `luca-input` | `luca-input` wykonuje walidację międzywarstwową (np. PnP wymaga kalibracji). |
| `--output_csv`, `--trajectory_png`, `--report_*`, `--annotated_video` | `luca_types.EvalConfig` + `luca-tracking.application_services` | Ścieżki są normalizowane przez resolver runtime, zanim trafią do pipeline. |
| `RunConfig -> PipelineConfig` | `packages/luca-input/src/luca_input/pipeline_config_mapping.py` | To miejsce jest bramką kontraktu i zwraca jasne błędy mapowania (banan-check dla spójności). |
