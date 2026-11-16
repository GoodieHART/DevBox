"""Tests for the RDP quality profiles shared by every desktop box.

`runtime/rdp_quality.py` has to work in two places: a Modal Function container,
where `runtime.shared_runtime` imports it, and the HTB VM Sandbox, where the
shell script calls it before xrdp starts. These tests therefore import it
directly, never through Modal, and drive the external commands with a fake
runner.

Covered here:

* profile selection and color-depth precedence;
* the `xrdp.ini` rewrite, including insertion when `max_bpp` is absent;
* the profile marker the session launcher reads;
* server-side resolution through a fake `xrandr`, including the modeline path
  and every failure fallback;
* the XFCE backup/restore round trip for compositing and wallpaper;
* the CLI contract (one JSON line, exit 0 even when nothing could be applied).
"""

import json
import pathlib

import pytest

from runtime import rdp_quality


# --- profile selection -----------------------------------------------------


def test_the_three_profiles_carry_the_documented_settings():
    low = rdp_quality.RDP_PROFILES["low"]
    assert low["max_bpp"] == 16
    assert low["resolution"] == "1024x768"
    assert low["compositing"] is False
    assert low["wallpaper"] is False
    assert low["audio"] is False

    balanced = rdp_quality.RDP_PROFILES["balanced"]
    assert balanced["max_bpp"] == 24
    assert balanced["resolution"] == "1280x720"
    assert balanced["compositing"] is True
    assert balanced["audio"] is True

    high = rdp_quality.RDP_PROFILES["high"]
    assert high["max_bpp"] == 32
    assert high["resolution"] is None
    assert high["audio"] is True


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("low", "low"),
        ("LOW", "low"),
        ("balanced", "balanced"),
        ("medium", "balanced"),
        ("high", "high"),
        ("auto", "high"),
        ("", "high"),
        (None, "high"),
        ("nonsense", "high"),
    ],
)
def test_quality_names_are_canonicalised(name, expected):
    assert rdp_quality.canonical_quality(name) == expected


def test_an_explicit_depth_beats_every_other_source():
    env = {"RDP_MAX_BPP": "8", "RDP_QUALITY": "low"}
    assert rdp_quality.resolve_max_bpp("high", 24, env) == 24


def test_the_environment_depth_beats_the_quality_preset():
    env = {"RDP_MAX_BPP": "15", "RDP_QUALITY": "low"}
    assert rdp_quality.resolve_max_bpp("high", None, env) == 15


def test_the_environment_quality_beats_the_argument():
    env = {"RDP_QUALITY": "low"}
    assert rdp_quality.resolve_max_bpp("high", None, env) == 16


def test_the_quality_argument_is_used_without_environment_overrides():
    assert rdp_quality.resolve_max_bpp("balanced", None, {}) == 24


def test_an_unknown_quality_falls_back_to_32_bit():
    assert rdp_quality.resolve_max_bpp("turbo", None, {}) == 32


def test_an_unsupported_depth_is_rounded_to_the_nearest_supported_one():
    assert rdp_quality.resolve_max_bpp("high", 20, {}) == 16
    assert rdp_quality.resolve_max_bpp("high", 30, {}) == 32


def test_a_non_numeric_depth_is_rejected():
    with pytest.raises(ValueError):
        rdp_quality.resolve_max_bpp("high", "lots", {})


def test_an_empty_override_means_unset():
    assert rdp_quality.resolve_max_bpp("low", "", {"RDP_MAX_BPP": ""}) == 16


def test_the_resolved_profile_keeps_the_preset_and_the_depth():
    profile = rdp_quality.resolve_profile("low", None, {})
    assert profile["quality"] == "low"
    assert profile["max_bpp"] == 16
    assert profile["resolution"] == "1024x768"
    assert profile["force_resolution"] is True


