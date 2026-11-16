"""RDP quality profiles for DevBox desktop boxes.

The module runs in two environments:

* a Modal Function container, where ``runtime.shared_runtime`` imports it;
* a Modal VM Sandbox, where the shell session launcher imports it directly.

It therefore imports no ``modal`` package and uses the standard library only.

A profile is applied in two stages:

* pre-session: write ``max_bpp`` into ``/etc/xrdp/xrdp.ini`` and record the
  selected profile in ``/run/devbox/rdp-quality``;
* in-session: ``startxfce4-wrapper`` sets the display mode before XFCE starts,
  then an XDG autostart entry applies XFCE compositing and the backdrop, which
  only works once the session bus exists.

Nothing here is fatal. A profile that cannot be applied leaves the stock xrdp
and XFCE behaviour in place, and the caller logs the result.
"""

import json
import os
import re
import subprocess
import sys
import time

# xrdp only supports these color depths. A requested value is rounded to the
# nearest one, so an out-of-range number still produces a working config.
SUPPORTED_BPP = (8, 15, 16, 24, 32)

# The profile settings. `resolution` is the server-side mode; None keeps the
# client's native resolution. `audio` gates the PipeWire xrdp sink.
RDP_PROFILES = {
    "low": {
        "max_bpp": 16,
        "resolution": "1024x768",
        "compositing": False,
        "wallpaper": False,
        "audio": False,
    },
    "balanced": {
        "max_bpp": 24,
        "resolution": "1280x720",
        "compositing": True,
        "wallpaper": True,
        "audio": True,
    },
    "high": {
        "max_bpp": 32,
        "resolution": None,
        "compositing": True,
        "wallpaper": True,
        "audio": True,
    },
}

# Backwards-compatible names: `medium` maps to `balanced` and `auto` to
# `high`.
RDP_QUALITY_ALIASES = {
    "medium": "balanced",
    "auto": "high",
    "high": "high",
    "balanced": "balanced",
    "low": "low",
}

RDP_QUALITY_PRESETS = {
    "low": 16,
    "medium": 24,
    "balanced": 24,
    "high": 32,
    "auto": 32,
}

# The VM script and the shell launcher read this marker. `/run` is ephemeral,
# so a reboot never carries a stale profile into a new session.
RDP_QUALITY_FILE = "/run/devbox/rdp-quality"

# Set DEVBOX_RDP_FORCE_RESOLUTION=0 to keep the client resolution while the
# rest of the profile still applies.
RDP_FORCE_RESOLUTION_ENV = "DEVBOX_RDP_FORCE_RESOLUTION"

# Backup of the XFCE properties a low-quality session changes. It lives under
# the persisted xfce4 config, so a later Balanced or High launch can restore
# the user's settings.
RDP_XFCE_BACKUP = "devbox-rdp-backup.json"

_MODE_RE = re.compile(r"\b(\d{3,5})x(\d{3,5})\b")


# --- profile resolution ----------------------------------------------------


def canonical_quality(quality):
    """Map a user-facing name to one of low/balanced/high."""
    name = str(quality or "high").strip().lower()
    return RDP_QUALITY_ALIASES.get(name, "high")


def _nearest_bpp(value):
    return min(SUPPORTED_BPP, key=lambda candidate: abs(candidate - value))


def _bpp_from(value, label):
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"invalid {label} value: {value!r}") from error
    return number if number in SUPPORTED_BPP else _nearest_bpp(number)


def _force_resolution(env):
    value = str(env.get(RDP_FORCE_RESOLUTION_ENV, "1")).strip().lower()
    return value not in {"0", "false", "no", "off"}


