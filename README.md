# alf-luca

Narzędzia do kalibracji kamery, śledzenia plamki światła oraz analizy wyników z pliku wideo albo kamery na żywo.

## Autor

J2S

## Dokumentacja deweloperska

- Setup środowiska i zasady uruchamiania: `docs/development.md`.


## Struktura repozytorium

- `luca_tracker/` - legacy facade + wygodny punkt wejścia `python -m luca_tracker ...`; część logiki GUI nadal jest utrzymywana tutaj.
- `tools/` - skrypty pomocnicze do analizy CSV, QA wideo i ekstrakcji obrazów kalibracyjnych.
- `scripts/` - gotowe skrypty uruchomieniowe.
- `config/` - konfiguracja GUI i przykładowa konfiguracja pełnego uruchomienia.
- `video/` - przykładowe pliki wejściowe.
- `images_calib/` - obrazy szachownicy do kalibracji.
- `Dockerfile` - obraz środowiska uruchomieniowego.


## Pakiety Python (monorepo)

| Pakiet | Odpowiedzialność | Kluczowe zależności | Entrypointy |
|---|---|---|---|
| `luca-types` | Modele konfiguracji i typy domenowe współdzielone przez pozostałe moduły. | `pydantic` | brak CLI (import biblioteczny) |
| `luca-input` | Mapowanie konfiguracji i ścieżek wejścia/wyjścia. | `pyyaml`, `luca-types` | brak CLI (import biblioteczny) |
| `luca-camera` | Obsługa źródeł obrazu i kalibracji kamery. | `opencv-python`, `numpy`, `luca-input`, `luca-tracking` | brak CLI (import biblioteczny) |
| `luca-processing` | Detektory, postprocess i logika filtracji śledzenia. | `opencv-python`, `numpy`, `luca-types` | brak CLI (import biblioteczny) |
| `luca-tracking` | Pipeline śledzenia i serwisy aplikacyjne. | `luca-types`, `luca-input`, `luca-processing` | brak CLI (import biblioteczny) |
| `luca-reporting` | Raporty CSV/PDF i eksport materiałów wynikowych. | `pandas`, `matplotlib`, `fpdf2`, `opencv-python`, `luca-types` | brak CLI (import biblioteczny) |
| `luca-publishing` | Integracja publikacji zdarzeń śledzenia (ROS2/adaptory). | `opencv-python`, `numpy`, `luca-processing` | brak CLI (import biblioteczny) |
| `luca-interface-cli` | Interfejs uruchomieniowy CLI dla usług LUCA. | `luca-tracking`, `luca-tracker` | `luca-cli` |
| `luca-interface-gui` | Interfejs GUI dla usług LUCA. | `luca-tracking`, `luca-tracker` | `luca-gui` |
| `luca-interface-ros2` | Interfejs ROS2 dla uruchamiania i publikacji danych online. | `luca-tracking`, `luca-tracker` | `luca-ros2` |
| `luca-suite` | Metapakiet spinający kompatybilne wersje wszystkich modułów. | Wszystkie pakiety `luca-*` w zakresie `>=0.1.0,<0.2.0` | brak CLI (meta-zależności) |

## Gdzie rozwijać nowy kod

Najczęstsza pomyłka w tym repo to dopisywanie nowej logiki w niewłaściwej warstwie. Najbezpieczniejsza zasada jest taka:

- nową logikę produkcyjną dodawaj do `packages/*/src/*`,
- `luca_tracker/` traktuj głównie jako legacy facade, punkt wejścia i miejsce utrzymywania zgodności wstecznej,
- `scripts/` traktuj jako wygodne uruchamianie, a nie główne miejsce logiki domenowej.

Praktyczna mapa:

- nowy detektor lub filtrowanie obrazu -> `packages/luca-processing/src/luca_processing/`
- tracking, pipeline i przypadki użycia -> `packages/luca-tracking/src/luca_tracking/`
- publikacja ROS2, runtime online i kontrakt JSON -> `packages/luca-publishing/src/luca_publishing/`
- typy i modele konfiguracji -> `packages/luca-types/src/luca_types/`
- mapowanie wejść/wyjść i ścieżek -> `packages/luca-input/src/luca_input/`
- GUI -> `luca_tracker/gui.py` oraz adaptery `packages/luca-interface-gui/`
- kompatybilność starych importów -> `luca_tracker/`

Jeśli nie wiesz, gdzie zacząć, najpierw sprawdź `packages/luca-tracking/src/luca_tracking/application_services.py`, a potem zejdź warstwę niżej do pakietu domenowego, który naprawdę powinien dostać zmianę.

## Jak się w tym nie pogubić

Jeśli wchodzisz do projektu pierwszy raz, nie musisz rozumieć od razu wszystkich pakietów. W praktyce najważniejsze są tylko cztery warstwy:

1. `luca_tracker`  
   To najwygodniejszy punkt wejścia. Stąd uruchamiasz `python -m luca_tracker ...`, GUI i skrypty z katalogu `scripts/`.
2. `luca-processing`  
   Tu dzieje się detekcja plamki na obrazie: progowanie, filtrowanie, wybór najlepszego punktu.
3. `luca-tracking`  
   Tu składany jest cały pipeline: wejście wideo/kamera, detekcja, śledzenie, zapis wyników.
4. `luca-publishing`  
   Tu dane są publikowane online, głównie do ROS2.

Najprostszy model mentalny jest taki:

- kamera albo plik wideo daje klatki,
- detektor znajduje na klatce najjaśniejszą plamkę,
- tracker zamienia to na stabilny punkt `x/y` w czasie,
- jeśli mamy kalibrację i referencje PnP, punkt `x/y` jest przeliczany na `x_world/y_world/z_world`,
- wynik trafia do CSV, GUI albo na topic ROS2.

Jeżeli masz mało czasu, zacznij od tych plików:

- `luca_tracker/cli.py`  
  Pokazuje, jakie są tryby uruchamiania i jakie argumenty można podać.
- `packages/luca-tracking/src/luca_tracking/application_services.py`  
  To warstwa spinająca przypadki użycia: `track`, `compare`, `ros2`, `calibrate`.
- `packages/luca-tracking/src/luca_tracking/pipeline.py`  
  To główne miejsce, gdzie wykonywane jest śledzenie offline/live.
- `packages/luca-publishing/src/luca_publishing/ros2_node.py`  
  To najważniejszy plik dla publikacji online i współrzędnych `XYZ`.
- `scripts/`  
  Tu są gotowe, praktyczne wejścia do najczęstszych scenariuszy.

## Gdzie rozwijać nowy kod

Najczęstsza pomyłka w tym repo to dopisywanie nowej logiki w niewłaściwej warstwie. Najbezpieczniejsza zasada jest taka:

- nową logikę produkcyjną dodawaj do `packages/*/src/*`,
- `luca_tracker/` traktuj głównie jako legacy facade, punkt wejścia i miejsce utrzymywania zgodności wstecznej,
- `scripts/` traktuj jako wygodne uruchamianie, a nie główne miejsce logiki domenowej.

Praktyczna mapa:

- nowy detektor lub filtrowanie obrazu -> `packages/luca-processing/src/luca_processing/`
- tracking, pipeline i przypadki użycia -> `packages/luca-tracking/src/luca_tracking/`
- publikacja ROS2, runtime online i kontrakt JSON -> `packages/luca-publishing/src/luca_publishing/`
- typy i modele konfiguracji -> `packages/luca-types/src/luca_types/`
- mapowanie wejść/wyjść i ścieżek -> `packages/luca-input/src/luca_input/`
- GUI -> `luca_tracker/gui.py` oraz adaptery `packages/luca-interface-gui/`
- kompatybilność starych importów -> `luca_tracker/`

Jeśli nie wiesz, gdzie zacząć, najpierw sprawdź `packages/luca-tracking/src/luca_tracking/application_services.py`, a potem zejdź warstwę niżej do pakietu domenowego, który naprawdę powinien dostać zmianę.

## Co po kolei robi system

Poniżej najkrótsze wyjaśnienie całego przepływu, prostym językiem:

1. **Pobranie obrazu**  
   Program czyta klatkę z pliku wideo albo z fizycznej kamery.
2. **Wykrycie plamki**  
   Z obrazu wybierany jest najjaśniejszy albo kolorowy punkt, zależnie od trybu.
3. **Ustalenie pozycji 2D**  
   Dla wykrytej plamki wyznaczane są współrzędne obrazu `x` i `y`, a także parametry jakości jak `area`, `radius`, `confidence`.
4. **Śledzenie w czasie**  
   Kolejne klatki są łączone w jedną trajektorię, żeby ruch nie był „skaczący” od klatki do klatki.
5. **Opcjonalne przeliczenie do 3D (`XYZ`)**  
   Jeśli dostępna jest kalibracja kamery i punkty odniesienia PnP, punkt z obrazu jest rzutowany na układ świata.
6. **Publikacja albo zapis**  
   Wynik trafia do CSV, raportu, GUI, filmu wynikowego albo na topic ROS2.

## Skąd biorą się punkty XYZ

To jest najważniejsza rzecz dla osób integrujących ten projekt z innym oprogramowaniem.

`x` i `y` są współrzędnymi punktu na obrazie, czyli po prostu pozycją plamki w pikselach.

`x_world`, `y_world`, `z_world` to współrzędne tego samego punktu, ale w umownym układzie świata. Żeby je policzyć, potrzebne są trzy rzeczy:

1. **Kalibracja kamery**  
   Plik `camera_calib.npz` zawiera parametry optyki kamery: macierz kamery i dystorsję.
2. **Referencje PnP**  
   Trzeba znać kilka punktów planszy lub sceny:
   - gdzie leżą w świecie (`pnp_object_points`),
   - gdzie widać je na obrazie (`pnp_image_points`).
3. **Założenie płaszczyzny świata**  
   Program zakłada, że szukany punkt leży na płaszczyźnie `Z = const` i przecina promień kamery z tą płaszczyzną.

W praktyce działa to tak:

- kamera widzi punkt plamki w pikselu `x/y`,
- z kalibracji wiadomo, jak ten piksel przekłada się na kierunek patrzenia kamery,
- z PnP wiadomo, gdzie kamera znajduje się względem planszy odniesienia,
- z przecięcia tego kierunku z płaszczyzną świata powstaje `x_world/y_world/z_world`.

Technicznie ten algorytm jest utrzymywany jako jeden współdzielony kod w `luca-processing`
(`luca_processing.world_projection`) i jest używany zarówno przez pipeline offline (`track`),
jak i publikację online ROS2 (`ros2`).

Dlatego `XYZ` nie jest „magiczne” ani brane z modelu AI. To czysta geometria kamery.

## Dlaczego XYZ jest puste?

Jeśli w CSV/GUI/ROS2 widzisz puste `x_world/y_world/z_world`, przejdź checklistę:

1. **Sprawdź status kalibracji w logu** (`track` i `ros2`):
   - `intrinsics_loaded=True` — plik `camera_calib.npz` został poprawnie wczytany,
   - `pnp_points_loaded=True` — podano komplet `pnp_object_points` + `pnp_image_points`,
   - `pnp_solved=True` — estymacja PnP się powiodła,
   - `world_projection_enabled=True` — rekonstrukcja `XYZ` jest realnie aktywna.
2. **Zweryfikuj intrinsics**:
   - czy wskazujesz właściwy plik `--calib_file`,
   - czy plik zawiera `camera_matrix` i `dist_coeffs`.
3. **Zweryfikuj PnP**:
   - czy liczba punktów 3D i 2D jest taka sama,
   - czy punktów jest co najmniej 4,
   - czy punkty odpowiadają sobie kolejnością.
4. **Sprawdź skrypty auto-derywacji** (`run_ros2_camera_xyz.sh/.bat`):
   - skrypt wypisuje czy auto-derywacja PnP zakończyła się sukcesem,
   - przy błędzie popraw `images_calib/` albo podaj `LUCA_PNP_OBJECT_POINTS` / `LUCA_PNP_IMAGE_POINTS` ręcznie.
5. **(Opcjonalnie) ROS2 diagnostyka w payloadzie**:
   - ustaw `--message_schema luca_tracker.ros2.tracking.v2`,
   - runtime doda pole `diagnostics.calibration_status` bez łamania kontraktu v1.

### Objaw -> przyczyna -> naprawa (diagnostyka XYZ)

| Objaw | Prawdopodobna przyczyna | Krok naprawczy |
|---|---|---|
| `x_world/y_world/z_world` są puste, a `intrinsics_status_code=INTRINSICS_MISSING` | Nie podano `--calib_file` albo plik nie ma `camera_matrix`/`dist_coeffs`. | Podaj poprawny plik kalibracji i zweryfikuj jego zawartość (`camera_matrix`, `dist_coeffs`). |
| `x_world/y_world/z_world` są puste, a `pnp_points_status_code=PNP_POINTS_INCOMPLETE` lub `PNP_POINTS_MISSING` | Brakuje jednej listy punktów PnP (3D albo 2D). | Podaj oba pola: `pnp_object_points` i `pnp_image_points` w tej samej kolejności punktów. |
| `x_world/y_world/z_world` są puste, a `pnp_points_status_code=PNP_POINTS_PARSE_ERROR` | Niepoprawny format tekstu punktów (separator, liczba współrzędnych, puste wpisy). | Użyj formatu `X,Y,Z;...` dla 3D i `x,y;...` dla 2D, bez dodatkowych znaków. |
| `x_world/y_world/z_world` są puste, a `pnp_points_status_code=PNP_POINTS_COUNT_MISMATCH` | Inna liczba punktów 3D i 2D. | Wyrównaj listy tak, aby każdemu punktowi 3D odpowiadał dokładnie jeden punkt 2D. |
| `x_world/y_world/z_world` są puste, a `solvepnp_status_code=SOLVEPNP_FAILED` | Geometria referencji jest niestabilna (duplikaty, degeneracja, zła kolejność punktów). | Zmień punkty referencyjne: min. 4 unikalne pary, dobre pokrycie planszy, spójna kolejność. |
| `x_world/y_world/z_world` są puste tylko dla części klatek, `ray_plane_status_code=RAY_PLANE_PARALLEL` | Dla tej klatki promień kamery jest równoległy do płaszczyzny świata. | Skoryguj `pnp_world_plane_z`, pozycję kamery lub punkt detekcji; sprawdź stabilność PnP na materiale wejściowym. |

W payloadzie ROS2 dostępne są równolegle:
- `world_projection_status_codes` (status każdego etapu),
- `world_projection_error_causes` (kod przyczyny błędu per etap lub `null`, gdy etap jest poprawny).