def test_resolution_forcing_can_be_disabled_without_changing_the_profile():
    profile = rdp_quality.resolve_profile(
        "low", None, {rdp_quality.RDP_FORCE_RESOLUTION_ENV: "0"}
    )
    assert profile["quality"] == "low"
    assert profile["force_resolution"] is False


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1024x768", (1024, 768)),
        ("1280x720", (1280, 720)),
        ("  800x600  ", (800, 600)),
        ("", None),
        ("1024", None),
        ("1024x", None),
        ("ax768", None),
        ("0x768", None),
        ("1024x768x2", None),
        (None, None),
    ],
)
def test_resolution_parsing(value, expected):
    assert rdp_quality.parse_resolution(value) == expected


def test_the_summary_names_every_disabled_feature():
    summary = rdp_quality.profile_summary(rdp_quality.resolve_profile("low", None, {}))
    assert "low" in summary
    assert "16-bit" in summary
    assert "1024x768 forced" in summary
    assert "effects off" in summary
    assert "no wallpaper" in summary
    assert "audio off" in summary


def test_the_high_summary_says_native_resolution():
    summary = rdp_quality.profile_summary(rdp_quality.resolve_profile("high", None, {}))
    assert "native resolution" in summary
    assert "forced" not in summary


def test_client_hints_match_the_low_profile():
    hints = rdp_quality.client_hint(rdp_quality.resolve_profile("low", None, {}))
    assert "1024x768" in hints["mstsc"]
    assert "16-bit" in hints["mstsc"]
    assert "/bpp:16" in hints["freerdp"]
    assert "/network:modem" in hints["freerdp"]


def test_client_hints_match_the_high_profile():
    hints = rdp_quality.client_hint(rdp_quality.resolve_profile("high", None, {}))
    assert "native resolution" in hints["mstsc"]
    assert "/dynamic-resolution" in hints["freerdp"]


# --- xrdp configuration ----------------------------------------------------


def test_an_existing_max_bpp_line_is_replaced(tmp_path):
    config = tmp_path / "xrdp.ini"
    config.write_text("[Globals]\nmax_bpp=32\nport=3389\n")
    assert rdp_quality.configure_xrdp(16, str(config)) is True
    text = config.read_text()
    assert "max_bpp=16\n" in text
    assert "max_bpp=32" not in text
    # Nothing else is touched.
    assert "port=3389" in text


def test_a_missing_max_bpp_is_inserted_under_globals(tmp_path):
    config = tmp_path / "xrdp.ini"
    config.write_text("[Globals]\nport=3389\n\n[Xorg]\nname=Xorg\n")
    rdp_quality.configure_xrdp(24, str(config))
    lines = config.read_text().splitlines()
    assert lines.index("max_bpp=24") == lines.index("[Globals]") + 1


def test_a_config_without_globals_still_gets_the_depth(tmp_path):
    config = tmp_path / "xrdp.ini"
    config.write_text("[Xorg]\nname=Xorg\n")
    rdp_quality.configure_xrdp(32, str(config))
    assert config.read_text().startswith("max_bpp=32\n")


def test_configuring_a_missing_file_is_not_fatal(tmp_path):
    assert rdp_quality.configure_xrdp(16, str(tmp_path / "nope.ini")) is False


def test_configuration_is_idempotent(tmp_path):
    config = tmp_path / "xrdp.ini"
    config.write_text("[Globals]\nmax_bpp=32\n")
    rdp_quality.configure_xrdp(16, str(config))
    first = config.read_text()
    rdp_quality.configure_xrdp(16, str(config))
    assert config.read_text() == first


# --- marker ----------------------------------------------------------------


def test_the_marker_round_trips_a_canonical_name(tmp_path):
    marker = tmp_path / "run" / "rdp-quality"
    rdp_quality.write_marker("medium", str(marker))
    assert marker.read_text().strip() == "balanced"
    assert rdp_quality.read_marker(str(marker)) == "balanced"


def test_a_missing_marker_reads_as_none(tmp_path):
    assert rdp_quality.read_marker(str(tmp_path / "missing")) is None


# --- pre-session apply -----------------------------------------------------


def test_apply_writes_the_depth_and_the_marker(tmp_path):
    config = tmp_path / "xrdp.ini"
    config.write_text("[Globals]\nmax_bpp=32\n")
    marker = tmp_path / "rdp-quality"

    result = rdp_quality.apply("low", None, home=str(tmp_path),
                               xrdp_ini=str(config), marker=str(marker), env={})

    assert result["ok"] is True
    assert result["xrdp_configured"] is True
    assert result["max_bpp"] == 16
    assert "low" in result["summary"]
    assert config.read_text().strip() == "[Globals]\nmax_bpp=16"
    assert marker.read_text().strip() == "low"


