"""Run Spark 4.2.1's unmodified Python SDP tests against a Sail server.

Example:
    .venv/bin/python scripts/spark-pipelines-tests/run.py \
        --spark-source ../spark-sdp-4.2.1 --remote sc://localhost:50051 \
        --report /tmp/sail-sdp-python.json

This runner deliberately does not load Sail's general Spark compatibility
plugin: no assertion normalization, xfails, or test deselection are applied.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

SPARK_VERSION = "4.2.1"
SPARK_COMMIT = "617618396087429b5627a86ce933bb0f5d6645cb"


class Result(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.outcomes = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.outcomes.append({"id": test.id(), "outcome": "passed"})

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.outcomes.append({"id": test.id(), "outcome": "failed", "detail": self.failures[-1][1]})

    def addError(self, test, err):
        super().addError(test, err)
        self.outcomes.append({"id": test.id(), "outcome": "error", "detail": self.errors[-1][1]})

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.outcomes.append({"id": test.id(), "outcome": "skipped", "detail": reason})


def test_ids(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from test_ids(test)
        else:
            yield test.id()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spark-source", type=Path, required=True)
    parser.add_argument("--remote", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    source = args.spark_source.resolve()
    commit = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if commit != SPARK_COMMIT:
        parser.error(f"Expected Spark {SPARK_VERSION} at {SPARK_COMMIT}, found {commit}")
    subprocess.run(
        [
            "git",
            "-C",
            str(source),
            "diff",
            "--exit-code",
            "HEAD",
            "--",
            "python/pyspark/pipelines/tests",
        ],
        check=True,
    )
    if not args.remote.startswith("sc://"):
        parser.error("--remote must name a Spark Connect server (sc://…)")

    os.environ["SPARK_CONNECT_TESTING_REMOTE"] = args.remote
    # Upstream's remote-only switch prevents the shared fixture from looking for
    # a local JVM SparkSession. None of the SDP cases are JVM-only compatibility
    # tests; any unexpected skips still fail this runner.
    os.environ["SPARK_SKIP_CONNECT_COMPAT_TESTS"] = "1"
    os.environ["SPARK_CONNECT_MODE_ENABLED"] = "1"

    import pyspark
    import pyspark.pipelines
    from pyspark.sql import SparkSession

    if pyspark.__version__ != SPARK_VERSION:
        parser.error(f"Install pyspark[connect,pipelines]=={SPARK_VERSION}; found {pyspark.__version__}")
    session = SparkSession.builder.remote(args.remote).create()
    try:
        server_version = session.version
    finally:
        session.stop()
    if server_version != SPARK_VERSION:
        parser.error(
            f"Expected the server to report Spark {SPARK_VERSION}; found {server_version}. "
            "Ensure the Sail server's Python environment contains the pinned PySpark version."
        )
    # Wheels omit the upstream tests. Add just the source tests, continuing to
    # use the installed, version-pinned PySpark implementation and test helpers.
    pyspark.pipelines.__path__.append(str(source / "python/pyspark/pipelines"))
    suite = unittest.TestSuite()
    for path in sorted((source / "python/pyspark/pipelines/tests").glob("test_*.py")):
        module = importlib.import_module(f"pyspark.pipelines.tests.{path.stem}")
        if Path(module.__file__).resolve() != path.resolve():
            raise RuntimeError(f"Unexpected test module location: {module.__file__}")
        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
    collected = list(test_ids(suite))
    if not collected:
        raise RuntimeError("No upstream tests collected")
    result = unittest.TextTestRunner(verbosity=2, resultclass=Result).run(suite)
    report = {
        "spark_version": SPARK_VERSION,
        "spark_commit": commit,
        "server_spark_version": server_version,
        "remote": args.remote,
        "collected": collected,
        "tests_run": result.testsRun,
        "outcomes": result.outcomes,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    return 0 if result.wasSuccessful() and not result.skipped and result.testsRun == len(collected) else 1


if __name__ == "__main__":
    sys.exit(main())