## Jak czytać XYZ i co można z tym zrobić dalej

Najprostsze miejsca odczytu to:

- CSV z `track`  
  dobre do analizy offline, wykresów, eksportu do Excela, Pandas, Matlab lub innego narzędzia.
- JSON publikowany na ROS2  
  dobre do pracy online, sterowania robotem, synchronizacji z innymi sensorami albo dalszego przetwarzania w osobnym procesie.
- GUI / podgląd  
  dobre do strojenia i weryfikacji, ale nie jako główny interfejs integracyjny.

Co programista może zrobić dalej z `XYZ`:

- liczyć prędkość i przyspieszenie punktu,
- wykrywać przekroczenie stref lub progów,
- sterować manipulatorem, kamerą albo innym układem wykonawczym,
- łączyć dane z IMU, enkoderami albo innym trackingiem,
- zapisywać trajektorie do własnej bazy, logów lub systemu analitycznego,
- filtrować dane w osobnym programie, np. Kalmana, EMA albo własnym estymatorem.

Najpraktyczniejsza zasada integracyjna:

- ten projekt traktuj jako warstwę „detekcja + pozycja”,
- logikę biznesową lub sterowanie trzymaj w osobnym programie,
- konsumuj `x/y/XYZ` przez CSV albo ROS2 i buduj na tym kolejne etapy.

## Wymagania

- Python 3.10+
- pakiety z `requirements.txt`
- opcjonalnie `ffmpeg` i `ffprobe` dla `tools/video_tool.py`

Instalacja:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Uruchamianie z checkoutu repo:

- `python -m luca_tracker ...` działa bez ręcznego `pip install -e` dla pakietów z `packages/*`,
- legacy entrypoint `luca_tracker` automatycznie doładowuje lokalne ścieżki `packages/*/src`,
- editable installs są nadal przydatne do pracy stricte pakietowej i publikacji, ale nie są wymagane do podstawowego uruchamiania CLI/skryptów z repo.

## Szybki start krok po kroku (co uruchamiać po kolei)

Poniżej najkrótsza, praktyczna ścieżka od zera do działającego śledzenia:

1. Wejdź do katalogu projektu i zainstaluj zależności:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

2. (Opcjonalnie, ale zalecane) wykonaj kalibrację kamery, jeśli pracujesz z kamerą fizyczną:

```bash
python -m luca_tracker calibrate \
  --calib_dir images_calib \
  --rows 7 \
  --cols 10 \
  --square_size 1.0 \
  --output_file camera_calib.npz
```

3. Uruchom tracking na materiale testowym z repozytorium (najprostszy start):

```bash
python -m luca_tracker track \
  --video video/sledzenie_plamki.mp4 \
  --track_mode brightness \
  --output_csv output/manual/tracking_results.csv \
  --report_csv output/manual/report.csv \
  --trajectory_png output/manual/trajectory.png
```

4. Sprawdź wyniki w katalogu `output/manual/` albo domyślnie `output/<timestamp>/`.

5. Dla pracy na żywo z kamerą uruchom:

```bash
python -m luca_tracker track \
  --camera 0 \
  --display \
  --calib_file camera_calib.npz
```

6. Zakończ tryb podglądu klawiszem `q` (okno OpenCV) albo przerwaniem procesu (`Ctrl+C`).

## Gdzie są wystawione informacje o aktualnej pozycji plamki (w tym XYZ)

Aktualna pozycja śledzonego obiektu jest dostępna w kilku miejscach – zależnie od trybu uruchomienia:

1. **CSV głównej trajektorii (`--output_csv`)**
   - zawiera pozycję 2D (`x`, `y`) i pola rekonstrukcji 3D (`x_world`, `y_world`, `z_world`),
   - to podstawowe źródło do analizy offline po zakończeniu przebiegu.

2. **CSV wszystkich torów (`--all_tracks_csv`)**
   - przydatne w `--multi_track`, gdy trzeba analizować wiele obiektów równolegle,
   - zawiera analogiczne pola pozycyjne dla każdego `track_id`.

3. **ROS2 topic (`python -m luca_tracker ros2`)**
   - node publikuje JSON (`std_msgs/String`) na topicu `--topic` (domyślnie `/luca_tracker/tracking`),
   - wiadomości zawierają bieżące dane klatkowe, m.in. `x`, `y`, `radius`, `detected`, `frame_index`, `time_sec`,
   - to główne źródło danych "online" dla integracji z innymi systemami.

4. **Podgląd GUI / OpenCV (`--display` lub `gui`)**
   - umożliwia obserwację pozycji i jakości detekcji w czasie rzeczywistym,
   - traktuj jako szybki podgląd operatorski (nie jako docelowy interfejs integracyjny).

> Uwaga: pola `x_world/y_world/z_world` są wyliczane, gdy podasz dane PnP (`--pnp_object_points`, `--pnp_image_points`) i poprawną geometrię płaszczyzny (`--pnp_world_plane_z`). Bez tego kolumny świata mogą być puste.

### Opis jednostek podglądu i wykresu top-down (wariant PyWebIO)

Aby uniknąć nieporozumień przy interpretacji danych:

- `x/y` w obrazie są w **pikselach** (`px`),
- `x_world/y_world/z_world` są w **jednostkach świata** wynikających z `pnp_object_points` (najczęściej metry, ale zależy to od Twojej kalibracji).

W GUI te jednostki są teraz dopisywane bezpośrednio do panelu top-down i HUD.  
Jeżeli chcesz analogiczny opis w prostym panelu webowym, możesz użyć PyWebIO:

```python
from pywebio.output import put_markdown, put_table


def show_units_legend():
    # Opis jednostek podglądu dla operatora i QA.
    put_markdown("## Legenda jednostek podglądu LUCA")
    put_table([
        ["Pole", "Znaczenie", "Jednostka"],
        ["x, y", "Pozycja plamki w obrazie kamery", "px"],
        ["x_world, y_world, z_world", "Pozycja w układzie świata (PnP)", "world_u (typically m)"],
        ["plane_z", "Wysokość płaszczyzny projekcji", "world_u (typically m)"],
    ])
```

Instalacja PyWebIO (opcjonalnie, tylko dla panelu opisowego):

```bash
pip install pywebio
```

## Matryca parametrów kontraktu konfiguracji

Ujednoliconą matrycę opcji (`input`, `detection`, `tracking`, `calibration`,
`reporting`, `publication`) utrzymujemy w pliku:

- `packages/luca-input/src/luca_input/entrypoint_option_contract.py` (`PARAMETER_MATRIX`).

Ta sama matryca jest pokryta testem kontraktowym
`tests/test_configuration_contract.py`, który porównuje wynikowe `RunConfig`
pomiędzy adapterami `track/gui/ros2` oraz sprawdza mapowanie do pipeline.

Poglądowa tabela mapowań do `RunConfig`:

| Opcja CLI | Pole adaptera | Pole w `RunConfig` |
| --- | --- | --- |
| `--video` | `video` | `input.video` |
| `--camera` / `--camera_index` | `camera` / `camera_index` | `input.camera` |
| `--display` | `display` | `input.display` |
| `--track_mode` | `track_mode` | `detector.track_mode` |
| `--min_detection_confidence` | `min_detection_confidence` | `detector.min_detection_confidence` |
| `--max_distance` | `max_distance` | `tracker.max_distance` |
| `--min_match_score` | `min_match_score` | `tracker.min_match_score` |
| `--calib_file` | `calib_file` | `input.calib_file` |
| `--pnp_object_points` | `pnp_object_points` | `pose.pnp_object_points` |
| `--output_csv` | `output_csv` | `eval.output_csv` |
| `--use_kalman` | `use_kalman` | `postprocess.use_kalman` |
| `--topic` | `topic` | runtime-only (ROS2, poza `RunConfig`) |