def test_apply_is_not_fatal_when_xrdp_is_absent(tmp_path):
    marker = tmp_path / "rdp-quality"
    result = rdp_quality.apply("low", None, home=str(tmp_path),
                               xrdp_ini=str(tmp_path / "absent.ini"),
                               marker=str(marker), env={})
    assert result["ok"] is False
    assert "not found" in result["error"]
    # The profile is still recorded, so the in-session stage can apply it.
    assert marker.read_text().strip() == "low"


def test_apply_reports_an_invalid_explicit_depth(tmp_path):
    config = tmp_path / "xrdp.ini"
    config.write_text("[Globals]\n")
    result = rdp_quality.apply("low", "wat", home=str(tmp_path),
                               xrdp_ini=str(config), marker=str(tmp_path / "m"), env={})
    assert result["ok"] is False
    assert "invalid max_bpp" in result["error"]


# --- in-session helpers ----------------------------------------------------


class FakeRunner:
    """Answer `xrandr` and `xfconf-query` calls from in-memory state."""

    def __init__(self, outputs=None, modes=None, state=None, fail=()):
        self.outputs = outputs if outputs is not None else {"X11-0": "connected"}
        self.modes = modes if modes is not None else {}
        self.state = state if state is not None else {}
        self.fail = set(fail)
        self.calls = []

    # xrandr ------------------------------------------------------------
    def _query(self):
        lines = ["Screen 0: minimum 8 x 8, current 1280 x 720, maximum 32767 x 32767"]
        for name in self.outputs:
            lines.append(f"{name} connected primary 1280x720+0+0 (normal left inverted)")
            for mode in self.modes.get(name, []):
                lines.append(f"   {mode}      60.00*+")
            lines.append(f"   1280x720      60.00*")
        return "\n".join(lines) + "\n"

    def __call__(self, command):
        self.calls.append(list(command))
        tool = command[0]
        if tool == "cvt":
            return rdp_quality._Result(0, "Modeline \"1024x768_60.00\"  65.00  1024 1048 1184 1344  768 771 777 806 -hsync -vsync\n")
        if tool == "xrandr":
            if "xrandr" in self.fail:
                return rdp_quality._Result(1, "", "cannot open display")
            if "--query" in command:
                return rdp_quality._Result(0, self._query())
            if "--newmode" in command:
                return rdp_quality._Result(0)
            if "--addmode" in command:
                output, mode = command[command.index("--addmode") + 1:][:2]
                self.modes.setdefault(output, []).append(mode)
                return rdp_quality._Result(0)
            if "--output" in command:
                output = command[command.index("--output") + 1]
                mode = command[command.index("--mode") + 1]
                if mode != "1280x720" and mode not in self.modes.get(output, []):
                    return rdp_quality._Result(1, "", "no mode")
                return rdp_quality._Result(0)
        if tool == "xfconf-query":
            return self._xfconf(command)
        return rdp_quality._Result(1, "", f"unknown tool {tool}")

    # xfconf ------------------------------------------------------------
    def _xfconf(self, command):
        channel = command[command.index("-c") + 1]
        if "-l" in command:
            props = sorted(prop for (chan, prop) in self.state if chan == channel)
            return rdp_quality._Result(0, "\n".join(props))
        prop = command[command.index("-p") + 1]
        key = (channel, prop)
        if "-s" in command:
            self.state[key] = command[command.index("-s") + 1]
            return rdp_quality._Result(0)
        if key not in self.state:
            return rdp_quality._Result(1, "", "no such property")
        return rdp_quality._Result(0, self.state[key])


def test_an_already_listed_mode_is_selected_without_a_new_modeline():
    runner = FakeRunner()
    assert rdp_quality.apply_resolution("1280x720", runner=runner) is True
    outputs = [call for call in runner.calls if "--output" in call]
    assert outputs[-1] == ["xrandr", "--output", "X11-0", "--mode", "1280x720"]
    assert not any("--newmode" in call for call in runner.calls)


