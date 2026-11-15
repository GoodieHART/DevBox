"""
DevBox identity: box names, hostname rewriting, and the identity surfaces.

Every Modal container starts with the same generic hostname, so `hostname`,
`uname -n` and the shell prompt give no clue which box is which. This module
gives a box a name derived from its launch context and applies that name
wherever the runtime allows.

Two runtimes, two capabilities:

* **Modal VM Sandbox** (`runtime="vm"`): a full VM with its own kernel.
  ``socket.sethostname`` works, ``/etc/hostname`` and ``/etc/hosts`` are
  writable and ``/dev/net/tun`` exists. The kernel hostname becomes the box
  name and the name resolves as a local FQDN.
* **Modal Function**: an ordinary container. ``socket.sethostname`` fails
  with EPERM (no CAP_SYS_ADMIN) and ``unshare --uts`` is blocked, so the
  kernel hostname keeps the value Modal set. The name still reaches the name
  file, the login banner, the tmux status bar and the shell prompt.

A failure is reported and never fatal.

This module imports no ``modal`` package: the HTB VM Sandbox image ships it,
and that image has none.
"""

import os
import re
import socket
import uuid


# The name file is the canonical record of a box's identity. The tmux status
# bar and the shell prompt read it, so neither needs the name at build time.
BOX_NAME_FILE = "/etc/devbox/name"

# Prefix on every generated name, so DevBox nodes are recognisable in a tailnet
# and do not collide with other nodes.
BOX_NAME_PREFIX = "devbox"

# DNS label limit. Tailscale machine names and /etc/hosts entries both have to
# fit inside it.
BOX_NAME_MAX = 63

# Short random suffix, so two boxes of the same kind can run at once.
BOX_NAME_SUFFIX_LENGTH = 4

# devbox_type -> the slug used inside a generated name.
#
# GPU variants all collapse to one "gpu" slug. The specific card is
# discoverable with `nvidia-smi` and would only make the name longer.
BOX_KINDS = {
    "standard_devbox": "std",
    "cuda_devbox_t4": "gpu",
    "cuda_devbox_l4": "gpu",
    "cuda_devbox_a10g": "gpu",
    "cuda_devbox_l40s": "gpu",
    "rdp_devbox": "rdp",
    "assisted_coding": "coding",
    "opencode": "coding",
    "llm_playroom": "llm",
    "forensic_analysis": "forensics",
    "llamacpp_cpu": "llamacpp",
    "llamacpp_gpu": "llamacpp-gpu",
}

# Anything that is not a lowercase letter, digit or hyphen becomes a hyphen.
_UNSAFE = re.compile(r"[^a-z0-9-]+")
_REPEATED_HYPHENS = re.compile(r"-{2,}")


def short_id(length=BOX_NAME_SUFFIX_LENGTH):
    """A short random suffix that keeps two same-kind boxes apart.

    Same uuid4 convention as `runtime.cost_tracker`.
    """
    return uuid.uuid4().hex[:length]


def sanitize_box_name(raw):
    """Reduce arbitrary input to a DNS-safe DevBox name.

    Lowercases, replaces every unsafe run with a single hyphen, collapses
    repeated hyphens and trims the ends. Returns "" when nothing usable is
    left, so callers can fall back to a generated name.
    """
    if not raw:
        return ""
    name = _UNSAFE.sub("-", str(raw).strip().lower())
    name = _REPEATED_HYPHENS.sub("-", name).strip("-")
    return name[:BOX_NAME_MAX].strip("-")


def build_box_name(kind, htb=False, custom=None, shortid=None):
    """Build a DevBox name.

    A caller-supplied `custom` name wins and is sanitised before use. A
    generated name is `devbox[-htb]-<kind>-<shortid>`.
    """
    if custom:
        cleaned = sanitize_box_name(custom)
        if cleaned:
            return cleaned

    parts = [BOX_NAME_PREFIX]
    if htb:
        parts.append("htb")
    parts.append(kind or "box")
    parts.append(shortid or short_id())
    return "-".join(parts)


def resolve_box_name(devbox_type, htb=False, custom=None):
    """The name for a box of `devbox_type`, optionally running the HTB VM."""
    kind = BOX_KINDS.get(devbox_type, "box")
    return build_box_name(kind, htb=htb, custom=custom)


def write_name_file(name, path=BOX_NAME_FILE):
    """Record the box name where the surfaces can find it."""
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(f"{name}\n")
    return path


