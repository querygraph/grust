#!/usr/bin/env bash
# Reproducible local PoC: one host executable, two independent native wheels.
set -euo pipefail
repo=$(cd "$(dirname "$0")/../../.." && pwd)
base="$repo/examples/extensions"
venv=${SAIL_EXTENSION_VENV:-"$repo/.venv"}
target=${SAIL_EXTENSION_TARGET:-"$repo/target/extensions-poc"}
python=${SAIL_EXTENSION_PYTHON:-python3.12}
export CARGO_INCREMENTAL=0 CARGO_PROFILE_DEV_DEBUG=0
export CARGO_BUILD_JOBS=${CARGO_BUILD_JOBS:-4}
df -h "$repo"
if [[ ! -x "$venv/bin/python" ]]; then
    uv venv --python "$python" "$venv"
fi
uv pip sync --python "$venv/bin/python" "$base/requirements.lock"
export PYO3_PYTHON="$venv/bin/python"
if [[ "$(uname -s)" == Darwin ]]; then
    export DYLD_LIBRARY_PATH=$("$venv/bin/python" -c 'import sysconfig; print(sysconfig.get_config_var("LIBDIR"))')
else
    export LD_LIBRARY_PATH=$("$venv/bin/python" -c 'import sysconfig; print(sysconfig.get_config_var("LIBDIR"))')
fi
"$venv/bin/python" "$base/sedona/scripts/prepare.py"
mkdir -p "$target/wheels"
for package in sedona nutmeg; do
    raw=$(mktemp -d "$target/raw-wheel-$package.XXXXXX")
    CARGO_TARGET_DIR="$target/$package" "$venv/bin/python" -m maturin build \
        --manifest-path "$base/$package/Cargo.toml" --locked --profile dev \
        --interpreter "$venv/bin/python" --out "$raw" --auditwheel repair
    if [[ "$(uname -s)" == Darwin ]]; then
        "$venv/bin/python" -m delocate.cmd.delocate_wheel -v -w "$raw/repaired" "$raw"/*.whl
        raw="$raw/repaired"
    fi
    for wheel in "$raw"/*.whl; do
        if [[ "$package" == sedona ]]; then
            "$venv/bin/python" "$base/scripts/check_wheel.py" "$wheel" \
                --output "$target/sedona-native-dependencies.json"
        fi
        # A repaired macOS wheel may acquire a newer minimum OS tag. Remove
        # stale variants of this package so pip cannot pick the unrepaired one.
        "$venv/bin/python" - "$wheel" "$target/wheels" <<'PY'
from pathlib import Path
import shutil
import sys
wheel, output = map(Path, sys.argv[1:])
for old in output.glob(wheel.name.split('-')[0] + '-*.whl'):
    old.unlink()
shutil.copy2(wheel, output / wheel.name)
PY
    done
done
uv pip install --python "$venv/bin/python" --reinstall "$target"/wheels/*.whl
# Pecan keeps its established source directory; its distribution is pyspark-pecan.
uv pip install --python "$venv/bin/python" --no-deps "$base/graph-algorithms"
CARGO_TARGET_DIR="$target/host" cargo build --manifest-path "$repo/Cargo.toml" --locked -p sail-cli
printf 'Host: %s\nPython: %s\nWheels: %s\n' "$target/host/debug/sail" "$venv/bin/python" "$target/wheels"