def test_a_missing_mode_is_created_with_cvt_and_added():
    runner = FakeRunner()
    assert rdp_quality.apply_resolution("1024x768", runner=runner) is True
    assert any(call[:2] == ["xrandr", "--newmode"] for call in runner.calls)
    assert any("--addmode" in call for call in runner.calls)
    final = [call for call in runner.calls if "--output" in call][-1]
    assert final[-1] == "devbox_1024x768"


def test_a_failed_mode_query_keeps_the_client_resolution():
    messages = []
    runner = FakeRunner(fail=["xrandr"])
    assert rdp_quality.apply_resolution("1024x768", runner=runner, log=messages.append) is False
    assert any("xrandr" in message for message in messages)


def test_no_connected_output_keeps_the_client_resolution():
    messages = []
    runner = FakeRunner(outputs={})
    assert rdp_quality.apply_resolution("1024x768", runner=runner, log=messages.append) is False
    assert any("no connected" in message for message in messages)


def test_a_refused_mode_switch_is_reported_but_not_raised():
    messages = []
    runner = FakeRunner()

    def refuse(command):
        if "--output" in command:
            return rdp_quality._Result(1, "", "configure crtc failed")
        return FakeRunner.__call__(runner, command)

    assert rdp_quality.apply_resolution("1280x720", runner=refuse, log=messages.append) is False
    assert any("failed" in message for message in messages)


def test_an_unparseable_resolution_is_ignored():
    runner = FakeRunner()
    assert rdp_quality.apply_resolution("native", runner=runner) is False
    assert runner.calls == []


def test_a_rejected_new_mode_reports_why():
    """A server that silently refuses --newmode must explain the failure."""
    messages = []

    def runner(command):
        if "--newmode" in command:
            return rdp_quality._Result(0)
        if "--addmode" in command:
            return rdp_quality._Result(1, "", 'cannot find mode "devbox_1024x768"')
        if "--output" in command:
            return rdp_quality._Result(1, "", "cannot find mode devbox_1024x768")
        if "cvt" in command[0]:
            return rdp_quality._Result(
                0, 'Modeline "1024x768_60.00"  65.00  1024 1048 1184 1344 768 771 777 806 -hsync -vsync\n'
            )
        return FakeRunner().__call__(command)

    assert rdp_quality.apply_resolution("1024x768", runner=runner, log=messages.append) is False
    assert any("cannot find mode" in message for message in messages)


# --- XFCE settings ---------------------------------------------------------


def _desktop_state():
    return {
        ("xfwm4", "/general/use_compositing"): "true",
        ("xfce4-desktop", "/backdrop/screen0/monitor0/workspace0/last-image"): "/usr/share/wallpapers/a.jpg",
        ("xfce4-desktop", "/backdrop/screen0/monitor0/workspace0/image-style"): "5",
    }


def test_low_disables_compositing_and_clears_the_wallpaper(tmp_path):
    state = _desktop_state()
    runner = FakeRunner(state=state)
    profile = rdp_quality.resolve_profile("low", None, {})

    assert rdp_quality.apply_xfce(profile, home=str(tmp_path), runner=runner) is True
    assert state[("xfwm4", "/general/use_compositing")] == "false"
    assert state[("xfce4-desktop", "/backdrop/screen0/monitor0/workspace0/last-image")] == ""
    assert state[("xfce4-desktop", "/backdrop/screen0/monitor0/workspace0/image-style")] == "0"


def test_the_original_values_are_backed_up_before_the_first_low_session(tmp_path):
    runner = FakeRunner(state=_desktop_state())
    rdp_quality.apply_xfce(rdp_quality.resolve_profile("low", None, {}),
                           home=str(tmp_path), runner=runner)

    backup = json.loads((tmp_path / ".config" / "xfce4" / "devbox-rdp-backup.json").read_text())
    assert backup["xfwm4"]["/general/use_compositing"] == "true"
    assert backup["xfce4-desktop"]["/backdrop/screen0/monitor0/workspace0/image-style"] == "5"


