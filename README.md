# alf-luca

Narzędzia do kalibracji kamery, śledzenia plamki światła oraz analizy wyników z pliku wideo albo kamery na żywo.

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
python tools/data.py output/a.csv output/b.csv --x-col frame --y-cols x y speed
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