## Przykłady uruchamiania aplikacji w różnych trybach

### 1) Tryb CLI – plik wideo (jasność)

```bash
python -m luca_tracker track \
  --video video/sledzenie_plamki.mp4 \
  --track_mode brightness \
  --threshold_mode adaptive \
  --use_clahe \
  --display
```

### 2) Tryb CLI – plik wideo (kolor)

```bash
python -m luca_tracker track \
  --video video/luca_kolory.mp4 \
  --track_mode color \
  --color_name red \
  --output_csv output/manual/color_track.csv
```

### 3) Tryb CLI – kamera na żywo

```bash
python -m luca_tracker track \
  --camera 0 \
  --track_mode brightness \
  --display
```

### 3a) Auto-tuning z nagrania i presety do live-trackingu

Najpierw wyznacz preset na podstawie wskazanego nagrania referencyjnego:

```bash
python -m luca_tracker track \
  --camera 0 \
  --auto_tune_from_video video/sledzenie_plamki.mp4 \
  --auto_tune_preset_name lab_live \
  --tracking_presets_file config/live_tracking_presets.json \
  --display
```

Potem możesz używać gotowego presetu podczas śledzenia kamerą na żywo:

```bash
python -m luca_tracker track \
  --camera 0 \
  --live_tracking_preset lab_live \
  --tracking_presets_file config/live_tracking_presets.json \
  --display
```

Lista dostępnych presetów:

```bash
python -m luca_tracker track \
  --camera 0 \
  --list_live_tracking_presets \
  --tracking_presets_file config/live_tracking_presets.json
```

### 4) Tryb GUI (strojenie parametrów)

```bash
python -m luca_tracker gui --video video/sledzenie_plamki.mp4
```

### 5) Tryb konfiguracji YAML (powtarzalne uruchomienia)

```bash
python -m luca_tracker track --config config/run_tracking.sample.yaml
```

### 5a) Gotowy preset anti-false-positive (video/sledzenie_plamki.mp4)

Jeśli chcesz szybciej ograniczyć przypadkowe artefakty i pojedyncze „błyski”, użyj gotowego presetu:

```bash
python -m luca_tracker track --config config/run_tracking.sledzenie_low_fp.yaml
```

W tym presecie celowo podniesiono progi jakości detekcji (`min_detection_confidence`, `min_detection_score`), dodano filtr trwałości (`min_persistence_frames`) i lekko zaostrzono gating trackera.
Jeżeli tracking stanie się zbyt „ostrożny” (za dużo braków detekcji), najpierw poluzuj:

1. `min_detection_confidence` (np. z `0.62` do `0.50`),
2. `min_persistence_frames` (np. z `3` do `2`),
3. `min_match_score` (np. z `0.62` do `0.55`).

### 6) Tryb ROS2 (strumień online + publikacja pozycji)

```bash
python -m luca_tracker ros2 \
  --camera_index 0 \
  --topic /luca_tracker/tracking \
  --max_distance 45 \
  --min_match_score 0.45 \
  --fps 30 \
  --display
```

Przykład dla wymagania „detector_node + pozycja 2D/3D wybranego ID”:

```bash
python -m luca_tracker ros2 \
  --node_name detector_node \
  --camera_index 0 \
  --topic /luca_tracker/tracking \
  --spot_id 0 \
  --run_metadata_json output/example.run.json \
  --calib_file camera_calib.npz \
  --pnp_object_points "0,0,0;1,0,0;1,1,0;0,1,0" \
  --pnp_image_points "120,210;520,205;525,470;115,475" \
  --pnp_world_plane_z 0.0 \
  --fps 30 \
  --display
```

Publikowany JSON na topicu zawiera m.in. pola:
- `schema` (wersja kontraktu wiadomości, konfigurowana przez `--message_schema`),
- `spot_id`, `detected`, `x`, `y` (współrzędne ekranowe),
- `x_world`, `y_world`, `z_world` (współrzędne 3D),
- `frame_index`, `time_sec`, `detections_count`,
- `run_metadata` (opcjonalny obiekt JSON pochodzący z `--run_metadata_json`, np. z plików `*.run.json`).

#### Przepływ danych krok po kroku (od skryptu do publikacji ROS2)

1. **Uruchomienie adaptera ROS2 (`luca-interface-ros2`)**  
   Skrypt wejściowy buduje parser argumentów (`--camera_index`, `--topic`, `--spot_id`, konfiguracja detektora itp.) i przekazuje zebrane parametry do warstwy usług aplikacyjnych.
2. **Mapowanie argumentów na konfigurację runtime (`luca-publishing`)**  
   Argumenty CLI są normalizowane do obiektu konfiguracyjnego node, gdzie ustawiane są źródło wideo, częstotliwość przetwarzania, tryb detekcji, ROI i opcje kalibracji/PnP.
3. **Start node ROS2 i timera przetwarzania**  
   Node tworzy publisher `std_msgs/String` i uruchamia cykliczny timer zgodny z docelowym FPS. Każde wywołanie timera odpowiada pojedynczej iteracji przetwarzania klatki.
4. **Pobranie klatki z kamery i detekcja plamki**  
   W każdej iteracji runtime czyta nową klatkę (`cv2.VideoCapture.read()`), uruchamia detektor i pobiera listę wykryć wraz z ROI. Następnie wybierana jest plamka o indeksie `spot_id`.
5. **Wyliczenie współrzędnych 2D i opcjonalnie 3D**  
   Dla wybranej detekcji wyznaczane są współrzędne pikselowe (`x`, `y`) i parametry geometrii (`area`, `radius`, `rank`). Jeśli aktywna jest kalibracja i PnP, przeliczane są także współrzędne świata (`x_world`, `y_world`, `z_world`).
6. **Budowa kontraktowego payloadu JSON**  
   Runtime składa kompletny obiekt JSON: metadane czasu ROS, informacje o źródle i trybie pracy, status detekcji oraz dane pozycji. Kontrakt jest walidowany pod kątem obecności wymaganych pól.
7. **Publikacja wiadomości na topicu ROS2**  
   Gotowy payload jest serializowany do `msg.data` i publikowany na skonfigurowanym topicu (domyślnie `/luca_tracker/tracking`), gotowy do konsumpcji przez kolejne nody.

#### Sugestie dla programistów konsumujących współrzędne (`x`, `y`, `x_world`, `y_world`, `z_world`)

- **Zawsze weryfikuj `schema` i wersjonuj własny parser.**  
  Traktuj `schema` jako twardy kontrakt wejściowy i przygotuj jawne mapowanie wersji, aby bezpiecznie przechodzić między rewizjami payloadu.
- **Nie zakładaj ciągłości detekcji.**  
  Gdy `detected=false`, pola pozycji mogą być `null`. Po stronie konsumenta warto utrzymywać stan `last_valid_sample` i politykę timeoutu (np. 200–500 ms) zamiast natychmiastowego zerowania.