def resolve_max_bpp(quality="auto", max_bpp=None, env=None):
    """Resolve the xrdp color depth.

    Precedence: explicit argument, then ``RDP_MAX_BPP``, then the quality
    preset (``RDP_QUALITY`` overrides the argument), then 32.
    """
    environment = os.environ if env is None else env

    if max_bpp is not None and str(max_bpp).strip() != "":
        return _bpp_from(max_bpp, "max_bpp")

    env_bpp = environment.get("RDP_MAX_BPP")
    if env_bpp is not None and str(env_bpp).strip() != "":
        return _bpp_from(env_bpp, "RDP_MAX_BPP")

    selected = environment.get("RDP_QUALITY") or quality or "auto"
    return RDP_QUALITY_PRESETS.get(str(selected).strip().lower(), 32)


def resolve_profile(quality="auto", max_bpp=None, env=None):
    """The effective profile: preset values plus the resolved color depth."""
    environment = os.environ if env is None else env
    selected = canonical_quality(environment.get("RDP_QUALITY") or quality)
    profile = dict(RDP_PROFILES[selected])
    profile["quality"] = selected
    profile["max_bpp"] = resolve_max_bpp(quality, max_bpp, environment)
    profile["force_resolution"] = _force_resolution(environment)
    return profile


def parse_resolution(value):
    """Return ``(width, height)`` for a ``WIDTHxHEIGHT`` string, or None."""
    match = _MODE_RE.fullmatch(str(value or "").strip())
    if not match:
        return None
    width, height = int(match.group(1)), int(match.group(2))
    if width <= 0 or height <= 0:
        return None
    return width, height


def profile_summary(profile):
    """A compact one-line description for the connection block."""
    quality = profile.get("quality", "high")
    max_bpp = profile.get("max_bpp", 32)
    parts = [f"{quality} ({max_bpp}-bit"]
    resolution = profile.get("resolution")
    if resolution and profile.get("force_resolution", True):
        parts.append(f", {resolution} forced")
    elif resolution:
        parts.append(f", {resolution} recommended")
    else:
        parts.append(", native resolution")
    if not profile.get("compositing", True):
        parts.append(", effects off")
    if not profile.get("wallpaper", True):
        parts.append(", no wallpaper")
    if not profile.get("audio", True):
        parts.append(", audio off")
    return "".join(parts) + ")"


def client_hint(profile):
    """Client-side settings that match the server profile."""
    quality = profile.get("quality", "high")
    max_bpp = profile.get("max_bpp", 32)
    resolution = profile.get("resolution")
    if quality == "low":
        return {
            "mstsc": f"{resolution or '1024x768'}, {max_bpp}-bit, Low-speed broadband",
            "freerdp": f"/size:{resolution or '1024x768'} /bpp:{max_bpp} /network:modem",
        }
    if quality == "balanced":
        return {
            "mstsc": f"{resolution or '1280x720'}, {max_bpp}-bit, Broadband",
            "freerdp": f"/size:{resolution or '1280x720'} /bpp:{max_bpp} /network:broadband",
        }
    return {
        "mstsc": f"native resolution, {max_bpp}-bit, LAN",
        "freerdp": f"/dynamic-resolution /bpp:{max_bpp} /network:lan",
    }


# --- pre-session -----------------------------------------------------------


def configure_xrdp(max_bpp, path="/etc/xrdp/xrdp.ini"):
    """Rewrite or insert ``max_bpp`` in xrdp's configuration.

    Returns True when the file was written. A missing config is not fatal.
    """
    if not os.path.isfile(path):
        return False

    with open(path, "r", encoding="utf-8") as handle:
        lines = handle.readlines()

    replaced = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("max_bpp=") or stripped.startswith("max_bpp ="):
            lines[index] = f"max_bpp={max_bpp}\n"
            replaced = True
            break

    if not replaced:
        for index, line in enumerate(lines):
            if line.strip() == "[Globals]":
                lines.insert(index + 1, f"max_bpp={max_bpp}\n")
                break
        else:
            lines.insert(0, f"max_bpp={max_bpp}\n")

    with open(path, "w", encoding="utf-8") as handle:
        handle.writelines(lines)
    return True


def write_marker(quality, path=RDP_QUALITY_FILE):
    """Record the selected profile where the session launcher can read it."""
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(f"{canonical_quality(quality)}\n")
    return path


