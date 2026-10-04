#!/bin/zsh
# serve.sh <port> [NAME=value ...]: a release Sail server in local mode with the harness's settings.
W=$HOME/src/sail-pecan-integrated; PY=$W/.venv/bin/python; port=$1; shift
export PYTHONHOME=$($PY -c 'import sys; print(sys.base_prefix)')
export PYTHONPATH=$($PY -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')
export DYLD_LIBRARY_PATH=$($PY -c 'import sysconfig; print(sysconfig.get_config_var("LIBDIR"))')
mkdir -p $W/target/staging-$port
export SAIL_EXPERIMENTAL_EXTENSIONS=1 SAIL_MODE=local SAIL_GRAPH_UTILS_ROOT=file://$W/target/staging-$port \
  SAIL_EXECUTION__DEFAULT_PARALLELISM=10 SAIL_RUNTIME__MEMORY_POOL__TYPE=greedy \
  SAIL_RUNTIME__MEMORY_POOL__GREEDY__MAX_SIZE=$((30 * 1024 * 1024 * 1024)) TOKIO_WORKER_THREADS=10 RAYON_NUM_THREADS=10 RUST_LOG=warn
for pair in "$@"; do export "$pair"; done
exec $W/target/host/release/sail spark server --ip 127.0.0.1 --port $port > $W/target/host-server-$port.log 2>&1
