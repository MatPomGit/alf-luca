# alf-luca

Narzędzia do analizy materiałów wideo (MP4), kalibracji kamery i śledzenia plamki światła w nagraniach.

## Zawartość repozytorium

- `track_luca.py` — główny program CLI z trybami:
  - `calibrate` (kalibracja kamery),
  - `track` (śledzenie plamki),
  - `compare` (porównanie CSV),
  - `gui` (interaktywne strojenie parametrów).
- `kalman_tracker.py` — moduł filtru Kalmana do wygładzania trajektorii.
- `tools/video_tool.py` — narzędzie do weryfikacji jakości MP4 i opcjonalnej naprawy/normalizacji.
- `config/` — pliki konfiguracyjne i przykładowe dane kalibracyjne.

## Wymagania

Python 3.10+ oraz biblioteki:

```bash
pip install opencv-python numpy matplotlib
```

Dla narzędzia QA MP4 wymagane są dodatkowo binarki systemowe:

- `ffmpeg`
- `ffprobe`

## Szybki start

### 1. Kalibracja kamery

```bash
python track_luca.py calibrate \
  --calib_dir ./images_calib \
  --rows 6 \
  --cols 9 \
  --square_size 1.0 \
  --output_file camera_calib.npz
```

### 2. Śledzenie plamki (tryb klasyczny)

```bash
python track_luca.py track \
  --video film.mp4 \
  --track_mode brightness \
  --output_csv tracking_results.csv \
  --trajectory_png trajectory.png \
  --report_csv report.csv \
  --report_pdf report.pdf
```

### 3. GUI do strojenia parametrów

```bash
python track_luca.py gui --video film.mp4
```

W GUI wyświetlany jest odnośnik do narzędzia QA MP4 (`tools/video_tool.py`).
Możesz też nacisnąć klawisz `m`, aby wypisać w konsoli gotową komendę uruchomienia narzędzia.

### 4. Weryfikacja jakości MP4 (bez modyfikacji pliku)

```bash
python tools/video_tool.py \
  --input film.mp4 \
  --analyze-only \
  --report-json report_mp4.json
```

### 5. Naprawa/normalizacja MP4 z ustawieniem bitrate i FPS

```bash
python tools/video_tool.py \
  --input film.mp4 \
  --output film_fixed.mp4 \
  --target-bitrate 2500k \
  --target-fps 30 \
  --crf 22 \
  --preset medium
```

### 6. Usunięcie dźwięku z pliku MP4

```bash
python tools/video_tool.py \
  --input film.mp4 \
  --output film_no_audio.mp4 \
  --remove-audio
```

## Wyniki i artefakty

Programy mogą generować m.in.:

- CSV z trajektorią (`--output_csv`),
- CSV ze statystykami (`--report_csv`),
- PDF z raportem (`--report_pdf`),
- PNG wykresu trajektorii (`--trajectory_png`),
- MP4 z naniesionymi trajektoriami (`--annotated_video`),
- JSON z analizą jakości MP4 (`--report-json`).

## Uwagi

- Dla stabilniejszych wyników śledzenia warto użyć kalibracji kamery (`--calib_file`).
- Tryb wieloobiektowy (`--multi_track`) pozwala śledzić wiele plamek i wybrać główną trajektorię (`--selection_mode`).
- Narzędzie `video_tool.py` działa niezależnie od głównego pipeline'u śledzenia i może być używane osobno.
