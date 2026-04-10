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
