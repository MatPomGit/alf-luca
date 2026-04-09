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

### 1a. Wyodrębnianie zdjęć do kalibracji z wideo (`extract_calibration_images.py`)

Skrypt `tools/extract_calibration_images.py` automatycznie:

1. czyta plik `.mp4` lub `.mkv`,
2. wykrywa klatki z tablicą szachownicy,
3. wybiera możliwie zróżnicowane i ostre ujęcia,
4. zapisuje gotowe obrazy PNG do katalogu kalibracyjnego.

#### Podstawowe użycie

```bash
python tools/extract_calibration_images.py video/kalibracja.mp4
```

Domyślnie obrazy trafią do `./images_calib`, a liczba zapisanych klatek to `25`.

#### Przykład z własnym katalogiem i liczbą zdjęć

```bash
python tools/extract_calibration_images.py video/kalibracja.mkv \
  --output-dir ./images_calib_custom \
  --count 40
```

#### Przykład dla innego wzorca szachownicy

```bash
python tools/extract_calibration_images.py video/kalibracja.mp4 \
  --pattern-cols 10 \
  --pattern-rows 7 \
  --sample-step 2
```

- `--pattern-cols` i `--pattern-rows` oznaczają liczbę **wewnętrznych** narożników szachownicy.
- `--sample-step` określa, co ile klatek wykonywana jest detekcja (mniejsza wartość = dokładniej, ale wolniej).

#### Gotowy workflow: od wideo do pliku kalibracji

```bash
# 1) Wytnij obrazy kalibracyjne z nagrania szachownicy
python tools/extract_calibration_images.py video/kalibracja.mp4 \
  --output-dir ./images_calib \
  --count 30 \
  --pattern-cols 9 \
  --pattern-rows 6

# 2) Na podstawie obrazów policz kalibrację kamery
python track_luca.py calibrate \
  --calib_dir ./images_calib \
  --rows 6 \
  --cols 9 \
  --square_size 1.0 \
  --output_file camera_calib.npz

# 3) Użyj kalibracji podczas śledzenia
python track_luca.py track \
  --video video/sledzenie_plamki.mp4 \
  --track_mode brightness \
  --calib_file camera_calib.npz \
  --output_csv output/tracking_with_calib.csv \
  --trajectory_png output/trajectory_with_calib.png
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

### 2a. Więcej gotowych przykładów śledzenia (kopiuj-wklej)

#### Śledzenie z ROI i zakresem klatek

```bash
python track_luca.py track \
  --video video/sledzenie_plamki.mp4 \
  --track_mode brightness \
  --roi 220,120,900,650 \
  --start_frame 0 \
  --end_frame 1200 \
  --output_csv output/tracking_roi.csv \
  --trajectory_png output/trajectory_roi.png
```

#### Śledzenie wieloobiektowe z wyborem trajektorii głównej

```bash
python track_luca.py track \
  --video video/sledzenie_plamki.mp4 \
  --multi_track \
  --selection_mode longest \
  --output_csv output/tracking_multi.csv \
  --annotated_video output/tracking_multi.mp4 \
  --report_csv output/tracking_multi_report.csv
```

#### Śledzenie z kalibracją + raport PDF

```bash
python track_luca.py track \
  --video video/sledzenie_plamki.mp4 \
  --track_mode brightness \
  --calib_file camera_calib.npz \
  --output_csv output/tracking_calib.csv \
  --report_csv output/tracking_calib_report.csv \
  --report_pdf output/tracking_calib_report.pdf
```

### 2b. Pełny proces end-to-end: od wideo do porównania wyników

Poniżej znajdziesz kompletne, gotowe scenariusze do uruchomienia „krok po kroku”.
Każdy wariant obejmuje:

1. wczytanie pliku wideo,
2. śledzenie punktu/plamki,
3. eksport wyników,
4. ponowne wczytanie wyników i ich porównanie.

> Przykłady zakładają, że pracujesz z katalogu głównego repozytorium.

#### Wariant A — podstawowy (bez zapisu wideo z nałożeniem)

```bash
# 1) Pomiar referencyjny
python track_luca.py track \
  --video video/sledzenie_plamki.mp4 \
  --track_mode brightness \
  --output_csv output/luca_regal_ref.csv \
  --trajectory_png output/luca_regal_ref.png \
  --report_csv output/luca_regal_ref_report.csv \
  --report_pdf output/luca_regal_ref_report.pdf

# 2) Pomiar porównawczy (inne parametry detekcji)
python track_luca.py track \
  --video video/sledzenie_plamki.mp4 \
  --track_mode brightness \
  --threshold 185 \
  --blur 9 \
  --min_area 8 \
  --output_csv output/sledzenie_plamki_test.csv \
  --trajectory_png output/sledzenie_plamki_test.png \
  --report_csv output/sledzenie_plamki_test_report.csv \
  --report_pdf output/sledzenie_plamki_test_report.pdf

