"""Exec the existing native worker, retaining its PID and a separate raw log."""
import argparse
import json
import os
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    pid = os.getpid()
    identity = {
        "pid": pid, "pgid": os.getpgid(pid), "ppid": os.getppid(),
        "worker_id": os.environ.get("SAIL_CLUSTER__WORKER_ID"),
        "session_id": os.environ.get("SAIL_CLUSTER__SESSION_ID"),
        "dyld_library_path": os.environ.get("DYLD_LIBRARY_PATH"),
        "argv": [str(args.binary), "worker"],
    }
    with (args.output / f"worker-{pid}.json").open("x") as stream:
        stream.write(json.dumps(identity, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    fd = os.open(args.output / f"worker-{pid}.log", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.dup2(fd, 1)
    os.dup2(fd, 2)
    os.close(fd)
    os.execv(args.binary, [str(args.binary), "worker"])


if __name__ == "__main__":
    main()
