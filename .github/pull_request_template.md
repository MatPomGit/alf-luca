## Opis zmian

<!-- Krótkie podsumowanie celu i zakresu PR. -->

## Architecture impact

- [ ] Zmiana nie wpływa na granice pakietów i kierunki zależności.
- [ ] Zmiana wpływa na architekturę (opisano poniżej, co i dlaczego).

<!-- Jeśli zaznaczono drugi checkbox, opisz krótko wpływ na architekturę. -->

## API compatibility checklist

- [ ] Publiczne eksporty (`__all__`) zostały świadomie zweryfikowane dla zmienianych pakietów.
- [ ] Sekcja `Public API` w README zmienianych pakietów odpowiada realnym eksportom.
- [ ] Nie dodano importów do modułów `internal-only` (segmenty z prefiksem `_`) spoza pakietu właściciela.
- [ ] Zmiany utrzymują kompatybilność wsteczną API lub opisano plan migracji.

## Walidacja

- [ ] Uruchomiono lokalne testy/checki adekwatne do zakresu zmian.