def test_high_restores_the_backup_and_removes_it(tmp_path):
    state = _desktop_state()
    runner = FakeRunner(state=state)
    low = rdp_quality.resolve_profile("low", None, {})
    high = rdp_quality.resolve_profile("high", None, {})

    rdp_quality.apply_xfce(low, home=str(tmp_path), runner=runner)
    assert rdp_quality.apply_xfce(high, home=str(tmp_path), runner=runner) is True

    assert state[("xfwm4", "/general/use_compositing")] == "true"
    assert state[("xfce4-desktop", "/backdrop/screen0/monitor0/workspace0/last-image")] == "/usr/share/wallpapers/a.jpg"
    assert not (tmp_path / ".config" / "xfce4" / "devbox-rdp-backup.json").exists()


def test_high_without_a_backup_changes_nothing(tmp_path):
    state = _desktop_state()
    runner = FakeRunner(state=state)
    before = dict(state)
    high = rdp_quality.resolve_profile("high", None, {})
    assert rdp_quality.apply_xfce(high, home=str(tmp_path), runner=runner) is False
    assert state == before


def test_a_second_low_session_does_not_overwrite_the_backup(tmp_path):
    state = _desktop_state()
    runner = FakeRunner(state=state)
    low = rdp_quality.resolve_profile("low", None, {})

    rdp_quality.apply_xfce(low, home=str(tmp_path), runner=runner)
    original = (tmp_path / ".config" / "xfce4" / "devbox-rdp-backup.json").read_text()
    rdp_quality.apply_xfce(low, home=str(tmp_path), runner=runner)
    assert (tmp_path / ".config" / "xfce4" / "devbox-rdp-backup.json").read_text() == original


def test_a_later_round_merges_backdrop_properties_that_appear_late(tmp_path):
    """xfdesktop only creates the RDP monitor's props once the session is up.

    The first round cannot back them up, so the retry has to add them without
    re-reading the values the low profile already replaced.
    """
    state = {("xfwm4", "/general/use_compositing"): "true"}
    runner = FakeRunner(state=state)
    low = rdp_quality.resolve_profile("low", None, {})
    backup_path = tmp_path / ".config" / "xfce4" / "devbox-rdp-backup.json"

    rdp_quality.apply_xfce(low, home=str(tmp_path), runner=runner)
    first = json.loads(backup_path.read_text())
    assert first["xfwm4"]["/general/use_compositing"] == "true"
    assert first["xfce4-desktop"] == {}

    state[("xfce4-desktop", "/backdrop/screen0/monitorrdp0/workspace0/last-image")] = "/wall.jpg"
    state[("xfce4-desktop", "/backdrop/screen0/monitorrdp0/workspace0/image-style")] = "5"

    rdp_quality.apply_xfce(low, home=str(tmp_path), runner=runner)

    merged = json.loads(backup_path.read_text())
    assert merged["xfce4-desktop"]["/backdrop/screen0/monitorrdp0/workspace0/last-image"] == "/wall.jpg"
    assert merged["xfce4-desktop"]["/backdrop/screen0/monitorrdp0/workspace0/image-style"] == "5"
    assert merged["xfwm4"]["/general/use_compositing"] == "true"
    # And the merge is what gets restored, not the cleared values.
    assert state[("xfce4-desktop", "/backdrop/screen0/monitorrdp0/workspace0/last-image")] == ""


# --- session and CLI -------------------------------------------------------


def test_the_session_reads_the_marker_and_applies_both_halves(tmp_path):
    marker = tmp_path / "rdp-quality"
    rdp_quality.write_marker("low", str(marker))
    state = _desktop_state()
    runner = FakeRunner(state=state)

    result = rdp_quality.session(home=str(tmp_path), marker=str(marker), runner=runner)

    assert result["ok"] is True
    assert result["quality"] == "low"
    assert result["resolution_applied"] is True
    assert result["xfce_changed"] is True
    assert state[("xfwm4", "/general/use_compositing")] == "false"