def read_marker(path=RDP_QUALITY_FILE):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return canonical_quality(handle.read().strip())
    except OSError:
        return None


def apply(quality="auto", max_bpp=None, home="/root",
          xrdp_ini="/etc/xrdp/xrdp.ini", marker=RDP_QUALITY_FILE, env=None):
    """Apply the pre-session stage of a profile. Never raises."""
    result = {"ok": False, "error": None, "xrdp_configured": False}
    try:
        profile = resolve_profile(quality, max_bpp, env)
        result.update(profile)
        result["summary"] = profile_summary(profile)
        result["xrdp_configured"] = configure_xrdp(profile["max_bpp"], xrdp_ini)
        try:
            write_marker(profile["quality"], marker)
            result["marker"] = marker
        except OSError as error:
            result["error"] = f"profile marker not written: {error}"
        result["ok"] = result["xrdp_configured"]
        if not result["xrdp_configured"] and not result["error"]:
            result["error"] = f"xrdp config not found at {xrdp_ini}"
    except Exception as error:  # noqa: BLE001 - the box must still start
        result["error"] = f"{type(error).__name__}: {error}"
    return result


# --- in-session ------------------------------------------------------------


class _Result:
    """The subset of subprocess.CompletedProcess used here."""

    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout or ""
        self.stderr = stderr or ""


def _run(command, runner=None):
    if runner is not None:
        return runner(command)
    try:
        return subprocess.run(
            command, capture_output=True, text=True, timeout=20, check=False
        )
    except (OSError, subprocess.SubprocessError) as error:
        return _Result(1, "", str(error))


def _first_connected_output(query):
    for line in str(query or "").splitlines():
        match = re.match(r"^(\S+)\s+connected\b", line)
        if match:
            return match.group(1)
    return None


def _mode_is_listed(query, width, height):
    """True when xrandr already offers this mode.

    xrandr indents mode lines under their output, so the first token is what
    tells them apart: an output name on a header line, `WIDTHxHEIGHT` on a
    mode line.
    """
    target = f"{width}x{height}"
    for line in str(query or "").splitlines():
        parts = line.split()
        if parts and parts[0] == target:
            return True
    return False


def _modeline(width, height, runner=None):
    """A modeline for the requested size, from cvt or a built-in fallback."""
    cvt = _run(["cvt", str(width), str(height), "60"], runner)
    for line in str(cvt.stdout or "").splitlines():
        if line.startswith("Modeline "):
            parts = line.split()
            # Drop Modeline and the quoted mode name.
            return " ".join(parts[2:])

    fallbacks = {
        (1024, 768): "65.00 1024 1048 1184 1344 768 771 777 806 -hsync -vsync",
        (1280, 720): "74.48 1280 1336 1472 1664 720 721 724 746 -hsync +vsync",
    }
    return fallbacks.get((width, height))


def apply_resolution(resolution, runner=None, log=None):
    """Set the X display to ``resolution``. Returns True when applied."""
    size = parse_resolution(resolution)
    if size is None:
        return False
    width, height = size

    query = _run(["xrandr", "--query"], runner)
    if query.returncode != 0:
        if log:
            log("xrandr is not available; keeping the client resolution")
        return False

    output = _first_connected_output(query.stdout)
    if not output:
        if log:
            log("no connected xrandr output; keeping the client resolution")
        return False

    setup_detail = ""
    if _mode_is_listed(query.stdout, width, height):
        mode = f"{width}x{height}"
    else:
        mode = f"devbox_{width}x{height}"
        modeline = _modeline(width, height, runner)
        if not modeline:
            if log:
                log(f"no modeline for {width}x{height}; keeping the client resolution")
            return False
        # Both calls are advisory: a mode created by an earlier session makes
        # --newmode fail, while --output below still works. Keep the first
        # error so a failure is explained rather than just "cannot find mode".
        created = _run(["xrandr", "--newmode", mode, *modeline.split()], runner)
        attached = _run(["xrandr", "--addmode", output, mode], runner)
        setup_detail = (
            (created.stderr or "").strip() or (attached.stderr or "").strip()
        )

    applied = _run(["xrandr", "--output", output, "--mode", mode], runner)
    if applied.returncode != 0:
        if log:
            detail = (applied.stderr or "").strip() or setup_detail
            log(f"xrandr resize to {width}x{height} failed{': ' + detail if detail else ''}")
        return False
    return True


