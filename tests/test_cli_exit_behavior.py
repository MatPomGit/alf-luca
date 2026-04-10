from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Dodajemy katalogi `src`, aby testy działały bez instalacji pakietów.
for src_dir in sorted((REPO_ROOT / "packages").glob("*/src")):
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

from luca_tracker import cli


def _install_fake_tracking_services(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[tuple]]:
    """Podmienia `luca_tracking.application_services` na lekki stub do testów przepływu CLI."""
    calls: dict[str, list[tuple]] = {"calibrate": [], "track": [], "compare": []}

    fake_module = types.ModuleType("luca_tracking.application_services")
    fake_module.run_calibrate = lambda *args: calls["calibrate"].append(args)
    fake_module.run_tracking = lambda args: calls["track"].append((args.command,))
    fake_module.run_compare = lambda *args: calls["compare"].append(args)
    fake_module.run_ros2 = lambda _args: None

    monkeypatch.setitem(sys.modules, "luca_tracking.application_services", fake_module)
    return calls


def test_parser_has_interactive_shell_flag_for_ci_flow() -> None:
    """Weryfikuje, że komendy batch mają jawny przełącznik legacy zachowania konsoli."""
    parser = cli.build_parser()

    args_cal = parser.parse_args(["calibrate", "--calib_dir", "calib"])
    args_track = parser.parse_args(["track", "--video", "input.mp4"])
    args_cmp = parser.parse_args(["compare", "--reference", "a.csv", "--candidate", "b.csv", "--output_csv", "out.csv"])

    assert args_cal.interactive_shell is False
    assert args_track.interactive_shell is False
    assert args_cmp.interactive_shell is False


def test_main_calibrate_default_has_no_sleep_or_terminal_side_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    """Domyślny tryb CI powinien kończyć się natychmiast bez dźwięku i bez opóźnień."""
    calls = _install_fake_tracking_services(monkeypatch)

    monkeypatch.setenv(cli.LEGACY_EXIT_ENV_VAR, "0")
    monkeypatch.setattr(sys, "argv", ["luca", "calibrate", "--calib_dir", "calib"])

    sleep_called = {"value": False}
    monkeypatch.setattr(cli.time, "sleep", lambda _seconds: sleep_called.__setitem__("value", True))

    cli.main()

    assert calls["calibrate"], "Komenda calibrate powinna zostać wykonana."
    assert sleep_called["value"] is False


def test_main_calibrate_legacy_env_enables_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tryb legacy przez ENV powinien aktywować opóźnienie po komendzie analitycznej."""
    _install_fake_tracking_services(monkeypatch)

    monkeypatch.setenv(cli.LEGACY_EXIT_ENV_VAR, "1")
    monkeypatch.setenv("LUCA_CONSOLE_CLOSE_TIMEOUT", "0")
    monkeypatch.setattr(sys, "argv", ["luca", "calibrate", "--calib_dir", "calib"])

    recorded_sleep: list[float] = []
    monkeypatch.setattr(cli.time, "sleep", lambda seconds: recorded_sleep.append(seconds))

    cli.main()

    assert recorded_sleep == [0]


def test_main_track_interactive_shell_flag_enables_legacy_behavior(monkeypatch: pytest.MonkeyPatch) -> None:
    """Flaga `--interactive-shell` powinna działać niezależnie od wartości ENV."""
    _install_fake_tracking_services(monkeypatch)

    monkeypatch.setenv(cli.LEGACY_EXIT_ENV_VAR, "0")
    monkeypatch.setenv("LUCA_CONSOLE_CLOSE_TIMEOUT", "0")
    monkeypatch.setattr(sys, "argv", ["luca", "track", "--video", "input.mp4", "--interactive-shell"])

    recorded_sleep: list[float] = []
    monkeypatch.setattr(cli.time, "sleep", lambda seconds: recorded_sleep.append(seconds))

    cli.main()

    assert recorded_sleep == [0]