- **Filtruj sygnał pozycji przed sterowaniem.**  
  Dla sterowania robotem rekomendowane są co najmniej: EMA (prostota), filtr Kalmana (szum + predykcja), albo filtr komplementarny przy łączeniu z IMU/odometrią.
- **Używaj `stamp_sec` + `stamp_nanosec` do synchronizacji między topicami.**  
  Nie opieraj logiki czasowej wyłącznie na czasie lokalnym subskrybenta; do korelacji z innymi sensorami stosuj timestamp ROS z payloadu i/lub `message_filters`.
- **Oddziel warstwę detekcji od logiki decyzyjnej.**  
  Dobrą praktyką jest osobny node „estymatora” (wygładzanie + walidacja ruchu) i dopiero potem node „kontrolera”, aby uprościć testowanie i diagnostykę.
- **Dodaj bramki jakości danych.**  
  Wykorzystuj `area`, `radius`, `rank`, `detections_count` do odrzucania niestabilnych pomiarów (np. minimalna powierzchnia, maksymalny skok pozycji, ograniczenie prędkości punktu).
- **Rozważ publikację pochodnych wielkości.**  
  Jeśli aplikacja tego wymaga, wyliczaj prędkość/przyspieszenie punktu (`dx/dt`, `dy/dt`) w osobnym node i publikuj je jako nowy topic, zamiast przeciążać bazowy kontrakt trackera.
- **Przy przetwarzaniu 3D waliduj geometrię stanowiska.**  
  Jakość `x_world/y_world/z_world` zależy od kalibracji i stabilności punktów referencyjnych PnP; regularnie wykonuj rekalibrację i testy błędu reprojekcji.

Przykładowy payload:

```json
{
  "schema": "luca_tracker.ros2.tracking.v1",
  "stamp_sec": 1712750400,
  "stamp_nanosec": 245001000,
  "frame_index": 124,
  "time_sec": 4.13,
  "source": "0",
  "track_mode": "brightness",
  "spot_id": 0,
  "detected": true,
  "roi": {"x": 0, "y": 0, "w": 640, "h": 480},
  "detections_count": 1,
  "x": 318.4,
  "y": 251.7,
  "x_world": 1.02,
  "y_world": -0.15,
  "z_world": 0.0,
  "world_projection_reason": "Rekonstrukcja XYZ działa poprawnie.",
  "world_projection_status_codes": {
    "intrinsics": "INTRINSICS_OK",
    "pnp_points": "PNP_POINTS_OK",
    "solvepnp": "SOLVEPNP_OK",
    "ray_plane": "RAY_PLANE_OK"
  },
  "world_projection_error_causes": {
    "intrinsics": null,
    "pnp_points": null,
    "solvepnp": null,
    "ray_plane": null
  },
  "area": 211.3,
  "radius": 8.2,
  "rank": 0,
  "run_metadata": {
    "run_id": "20260410T101530Z-a1b2c3d4",
    "input_source": "video/sledzenie_plamki.mp4",
    "detector_name": "brightness",
    "config_hash": "e1f2a3b4c5d6"
  }
}
```

#### Schemat i znaczenie zmiennych publikowanych na ROS2

| Pole | Typ | Znaczenie |
|---|---|---|
| `schema` | `string` | Identyfikator wersji kontraktu wiadomości JSON. |
| `stamp_sec` / `stamp_nanosec` | `int` / `int` | Znacznik czasu ROS (`node.get_clock().now()`). |
| `frame_index` | `int` | Numer klatki przetworzonej od startu node. |
| `time_sec` | `float` | Czas monotoniczny od startu node w sekundach. |
| `source` | `string` | Źródło kamery (`camera_index` lub ścieżka urządzenia). |
| `track_mode` | `string` | Tryb detekcji (`brightness` albo `color`). |
| `spot_id` | `int` | Indeks detekcji wybranej jako główny obiekt raportowany. |
| `detected` | `bool` | Czy obiekt główny został wykryty w bieżącej klatce. |
| `roi` | `object` | Obszar analizy (`x`, `y`, `w`, `h`) użyty przez detektor. |
| `detections_count` | `int` | Liczba wszystkich detekcji w klatce. |
| `x`, `y` | `float \| null` | Pozycja obiektu w pikselach (null, gdy brak detekcji). |
| `x_world`, `y_world`, `z_world` | `float \| null` | Współrzędne świata (gdy aktywne PnP+kalibracja). |
| `world_projection_reason` | `string` | Czytelny opis bieżącego statusu rekonstrukcji XYZ. |
| `world_projection_status_codes` | `object` | Kody statusu etapów: `intrinsics`, `pnp_points`, `solvepnp`, `ray_plane`. |
| `world_projection_error_causes` | `object` | Kody przyczyn błędów per etap (`null` gdy etap jest poprawny). |
| `area`, `radius`, `rank` | `float/int \| null` | Parametry geometryczne i ranking wybranej detekcji. |
| `run_metadata` | `object \| null` | Metadane runu z pliku `--run_metadata_json` (np. `*.run.json`). |

### 7) Gotowe skrypty startowe (Linux/macOS)

```bash
bash scripts/run_gui.sh
bash scripts/run_cli.sh
bash scripts/run_analysis.sh
bash scripts/run_ros2_camera_xyz.sh
```

Przykład dla publikacji `XYZ` na ROS2:

```bash
export LUCA_PNP_OBJECT_POINTS="0,0,0;1,0,0;1,1,0;0,1,0"
export LUCA_PNP_IMAGE_POINTS="120,210;520,205;525,470;115,475"
bash scripts/run_ros2_camera_xyz.sh
```

Więcej przykładów Linux/macOS:

```bash
# Własny setup ROS2 i własny topic
export LUCA_ROS2_SETUP_FILE=/opt/ros/humble/setup.bash
export LUCA_ROS2_TOPIC=/detector/spot_xyz
export LUCA_ROS2_NODE_NAME=detector_node
export LUCA_PNP_OBJECT_POINTS="0,0,0;1,0,0;1,1,0;0,1,0"
export LUCA_PNP_IMAGE_POINTS="120,210;520,205;525,470;115,475"
bash scripts/run_ros2_camera_xyz.sh

# Kamera o indeksie 1, bez podglądu OpenCV
export LUCA_CAMERA_INDEX=1
export LUCA_DISPLAY=0
export LUCA_PNP_OBJECT_POINTS="0,0,0;1,0,0;1,1,0;0,1,0"
export LUCA_PNP_IMAGE_POINTS="120,210;520,205;525,470;115,475"
bash scripts/run_ros2_camera_xyz.sh

# Ograniczenie analizy do ROI i inne FPS
export LUCA_ROI="100,80,900,700"
export LUCA_ROS2_FPS=20
export LUCA_PNP_OBJECT_POINTS="0,0,0;1,0,0;1,1,0;0,1,0"
export LUCA_PNP_IMAGE_POINTS="120,210;520,205;525,470;115,475"
bash scripts/run_ros2_camera_xyz.sh
```

### 8) Gotowe skrypty startowe (Windows)

```bat
scripts\run_gui.bat
scripts\run_cli.bat
scripts\run_camera.bat
scripts\run_ros2_camera_xyz.bat
```

Przykłady Windows (`cmd.exe`):

