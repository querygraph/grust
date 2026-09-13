"""Retain each process outcome before the companion's correctness comparisons."""
import datetime
import functools
import hashlib
import json
import os
from pathlib import Path
import subprocess


def capture(execute):
    @functools.wraps(execute)
    def run(exe, graph, algorithm, source, output):
        receipt = {
            "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "executable": str(exe), "graph": str(graph), "algorithm": algorithm,
            "source": source,
        }
        try:
            metrics, values = execute(exe, graph, algorithm, source, output)
            receipt.update(status="completed", metrics=metrics,
                           output_sha256=hashlib.sha256(output.read_bytes()).hexdigest())
            return metrics, values
        except subprocess.TimeoutExpired as error:
            receipt.update(status="timeout", error=str(error), stdout=str(error.stdout), stderr=str(error.stderr))
            raise
        except FileNotFoundError as error:
            receipt.update(status="unavailable", error=str(error))
            raise
        except Exception as error:
            receipt.update(status="error", error=str(error), stdout=str(getattr(error, "stdout", "")),
                           stderr=str(getattr(error, "stderr", "")), exit_code=getattr(error, "returncode", None))
            raise
        finally:
            label = os.environ.get("BENCH_AUDIT_LABEL", "validation")
            if not label or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in label):
                raise ValueError("invalid audit label")
            directory = Path(os.environ.get("BENCH_RESULTS_DIR", "/work/results"))
            directory.mkdir(parents=True, exist_ok=True)
            with (directory / f"{label}-processes.jsonl").open("a") as stream:
                stream.write(json.dumps(receipt) + "\n")
    return run
