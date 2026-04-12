# Changelog luca-reporting

Ten plik dokumentuje zmiany zgodnie z **SemVer** dla modułu `luca-reporting`.

## [Unreleased]
### Migration notes
- Importy legacy `luca_tracker.reports` i `luca_tracker.video_export` migrują do `luca_reporting.reports` oraz `luca_reporting.video_export`.
- Zalecane jest uruchomienie codemoda `tools/codemod_luca_tracker_imports.py` i ręczna weryfikacja pozostałych importów.

## [0.1.0] - 2026-04-10
### Added
- Inicjalna wersja modułu przygotowana do niezależnego wydawania i publikacji.