```bat
REM Minimalny start z publikacją XYZ
set "LUCA_PNP_OBJECT_POINTS=0,0,0;1,0,0;1,1,0;0,1,0"
set "LUCA_PNP_IMAGE_POINTS=120,210;520,205;525,470;115,475"
scripts\run_ros2_camera_xyz.bat

REM Własny setup ROS2 i własny topic
set "LUCA_ROS2_SETUP_BAT=C:\dev\ros2_humble\local_setup.bat"
set "LUCA_ROS2_TOPIC=/detector/spot_xyz"
set "LUCA_ROS2_NODE_NAME=detector_node"
set "LUCA_PNP_OBJECT_POINTS=0,0,0;1,0,0;1,1,0;0,1,0"
set "LUCA_PNP_IMAGE_POINTS=120,210;520,205;525,470;115,475"
scripts\run_ros2_camera_xyz.bat

REM Kamera 1, bez podglądu i z ROI
set "LUCA_CAMERA_INDEX=1"
set "LUCA_DISPLAY=0"
set "LUCA_ROI=100,80,900,700"
set "LUCA_PNP_OBJECT_POINTS=0,0,0;1,0,0;1,1,0;0,1,0"
set "LUCA_PNP_IMAGE_POINTS=120,210;520,205;525,470;115,475"
scripts\run_ros2_camera_xyz.bat
```

## CLI

Główne wejście:

```bash
python -m luca_tracker --help
```

Śledzenie z pliku:

```bash
python -m luca_tracker track \
  --video video/sledzenie_plamki.mp4 \
  --track_mode brightness
```

Śledzenie z kamery na żywo:

```bash
python -m luca_tracker track \
  --camera 0 \
  --display
```

`--camera` przyjmuje indeks OpenCV, np. `0`, albo ścieżkę urządzenia, np. `/dev/video0`.

Kalibracja kamery:

```bash
python -m luca_tracker calibrate \
  --calib_dir images_calib \
  --rows 7 \
  --cols 10 \
  --square_size 1.0 \
  --output_file camera_calib.npz
```

Porównanie dwóch pomiarów:

```bash
python -m luca_tracker compare \
  --reference output/ref.csv \
  --candidate output/test.csv \
  --output_csv output/diff.csv
```

GUI:

```bash
python -m luca_tracker gui
```

GUI działa na plikach wideo i automatycznie wybiera pliki z katalogu `video/`, jeśli nie podasz `--video`.

## Konfiguracja pełnego uruchomienia

Przykładowa konfiguracja znajduje się w `config/run_tracking.sample.yaml`.

Uruchomienie z konfiguracji:

```bash
python -m luca_tracker track --config config/run_tracking.sample.yaml
```

W sekcji `input` ustaw dokładnie jedno źródło:

- `video` dla pliku
- `camera` dla kamery na żywo

## Skrypty pomocnicze

Linux/macOS:

- `scripts/run_gui.sh` - uruchamia GUI.
- `scripts/run_cli.sh` - przykładowe uruchomienie `track` z wynikami w `output/manual/`.
- `scripts/run_analysis.sh` - generuje wykresy porównawcze z CSV w `output/manual/` przez `tools/data_tool.py`.
- `scripts/compute_pnp_reference.py` - wylicza referencje PnP z obrazów w `images_calib/` i wypisuje je jako zmienne środowiskowe dla `.sh` albo `.bat`.
- `scripts/run_ros2_camera_xyz.sh` - uruchamia ROS2 z kamery fizycznej, śledzi najjaśniejszą plamkę i publikuje `x/y/x_world/y_world/z_world`.

Windows:

- `scripts/run_gui.bat` - uruchamia GUI.
- `scripts/run_cli.bat` - uruchamia analizę przykładowego pliku `video/sledzenie_plamki.mkv`.
- `scripts/run_camera.bat` - uruchamia szybki start z kamery `--camera 0 --display`.
- `scripts/run_ros2_camera_xyz.bat` - uruchamia ROS2 z kamery fizycznej, śledzi najjaśniejszą plamkę i publikuje `x/y/x_world/y_world/z_world`.

Skrypty `run_cli` i `run_camera` automatycznie dodają `--calib_file camera_calib.npz`, jeśli plik kalibracji istnieje w katalogu repozytorium.
Wszystkie skrypty startowe zakładają uruchamianie bezpośrednio z checkoutu repo i nie wymagają osobnej instalacji editable pakietów workspace.
Skrypt `run_ros2_camera_xyz.sh` dodatkowo wymaga aktywnego środowiska ROS2 (`rclpy`, `std_msgs`) oraz pliku kalibracji. Referencje PnP są domyślnie liczone automatycznie z `images_calib/` dla planszy `10x7`, a zmienne `LUCA_PNP_OBJECT_POINTS` i `LUCA_PNP_IMAGE_POINTS` służą do ręcznego nadpisania tego fallbacku.
W Windows odpowiednik korzysta z `LUCA_ROS2_SETUP_BAT` i `LUCA_ROS2_OVERLAY_SETUP_BAT`, jeśli chcesz automatycznie wykonać `call` do skryptów środowiska ROS2 przed startem.

## Artefakty wynikowe

Domyślnie wyniki trafiają do `output/<timestamp>/`.

Typowe artefakty:

- CSV z trajektorią,
- CSV z raportem,
- PDF z raportem,
- PNG z wykresem trajektorii,
- MP4 z naniesioną trajektorią dla wejścia plikowego.

Skrypty z katalogu `scripts/` zapisują wyniki do `output/manual/`.

Możesz nadpisać katalog wynikowy zmienną `LUCA_OUTPUT_DIR`.

Przy kamerze na żywo zakończenie analizy następuje przez `q` w oknie podglądu albo przerwanie procesu w terminalu. Eksport `--annotated_video` jest obsługiwany tylko dla wejścia plikowego.

## Narzędzia dodatkowe

Ekstrakcja obrazów do kalibracji:

```bash
python tools/extract_calibration_images.py video/kalibracja.mp4
```

QA i normalizacja wideo:

```bash
python tools/video_tool.py --input video/sledzenie_plamki.mp4 --analyze-only
```

Wykresy porównawcze z wielu CSV:

```bash
python tools/data_tool.py output/a.csv output/b.csv --x-col frame --y-cols x y speed
```

## Docker

Budowanie obrazu:

```bash
docker build -t alf-luca .
```

Uruchomienie (domyślnie pokazuje pomoc CLI):

```bash
docker run --rm -it alf-luca
```

Uruchomienie konkretnej podkomendy (np. `track`):

```bash
docker run --rm -it alf-luca track --help
```

## Wyniki i artefakty

Programy mogą generować m.in.:

- CSV z trajektorią (`--output_csv`),
- CSV ze statystykami (`--report_csv`),
- PDF z raportem (`--report_pdf`),
- PNG wykresu trajektorii (`--trajectory_png`),
- MP4 z naniesionymi trajektoriami (`--annotated_video`),
- JSON z analizą jakości MP4/MKV (`--report-json`).

## Uwagi

- Dla stabilniejszych wyników śledzenia warto użyć kalibracji kamery (`--calib_file`).
- Tryb wieloobiektowy (`--multi_track`) pozwala śledzić wiele plamek i wybrać główną trajektorię (`--selection_mode`).
- Narzędzie `video_tool.py` działa niezależnie od głównego pipeline'u śledzenia i może być używane osobno.
- Dla detektora jasności:
  - `threshold_mode=fixed` wybieraj przy stabilnym oświetleniu i wysokim kontraście plamki względem tła (najprostszy i zwykle najszybszy wariant),
  - `threshold_mode=adaptive` wybieraj przy nierównomiernym świetle, cieniach albo gradientach jasności; w trudnych scenach warto dodatkowo włączyć `--use_clahe`,
  - `threshold_mode=otsu` traktuj jako szybki punkt startowy, gdy nie znasz dobrego progu stałego.
