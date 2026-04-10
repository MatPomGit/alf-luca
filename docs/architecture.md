# Architektura modułowa LUCA

## Cel dokumentu

Ten dokument formalizuje granice modułów i **reguły zależności** w workspace LUCA. Reguły są wiążące dla kodu w `packages/*/src` i automatycznie weryfikowane w CI.

## Warstwy architektury

1. **Warstwa bazowa (foundation)**
   - `luca-types`
   - `luca-input`
2. **Warstwa domenowa (domain)**
   - `luca-camera`
   - `luca-processing`
3. **Orkiestrator use-case**
   - `luca-tracking`
4. **Output adapters**
   - `luca-reporting`
   - `luca-publishing`
5. **Entrypointy**
   - `luca-interface-*`

## Reguły zależności

### Reguła R1: kierunek zależności

Zależności mogą iść wyłącznie „w dół” architektury (do warstw bazowych) albo do ściśle określonych adapterów używanych przez orkiestrator.

### Reguła R2: lista dozwolonych importów

Źródłem prawdy jest plik `docs/architecture_import_policy.toml`.

| Pakiet | Dozwolone importy wewnętrzne |
|---|---|
| `luca-types` | *(brak)* |
| `luca-input` | `luca-types` |
| `luca-camera` | `luca-types`, `luca-input` |
| `luca-processing` | `luca-types`, `luca-input` |
| `luca-tracking` | `luca-types`, `luca-input`, `luca-camera`, `luca-processing`, `luca-reporting`, `luca-publishing` |
| `luca-reporting` | `luca-types` |
| `luca-publishing` | `luca-types`, `luca-processing` |
| `luca-interface-cli` | `luca-types`, `luca-input`, `luca-tracking` |
| `luca-interface-gui` | `luca-types`, `luca-input`, `luca-tracking` |
| `luca-interface-ros2` | `luca-types`, `luca-input`, `luca-tracking` |
| `luca-suite` | *(brak)* |

### Reguła R3: publiczne API pakietu

Każdy pakiet musi publikować stabilny kontrakt przez:
- `src/<package>/__init__.py` (`__all__`),
- sekcję **Public API** w README pakietu.

Importy między pakietami powinny używać tego kontraktu (`from luca_x import ...`), zamiast importów z modułów implementacyjnych.

### Reguła R4: moduły internal-only

Moduły i podpakiety oznaczone prefiksem `_` (np. `_internal`, `_internal_parser`) są traktowane jako **internal-only** i nie mogą być importowane spoza własnego pakietu.

Przykład:
- ✅ `from luca_processing import detect_spots_with_config`
- ❌ `from luca_processing._internal.pipeline import ...`

## Egzekwowanie reguł

Reguły są sprawdzane przez skrypt `tools/check_architecture_policy.py` uruchamiany w CI workflow `dependency-guard.yml`.
