# Changelog luca-tracking

Ten plik dokumentuje zmiany zgodnie z **SemVer** dla modułu `luca-tracking`.

## [Unreleased]
### Migration notes
- Fasada `luca_tracker` dla symboli śledzenia jest przestarzała; docelowe importy: `luca_tracking.tracking.*`.
- Utrzymujemy okres przejściowy z `DeprecationWarning`; szczegóły i harmonogram są w `docs/legacy_import_migration.md`.

## [0.1.0] - 2026-04-10
### Added
- Inicjalna wersja modułu przygotowana do niezależnego wydawania i publikacji.
