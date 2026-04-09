#!/usr/bin/env python3
"""
Narzędzie do weryfikacji jakości plików wideo i opcjonalnej naprawy.

Funkcje:
- odczyt metadanych przez ffprobe,
- analiza potencjalnych problemów technicznych,
- ponowne kodowanie (naprawa + normalizacja),
- dostosowanie bitrate i FPS,
- zapis raportu JSON.

Wymaga:
- ffmpeg
- ffprobe
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import threading
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


@dataclass
class Issue:
    level: str  # info | warning | error
    code: str
    message: str


@dataclass
class AnalysisResult:
    input_file: str
    format_name: Optional[str]
    duration_sec: Optional[float]
    size_bytes: Optional[int]
    video_codec: Optional[str]
    width: Optional[int]
    height: Optional[int]
    fps: Optional[float]
    video_bitrate_bps: Optional[int]
    audio_codec: Optional[str]
    audio_bitrate_bps: Optional[int]
    issues: List[Issue]


def run_cmd(cmd: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)


def ensure_binary(name: str) -> None:
    try:
        check = run_cmd([name, "-version"])
    except FileNotFoundError:
        print(f"[BŁĄD] Nie znaleziono polecenia '{name}' w PATH.", file=sys.stderr)
        sys.exit(2)
    if check.returncode != 0:
        print(f"[BŁĄD] Nie znaleziono polecenia '{name}' w PATH.", file=sys.stderr)
        sys.exit(2)


def parse_fraction(value: Optional[str]) -> Optional[float]:
    if not value or value == "0/0":
        return None
    if "/" in value:
        num, den = value.split("/", 1)
        try:
            n = float(num)
            d = float(den)
            return None if d == 0 else n / d
        except ValueError:
            return None
    try:
        return float(value)
    except ValueError:
        return None


def to_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def ffprobe_json(input_file: Path) -> Dict[str, Any]:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-of",
        "json",
        str(input_file),
    ]
    proc = run_cmd(cmd)
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe zwrócił błąd: {proc.stderr.strip()}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Nie udało się sparsować odpowiedzi ffprobe jako JSON.") from exc


ALLOWED_INPUT_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".m4v", ".webm"}
FASTSTART_EXTENSIONS = {".mp4", ".m4v", ".mov"}


def analyze_video(input_file: Path) -> AnalysisResult:
    # Funkcja analizuje metadane kontenera i strumieni dla wspieranych formatów.
    payload = ffprobe_json(input_file)
    streams = payload.get("streams", [])
    fmt = payload.get("format", {})

    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

    issues: List[Issue] = []

    format_name = fmt.get("format_name")
    duration_sec = to_float(fmt.get("duration"))
    size_bytes = to_int(fmt.get("size"))

    video_codec = video_stream.get("codec_name") if video_stream else None
    width = to_int(video_stream.get("width")) if video_stream else None
    height = to_int(video_stream.get("height")) if video_stream else None
    fps = parse_fraction(video_stream.get("avg_frame_rate")) if video_stream else None
    v_bitrate = to_int(video_stream.get("bit_rate")) if video_stream else None

    audio_codec = audio_stream.get("codec_name") if audio_stream else None
    a_bitrate = to_int(audio_stream.get("bit_rate")) if audio_stream else None

    if not input_file.exists():
        issues.append(Issue("error", "file_missing", "Plik wejściowy nie istnieje."))
    if input_file.suffix.lower() not in ALLOWED_INPUT_EXTENSIONS:
        issues.append(
            Issue(
                "warning",
                "unsupported_extension",
                "Rozszerzenie pliku nie jest wspierane (obsługiwane: .mp4, .mkv, .avi, .mov, .m4v, .webm).",
            )
        )
    if not video_stream:
        issues.append(Issue("error", "missing_video_stream", "Brak strumienia wideo."))
    if not audio_stream:
        issues.append(Issue("warning", "missing_audio_stream", "Brak strumienia audio."))

    if video_stream:
        if width is None or height is None:
            issues.append(Issue("error", "invalid_dimensions", "Nie udało się odczytać rozdzielczości wideo."))
        else:
            if width < 320 or height < 240:
                issues.append(Issue("warning", "low_resolution", f"Niska rozdzielczość: {width}x{height}."))
            if width % 2 != 0 or height % 2 != 0:
                issues.append(
                    Issue("warning", "odd_dimensions", "Nieparzyste wymiary mogą sprawiać problemy przy kodowaniu.")
                )

        if fps is None:
            issues.append(Issue("warning", "missing_fps", "Brak poprawnej informacji o FPS."))
        else:
            if fps < 15:
                issues.append(Issue("warning", "very_low_fps", f"Bardzo niski FPS: {fps:.3f}."))
            if fps > 120:
                issues.append(Issue("warning", "very_high_fps", f"Bardzo wysoki FPS: {fps:.3f}."))

        if v_bitrate is not None and v_bitrate < 400_000:
            issues.append(Issue("warning", "low_video_bitrate", f"Niski bitrate wideo: {v_bitrate} bps."))

        codec_tag = video_codec or "unknown"
        if codec_tag not in {"h264", "hevc", "mpeg4", "av1"}:
            issues.append(Issue("warning", "uncommon_video_codec", f"Nietypowy kodek wideo: {codec_tag}."))

    if duration_sec is None or duration_sec <= 0:
        issues.append(Issue("error", "invalid_duration", "Nieprawidłowa długość nagrania."))

    if format_name and not any(name in format_name for name in ("mp4", "matroska", "webm", "avi", "mov")):
        issues.append(
            Issue(
                "warning",
                "uncommon_container",
                f"Kontener to: {format_name} (oczekiwany MP4/MKV/AVI/MOV/WEBM).",
            )
        )

    return AnalysisResult(
        input_file=str(input_file),
        format_name=format_name,
        duration_sec=duration_sec,
        size_bytes=size_bytes,
        video_codec=video_codec,
        width=width,
        height=height,
        fps=fps,
        video_bitrate_bps=v_bitrate,
        audio_codec=audio_codec,
        audio_bitrate_bps=a_bitrate,
        issues=issues,
    )


def build_ffmpeg_command(
    input_file: Path,
    output_file: Path,
    target_bitrate: Optional[str],
    target_fps: Optional[float],
    crf: int,
    preset: str,
    audio_bitrate: str,
    remove_audio: bool,
) -> List[str]:
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_file),
        "-map",
        "0:v:0",
        "-c:v",
        "libx264",
        "-preset",
        preset,
        "-crf",
        str(crf),
        "-pix_fmt",
        "yuv420p",
        "-vf",
        "scale=trunc(iw/2)*2:trunc(ih/2)*2",
    ]

    if target_fps is not None:
        cmd += ["-r", f"{target_fps:g}"]

    if target_bitrate:
        cmd += ["-b:v", target_bitrate]

    if remove_audio:
        cmd += ["-an"]
    else:
        cmd += ["-map", "0:a?", "-c:a", "aac", "-b:a", audio_bitrate]

    # Flaga faststart ma sens głównie dla kontenerów opartych o ISO BMFF.
    if output_file.suffix.lower() in FASTSTART_EXTENSIONS:
        cmd += ["-movflags", "+faststart"]
    cmd += [str(output_file)]
    return cmd


def print_analysis(result: AnalysisResult) -> None:
    print("\n=== Analiza wideo (MP4/MKV/AVI/MOV/WEBM) ===")
    print(f"Plik: {result.input_file}")
    print(f"Kontener: {result.format_name}")
    print(f"Czas trwania: {result.duration_sec}")
    print(f"Rozmiar [B]: {result.size_bytes}")
    print(f"Wideo: codec={result.video_codec}, {result.width}x{result.height}, fps={result.fps}, bitrate={result.video_bitrate_bps}")
    print(f"Audio: codec={result.audio_codec}, bitrate={result.audio_bitrate_bps}")

    if not result.issues:
        print("[OK] Nie wykryto istotnych problemów.")
        return

    print("\nWykryte problemy:")
    for issue in result.issues:
        prefix = {"info": "[INFO]", "warning": "[WARN]", "error": "[ERR]"}.get(issue.level, "[?]")
        print(f"{prefix} {issue.code}: {issue.message}")


def save_report(path: Path, result: AnalysisResult) -> None:
    payload = asdict(result)
    payload["issues"] = [asdict(i) for i in result.issues]
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[OK] Zapisano raport JSON: {path}")


def format_analysis(result: AnalysisResult) -> str:
    lines = [
        "=== Analiza wideo (MP4/MKV/AVI/MOV/WEBM) ===",
        f"Plik: {result.input_file}",
        f"Kontener: {result.format_name}",
        f"Czas trwania: {result.duration_sec}",
        f"Rozmiar [B]: {result.size_bytes}",
        f"Wideo: codec={result.video_codec}, {result.width}x{result.height}, fps={result.fps}, bitrate={result.video_bitrate_bps}",
        f"Audio: codec={result.audio_codec}, bitrate={result.audio_bitrate_bps}",
    ]

    if not result.issues:
        lines.append("[OK] Nie wykryto istotnych problemów.")
    else:
        lines.append("")
        lines.append("Wykryte problemy:")
        for issue in result.issues:
            prefix = {"info": "[INFO]", "warning": "[WARN]", "error": "[ERR]"}.get(issue.level, "[?]")
            lines.append(f"{prefix} {issue.code}: {issue.message}")

    return "\n".join(lines)


class VideoToolGUI:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Video Tool - analiza i naprawa plików wideo")
        self.root.geometry("840x580")

        self.selected_file: Optional[Path] = None
        self.last_result: Optional[AnalysisResult] = None

        self.file_var = tk.StringVar(value="Nie wybrano pliku.")
        self.output_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Gotowe.")

        self._build_ui()

    def _build_ui(self) -> None:
        top = ttk.Frame(self.root, padding=12)
        top.pack(fill="x")
        ttk.Label(top, text="Plik wejściowy:").grid(row=0, column=0, sticky="w")
        ttk.Label(top, textvariable=self.file_var, width=80).grid(row=0, column=1, columnspan=4, sticky="w")

        btn_pick = ttk.Button(top, text="Wybierz plik wideo", command=self.pick_file)
        btn_pick.grid(row=1, column=0, pady=(8, 0), sticky="w")

        btn_analyze = ttk.Button(top, text="Analizuj", command=self.analyze_current_file)
        btn_analyze.grid(row=1, column=1, padx=8, pady=(8, 0), sticky="w")

        btn_report = ttk.Button(top, text="Zapisz raport JSON", command=self.save_report_from_gui)
        btn_report.grid(row=1, column=2, padx=8, pady=(8, 0), sticky="w")

        btn_repair = ttk.Button(top, text="Napraw / normalizuj", command=self.repair_current_file)
        btn_repair.grid(row=1, column=3, padx=8, pady=(8, 0), sticky="w")

        self.text = tk.Text(self.root, wrap="word", height=24)
        self.text.pack(fill="both", expand=True, padx=12, pady=12)

        status = ttk.Label(self.root, textvariable=self.status_var, relief="sunken", anchor="w")
        status.pack(fill="x", side="bottom")

    def _set_status(self, message: str) -> None:
        self.status_var.set(message)
        self.root.update_idletasks()

    def pick_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Wybierz plik wideo",
            filetypes=[
                ("Pliki wideo", "*.mp4 *.mkv *.avi *.mov *.m4v *.webm"),
                ("Pliki MP4", "*.mp4"),
                ("Pliki MKV", "*.mkv"),
                ("Pliki AVI", "*.avi"),
                ("Pliki MOV", "*.mov"),
                ("Pliki M4V", "*.m4v"),
                ("Pliki WEBM", "*.webm"),
                ("Wszystkie pliki", "*.*"),
            ],
        )
        if not path:
            return
        self.selected_file = Path(path)
        self.file_var.set(str(self.selected_file))
        self.text.delete("1.0", tk.END)
        self.text.insert(tk.END, f"Wybrano plik:\n{self.selected_file}\n")
        self._set_status("Wybrano plik.")

    def analyze_current_file(self) -> None:
        if not self.selected_file:
            messagebox.showwarning("Brak pliku", "Najpierw wybierz plik do analizy.")
            return
        self._set_status("Analiza pliku...")
        self.root.after(50, self._run_analysis)

    def _run_analysis(self) -> None:
        try:
            result = analyze_video(self.selected_file)  # type: ignore[arg-type]
            self.last_result = result
            self.text.delete("1.0", tk.END)
            self.text.insert(tk.END, format_analysis(result))
            self._set_status("Analiza zakończona.")
        except Exception as exc:
            self._set_status("Błąd analizy.")
            messagebox.showerror("Błąd", str(exc))

    def save_report_from_gui(self) -> None:
        if not self.last_result:
            messagebox.showwarning("Brak analizy", "Najpierw wykonaj analizę pliku.")
            return
        path = filedialog.asksaveasfilename(
            title="Zapisz raport JSON",
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
        )
        if not path:
            return
        save_report(Path(path), self.last_result)
        self._set_status(f"Zapisano raport: {path}")

    def repair_current_file(self) -> None:
        if not self.selected_file:
            messagebox.showwarning("Brak pliku", "Najpierw wybierz plik do naprawy.")
            return
        path = filedialog.asksaveasfilename(
            title="Zapisz naprawiony plik",
            defaultextension=".mp4",
            filetypes=[
                ("Pliki MP4", "*.mp4"),
                ("Pliki MKV", "*.mkv"),
                ("Pliki AVI", "*.avi"),
                ("Pliki MOV", "*.mov"),
                ("Pliki M4V", "*.m4v"),
                ("Pliki WEBM", "*.webm"),
            ],
        )
        if not path:
            return
        self.output_var.set(path)
        self._set_status("Trwa naprawa/normalizacja...")
        worker = threading.Thread(target=self._repair_worker, args=(Path(path),), daemon=True)
        worker.start()

    def _repair_worker(self, output_file: Path) -> None:
        try:
            cmd = build_ffmpeg_command(
                input_file=self.selected_file,  # type: ignore[arg-type]
                output_file=output_file,
                target_bitrate=None,
                target_fps=None,
                crf=23,
                preset="medium",
                audio_bitrate="128k",
                remove_audio=False,
            )
            proc = run_cmd(cmd)
            if proc.returncode != 0:
                raise RuntimeError(proc.stderr.strip() or "ffmpeg nie zakończył się poprawnie.")
            repaired = analyze_video(output_file)
            self.last_result = repaired
            text = format_analysis(repaired)
            self.root.after(0, self._repair_done, text, str(output_file))
        except Exception as exc:
            self.root.after(0, self._repair_error, str(exc))

    def _repair_done(self, output_text: str, output_path: str) -> None:
        self.text.delete("1.0", tk.END)
        self.text.insert(tk.END, output_text)
        self._set_status(f"Naprawa zakończona: {output_path}")
        messagebox.showinfo("Sukces", f"Zapisano plik wynikowy:\n{output_path}")

    def _repair_error(self, message: str) -> None:
        self._set_status("Błąd naprawy.")
        messagebox.showerror("Błąd naprawy", message)

    def run(self) -> int:
        self.root.mainloop()
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Weryfikacja i normalizacja plików wideo (MP4/MKV/AVI/MOV/M4V/WEBM). "
            "Program analizuje plik i opcjonalnie naprawia go przez ponowne kodowanie."
        )
    )
    parser.add_argument("--input", help="Ścieżka do pliku wejściowego.")
    parser.add_argument("--output", help="Ścieżka do pliku wyjściowego (wymagana dla naprawy).")
    parser.add_argument("--analyze-only", action="store_true", help="Tylko analiza, bez zapisu pliku.")
    parser.add_argument("--target-bitrate", help="Docelowy bitrate wideo, np. 2500k.")
    parser.add_argument("--target-fps", type=float, help="Docelowa liczba FPS, np. 30.")
    parser.add_argument("--crf", type=int, default=23, help="CRF dla kodera x264 (domyślnie: 23).")
    parser.add_argument("--preset", default="medium", help="Preset kodowania x264 (domyślnie: medium).")
    parser.add_argument("--audio-bitrate", default="128k", help="Bitrate audio AAC (domyślnie: 128k).")
    parser.add_argument("--remove-audio", action="store_true", help="Usuń dźwięk z pliku wyjściowego.")
    parser.add_argument("--report-json", help="Opcjonalna ścieżka do zapisu raportu JSON.")
    parser.add_argument("--gui", action="store_true", help="Uruchom graficzny interfejs narzędzia.")
    args = parser.parse_args()

    if args.gui:
        ensure_binary("ffmpeg")
        ensure_binary("ffprobe")
        app = VideoToolGUI()
        return app.run()

    ensure_binary("ffmpeg")
    ensure_binary("ffprobe")

    if not args.input:
        print("[BŁĄD] Dla trybu CLI wymagane jest --input.", file=sys.stderr)
        return 2

    input_file = Path(args.input)
    if not input_file.exists():
        print(f"[BŁĄD] Plik wejściowy nie istnieje: {input_file}", file=sys.stderr)
        return 2

    result = analyze_video(input_file)
    print_analysis(result)

    if args.report_json:
        save_report(Path(args.report_json), result)

    has_error = any(i.level == "error" for i in result.issues)

    if args.analyze_only:
        return 1 if has_error else 0

    if not args.output:
        print("[BŁĄD] Dla trybu naprawy wymagane jest --output.", file=sys.stderr)
        return 2

    output_file = Path(args.output)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    cmd = build_ffmpeg_command(
        input_file=input_file,
        output_file=output_file,
        target_bitrate=args.target_bitrate,
        target_fps=args.target_fps,
        crf=args.crf,
        preset=args.preset,
        audio_bitrate=args.audio_bitrate,
        remove_audio=args.remove_audio,
    )

    print("\n=== Naprawa/normalizacja ===")
    print("Uruchamianie:")
    print(" ", " ".join(shlex.quote(x) for x in cmd))

    proc = run_cmd(cmd)
    if proc.returncode != 0:
        print("[BŁĄD] ffmpeg nie zakończył się poprawnie.", file=sys.stderr)
        if proc.stderr:
            print(proc.stderr, file=sys.stderr)
        return proc.returncode

    print(f"[OK] Zapisano plik wynikowy: {output_file}")

    # Analiza po naprawie
    repaired_result = analyze_video(output_file)
    print_analysis(repaired_result)

    if has_error:
        print("[INFO] W pliku wejściowym były błędy; zakończono po próbie naprawy.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
