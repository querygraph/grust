export PYTHONHOME="$(.venv/bin/python -c 'import sys; print(sys.base_prefix)')"
export PYTHONPATH="$(.venv/bin/python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
export DYLD_LIBRARY_PATH="$(.venv/bin/python -c 'import sysconfig; print(sysconfig.get_config_var("LIBDIR") or "")')"
export LD_LIBRARY_PATH="$DYLD_LIBRARY_PATH"
export SAIL_EXPERIMENTAL_EXTENSIONS=1
export SAIL_EXECUTION__DEFAULT_PARALLELISM=4
export SAIL_CLUSTER__WORKER_INITIAL_COUNT=2
export SAIL_CLUSTER__WORKER_MAX_COUNT=2
SAIL_MODE=local SAIL_EXPERIMENTAL_PROCESS_WORKERS=0 \
  target/extensions-poc/host/debug/sail spark server --ip 127.0.0.1 --port 50051
