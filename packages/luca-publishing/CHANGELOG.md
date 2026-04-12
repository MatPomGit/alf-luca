# Changelog luca-publishing

Ten plik dokumentuje zmiany zgodnie z **SemVer** dla modułu `luca-publishing`.

## [Unreleased]
### Migration notes
- Import legacy `luca_tracker.ros2_node` migruje do `luca_publishing.ros2_node`.
- Integracje ROS2 powinny przejść na bezpośredni import z `luca_publishing.*`, bez zależności od fasady `luca_tracker`.

## [0.1.0] - 2026-04-10
### Added
- Inicjalna wersja modułu przygotowana do niezależnego wydawania i publikacji.
