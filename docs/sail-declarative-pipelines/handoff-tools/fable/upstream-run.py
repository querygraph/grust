"""Start an in-process PySail Spark Connect server and run Sail's pinned upstream SDP Python tests against it."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from pysail.spark import SparkConnectServer


def main() -> int:
    worktree = Path(sys.argv[1])
    spark_source = Path(sys.argv[2])
    report = Path(sys.argv[3])
    server = SparkConnectServer("127.0.0.1", 0)
    server.start(background=True)
    try:
        _, port = server.listening_address
        print(f"server sc://localhost:{port}", flush=True)
        return subprocess.call(
            [
                sys.executable,
                str(worktree / "scripts/spark-pipelines-tests/run.py"),
                "--spark-source",
                str(spark_source),
                "--remote",
                f"sc://localhost:{port}",
                "--report",
                str(report),
            ]
        )
    finally:
        server.stop()


if __name__ == "__main__":
    sys.exit(main())
