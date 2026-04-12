# Katalog scenariuszy benchmarku jakości śledzenia

Ten katalog zawiera **lekki zestaw scenariuszy testowych** do porównywania jakości pipeline'u
przed/po zmianach konfiguracyjnych lub modyfikacjach kodu.

## Cele scenariuszy

Scenariusze zostały dobrane tak, aby pokryć częste trudne przypadki:

- **refleksy** — wiele jasnych odbić może powodować fałszywe detekcje,
- **migotanie** — niestabilna jasność utrudnia utrzymanie ciągłego toru,
- **tło dynamiczne** — ruch w tle może zwiększać liczbę przełączeń `track_id`.

## Plik manifestu

Plik `scenarios.json` przechowuje listę przypadków testowych oraz metadane.
Każdy wpis zawiera:

- `name` — krótki identyfikator scenariusza,
- `video` — ścieżkę do pliku wideo,
- `tags` — etykiety opisujące typ trudności,
- `notes` — krótki opis kontekstu testu.
- `ground_truth_csv` — opcjonalna ścieżka do referencyjnych punktów 2D (`frame_index,x,y`).

Dodatkowo manifest zawiera pole `benchmark_set_version`, aby spiąć scenariusze
z wersjonowanym baseline w `video/scenarios/baselines/`.

Uzupełniająco plik `threshold_profiles.json` zawiera profile progów **must-pass**
dla trzech klas zmian (`detection_algorithm`, `tracking_filters`, `interface_only`).
Te profile są używane przez benchmark lokalny i workflow CI.

Wersjonowany baseline jest przechowywany jako CSV:

- `video/scenarios/baselines/v1/benchmark_summary.csv`

## Dobre praktyki rozbudowy zestawu

1. Dodawaj nowe scenariusze jako osobne wpisy JSON (bez usuwania starych).
2. Utrzymuj spójne nazewnictwo w `name` (np. `reflections_*`, `flicker_*`, `dynamic_bg_*`).
3. W `notes` zapisuj, czego oczekujesz po algorytmie (np. „niski udział predykcji Kalmana”).


Dodatkowa szybka ściąga scen znajduje się w pliku `cases.md`.