- Opcjonalne profile detekcji (`--detector_profile`) pozwalają szybko przełączać zestawy parametrów:
  - stabilny `bright_default`,
  - eksperymentalne `bright_low_light_exp` i `color_robust_exp` (wymagają `--enable_experimental_profiles`).
- Przełączniki use-case trackingu:
  - `--experimental_mode`,
  - `--experimental_adaptive_association`,
  służą do R&D i zawsze powinny być walidowane benchmarkiem względem baseline.

## Benchmark jakości „przed/po” zmianach (lekki framework ewaluacyjny)

Dodano lekki benchmark uruchamiający istniejący pipeline na **stałych konfiguracjach**,
bez trenowania modeli i bez generowania ciężkich artefaktów (PDF/MP4).

### Struktura scenariuszy

- Manifest scenariuszy: `video/scenarios/scenarios.json`
- Opis scenariuszy i zasad rozbudowy: `video/scenarios/README.md`
- Krótka karta przypadków testowych: `video/scenarios/cases.md`

Scenariusze obejmują m.in. przypadki:

- refleksów,
- migotania,
- tła dynamicznego.

Stałe konfiguracje benchmarku są raportowane z podziałem na:

- tryb `brightest` (technicznie `track_mode=brightness`) z profilami progowania `fixed` i `adaptive`,
- tryb `color` (technicznie `track_mode=color`) z profilem `otsu`.
- warianty eksperymentalne `brightest_low_light_exp` oraz `color_robust_exp`, gdzie każda konfiguracja ma jawnie przypisany `baseline_config_name`.

Wynik CSV zawiera kolumnę `baseline_config_name`, aby dla każdego trybu eksperymentalnego było jasne,
z którym baseline należy porównywać wyniki.

### Uruchomienie benchmarku

```bash
python tools/quality_benchmark.py \
  --scenarios video/scenarios/scenarios.json \
  --output-dir output/quality_benchmark \
  --label before_changes \
  --baseline-version v1
```

Po wdrożeniu zmian uruchom ponownie z inną etykietą:

```bash
python tools/quality_benchmark.py \
  --scenarios video/scenarios/scenarios.json \
  --output-dir output/quality_benchmark \
  --label after_changes \
  --baseline-version v1
```

Aby dostać raport z różnicami „przed/po”, podaj CSV z uruchomienia bazowego:

```bash
python tools/quality_benchmark.py \
  --scenarios video/scenarios/scenarios.json \
  --output-dir output/quality_benchmark \
  --label after_changes \
  --baseline-csv output/quality_benchmark/<run_before>/benchmark_summary.csv
```

### Jakie metryki są liczone

- `position_error_2d_mean_px` / `position_error_2d_p95_px` — błąd pozycji 2D względem ground truth (jeśli dostępne),
- `point_precision_mean_px` / `point_precision_p95_px` — precyzja punktu względem ground truth (metryka błędu; niżej = lepiej),
- `trajectory_jitter_p95_px` — jitter toru (P95 skoku pozycji między kolejnymi detekcjami),
- `lost_frames` — liczba utraconych klatek (bez detekcji celu głównego),
- `lost_tracks_total` — liczba utraconych fragmentów toru (fragmentacja poza torem głównym),
- `false_positives_total` — liczba false positives w torach niegłównych,
- `false_detections_per_frame` — proxy fałszywych detekcji/klatkę (niżej = lepiej),
- `stable_track_len_frames` — długość najdłuższego stabilnego fragmentu toru (wyżej = lepiej),
- `track_id_switches` — liczba przełączeń dominującego `track_id` (niżej = lepiej),
- `fps` — wydajność przetwarzania benchmarku (wyżej = lepiej),
- `fps_stability_ratio` — relacja `processing_fps / source_fps` (blisko lub powyżej `1.0` = stabilnie).

### Profile progów „must-pass”

Plik `video/scenarios/threshold_profiles.json` zawiera profile zmian (w tym gate P0):

- `detection_algorithm` — najbardziej restrykcyjny profil dla zmian detektora,
- `tracking_filters` — średnio restrykcyjny profil dla trackerów i filtracji temporalnej,
- `interface_only` — profil łagodny dla zmian interfejsu (CLI/GUI/docs).
- `p0_regression_gate` — profil blokujący merge przy regresji P0 (precision/jitter/lost/false positives/FPS).

### Kryteria promocji trybu eksperymentalnego do stabilnego

Rekomendowany minimalny checklist (co najmniej 3 kolejne uruchomienia benchmarku):

1. brak naruszeń `blocking` dla profilu `p0_regression_gate`,
2. `false_detections_per_frame` i `trajectory_jitter_p95_px` nie gorsze od baseline (delta <= 0),
3. `lost_frames` nie rośnie względem baseline o więcej niż 3 klatki na scenariusz,
4. `fps_stability_ratio >= 0.92`,
5. opisane ograniczenia i zakres użycia zostały dodane do dokumentacji użytkowej.

Przykład uruchomienia z profilem i twardym wymuszeniem progów:

```bash
python tools/quality_benchmark.py \
  --scenarios video/scenarios/scenarios.json \
  --output-dir output/quality_benchmark \
  --label candidate_gate \
  --baseline-csv output/quality_benchmark/<run_before>/benchmark_summary.csv \
  --threshold-profile detection_algorithm \
  --enforce-thresholds
```

### Artefakty benchmarku

Dla każdego uruchomienia tworzony jest katalog:

- `benchmark_summary.csv` — pełne zestawienie metryk,
- `benchmark_report.md` — krótki raport tabelaryczny,
- `baseline_vs_candidate.md` — raport różnic kandydat vs baseline + lista naruszeń must-pass,
- `benchmark_delta.csv` — tabela różnic (`delta`) względem baseline gotowa do analizy CI,
- podkatalogi z `main_track.csv` i `all_tracks.csv` dla każdej pary (scenariusz, konfiguracja).

### Integracja z CI

Workflow `.github/workflows/quality-benchmark.yml` wykonuje:

1. **Job informacyjny dla PR**: pełny zestaw scenariuszy z `video/scenarios/scenarios.json` + porównanie do baseline.
2. **Job blokujący dla PR** (tylko przy zmianach w `packages/luca-processing/**` lub `packages/luca-tracking/**`): uruchomienie z profilem `p0_regression_gate` i `--enforce-thresholds`.
3. **Job nocny** (`schedule`) dla pełnego benchmarku wszystkich scenariuszy.

### Interpretacja „przed/po”

1. Porównuj te same scenariusze i te same konfiguracje między uruchomieniami.
2. Szukaj trendów:
   - spadek `false_detections_per_frame`,
   - wzrost `stable_track_len_frames`,
   - spadek `track_id_switches`.
3. `position_error_2d_*` analizuj razem z `lost_frames`:
   - niski błąd 2D i niski `lost_frames` zwykle oznaczają stabilny tor,
   - jeśli `lost_frames` rośnie przy stałym FPS, to zwykle problem dotyczy detekcji/progowania.

## Docker na GitHub Actions (GHCR)

