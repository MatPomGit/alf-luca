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

### Uruchomienie benchmarku

```bash
python tools/quality_benchmark.py \
  --scenarios video/scenarios/scenarios.json \
  --output-dir output/quality_benchmark \
  --label before_changes
```

Po wdrożeniu zmian uruchom ponownie z inną etykietą:

```bash
python tools/quality_benchmark.py \
  --scenarios video/scenarios/scenarios.json \
  --output-dir output/quality_benchmark \
  --label after_changes
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

- `false_detections_per_frame` — proxy fałszywych detekcji/klatkę (niżej = lepiej),
- `stable_track_len_frames` — długość najdłuższego stabilnego fragmentu toru (wyżej = lepiej),
- `track_id_switches` — liczba przełączeń dominującego `track_id` (niżej = lepiej),
- `kalman_predicted_share` — udział klatek z `kalman_predicted=1` (wartość kontekstowa).

### Artefakty benchmarku

Dla każdego uruchomienia tworzony jest katalog:

- `benchmark_summary.csv` — pełne zestawienie metryk,
- `benchmark_report.md` — krótki raport tabelaryczny,
- podkatalogi z `main_track.csv` i `all_tracks.csv` dla każdej pary (scenariusz, konfiguracja).

### Interpretacja „przed/po”

1. Porównuj te same scenariusze i te same konfiguracje między uruchomieniami.
2. Szukaj trendów:
   - spadek `false_detections_per_frame`,
   - wzrost `stable_track_len_frames`,
   - spadek `track_id_switches`.
3. `kalman_predicted_share` interpretuj razem z pozostałymi metrykami:
   - wysoki udział predykcji może oznaczać lepszą ciągłość,
   - ale też może sygnalizować, że detektor zbyt często gubi obiekt.

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
