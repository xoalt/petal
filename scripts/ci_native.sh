#!/usr/bin/env bash
set -euo pipefail
export XDG_RUNTIME_DIR="$(mktemp -d)"
chmod 700 "$XDG_RUNTIME_DIR"

# Synthetic picker responses test callbacks using GTK local dialogs, not live portal requests.
export GDK_DEBUG=no-portals
export WAYLAND_DISPLAY=wayland-petal GSETTINGS_BACKEND=memory GTK_A11Y=none GDK_BACKEND=wayland
mkdir -p work
weston --backend=headless-backend.so --renderer=pixman --socket="$WAYLAND_DISPLAY" --width=1280 --height=1024 --idle-time=0 > work/weston.log 2>&1 &
petal_compositor_pid=$!
trap 'kill "$petal_compositor_pid" 2>/dev/null || true; rm -rf -- "$XDG_RUNTIME_DIR"' EXIT
for petal_attempt in $(seq 1 100); do
 if [[ -S "$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY" ]]; then break; fi
 if ! kill -0 "$petal_compositor_pid" 2>/dev/null; then cat work/weston.log; exit 1; fi
 sleep 0.1
done
[[ -S "$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY" ]]
dbus-update-activation-environment WAYLAND_DISPLAY XDG_RUNTIME_DIR GDK_BACKEND
bash scripts/run_native_checks.sh "$PWD/work/native"