Repozytorium ma workflow CI, który buduje obraz Dockera i publikuje go do GitHub Container Registry (`ghcr.io`) dla pushy do gałęzi `main`/`master` oraz tagów `v*`.

- plik workflow: `.github/workflows/docker.yml`,
- obraz: `ghcr.io/<owner>/alf-luca`,
- dla Pull Request wykonywany jest tylko build (bez push),
- dla default branch automatycznie dodawany jest tag `latest`.

Przykład uruchomienia obrazu:

```bash
docker run --rm ghcr.io/<owner>/alf-luca --help
```

## Jeśli chcesz X, uruchom Y

| Jeśli chcesz... | Uruchom... | Po co / co dostaniesz |
|---|---|---|
| szybko sprawdzić dostępne komendy | `python -m luca_tracker --help` | listę wszystkich trybów pracy CLI |
| zrobić tracking offline z pliku wideo | `python -m luca_tracker track --video video/sledzenie_plamki.mp4` | CSV, raporty i trajektorię z analizy materiału |
| zrobić szybki start offline gotowym skryptem | `bash scripts/run_cli.sh` lub `scripts\run_cli.bat` | przykładowe uruchomienie z zapisaniem wyników do `output/manual/` |
| uruchomić GUI do strojenia parametrów | `python -m luca_tracker gui` | interfejs do podglądu i eksperymentów z parametrami |
| uruchomić GUI gotowym skryptem | `bash scripts/run_gui.sh` lub `scripts\run_gui.bat` | GUI z domyślnym wyborem pliku i opcjonalnym `camera_calib.npz` |
| śledzić plamkę z kamery na żywo | `python -m luca_tracker track --camera 0 --display` | bieżący podgląd OpenCV i wynik live |
| uruchomić szybki start z kamery gotowym skryptem | `scripts\run_camera.bat` | prosty start live na Windows |
| opublikować pozycję plamki online do ROS2 | `python -m luca_tracker ros2 --camera_index 0 --topic /luca_tracker/tracking` | strumień JSON na topicu ROS2 |
| opublikować również `XYZ` z gotowym fallbackiem PnP | `bash scripts/run_ros2_camera_xyz.sh` lub `scripts\run_ros2_camera_xyz.bat` | ROS2 + automatyczne liczenie referencji PnP z `images_calib/` |
| porównać dwa wyniki CSV | `python -m luca_tracker compare --reference a.csv --candidate b.csv --output_csv diff.csv` | różnice między dwoma przebiegami |
| wygenerować wykresy z kilku CSV | `python tools/data_tool.py output/a.csv output/b.csv --x-col frame --y-cols x y speed` | porównawcze wykresy PNG do dalszej analizy |
| wyliczyć same referencje PnP z obrazów kalibracyjnych | `python scripts/compute_pnp_reference.py --format shell` | gotowe zmienne `LUCA_PNP_OBJECT_POINTS` i `LUCA_PNP_IMAGE_POINTS` |
| zrobić kalibrację kamery od zera | `python -m luca_tracker calibrate --calib_dir images_calib --rows 7 --cols 10 --square_size 1.0 --output_file camera_calib.npz` | plik `camera_calib.npz` do korekcji i rekonstrukcji geometrii |

## Quick troubleshooting (Linux/macOS vs Windows)

### Linux/macOS (`.sh`)

- **Brak ROS2 (`rclpy`) przy `run_ros2_camera_xyz.sh`**
  - Objaw: `[LUCA][ERROR] Brak ROS2 runtime (modul rclpy).`
  - Kroki: doinstaluj ROS2 + `rclpy`, a następnie załaduj `setup.bash` (`LUCA_ROS2_SETUP_FILE` lub `/opt/ros/<distro>/setup.bash`).
- **Brak kamery**
  - Objaw: `[LUCA][ERROR] Brak dostepu do kamery (index=...)`.
  - Kroki: sprawdź uprawnienia do `/dev/video*`, popraw `LUCA_CAMERA_INDEX`, zamknij aplikacje blokujące kamerę.
- **Brak referencji PnP dla XYZ**
  - Objaw: `[LUCA][ERROR] Nie udalo sie automatycznie wyliczyc referencji PnP.`
  - Kroki: popraw dane w `images_calib/` albo ustaw `LUCA_PNP_OBJECT_POINTS` i `LUCA_PNP_IMAGE_POINTS` ręcznie.
- **Brak backendu GUI**
  - Objaw: `[LUCA][ERROR] Brak backendu GUI (Kivy).`
  - Kroki: doinstaluj zależności GUI i sprawdź dostępność serwera wyświetlania (X11/Wayland).

### Windows (`.bat`)

- **Brak ROS2 (`rclpy`) przy `run_ros2_camera_xyz.bat`**
  - Objaw: `[LUCA][ERROR] Brak ROS2 runtime (modul rclpy).`
  - Kroki: zainstaluj ROS2 dla Windows i uruchom skrypt po `local_setup.bat` (`LUCA_ROS2_SETUP_BAT`).
- **Brak kamery**
  - Objaw: `[LUCA][ERROR] Brak dostepu do kamery (index=...)`.
  - Kroki: sprawdź numer kamery, prawa dostępu oraz konflikt z inną aplikacją (Teams/Zoom/OBS).
- **Brak referencji PnP dla XYZ**
  - Objaw: `[LUCA][ERROR] Nie udalo sie automatycznie wyliczyc referencji PnP.`
  - Kroki: zweryfikuj `images_calib\` lub podaj `LUCA_PNP_OBJECT_POINTS` + `LUCA_PNP_IMAGE_POINTS`.
- **Brak backendu GUI**
  - Objaw: `[LUCA][ERROR] Brak backendu GUI (Kivy).`
  - Kroki: doinstaluj pakiety GUI i uruchamiaj skrypt w sesji z dostępem do pulpitu.

### Wspólny format logów, błędów i kodów zakończenia launcherów

Launchery `scripts/*.sh` i `scripts/*.bat` używają wspólnego formatu:

- start: `[LUCA][START] mode=<...> ...`
- informacje: `[LUCA][INFO] ...`
- błędy: `[LUCA][ERROR] ...`
- koniec: `[LUCA][END] mode=<...> exit_code=<...>`

Dla scenariuszy `ROS2`, kamera, auto-PnP i GUI backend utrzymujemy też wspólne komunikaty błędów po obu stronach (`.sh`/`.bat`), żeby diagnoza była powtarzalna niezależnie od systemu.

Najważniejsze kody zakończenia:

- `21` - brak ROS2 runtime,
- `22` - brak dostępu do kamery,
- `23` - brak danych PnP dla XYZ,
- `24` - brak backendu GUI (Kivy),
- `127` - brak interpretera Pythona.

### Smoke-check zgodności launcherów `.sh` vs `.bat`

Szybka walidacja statyczna spójności między parami launcherów:

```bash
python tools/check_script_argument_parity.py
```

Skrypt porównuje:

- flagi CLI `--...`,
- domyślne wartości runtime (m.in. ROS2 + auto-PnP),
- obecność wspólnego formatu logu startowego i kluczowych komunikatów błędów.

Walidacja dotyczy par:

- `run_cli.sh` vs `run_cli.bat`,
- `run_gui.sh` vs `run_gui.bat`,
- `run_ros2_camera_xyz.sh` vs `run_ros2_camera_xyz.bat`.
