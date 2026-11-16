"""Behavioural tests for the RDP quality prompt in the launcher menu.

The prompt is the only place a user picks a profile, so these tests drive the
real handlers with a fake `input()` and stub launchers. They pin:

* three profiles, with High as the default (including on EOF);
* the choice reaching the CPU, GPU, Function-forensics, and HTB-forensics
  launchers;
* the standard HTB box never asking, because it has no RDP server.
"""

import pathlib

import pytest

from ui.launcher_menu import prompt_rdp_quality

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _no_spinner(monkeypatch):
    """Handlers import show_spinner late, so patching the module is enough."""
    import ui.ui_utils as ui_utils

    monkeypatch.setattr(ui_utils, "show_spinner", lambda *args, **kwargs: None)


def source(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def _answers(monkeypatch, *values):
    remaining = list(values)

    def fake_input(prompt=""):
        if not remaining:
            raise EOFError
        return remaining.pop(0)

    monkeypatch.setattr("builtins.input", fake_input)


class FakeLauncher:
    """Records `.remote()` calls instead of starting a Modal app."""

    def __init__(self):
        self.calls = []

    def remote(self, **kwargs):
        self.calls.append(kwargs)


# --- prompt ----------------------------------------------------------------


def test_the_prompt_offers_low_balanced_and_high():
    text = source("ui/launcher_menu.py")
    prompt = text.split("def prompt_rdp_quality", 1)[1].split("def handle_rdp_choice", 1)[0]
    for label in ("High", "Balanced", "Low"):
        assert label in prompt
    assert "default 1" in prompt


def test_choice_three_selects_low(monkeypatch):
    _answers(monkeypatch, "3")
    assert prompt_rdp_quality() == ("low", None)


def test_choice_two_selects_balanced(monkeypatch):
    _answers(monkeypatch, "2")
    assert prompt_rdp_quality() == ("balanced", None)


def test_choice_one_selects_high(monkeypatch):
    _answers(monkeypatch, "1")
    assert prompt_rdp_quality() == ("high", None)


def test_enter_selects_high(monkeypatch):
    _answers(monkeypatch, "")
    assert prompt_rdp_quality() == ("high", None)


def test_eof_selects_high(monkeypatch):
    _answers(monkeypatch)
    assert prompt_rdp_quality() == ("high", None)


def test_an_unknown_answer_selects_high(monkeypatch):
    _answers(monkeypatch, "banana")
    assert prompt_rdp_quality() == ("high", None)


def test_the_prompt_accepts_the_profile_name(monkeypatch):
    _answers(monkeypatch, "low")
    assert prompt_rdp_quality() == ("low", None)


# --- wiring ----------------------------------------------------------------


def test_rdp_desktop_cpu_launch_forwards_the_profile(monkeypatch):
    from ui.launcher_menu import handle_rdp_choice

    _answers(monkeypatch, "", "3", "n")
    cpu = FakeLauncher()
    gpu = [FakeLauncher() for _ in range(4)]

    handle_rdp_choice(cpu, *gpu, False)

    assert cpu.calls == [
        {"extra_packages": [], "rdp_quality": "low", "rdp_max_bpp": None}
    ]


def test_rdp_desktop_gpu_launch_forwards_the_profile(monkeypatch):
    from ui.launcher_menu import handle_rdp_choice

    _answers(monkeypatch, "firefox", "2", "y", "1")
    cpu = FakeLauncher()
    t4, l4, a10g, l40s = (FakeLauncher() for _ in range(4))

    handle_rdp_choice(cpu, t4, l4, a10g, l40s, False)

    assert not cpu.calls
    assert t4.calls == [
        {"extra_packages": ["firefox"], "rdp_quality": "balanced", "rdp_max_bpp": None}
    ]


def test_gpu_launchers_are_refused_in_cpu_only_mode(monkeypatch, capsys):
    from ui.launcher_menu import handle_rdp_choice

    _answers(monkeypatch, "", "", "y")
    cpu = FakeLauncher()
    gpu = [FakeLauncher() for _ in range(4)]

    handle_rdp_choice(cpu, *gpu, True)

    assert not any(launcher.calls for launcher in gpu)
    assert "CPU-only mode" in capsys.readouterr().out


def test_the_function_forensics_box_gets_the_profile(monkeypatch):
    from ui.launcher_menu import handle_simple_choice

    _answers(monkeypatch, "n", "3")
    forensics = FakeLauncher()
    htb = FakeLauncher()

    handle_simple_choice("6", FakeLauncher(), forensics, FakeLauncher(), False, htb)

    assert forensics.calls == [{"rdp_quality": "low", "rdp_max_bpp": None}]
    assert not htb.calls


def test_the_htb_forensics_box_gets_the_profile(monkeypatch):
    from ui.launcher_menu import handle_simple_choice

    # HTB on, Labs, generated name, then the quality choice.
    _answers(monkeypatch, "y", "1", "", "2")
    forensics = FakeLauncher()
    htb = FakeLauncher()

    handle_simple_choice("6", FakeLauncher(), forensics, FakeLauncher(), False, htb)

    assert not forensics.calls
    assert len(htb.calls) == 1
    call = htb.calls[0]
    assert call["network"] == "labs"
    assert call["rdp_quality"] == "balanced"
    assert call["rdp_max_bpp"] is None


def test_a_standard_htb_box_never_prompts_for_quality():
    # handle_standard_choice owns the standard flow and has no RDP branch.
    text = source("ui/launcher_menu.py")
    standard = text.split("def handle_standard_choice", 1)[1].split(
        "def prompt_rdp_quality", 1
    )[0]
    assert "prompt_rdp_quality" not in standard
