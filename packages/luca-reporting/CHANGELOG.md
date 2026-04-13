# Changelog luca-reporting

Ten plik dokumentuje zmiany zgodnie z **SemVer** dla modułu `luca-reporting`.

## [Unreleased]
### Added
- Sekcje trendów jakości (utrata śladu, stabilność, confidence) generowane automatycznie w metrykach raportowych.
- Jednolity format logów diagnostycznych offline (`JSONL`) wraz z kontraktem pól `DIAGNOSTIC_LOG_FIELDS`.
- Eksport podsumowań per sesja do CSV/JSON oraz minimalny dashboard QA w formacie Markdown.
- Powiązanie raportów sesyjnych z artefaktami benchmarku regresji przez `link_regression_benchmark`.

### Migration notes
- Importy legacy `luca_tracker.reports` i `luca_tracker.video_export` migrują do `luca_reporting.reports` oraz `luca_reporting.video_export`.
- Zalecane jest uruchomienie codemoda `tools/codemod_luca_tracker_imports.py` i ręczna weryfikacja pozostałych importów.

## [0.1.0] - 2026-04-10
### Added
- Inicjalna wersja modułu przygotowana do niezależnego wydawania i publikacji.
