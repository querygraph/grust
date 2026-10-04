#!/usr/bin/env python3
"""One complete, no-shim Pecan package gate inside a fresh Linux container."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
import xml.etree.ElementTree as ET

BASE = "ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73"
CANDIDATE = "edc2c7c8cfc17cfc02f4f3a794bd4a3ec86ee3ed"


def utc():
    return datetime.now(timezone.utc).isoformat()


def clean_test_environment(repo, endpoint):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("PYTEST_") and k not in ("PYTHONPATH", "PYTHONHOME")}
    env.update(PYTHONPATH=str(repo / "examples/extensions/graph-algorithms/src"),
               PYTHONNOUSERSITE="1", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
               SPARK_CONNECT_MODE_ENABLED="1", SAIL_GRAPH_TEST_REMOTE=endpoint)
    return env


def junit_summary(path):
    root = ET.parse(path).getroot()
    cases = list(root.iter("testcase"))
    return dict(tests=len(cases), failures=sum(c.find("failure") is not None for c in cases),
                errors=sum(c.find("error") is not None for c in cases),
                skipped=sum(c.find("skipped") is not None for c in cases),
                failed_cases=[f"{c.get('classname')}::{c.get('name')}" for c in cases
                              if c.find("failure") is not None or c.find("error") is not None])


PROBE = r'''
import inspect,json,os
from pathlib import Path
from pyspark.sql.connect.session import SparkSession
from pyspark.sql.connect.client.retries import DefaultPolicy
from pyspark_pecan import GraphUtils
from pyspark_pecan import algorithms,utils
assert GraphUtils is utils.GraphUtils is algorithms.GraphUtils
assert Path(inspect.getfile(GraphUtils)).resolve() == Path(os.environ['PYTHONPATH'])/'pyspark_pecan/utils.py'
spark=SparkSession.builder.remote(os.environ['SAIL_GRAPH_TEST_REMOTE']).create()
spark.client.set_retry_policies([DefaultPolicy(max_retries=1,initial_backoff=100,max_backoff=100,jitter=0)])
try:
    client=GraphUtils(spark)
    path,token=client.allocate()
    assert client.exists(path,token)
    client.remove(path,token)
    assert client.remove(path,token) == 0
    print(json.dumps(dict(class_module=GraphUtils.__module__,source=inspect.getfile(GraphUtils),
        capabilities=sorted(client.capabilities),engine=client.engine,root=client.root,
        lease_seconds=client.lease_seconds,owned_run_roundtrip='passed')))
finally:
    spark.stop()
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--expected-sha", choices=[BASE, CANDIDATE], required=True)
    parser.add_argument("--sail-binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=["local", "process-cluster"], required=True)
    parser.add_argument("--timeout", type=int, default=1200)
    args = parser.parse_args()
    args.repo, args.output = args.repo.resolve(), args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(args.repo / "examples/extensions/benchmarks"))
    from runtime import git, native_package_identity, package_versions, server, sha256
    from measurement import Sampler, cgroup_snapshot, cpu_ticks, steal_fraction
    receipt = dict(started_utc=utc(), harness_source_sha=args.expected_sha,
                   runtime_source_sha=BASE, native_source_sha=BASE,
                   mode=args.mode, outcome="started", cleanup_errors=[],
                   gate="entire package tests; no selector, no injected plugin or GraphUtils replacement",
                   script_sha256=sha256(__file__), packages=package_versions(),
                   python=sys.version, cgroup_before=cgroup_snapshot())
    sampler = Sampler(args.output / "memory-samples.jsonl")
    before_ticks = cpu_ticks()
    try:
        assert Path("/.dockerenv").exists() and Path("/proc/stat").exists()
        assert git(args.repo, "rev-parse", "HEAD") == args.expected_sha
        assert not git(args.repo, "status", "--porcelain")
        receipt.update(binary_sha256=sha256(args.sail_binary),
                       native_package_identity=native_package_identity())
        with sampler, server(args.sail_binary, args.output, args.mode, 4, 4,
                             256 * 1024**2, receipt["cleanup_errors"],
                             worker_task_slots=16, sail_pool_bytes=3 * 1024**3,
                             http2_keepalive_timeout=120) as (endpoint, pid):
            receipt["driver_pid"] = pid
            env = clean_test_environment(args.repo, endpoint)
            sampler.mark("capability_probe")
            probe = subprocess.run([sys.executable, "-s", "-c", PROBE], env=env,
                                   cwd=args.repo, text=True, capture_output=True, timeout=90)
            (args.output / "graphutils-probe.log").write_text(probe.stdout + probe.stderr)
            probe.check_returncode()
            receipt["graphutils"] = json.loads(probe.stdout.strip().splitlines()[-1])
            command = [sys.executable, "-s", "-m", "pytest", "-q", "-ra",
                       "--junitxml=" + str(args.output / "junit.xml"),
                       str(args.repo / "examples/extensions/graph-algorithms/tests")]
            receipt["pytest_command"] = command
            sampler.mark("execute")
            started = time.monotonic()
            with (args.output / "pytest.log").open("w") as log:
                result = subprocess.run(command, env=env, cwd=args.repo, stdout=log,
                                        stderr=subprocess.STDOUT, timeout=args.timeout)
            receipt.update(pytest_returncode=result.returncode,
                           gate_seconds=time.monotonic() - started,
                           pytest=junit_summary(args.output / "junit.xml"))
            sampler.mark("cleanup")
            receipt["outcome"] = ("test_failure" if result.returncode else
                                  "incomplete" if receipt["pytest"]["skipped"] else "passed")
        receipt["staging_files_after_shutdown"] = [str(p.relative_to(args.output))
            for p in (args.output / "staging").rglob("*.parquet")]
        assert not receipt["staging_files_after_shutdown"], "staging files remain after shutdown"
        assert sampler.error is None, sampler.error
        assert git(args.repo, "rev-parse", "HEAD") == args.expected_sha
        assert not git(args.repo, "status", "--porcelain")
    except BaseException as error:
        receipt["outcome"] = "timeout" if isinstance(error, subprocess.TimeoutExpired) else "error"
        receipt["error"] = traceback.format_exc()
    finally:
        receipt.update(finished_utc=utc(), memory=sampler.receipt(),
                       cgroup_after=cgroup_snapshot(),
                       guest_steal_fraction=steal_fraction(before_ticks, cpu_ticks()))
        (args.output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        print(json.dumps({k: receipt[k] for k in ("outcome", "harness_source_sha", "mode")}))
    return 0 if receipt["outcome"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
