# alf-luca

Narzędzia do kalibracji kamery, śledzenia plamki światła w nagraniach oraz analizy wyników.

## Struktura repozytorium

- `luca_tracker/` - główny pakiet aplikacji z CLI, pipeline, GUI i raportami.
- `tools/` - pomocnicze skrypty do analizy danych, QA wideo i ekstrakcji obrazów kalibracyjnych.
- `scripts/` - gotowe skrypty uruchomieniowe dla Linux/macOS i Windows.
- `config/` - konfiguracje GUI oraz przykładowa konfiguracja pełnego runu.
- `video/` - przykładowe materiały wejściowe.
- `images_calib/` - obrazy szachownicy do kalibracji kamery.
- `track_luca.py` - historyczny wrapper CLI zachowany dla zgodności.
- `kalman_tracker.py` - historyczny wrapper importu zachowany dla zgodności.
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

## Uruchamianie

Preferowane uruchomienie:

```bash
python -m luca_tracker --help
```

Historyczny entrypoint nadal działa:

```bash
python track_luca.py --help
```

Kalibracja kamery:

```bash
python -m luca_tracker calibrate \
  --calib_dir images_calib \
  --rows 6 \
  --cols 9 \
  --square_size 1.0 \
  --output_file camera_calib.npz
```

Śledzenie plamki:

```bash
python -m luca_tracker track \
  --video video/sledzenie_plamki.mp4 \
  --track_mode brightness
```

GUI:

```bash
python -m luca_tracker gui
```

Porównanie dwóch pomiarów:

```bash
python -m luca_tracker compare \
  --reference output/ref.csv \
  --candidate output/test.csv \
  --output_csv output/diff.csv
```

## Konfiguracja

Pełny run można opisać plikiem YAML lub JSON:

```bash
python -m luca_tracker track --config config/run_tracking.sample.yaml
```

W repo znajdują się:

- `config/gui_display.yaml` - domyślne ustawienia GUI.
- `config/run_tracking.sample.yaml` - przykładowa konfiguracja pełnego uruchomienia trackera.

## Skrypty pomocnicze

- `scripts/run_gui.sh` - uruchamia GUI na Linux/macOS.
- `scripts/run_gui.bat` - uruchamia GUI na Windows.
- `scripts/run_cli.sh` - przykładowe uruchomienie `track` z wynikami w `output/manual/`.
- `scripts/run_analysis.sh` - porównanie danych przez `tools/data.py` w `output/manual/`.

## Artefakty wynikowe

Domyślnie wyniki trafiają do katalogu `output/` w podfolderze z timestampem. Dotyczy to między innymi:

- CSV z trajektorią,
- CSV z raportem,
- PDF z raportem,
- PNG z wykresem trajektorii,
- MP4 z naniesioną trajektorią.

Możesz nadpisać katalog wynikowy zmienną środowiskową `LUCA_OUTPUT_DIR`.

Skrypty z katalogu `scripts/` zapisują dane do stabilnej lokalizacji `output/manual/`, żeby łatwiej było uruchamiać kolejne kroki robocze.

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
