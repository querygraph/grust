"""Register or execute unmodified Scala suites on Spark, never on Sail.

Each execution uses one fresh JVM and records an explicit Spark-reference scope.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shlex
import signal
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from artifacts import (
    SPARK_PIN,
    Binding,
    bind_sources,
    digest,
    load_manifest,
    load_scope,
    prepare,
)

BUNDLE = Path(__file__).resolve().parent
LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class Check:
    command: list[str]
    exit_code: int
    log: str
    sha256: str
    timed_out: bool


@dataclass(slots=True)
class Receipt:
    mode: str
    started_at: str
    scope: str = "Original ScalaTest binaries on Spark reference; no Sail execution"
    source_pin: str = SPARK_PIN
    outcome: str = "running"
    bindings: list[Binding] = field(default_factory=list)
    runtime_sha256: dict[str, str] = field(default_factory=dict)
    environment: dict[str, str] = field(default_factory=dict)
    tool_sha256: dict[str, str] = field(default_factory=dict)
    output_sha256: dict[str, str] = field(default_factory=dict)
    checks: list[Check] = field(default_factory=list)
    error: str | None = None
    completed_at: str | None = None


def now() -> str:
    return datetime.now(UTC).isoformat()


def command(
    argv: list[str], output: Path, label: str, env: dict[str, str], timeout: int
) -> Check:
    log = output / f"{label}.log"
    timed_out = False
    with log.open("x") as stream:
        child = subprocess.Popen(
            argv,
            cwd=output,
            env=env,
            stdout=stream,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            child.wait(timeout=timeout)
        except BaseException:
            timed_out = sys.exc_info()[0] is subprocess.TimeoutExpired
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
            if not timed_out:
                raise
    return Check(argv, child.returncode, log.name, digest(log), timed_out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spark-source", type=Path, required=True)
    parser.add_argument("--spark-home", type=Path, required=True)
    parser.add_argument("--java-home", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=1800)
    sub = parser.add_subparsers(dest="mode", required=True)
    sub.add_parser("collect")
    run = sub.add_parser("run")
    run.add_argument("--suite", required=True)
    run.add_argument("--registration", type=Path, required=True)
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir()  # Existing attempts are never overwritten.
    receipt = Receipt(args.mode, now())
    receipt.tool_sha256 = {
        path.name: digest(path)
        for path in (
            BUNDLE / "run.py",
            BUNDLE / "artifacts.py",
            BUNDLE / "EnumerateSuites.scala",
            BUNDLE / "artifacts.json",
            BUNDLE / "scope.json",
        )
    }
    try:
        manifest = load_manifest(BUNDLE / "artifacts.json")
        scopes = load_scope(BUNDLE / "scope.json")
        extra_sources = {path for scope in scopes for path in scope.source_files}
        for name in ("spark_source", "spark_home", "java_home", "python", "cache"):
            setattr(args, name, getattr(args, name).resolve())
        if args.timeout <= 0:
            raise ValueError("Timeout must be positive")
        prepare(args.cache, manifest)
        receipt.bindings = bind_sources(
            args.spark_source, args.cache, manifest, extra_sources
        )
        runtime = sorted((args.spark_home / "jars").glob("spark-*.jar"))
        if not (args.spark_home / "jars/spark-core_2.13-4.2.1.jar").is_file():
            raise ValueError("Expected a Spark 4.2.1 runtime")
        receipt.runtime_sha256 = {path.name: digest(path) for path in runtime}
        receipt.environment = {
            "JAVA_HOME": str(args.java_home),
            "SPARK_LOCAL_IP": "127.0.0.1",
            "PYSPARK_PYTHON": str(args.python),
            "PYSPARK_DRIVER_PYTHON": str(args.python),
        }
        env = {**os.environ, **receipt.environment}
        for key in ("SPARK_REMOTE", "SPARK_CONNECT_MODE_ENABLED", "SPARK_LOCAL_REMOTE"):
            env.pop(key, None)
        env["SPARK_HOME"] = str(args.spark_home)
        java = args.java_home / "bin/java"
        submit = [
            str(args.spark_home / "bin/spark-submit"),
            "--master",
            "local[2]",
            "--driver-class-path",
            str(args.cache / "*"),
            "--driver-java-options",
            shlex.join(
                [
                    "-ea",
                    "-Dspark.testing=1",
                    f"-Dspark.test.home={args.spark_source}",
                    f"-Djava.io.tmpdir={args.output / 'tmp'}",
                ]
            ),
            "--class",
        ]
        (args.output / "tmp").mkdir()

        def checked(argv: list[str], label: str) -> None:
            result = command(argv, args.output, label, env, args.timeout)
            receipt.checks.append(result)
            (args.output / "receipt.json").write_text(
                json.dumps(asdict(receipt), indent=2) + "\n"
            )
            if result.exit_code or result.timed_out:
                raise RuntimeError(
                    f"{label} failed: inspect {args.output / result.log}"
                )

        if args.mode == "collect":
            classes = args.output / "classes"
            classes.mkdir()
            checked(
                [
                    str(java),
                    "-cp",
                    str(args.spark_home / "jars/*")
                    + os.pathsep
                    + str(args.cache / "*"),
                    "scala.tools.nsc.Main",
                    "-usejavacp",
                    "-d",
                    str(classes),
                    str(BUNDLE / "EnumerateSuites.scala"),
                ],
                "compile",
            )
            jar = args.output / "enumerator.jar"
            checked(
                [
                    str(args.java_home / "bin/jar"),
                    "cf",
                    str(jar),
                    "-C",
                    str(classes),
                    ".",
                ],
                "jar",
            )
            checked(
                submit
                + [
                    "org.apache.spark.sql.pipelines.conformance.EnumerateSuites",
                    str(jar),
                    str(args.output / "suites.json"),
                    str(BUNDLE / "scope.json"),
                ]
                + [
                    str(args.cache / f"spark-{module}_2.13-4.2.1-tests.jar")
                    for module in ("pipelines", "connect", "hive", "sql")
                ],
                "register",
            )
            rows = json.loads((args.output / "suites.json").read_text())
            if any(
                row["status"] == "unresolved" or row["nestedSuiteIds"] for row in rows
            ):
                raise RuntimeError(
                    "Unresolved classes or unexpanded nested suites remain"
                )
            if not any(row["testNames"] for row in rows):
                raise RuntimeError("No runtime tests registered")
            receipt.output_sha256["suites.json"] = digest(args.output / "suites.json")
        else:
            registration = args.registration.resolve()
            provenance = json.loads(registration.with_name("receipt.json").read_text())
            if (
                provenance["mode"] != "collect"
                or provenance["outcome"] != "passed"
                or provenance["source_pin"] != SPARK_PIN
                or provenance["tool_sha256"] != receipt.tool_sha256
                or provenance["runtime_sha256"] != receipt.runtime_sha256
            ):
                raise ValueError(
                    "Registration must come from this exact tool/runtime profile"
                )
            if digest(registration) != provenance["output_sha256"]["suites.json"]:
                raise ValueError("Registration bytes changed after collection")
            rows = json.loads(registration.read_text())
            matches = [
                row
                for row in rows
                if row["className"] == args.suite
                and row["status"] == "registered"
                and row["testNames"]
            ]
            if len(matches) != 1:
                raise ValueError("Suite must occur once with nonempty registered tests")
            (args.output / "registration.json").write_bytes(registration.read_bytes())
            (args.output / "xml").mkdir()
            checked(
                submit
                + [
                    "org.scalatest.tools.Runner",
                    str(args.cache / "scalatest-app_2.13-3.2.19.jar"),
                    "-s",
                    args.suite,
                    *[
                        value
                        for name in (
                            matches[0]["testNames"]
                            if matches[0]["selection"] == "named"
                            else []
                        )
                        for value in ("-t", name)
                    ],
                    "-o",
                    "-u",
                    str(args.output / "xml"),
                ],
                "suite",
            )
            cases = [
                case
                for path in (args.output / "xml").glob("*.xml")
                for case in ET.parse(path).iter("testcase")
            ]
            names = [case.attrib["name"] for case in cases]
            if (
                len(names) != len(matches[0]["testNames"])
                or set(names) != set(matches[0]["testNames"])
                or any(list(case) for case in cases)
            ):
                raise RuntimeError(
                    "XML outcomes do not prove every registered test passed"
                )
            receipt.output_sha256.update(
                {
                    str(path.relative_to(args.output)): digest(path)
                    for path in sorted((args.output / "xml").glob("*.xml"))
                }
            )
        prepare(args.cache, manifest)
        if receipt.runtime_sha256 != {path.name: digest(path) for path in runtime}:
            raise RuntimeError("Runtime artifacts changed during execution")
        if receipt.bindings != bind_sources(
            args.spark_source, args.cache, manifest, extra_sources
        ):
            raise RuntimeError("Source bindings changed during execution")
        receipt.outcome = "passed"
    except Exception as error:
        LOGGER.exception("Reference harness failed")
        receipt.outcome = "failed"
        receipt.error = repr(error)
    finally:
        receipt.completed_at = now()
        (args.output / "receipt.json").write_text(
            json.dumps(asdict(receipt), indent=2) + "\n"
        )
    print(f"{receipt.outcome.upper()} {receipt.scope}: {args.output}")
    return 0 if receipt.outcome == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
