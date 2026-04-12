## Opis zmian

<!-- Krótkie podsumowanie celu i zakresu PR. -->

## API compatibility checklist

- [ ] Publiczne eksporty (`__all__`) zostały świadomie zweryfikowane dla zmienianych pakietów.
- [ ] Sekcja `Public API` w README zmienianych pakietów odpowiada realnym eksportom.
- [ ] Nie dodano importów do modułów `internal-only` (segmenty z prefiksem `_`) spoza pakietu właściciela.
- [ ] Zmiany utrzymują kompatybilność wsteczną API lub opisano plan migracji.

## Walidacja

- [ ] Uruchomiono lokalne testy/checki adekwatne do zakresu zmian.