# 3) Porównanie dwóch wyników CSV
python track_luca.py compare \
  --reference output/sledzenie_plamki_ref.csv \
  --candidate output/sledzenie_plamki_test.csv \
  --output_csv output/sledzenie_plamki_diff.csv \
  --report_pdf output/sledzenie_plamki_diff_report.pdf
```

#### Wariant B — z dodatkowym zapisem wideo z nałożonym śledzonym punktem

```bash
# 1) Pomiar referencyjny + wideo z nałożoną trajektorią
python track_luca.py track \
  --video video/sledzenie_plamki.mp4 \
  --track_mode brightness \
  --multi_track \
  --selection_mode longest \
  --output_csv output/sledzenie_ref.csv \
  --all_tracks_csv output/sledzenie_ref_all_tracks.csv \
  --annotated_video output/sledzenie_ref_annotated.mp4 \
  --trajectory_png output/sledzenie_ref_traj.png \
  --report_csv output/sledzenie_ref_report.csv

# 2) Pomiar porównawczy + druga wersja filmu wynikowego
python track_luca.py track \
  --video video/sledzenie_plamki.mp4 \
  --track_mode brightness \
  --multi_track \
  --selection_mode stablest \
  --max_distance 30 \
  --max_missed 6 \
  --output_csv output/sledzenie_test.csv \
  --all_tracks_csv output/sledzenie_test_all_tracks.csv \
  --annotated_video output/sledzenie_test_annotated.mp4 \
  --trajectory_png output/sledzenie_test_traj.png \
  --report_csv output/sledzenie_test_report.csv

# 3) Porównanie wyników CSV
python track_luca.py compare \
  --reference output/sledzenie_ref.csv \
  --candidate output/sledzenie_test.csv \
  --output_csv output/sledzenie_diff.csv \
  --report_pdf output/sledzenie_diff_report.pdf
```

#### Wariant C — z kalibracją kamery + porównanie (bez zapisu wideo)

```bash
# 0) (Jednorazowo) kalibracja kamery
python track_luca.py calibrate \
  --calib_dir ./images_calib \
  --rows 7 \
  --cols 10 \
  --square_size 1.0 \
  --output_file camera_calib.npz

# 1) Pomiar referencyjny z kalibracją
python track_luca.py track \
  --video video/regal_plamka.mp4 \
  --track_mode brightness \
  --calib_file camera_calib.npz \
  --output_csv output/regal_ref_calib.csv \
  --trajectory_png output/regal_ref_calib.png

# 2) Pomiar porównawczy z kalibracją i innym ROI
python track_luca.py track \
  --video video/regal_plamka.mp4 \
  --track_mode brightness \
  --calib_file camera_calib.npz \
  --roi 150,100,950,700 \
  --output_csv output/regal_test_calib.csv \
  --trajectory_png output/regal_test_calib.png

# 3) Porównanie trajektorii po kalibracji
python track_luca.py compare \
  --reference output/regal_ref_calib.csv \
  --candidate output/regal_test_calib.csv \
  --output_csv output/regal_calib_diff.csv
```

#### Dodatkowy krok: szybkie porównanie większej liczby pomiarów i wykresów

Po wygenerowaniu kilku CSV możesz od razu zestawić je na wykresach:

```bash
python tools/data.py \
  output/luca_regal_ref.csv \
  output/luca_regal_test.csv \
  output/sledzenie_ref.csv \
  --x-col frame \
  --y-cols x y speed \
  --output-dir output/compare_plots
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
  --input sledzenie_plamki.mp4 \
  --analyze-only \
  --report-json report_mp4.json
```

### 5. Naprawa/normalizacja MP4/MKV z ustawieniem bitrate i FPS

```bash
python tools/video_tool.py \
  --input sledzenie_plamki.mp4 \
  --output film_fixed.mp4 \
  --target-bitrate 2500k \
  --target-fps 30 \
  --crf 22 \
  --preset medium
```

### 6. Usunięcie dźwięku z pliku MP4/MKV

```bash
python tools/video_tool.py \
  --input sledzenie_plamki.mp4 \
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

### 8. Gotowe przykłady poleceń QA wideo (kopiuj-wklej)

#### Szybka analiza kilku plików pod rząd (Linux/macOS)

```bash
python tools/video_tool.py --input video/luca_regal.mp4 --analyze-only --report-json output/qa_luca_regal.json
python tools/video_tool.py --input video/regal_plamka.mp4 --analyze-only --report-json output/qa_regal_plamka.json
python tools/video_tool.py --input video/sledzenie_plamki.mp4 --analyze-only --report-json output/qa_sledzenie_plamki.json
```

#### Normalizacja materiału przed śledzeniem

```bash
python tools/video_tool.py \
  --input video/sledzenie_plamki.mkv \
  --output output/sledzenie_plamki_fixed.mp4 \
  --target-bitrate 3000k \
  --target-fps 30 \
  --crf 21 \
  --preset medium
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