def _xfconf_list(channel, runner=None):
    result = _run(["xfconf-query", "-c", channel, "-l"], runner)
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _xfconf_get(channel, prop, runner=None):
    result = _run(["xfconf-query", "-c", channel, "-p", prop], runner)
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _xfconf_type(prop, value):
    if prop.endswith("/use_compositing") or str(value).lower() in {"true", "false"}:
        return "bool"
    if prop.endswith("/image-style"):
        return "int"
    return "string"


def _xfconf_set(channel, prop, value, runner=None):
    command = ["xfconf-query", "-c", channel, "-p", prop, "-s", str(value)]
    result = _run(command, runner)
    if result.returncode == 0:
        return True
    return _run(
        command[:-4]
        + ["-n", "-t", _xfconf_type(prop, value)]
        + command[-2:],
        runner,
    ).returncode == 0


def _wallpaper_properties(runner=None):
    return [
        prop
        for prop in _xfconf_list("xfce4-desktop", runner)
        if prop.endswith("/last-image") or prop.endswith("/image-style")
    ]


def _backup_path(home):
    return os.path.join(home, ".config", "xfce4", RDP_XFCE_BACKUP)


def _read_backup(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def _write_backup(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)


def _save_xfce_backup(home, runner=None):
    """Record the pre-low XFCE values, merging into an existing backup.

    The in-session stage runs more than once, because xfdesktop creates the RDP
    monitor's backdrop properties a moment after the session starts. The first
    round cannot see them, so a later round adds what is missing.

    Existing keys are never overwritten. By the time a later round reads them
    they hold what the low profile wrote, not the original.
    """
    path = _backup_path(home)
    data = _read_backup(path) or {}
    data.setdefault("xfwm4", {})
    data.setdefault("xfce4-desktop", {})
    changed = not os.path.isfile(path)

    compositing = _xfconf_get("xfwm4", "/general/use_compositing", runner)
    if compositing is not None and "/general/use_compositing" not in data["xfwm4"]:
        data["xfwm4"]["/general/use_compositing"] = compositing
        changed = True

    for prop in _wallpaper_properties(runner):
        if prop in data["xfce4-desktop"]:
            continue
        value = _xfconf_get("xfce4-desktop", prop, runner)
        if value is not None:
            data["xfce4-desktop"][prop] = value
            changed = True

    if not changed:
        return
    try:
        _write_backup(path, data)
    except OSError:
        pass


def _restore_xfce_backup(home, runner=None):
    path = _backup_path(home)
    data = _read_backup(path)
    if not data:
        return False
    restored = False
    for channel, properties in data.items():
        for prop, value in (properties or {}).items():
            if _xfconf_set(channel, prop, value, runner):
                restored = True
    try:
        os.remove(path)
    except OSError:
        pass
    return restored


def apply_xfce(profile, home="/root", runner=None):
    """Apply or restore the XFCE side of a profile."""
    if profile.get("compositing", True) and profile.get("wallpaper", True):
        return _restore_xfce_backup(home, runner)

    _save_xfce_backup(home, runner)
    changed = False

    if not profile.get("compositing", True):
        changed = _xfconf_set(
            "xfwm4", "/general/use_compositing", "false", runner
        ) or changed

    if not profile.get("wallpaper", True):
        for prop in _wallpaper_properties(runner):
            value = "" if prop.endswith("/last-image") else "0"
            changed = _xfconf_set("xfce4-desktop", prop, value, runner) or changed

    return changed


def session(home="/root", marker=RDP_QUALITY_FILE, runner=None, log=None,
            part="all", retries=1, delay=0.0):
    """Apply the in-session stage of the profile. Never raises.

    `part` selects a stage: ``all``, ``resolution`` (safe before XFCE starts),
    or ``xfce`` (must run inside the session bus). `retries`/`delay` repeat the
    work because xfdesktop only creates the RDP monitor's backdrop properties
    a moment after the session starts.
    """
    result = {"quality": "high", "resolution_applied": False, "xfce_changed": False}
    try:
        quality = read_marker(marker) or os.environ.get("RDP_QUALITY") or "high"
        profile = resolve_profile(quality)
        result["quality"] = profile["quality"]
        result["max_bpp"] = profile["max_bpp"]

        if part in ("all", "resolution"):
            if profile.get("resolution") and profile.get("force_resolution", True):
                result["resolution_applied"] = apply_resolution(
                    profile["resolution"], runner=runner, log=log
                )

        if part in ("all", "xfce"):
            rounds = max(1, int(retries or 1))
            for attempt in range(rounds):
                try:
                    result["xfce_changed"] = apply_xfce(
                        profile, home=home, runner=runner
                    ) or result["xfce_changed"]
                except Exception as error:  # noqa: BLE001 - never fatal
                    if log:
                        log(f"XFCE profile attempt {attempt + 1} failed: {error}")
                if attempt + 1 < rounds and delay:
                    time.sleep(delay)

        result["ok"] = True
    except Exception as error:  # noqa: BLE001 - a desktop must still start
        result["ok"] = False
        result["error"] = f"{type(error).__name__}: {error}"
    return result


# --- CLI -------------------------------------------------------------------


def main(argv=None):
    """CLI used by the HTB VM script and the XFCE session launcher.

    Prints one JSON line. `apply` and `session` always exit 0: a profile that
    cannot be applied leaves the session usable.
    """
    import argparse

    parser = argparse.ArgumentParser(prog="runtime.rdp_quality")
    commands = parser.add_subparsers(dest="command")

    apply_parser = commands.add_parser("apply", help="configure xrdp and record the profile")
    apply_parser.add_argument("--quality", default="high")
    apply_parser.add_argument("--max-bpp", type=int, default=None)
    apply_parser.add_argument("--home", default="/root")
    apply_parser.add_argument("--xrdp-ini", default="/etc/xrdp/xrdp.ini")
    apply_parser.add_argument("--marker", default=RDP_QUALITY_FILE)

    session_parser = commands.add_parser("session", help="apply the in-session X settings")
    session_parser.add_argument("--home", default="/root")
    session_parser.add_argument("--marker", default=RDP_QUALITY_FILE)
    session_parser.add_argument(
        "--part",
        choices=("all", "resolution", "xfce"),
        default="all",
        help="resolution can run before XFCE; xfce needs the session bus",
    )
    session_parser.add_argument("--retries", type=int, default=1)
    session_parser.add_argument("--delay", type=float, default=0.0)

    show_parser = commands.add_parser("show", help="print a resolved profile")
    show_parser.add_argument("--quality", default="high")
    show_parser.add_argument("--max-bpp", type=int, default=None)

    try:
        args = parser.parse_args(argv)
    except SystemExit as exit_error:
        return int(exit_error.code or 0)

    if args.command == "show":
        print(json.dumps(resolve_profile(args.quality, args.max_bpp), sort_keys=True))
        return 0

    if args.command == "apply":
        result = apply(
            args.quality,
            args.max_bpp,
            home=args.home,
            xrdp_ini=args.xrdp_ini,
            marker=args.marker,
        )
    elif args.command == "session":
        result = session(
            home=args.home,
            marker=args.marker,
            log=lambda text: print(f"[RDP] {text}", file=sys.stderr),
            part=args.part,
            retries=args.retries,
            delay=args.delay,
        )
    else:
        parser.print_usage(sys.stderr)
        return 2

    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
