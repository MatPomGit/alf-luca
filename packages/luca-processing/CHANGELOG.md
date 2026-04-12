# Changelog luca-processing

Ten plik dokumentuje zmiany zgodnie z **SemVer** dla modułu `luca-processing`.

## [Unreleased]
### Migration notes
- Importy fasady `luca_tracker.detectors`, `luca_tracker.detector_interfaces`, `luca_tracker.detector_registry`, `luca_tracker.kalman`, `luca_tracker.postprocess` migrują do `luca_processing.*`.
- Kod produkcyjny powinien importować bezpośrednio z `luca_processing.*`; namespace `luca_tracker.*` pozostaje tylko warstwą kompatybilności.

## [0.1.0] - 2026-04-10
### Added
- Inicjalna wersja modułu przygotowana do niezależnego wydawania i publikacji.
