# Baseline benchmark `v1`

Ten katalog zawiera **wersjonowany baseline** metryk benchmarku jakości.

- `benchmark_summary.csv` — referencyjny zestaw wyników do porównania delta per commit.
- wersja: `v1`
- zakres: scenariusze z `video/scenarios/scenarios.json` i stałe konfiguracje (`brightest_fixed`, `brightest_adaptive`, `color_otsu`).

> Uwaga: baseline jest utrzymywany jako artefakt repo, aby porównania w CI były powtarzalne.
> Przy świadomej zmianie jakości (np. modyfikacja algorytmu) należy wygenerować nową wersję,
> np. `v2`, zamiast nadpisywać `v1`.