def test_the_session_falls_back_to_the_environment_without_a_marker(tmp_path, monkeypatch):
    monkeypatch.setenv("RDP_QUALITY", "balanced")
    runner = FakeRunner()
    result = rdp_quality.session(home=str(tmp_path), marker=str(tmp_path / "none"),
                                 runner=runner)
    assert result["quality"] == "balanced"
    assert result["resolution_applied"] is True


def test_the_resolution_part_skips_xfce(tmp_path):
    marker = tmp_path / "rdp-quality"
    rdp_quality.write_marker("low", str(marker))
    state = _desktop_state()
    runner = FakeRunner(state=state)

    result = rdp_quality.session(home=str(tmp_path), marker=str(marker),
                                 runner=runner, part="resolution")

    assert result["resolution_applied"] is True
    assert result["xfce_changed"] is False
    assert state[("xfwm4", "/general/use_compositing")] == "true"


def test_the_xfce_part_skips_the_resize(tmp_path):
    marker = tmp_path / "rdp-quality"
    rdp_quality.write_marker("low", str(marker))
    state = _desktop_state()
    runner = FakeRunner(state=state)

    result = rdp_quality.session(home=str(tmp_path), marker=str(marker),
                                 runner=runner, part="xfce")

    assert result["resolution_applied"] is False
    assert result["xfce_changed"] is True
    assert state[("xfwm4", "/general/use_compositing")] == "false"
    assert not any("xrandr" in call[0] for call in runner.calls)


def test_the_xfce_part_retries_until_the_backdrop_properties_exist(tmp_path):
    """xfdesktop creates the RDP monitor's properties after the session starts."""
    marker = tmp_path / "rdp-quality"
    rdp_quality.write_marker("low", str(marker))
    state = {}
    runner = FakeRunner(state=state)
    created = {"done": False}

    def delayed(command):
        if not created["done"]:
            # First round: the monitor is not known yet, so no backdrop props.
            created["done"] = True
            state[("xfce4-desktop", "/backdrop/screen0/monitorrdp0/workspace0/last-image")] = "/wall.jpg"
            state[("xfce4-desktop", "/backdrop/screen0/monitorrdp0/workspace0/image-style")] = "5"
        return FakeRunner.__call__(runner, command)

    result = rdp_quality.session(home=str(tmp_path), marker=str(marker),
                                 runner=delayed, part="xfce", retries=2, delay=0)

    assert result["xfce_changed"] is True
    assert state[("xfce4-desktop", "/backdrop/screen0/monitorrdp0/workspace0/last-image")] == ""
    assert state[("xfce4-desktop", "/backdrop/screen0/monitorrdp0/workspace0/image-style")] == "0"


def test_a_broken_session_never_raises(tmp_path):
    marker = tmp_path / "rdp-quality"
    rdp_quality.write_marker("low", str(marker))

    def explode(command):
        raise OSError("boom")

    result = rdp_quality.session(home=str(tmp_path), marker=str(marker), runner=explode)
    assert result["ok"] is False
    assert "boom" in result["error"]


def test_the_cli_show_prints_the_resolved_profile(capsys):
    assert rdp_quality.main(["show", "--quality", "balanced"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["quality"] == "balanced"
    assert payload["max_bpp"] == 24


def test_the_cli_apply_always_exits_zero(tmp_path, capsys):
    config = tmp_path / "xrdp.ini"
    config.write_text("[Globals]\n")
    marker = tmp_path / "marker"
    code = rdp_quality.main([
        "apply", "--quality", "low", "--home", str(tmp_path),
        "--xrdp-ini", str(config), "--marker", str(marker),
    ])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["max_bpp"] == 16


def test_the_cli_apply_tolerates_a_missing_config(tmp_path, capsys):
    code = rdp_quality.main([
        "apply", "--quality", "low", "--home", str(tmp_path),
        "--xrdp-ini", str(tmp_path / "absent.ini"),
        "--marker", str(tmp_path / "marker"),
    ])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False


def test_the_module_has_no_modal_dependency():
    """The VM Sandbox imports it, and Modal is not installed there."""
    text = pathlib.Path(rdp_quality.__file__).read_text(encoding="utf-8")
    assert "import modal" not in text
    assert "from modal" not in text
