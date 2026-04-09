# alf-luca

Narzędzia do analizy materiałów wideo (MP4/MKV/AVI/MOV/M4V/WEBM), kalibracji kamery i śledzenia plamki światła w nagraniach.

## Zawartość repozytorium

- `track_luca.py` — główny program CLI z trybami:
  - `calibrate` (kalibracja kamery),
  - `track` (śledzenie plamki),
  - `compare` (porównanie CSV),
  - `gui` (interaktywne strojenie parametrów).
- `kalman_tracker.py` — moduł filtru Kalmana do wygładzania trajektorii.
- `tools/video_tool.py` — narzędzie do weryfikacji jakości MP4/MKV i opcjonalnej naprawy/normalizacji.
- `config/` — pliki konfiguracyjne i przykładowe dane kalibracyjne.
  - `config/gui_display.yaml` — domyślne wartości suwaków i stanu okna trybu `gui`.

## Wymagania

Python 3.10+ oraz biblioteki:

```bash
pip install opencv-python numpy matplotlib kivy
python3 -m pip install --upgrade pip

sudo apt-get update
sudo apt-get install libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev libfreetype6-dev libportmidi-dev libjpeg-dev python3-setuptools python3-dev

sudo dnf install SDL2-devel SDL2_image-devel SDL2_mixer-devel SDL2_ttf-devel portmidi-devel
python3 -m pip install --upgrade pip

pip install pygame
pip install ffmpeg ffprobe
```

Dla narzędzia QA wideo wymagane są dodatkowo binarki systemowe:

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
  --video luca_regal.mp4 \
  --track_mode brightness \
  --output_csv tracking_results.csv \
  --trajectory_png trajectory.png \
  --report_csv report.csv \
  --report_pdf report.pdf
```

### 3. GUI do strojenia parametrów

```bash
python track_luca.py gui
```

Na Windows możesz też uruchomić GUI przez dwuklik w plik `Uruchom_GUI.bat` (z katalogu repozytorium).
Na Linux (Ubuntu/Fedora) użyj `Uruchom_GUI.sh` (najpierw nadaj uprawnienia: `chmod +x Uruchom_GUI.sh`),
a następnie uruchom skrypt (np. dwuklik i opcja **Run**, zależnie od menedżera plików).

Możesz też uruchomić samo:

```bash
python track_luca.py
```

Wtedy program domyślnie przełączy się na tryb `gui` i spróbuje użyć pierwszego pliku `*.mp4`, `*.mkv`, `*.avi`, `*.mov`, `*.m4v` lub `*.webm` (najpierw z katalogu `video/`, potem z bieżącego katalogu).
Domyślne wartości suwaków GUI są ładowane z pliku `config/gui_display.yaml`.
Możesz też wskazać inny plik:

```bash
python track_luca.py gui --video luca_regal.mp4 --gui_config config/gui_display.yaml
```

GUI automatycznie wykrywa pliki wideo z folderu `video/` i pozwala przełączać je listą rozwijaną.
Wyniki analizy z GUI są zapisywane do folderu `output/` jako pliki `*_gui_analysis.csv`.
Wstępnie wybrany indeks pliku możesz ustawić przez `video_index` w `config/gui_display.yaml`.
Interfejs GUI (Kivy) pokazuje też panele statusu i podgląd przetworzonego obrazu, aby ułatwić pracę operatora.

### Nowe funkcjonalności GUI

- Okno aplikacji jest maksymalizowane przy starcie (jeśli wspiera to backend Kivy), a układ panelu dostosowuje się do zmiany rozmiaru okna.
- Dodano więcej przycisków akcji:
  - `Prev video` / `Next video` — szybkie przełączanie nagrania,
  - `Restart video` — restart od początku bieżącego materiału.
- Dodano pełny zestaw sterowania nagrywaniem/analityką:
  - `START` — start przetwarzania,
  - `PAUSE` — wstrzymanie,
  - `RESUME` — wznowienie,
  - `STOP` — zatrzymanie,
  - `QUIT` — zamknięcie aplikacji GUI.
- Działa nawigacja kółkiem myszy:
  - kółko bez `SHIFT` przełącza aktywne pole,
  - kółko z `SHIFT` zmienia wartość aktualnie wybranego pola.
- Działa nawigacja klawiszami strzałek:
  - `↑/↓` — wybór pól,
  - `←/→` — zmiana wartości pola.
- Dodatkowe skróty klawiszowe:
  - `Space` — szybkie przełączanie START/PAUSE/RESUME,
  - `S` — STOP,
  - `M` — wypisanie komendy do narzędzia QA wideo.

Wybór `Speed` pozwala przyśpieszyć odtwarzanie: `x1.25`, `x1.5`, `x2`, `x3`, `x5`, `x10`, `x20`.

W GUI wyświetlany jest odnośnik do narzędzia QA wideo (`tools/video_tool.py`).
Możesz też nacisnąć klawisz `m`, aby wypisać w konsoli gotową komendę uruchomienia narzędzia.

## Rozwiązywanie problemów

- Jeśli pojawiał się błąd:
  `ImportError: cannot import name 'parse_roi' from partially initialized module ...`
  był on związany z cyklicznym importem między modułami `tracking` i `video_export`.
  W aktualnej wersji repo problem został usunięty.
- W razie problemów z uruchomieniem sprawdź:
  1) czy uruchamiasz skrypt z katalogu repo (`python track_luca.py ...`),
  2) czy masz zainstalowane wymagane biblioteki (`opencv-python`, `numpy`, `matplotlib`),
  3) czy używasz wspieranej wersji Python 3.10+.

### 4. Weryfikacja jakości MP4/MKV (bez modyfikacji pliku)

```bash
python tools/video_tool.py \
  --input luca_regal.mp4 \
  --analyze-only \
  --report-json report_mp4.json
```

### 5. Naprawa/normalizacja MP4/MKV z ustawieniem bitrate i FPS

```bash
python tools/video_tool.py \
  --input luca_regal.mp4 \
  --output film_fixed.mp4 \
  --target-bitrate 2500k \
  --target-fps 30 \
  --crf 22 \
  --preset medium
```

### 6. Usunięcie dźwięku z pliku MP4/MKV

```bash
python tools/video_tool.py \
  --input luca_regal.mp4 \
  --output film_no_audio.mp4 \
  --remove-audio
```

### 7. Porównanie wielu plików pomiarowych i wykresy

```bash
python tools/data.py \
  output/tracking_results.csv \
  output/inny_pomiar.csv \
  --x-col frame \
  --y-cols x y speed \
  --output-dir output/compare_plots
```

Skrypt zapisuje wykresy porównawcze i różnicowe (`*.png`) dla wybranych kolumn.

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
