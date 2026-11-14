#!/bin/sh
# DevBox tmux session bootstrap, shared by the Function runtimes
# (`start_tmux_session()`) and the HTB VM entrypoint so config, window names,
# and mouse support stay identical. Baked at /usr/local/bin/devbox-tmux.
#
# Usage: devbox-tmux [session-name] [window-count]
# Exit: 0 when the session exists afterwards, 1 when it could not be created.

set -u

session=${1:-devbox}
windows=${2:-3}
config=/etc/devbox/tmux.conf

warn() {
    printf '%s\n' "$*" >&2
}

# `restore_backup()` can replace /root, so re-link the config on every launch.
# A restored regular file is removed first: it would shadow the baked config.
if [ -f "$config" ]; then
    if [ -L /root/.tmux.conf ]; then
        :
    elif [ -e /root/.tmux.conf ]; then
        rm -f /root/.tmux.conf && ln -s "$config" /root/.tmux.conf
    else
        ln -s "$config" /root/.tmux.conf
    fi
fi

if ! command -v tmux >/dev/null 2>&1; then
    warn "warning: tmux is not installed; no session was created"
    exit 1
fi

# Load the baked config explicitly: tmux never reads /etc/devbox on its own.
if [ -f "$config" ]; then
    set -- -f "$config"
else
    set --
fi

# Replace any session left behind by a restored container.
tmux kill-session -t "$session" >/dev/null 2>&1 || true

if ! tmux "$@" new-session -d -s "$session" -n window-1 >/dev/null 2>&1; then
    warn "warning: could not start the '$session' tmux session"
    exit 1
fi

window=2
while [ "$window" -le "$windows" ]; do
    tmux new-window -t "$session" -n "window-$window" >/dev/null 2>&1 ||
        warn "warning: could not create window-$window"
    window=$((window + 1))
done

# Also set here so a missing or stale config still gets working mouse support.
tmux set-option -g mouse on >/dev/null 2>&1 || true

# Select by name: base-index 1 in the config means window 0 does not exist.
tmux select-window -t "$session:window-1" >/dev/null 2>&1 || true

if ! tmux has-session -t "$session" >/dev/null 2>&1; then
    warn "warning: tmux reported no '$session' session after startup"
    exit 1
fi

exit 0