def read_name_file(path=BOX_NAME_FILE):
    """The recorded box name, or None when the box has no identity yet."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            name = handle.read().strip()
    except OSError:
        return None
    return name or None


def _update_etc_hosts(name):
    """Point the box's own address at its name, keeping Modal's alias.

    Modal writes `<ip> main` into /etc/hosts. Rewriting that line to
    `<ip> <name> main` makes the name the canonical name for the address
    while leaving `main` resolvable, so nothing that depends on Modal's
    alias breaks.

    Returns True when the file was rewritten.
    """
    path = "/etc/hosts"
    try:
        with open(path, "r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return False

    rewritten = []
    updated = False
    for line in lines:
        fields = line.split()
        is_container_line = (
            not updated
            and len(fields) >= 2
            and fields[0] not in ("127.0.0.1", "::1")
            and not fields[0].startswith("fd")
        )
        if is_container_line:
            address = fields[0]
            aliases = [field for field in fields[1:] if field != name]
            rewritten.append(" ".join([address, name] + aliases))
            updated = True
        else:
            rewritten.append(line)

    if not updated:
        return False

    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(rewritten) + "\n")
    except OSError:
        return False
    return True


def _set_kernel_hostname(name):
    """Set the kernel hostname. Returns (changed, reason)."""
    try:
        socket.sethostname(name)
    except OSError as error:
        # Function containers have no CAP_SYS_ADMIN, so this is EPERM there.
        return False, f"kernel hostname unchanged: {error}"

    try:
        with open("/etc/hostname", "w", encoding="utf-8") as handle:
            handle.write(f"{name}\n")
    except OSError:
        # Cosmetic only; the kernel hostname is the part that matters.
        pass

    _update_etc_hosts(name)
    return True, ""


def apply_box_identity(name, set_hostname=True):
    """Apply the box identity to the current process.

    Never raises. A box that cannot rename itself still gets its name file,
    so the banner, the tmux bar and the prompt can still identify it.

    Returns a dict with the name, whether the kernel hostname changed, and a
    human-readable reason when something could not be done.
    """
    result = {"name": name, "hostname_changed": False, "reason": ""}

    try:
        write_name_file(name)
    except OSError as error:
        result["reason"] = f"name file not written: {error}"

    if set_hostname:
        changed, reason = _set_kernel_hostname(name)
        result["hostname_changed"] = changed
        if not changed and reason:
            result["reason"] = reason

    return result


def apply_sandbox_identity(sandbox, name):
    """Apply the box identity inside a Modal Sandbox.

    The sandbox image ships this module, so the same implementation runs
    there. A sandbox that refuses is reported, not fatal.

    Returns the same dict shape as `apply_box_identity`.
    """
    result = {"name": name, "hostname_changed": False, "reason": ""}

    script = (
        "import json, sys\n"
        "from devbox_core.box_identity import apply_box_identity\n"
        "print(json.dumps(apply_box_identity(sys.argv[1])))\n"
    )
    try:
        process = sandbox.exec("python3", "-c", script, name)
        output = process.stdout.read()
        process.stderr.read()
        process.wait()
    except Exception as error:  # noqa: BLE001 - identity must never be fatal
        result["reason"] = f"identity script failed: {error}"
        return result

    import json

    for line in (output or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except ValueError:
            continue
        result["hostname_changed"] = bool(payload.get("hostname_changed"))
        result["reason"] = payload.get("reason", "")
    return result


def banner_text(name, icon, title, extra_lines=()):
    """The login banner body shared by every DevBox type.

    `extra_lines` are the per-type detail rows, e.g. "💾 Persistent: /data".

    `name` is optional. A box with a DevBox identity shows it as a row; a
    Function container cannot change its kernel hostname and passes None, so
    the row is omitted.
    """
    rows = [f"{icon} {title}"]
    if name:
        rows.append(f"🏷️  {name}")
    rows.extend(extra_lines)
    # `║  ` + 35 columns + ` ║` is 40 characters, matching the 40-character
    # border, so the two stay aligned.
    width = 35
    border = "╔" + "═" * 38 + "╗"
    footer = "╚" + "═" * 38 + "╝"
    body = [border]
    for row in rows:
        body.append(f"║  {row:<{width}} ║")
    body.append(footer)
    return "\n".join(body) + "\n"


def write_banner(name, icon, title, extra_lines=(), path="/etc/devbox-banner"):
    """Write the login banner that `/etc/profile.d/devbox-banner.sh` shows."""
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(banner_text(name, icon, title, extra_lines))
    return path
