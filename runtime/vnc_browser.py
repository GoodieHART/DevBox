"""Headless Chromium over noVNC for DevBox graphical sessions.

The shell script is the single source of truth used inside the HTB VM sandbox.

Security model: every listener is loopback-only. The phone reaches noVNC through
an SSH local forward (`-L 6080:127.0.0.1:6080`), never through a Modal tunnel.
"""

from devbox_core.config import (
    NOVNC_PORT,
    NOVNC_WEB_ROOT,
    VNC_DISPLAY,
    VNC_GEOMETRY,
    VNC_LOG_DIR,
    VNC_PROFILE_DIR,
    VNC_RFB_PORT,
)


_VNC_BROWSER_TEMPLATE = r'''#!/bin/sh
set -u

DISPLAY_NUM="__VNC_DISPLAY__"
GEOMETRY="__VNC_GEOMETRY__"
PROFILE="__VNC_PROFILE_DIR__"
LOG_DIR="__VNC_LOG_DIR__"
WEB_ROOT="__NOVNC_WEB_ROOT__"
RFB_PORT="__VNC_RFB_PORT__"
NOVNC_PORT="__NOVNC_PORT__"

mkdir -p "$PROFILE" "$LOG_DIR"
chmod 700 "$PROFILE" 2>/dev/null || true

WIDTH=${GEOMETRY%%x*}
REST=${GEOMETRY#*x}
HEIGHT=${REST%%x*}

is_running() {
    pgrep -f "$1" >/dev/null 2>&1
}

display_ready() {
    DISPLAY="$DISPLAY_NUM" xdpyinfo >/dev/null 2>&1
}

# Xvfb owns the virtual screen. A stale lock from a previous container must be
# removed, but only when no Xvfb is already starting for this display.
if ! display_ready; then
    if ! is_running "Xvfb $DISPLAY_NUM"; then
        rm -f "/tmp/.X${DISPLAY_NUM#:}-lock" "/tmp/.X11-unix/X${DISPLAY_NUM#:}"
        setsid nohup Xvfb "$DISPLAY_NUM" -screen 0 "$GEOMETRY" -nolisten tcp \
            >"$LOG_DIR/xvfb.log" 2>&1 &
    fi
    for _ in $(seq 1 50); do
        display_ready && break
        sleep 0.2
    done
    if ! display_ready; then
        echo "vnc_browser: Xvfb failed on $DISPLAY_NUM; see $LOG_DIR/xvfb.log" >&2
        exit 1
    fi
fi

if ! is_running "openbox"; then
    DISPLAY="$DISPLAY_NUM" setsid nohup openbox \
        >"$LOG_DIR/openbox.log" 2>&1 &
    for _ in $(seq 1 25); do
        is_running "openbox" && break
        sleep 0.2
    done
    if ! is_running "openbox"; then
        echo "vnc_browser: openbox did not start; see $LOG_DIR/openbox.log" >&2
    fi
fi

# Chromium writes Singleton* files into the profile. The profile lives on the
# persistent volume, so a relaunch can leave locks from a dead container.
if ! is_running "chromium.*--user-data-dir=$PROFILE"; then
    rm -f "$PROFILE/SingletonLock" "$PROFILE/SingletonSocket" "$PROFILE/SingletonCookie"
    DISPLAY="$DISPLAY_NUM" setsid nohup chromium \
        --no-sandbox \
        --disable-dev-shm-usage \
        --disable-gpu \
        --no-first-run \
        --no-default-browser-check \
        --hide-crash-restore-bubble \
        --password-store=basic \
        --user-data-dir="$PROFILE" \
        --window-size="$WIDTH,$HEIGHT" \
        --window-position=0,0 \
        --start-maximized \
        about:blank >"$LOG_DIR/chromium.log" 2>&1 &
    for _ in $(seq 1 150); do
        is_running "chromium.*--user-data-dir=$PROFILE" && break
        sleep 0.2
    done
    if ! is_running "chromium.*--user-data-dir=$PROFILE"; then
        echo "vnc_browser: Chromium failed; see $LOG_DIR/chromium.log" >&2
        exit 1
    fi
fi

if ! is_running "x11vnc.*-rfbport $RFB_PORT"; then
    setsid nohup x11vnc -display "$DISPLAY_NUM" -localhost -forever -shared \
        -nopw -quiet -rfbport "$RFB_PORT" >"$LOG_DIR/x11vnc.log" 2>&1 &
fi

# This websockify build has no --listen-host; the source address in the
# positional argument is what keeps the listener on loopback.
if ! is_running "websockify.*:$NOVNC_PORT"; then
    setsid nohup websockify --web="$WEB_ROOT" "127.0.0.1:$NOVNC_PORT" \
        "127.0.0.1:$RFB_PORT" >"$LOG_DIR/websockify.log" 2>&1 &
fi

for _ in $(seq 1 50); do
    if ss -ltn 2>/dev/null | awk '{print $4}' | grep -qx "127.0.0.1:$RFB_PORT" && \
       ss -ltn 2>/dev/null | awk '{print $4}' | grep -qx "127.0.0.1:$NOVNC_PORT"; then
        break
    fi
    sleep 0.2
done

if ! ss -ltn 2>/dev/null | awk '{print $4}' | grep -qx "127.0.0.1:$RFB_PORT"; then
    echo "vnc_browser: x11vnc did not bind 127.0.0.1:$RFB_PORT; see $LOG_DIR/x11vnc.log" >&2
    exit 1
fi
if ! ss -ltn 2>/dev/null | awk '{print $4}' | grep -qx "127.0.0.1:$NOVNC_PORT"; then
    echo "vnc_browser: websockify did not bind 127.0.0.1:$NOVNC_PORT; see $LOG_DIR/websockify.log" >&2
    exit 1
fi

echo "vnc_browser: noVNC ready at http://127.0.0.1:$NOVNC_PORT/vnc.html?autoconnect=1&resize=scale"
'''


VNC_BROWSER_SCRIPT = (
    _VNC_BROWSER_TEMPLATE
    .replace("__VNC_DISPLAY__", VNC_DISPLAY)
    .replace("__VNC_GEOMETRY__", VNC_GEOMETRY)
    .replace("__VNC_PROFILE_DIR__", VNC_PROFILE_DIR)
    .replace("__VNC_LOG_DIR__", VNC_LOG_DIR)
    .replace("__NOVNC_WEB_ROOT__", NOVNC_WEB_ROOT)
    .replace("__VNC_RFB_PORT__", str(VNC_RFB_PORT))
    .replace("__NOVNC_PORT__", str(NOVNC_PORT))
)
