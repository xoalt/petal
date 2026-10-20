#!/usr/bin/env bash
set -euo pipefail
petal_root="$(cd -- "$(dirname -- "$0")/.." && pwd)"
export GSETTINGS_BACKEND=memory GIO_USE_VFS=local GDK_BACKEND=wayland GSK_RENDERER=cairo
for petal_lib in /usr/lib/libgtk4-layer-shell.so /usr/lib64/libgtk4-layer-shell.so /usr/lib/x86_64-linux-gnu/libgtk4-layer-shell.so; do
 if [[ -f "$petal_lib" ]]; then export LD_PRELOAD="$petal_lib${LD_PRELOAD:+:$LD_PRELOAD}"; break; fi
done
petal_reports="${1:-$petal_root/work/native}"
mkdir -p "$petal_reports"
python3 "$petal_root/tests/verify_onboarding.py" --output-dir "$petal_reports/onboarding"
python3 "$petal_root/tests/verify_asset_ui.py" --output-dir "$petal_reports/editors"
python3 "$petal_root/tests/verify_release_ui.py" --output-dir "$petal_reports/ux"

python3 "$petal_root/tests/verify_beta2_ui.py" --output-dir "$petal_reports/beta2"
