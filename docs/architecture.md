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

## Dlaczego taki podział

Podział na warstwy jest celowy i wynika z wymagań R&D: szybkie iteracje eksperymentów bez utraty kontroli nad stabilnością integracji.

1. **Warstwa bazowa** (`luca-types`, `luca-input`) zawiera kontrakty danych i konfigurację, które powinny być:
   - stabilne,
   - lekkie,
   - niezależne od szczegółów algorytmicznych i technologii uruchomieniowych.
2. **Warstwa domenowa** (`luca-camera`, `luca-processing`) izoluje logikę pozyskiwania i przetwarzania danych:
   - można ją rozwijać eksperymentalnie,
   - zmiany nie powinny wymuszać zmian w interfejsach użytkownika ani adapterach wyjścia.
3. **Orkiestrator use-case** (`luca-tracking`) scala przepływ biznesowy:
   - jest jedynym miejscem kompozycji pełnego pipeline,
   - redukuje duplikację logiki między różnymi entrypointami.
4. **Output adapters** (`luca-reporting`, `luca-publishing`) oddzielają „co liczymy” od „jak publikujemy”:
   - formaty raportów i transport (np. ROS2) mogą ewoluować niezależnie,
   - mniejsze ryzyko „przecieku” zależności infrastrukturalnych do domeny.
5. **Entrypointy** (`luca-interface-*`) są cienką warstwą integracyjną:
   - mapują środowisko uruchomieniowe (CLI/GUI/ROS2) na use-case,
   - nie powinny zawierać logiki domenowej.

Efekt: mniejsze sprzężenie, prostsze testowanie, łatwiejsza wymiana komponentów i bardziej przewidywalne review zmian.

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

## Wytyczne integracyjne dla przyszłych zmian

Poniższe zasady są obowiązkowe dla każdej nowej integracji (nowy pakiet, nowy adapter, nowy entrypoint, nowy feature cross-package).

### 1) Zasada „najpierw kontrakt”

Przed implementacją:
- zdefiniuj modele/typy wejścia-wyjścia w `luca-types` (jeśli wymagane),
- zdefiniuj konfigurację/mapping wejścia w `luca-input` (jeśli wymagane),
- dopiero później dodawaj logikę w warstwie domenowej i orkiestracji.

Cel: uniknąć ad-hoc kontraktów rozproszonych po wielu pakietach.

### 2) Gdzie umieścić nowy kod

- **Nowy algorytm przetwarzania** -> `luca-processing`.
- **Nowe źródło obrazu/kamery** -> `luca-camera`.
- **Nowy scenariusz przebiegu pipeline** -> `luca-tracking`.
- **Nowy format raportu/eksportu** -> `luca-reporting`.
- **Nowy kanał publikacji/transportu** -> `luca-publishing`.
- **Nowy sposób uruchomienia aplikacji** -> `luca-interface-*`.

Jeżeli zmiana nie pasuje jednoznacznie do jednej kategorii, utwórz krótką decyzję architektoniczną (ADR) w `docs/adr/` i uzgodnij ją przed merge.

### 3) Zasada importów między pakietami

- Importuj tylko przez **Public API** (`__init__.py`) innego pakietu.
- Nie importuj modułów z segmentem zaczynającym się od `_` spoza własnego pakietu.
- Każda nowa zależność między pakietami wymaga:
  1. aktualizacji `docs/architecture_import_policy.toml`,
  2. aktualizacji tabeli w tym dokumencie,
  3. uzasadnienia w opisie PR (sekcja „Architecture impact”).

### 4) Definicja „done” dla zmian architektonicznych

Zmiana jest gotowa do merge tylko gdy:
- policy check przechodzi lokalnie i w CI,
- README zmienionego pakietu zawiera aktualną sekcję **Public API**,
- `__init__.py` zmienionego pakietu publikuje kompletne `__all__`,
- nie pojawiły się importy do modułów internal-only poza pakietem właściciela.

### 5) Stabilność i deprecacje API

- Public API traktujemy jako kontrakt semantyczny.
- Usunięcia lub zmiany niekompatybilne wymagają:
  - oznaczenia deprecacji (minimum jeden cykl wydania),
  - notatki migracyjnej w README pakietu lub changelogu.

### 6) Checklist dla autora PR

Przed otwarciem PR:
- [ ] Czy nowa logika znajduje się w poprawnej warstwie?
- [ ] Czy importy cross-package są zgodne z policy?
- [ ] Czy używam wyłącznie Public API innych pakietów?
- [ ] Czy README i `__all__` zostały zaktualizowane?
- [ ] Czy opisałem wpływ architektoniczny i plan migracji (jeśli dotyczy)?
