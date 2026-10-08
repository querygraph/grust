"""Own one native Sail lifetime and gate an unchanged detached source commit."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import sysconfig
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent


def git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args],
        cwd=ROOT,
        env={k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
        text=True,
    ).strip()


def wait_http(url: str, process: subprocess.Popen[bytes]) -> None:
    for _ in range(200):
        if process.poll() is not None:
            raise RuntimeError(f"server exited: {url}")
        try:
            with urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"server not ready: {url}")


def run(sail: Path, output: Path, detached: bool) -> None:
    output.mkdir(parents=True, exist_ok=False)
    before = git("rev-parse", "HEAD")
    if git("status", "--porcelain"):
        raise RuntimeError("gate source must be clean")
    if (
        detached
        and subprocess.run(
            ["git", "symbolic-ref", "-q", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            check=False,
            env={k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
        ).returncode
        == 0
    ):
        raise RuntimeError("final gate requires a detached checkout")
    for port in (18765, 18766, 18767):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", port))
    processes: list[subprocess.Popen[bytes]] = []
    logs: list[TextIO] = []
    cells: list[dict[str, Any]] = []
    started = datetime.now(timezone.utc).isoformat()
    sail_hash = hashlib.sha256(sail.read_bytes()).hexdigest()
    environment = dict(os.environ)
    environment.update(
        SAIL_EXPERIMENTAL_EXTENSIONS="1",
        SAIL_NUTMEG_MEMORY_BYTES=str(128 << 20),
        SAIL_MODE="local",
        TOKIO_WORKER_THREADS="2",
        SAIL_EXECUTION__DEFAULT_PARALLELISM="2",
        SAIL_RUNTIME__MEMORY_POOL__TYPE="fair",
        SAIL_RUNTIME__MEMORY_POOL__FAIR__MAX_SIZE=str(512 << 20),
        PYTHONHOME=sys.base_prefix,
        PYTHONPATH=sysconfig.get_paths()["purelib"],
        DYLD_LIBRARY_PATH=str(sysconfig.get_config_var("LIBDIR")),
        RUST_LOG="warn",
    )

    def command(name: str, args: list[str], cwd: Path = ROOT) -> None:
        with (output / f"{name}.log").open("w") as log:
            result = subprocess.run(args, cwd=cwd, stdout=log, stderr=log, check=False)
        cells.append({"name": name, "argv": args, "exit_code": result.returncode})
        if result.returncode:
            raise RuntimeError(f"{name} failed; see retained log")

    def launch(
        name: str, args: list[str], cwd: Path = ROOT, env: dict[str, str] | None = None
    ) -> subprocess.Popen[bytes]:
        log = (output / f"{name}.log").open("w")
        logs.append(log)
        process = subprocess.Popen(
            args, cwd=cwd, env=env, stdout=log, stderr=log, start_new_session=True
        )
        processes.append(process)
        return process

    outcome = "failed"
    try:
        command("ruff", [sys.executable, "-m", "ruff", "check", str(ROOT)])
        command(
            "ruff-format",
            [sys.executable, "-m", "ruff", "format", "--check", str(ROOT)],
        )
        command(
            "mypy",
            [sys.executable, "-m", "mypy", "--ignore-missing-imports", str(ROOT)],
        )
        command("schemas", [sys.executable, str(ROOT.parent / "validate_examples.py")])
        command(
            "browser-install",
            ["npm", "ci", "--no-audit", "--no-fund"],
            ROOT / "browser",
        )
        command("browser-build", ["npm", "run", "build"], ROOT / "browser")
        fixture = output / "fixture"
        command(
            "prepare",
            [
                sys.executable,
                str(ROOT / "prepare_fixture.py"),
                "--output",
                str(fixture),
            ],
        )
        host = launch(
            "sail",
            [str(sail), "spark", "server", "--ip", "127.0.0.1", "--port", "18765"],
            env=environment,
        )
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", 18765), timeout=0.1):
                    break
            except OSError:
                if host.poll() is not None:
                    raise RuntimeError("Sail exited before readiness") from None
                time.sleep(0.1)
        gateway = launch(
            "gateway",
            [
                sys.executable,
                str(ROOT / "server.py"),
                "--endpoint",
                "sc://127.0.0.1:18765",
                "--port",
                "18767",
                "--vertices",
                str(fixture / "vertices.parquet"),
                "--edges",
                str(fixture / "edges.parquet"),
                "--catalog",
                str(fixture / "catalog.json"),
                "--output",
                str(output / "objects"),
            ],
        )
        wait_http("http://127.0.0.1:18767/health", gateway)
        command(
            "semantics",
            [
                sys.executable,
                str(ROOT / "qualify.py"),
                "--output",
                str(output / "semantics.json"),
            ],
        )
        command(
            "mcp",
            [
                sys.executable,
                str(ROOT / "qualify_mcp.py"),
                "--fixture",
                str(fixture),
                "--output",
                str(output / "mcp.json"),
            ],
        )
        browser = launch(
            "vite", ["npm", "run", "dev", "--", "--port", "18766"], ROOT / "browser"
        )
        wait_http("http://127.0.0.1:18766", browser)
        command(
            "browser",
            ["node", str(ROOT / "browser/qualify.mjs"), str(output / "browser")],
        )
        if (
            git("rev-parse", "HEAD") != before
            or git("status", "--porcelain")
            or hashlib.sha256(sail.read_bytes()).hexdigest() != sail_hash
        ):
            raise RuntimeError("source or native binary changed during gate")
        outcome = "passed"
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
        for log in logs:
            log.close()
        receipt = {
            "observed_utc": started,
            "outcome": outcome,
            "source_commit": before,
            "head_after": git("rev-parse", "HEAD"),
            "source_clean_after": not git("status", "--porcelain"),
            "sail_sha256": sail_hash,
            "sail_path": str(sail),
            "detached_required": detached,
            "execution": "native macOS; local Sail; 2 workers; 512 MiB managed pool; 128 MiB Nutmeg reservation",
            "cells": cells,
            "owned_process_exit_codes": [p.returncode for p in processes],
        }
        (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"cosmolang: PASSED native gateway, MCP and Cosmograph gate at {before}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sail", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-branch", action="store_true")
    args = parser.parse_args()
    run(args.sail, args.output, not args.allow_branch)


if __name__ == "__main__":
    main()
