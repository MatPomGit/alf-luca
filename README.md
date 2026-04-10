# alf-luca

Narzędzia do kalibracji kamery, śledzenia plamki światła oraz analizy wyników z pliku wideo albo kamery na żywo.

## Autor

J2S

## Struktura repozytorium

- `luca_tracker/` - główny pakiet aplikacji z CLI, pipeline, GUI, raportami i ROS2.
- `tools/` - skrypty pomocnicze do analizy CSV, QA wideo i ekstrakcji obrazów kalibracyjnych.
- `scripts/` - gotowe skrypty uruchomieniowe.
- `config/` - konfiguracja GUI i przykładowa konfiguracja pełnego uruchomienia.
- `video/` - przykładowe pliki wejściowe.
- `images_calib/` - obrazy szachownicy do kalibracji.
- `Dockerfile` - obraz środowiska uruchomieniowego.

## Wymagania

- Python 3.10+
- pakiety z `requirements.txt`
- opcjonalnie `ffmpeg` i `ffprobe` dla `tools/video_tool.py`

Instalacja:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

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
  --rows 6 \
  --cols 9 \
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
  --calib_file camera_calib.npz \
  --pnp_object_points "0,0,0;1,0,0;1,1,0;0,1,0" \
  --pnp_image_points "120,210;520,205;525,470;115,475" \
  --pnp_world_plane_z 0.0 \
  --fps 30 \
  --display
```

Publikowany JSON na topicu zawiera m.in. pola:
- `spot_id`, `detected`, `x`, `y` (współrzędne ekranowe),
- `x_world`, `y_world`, `z_world` (współrzędne 3D),
- `frame_index`, `time_sec`, `detections_count`.

### 7) Gotowe skrypty startowe (Linux/macOS)

```bash
bash scripts/run_gui.sh
bash scripts/run_cli.sh
bash scripts/run_analysis.sh
```

### 8) Gotowe skrypty startowe (Windows)

```bat
scripts\run_gui.bat
scripts\run_cli.bat
scripts\run_camera.bat
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
  --rows 6 \
  --cols 9 \
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
- `scripts/run_analysis.sh` - porównanie danych CSV z `output/manual/`.

Windows:

- `scripts/run_gui.bat` - uruchamia GUI.
- `scripts/run_cli.bat` - uruchamia analizę przykładowego pliku `video/sledzenie_plamki.mkv`.
- `scripts/run_camera.bat` - uruchamia szybki start z kamery `--camera 0 --display`.

Skrypty `run_cli` i `run_camera` automatycznie dodają `--calib_file camera_calib.npz`, jeśli plik kalibracji istnieje w katalogu repozytorium.

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

Uruchomienie:

```bash
docker run --rm -it alf-luca
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
