"""Admit actual4b88 release wheel, native9f host and one tiny accounting plan."""

from __future__ import annotations

import argparse
import hashlib
import os
import runpy
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any, Literal
from unittest.mock import patch

import probe_models as m
import run_probes
from pydantic import ConfigDict

SUPPORT = Path(__file__).parent
BASE = Path("/Volumes/Apo/graph-tests/results/sem-review-20261001")
NEWROOT = Path("/Volumes/Apo/graph-tests/results/sem-completion-20261003")


class Recorded(m.Model):
    model_config = ConfigDict(extra="ignore", strict=True)


class Source(Recorded):
    commit: str
    tree: str
    path: Path


class BuildStep(Recorded):
    name: str
    returncode: int
    binary: m.Pin
    source_after: Source


class Build(Recorded):
    outcome: Literal["passed_optimized_native_binaries"]
    steps: list[BuildStep]


class F2Environment(Recorded):
    python: Path
    repo: Path
    tree: str
    binary: m.Pin
    wheel: m.Pin
    expected_source: list[m.Pin]
    expected_client: list[m.Pin]


def pin(path: Path) -> m.Pin:
    if path.is_symlink() or not path.is_file():
        raise ValueError("regular preparation input required")
    return m.Pin(
        path=path,
        bytes=path.stat().st_size,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )


def native_identity(host_repo: Path) -> str:
    entries = entry_points(group="pysail.extensions")
    if {entry.name for entry in entries} != {"nutmeg", "argentea"}:
        raise ValueError("exact admitted4b88 Nutmeg wheel discovery required")
    entry = next(entry for entry in entries if entry.name == "nutmeg")
    # Only factory manifest creation: no native bind, state allocation or engine.
    factory: Any = entry.load()()
    with patch.dict(os.environ, {"SAIL_NUTMEG_MEMORY_BYTES": str(128 * 1024**2)}):
        manifest = factory.manifest()
    identity_function: Any = runpy.run_path(
        str(host_repo / "crates/sail-session/src/extensions/package_identity.py")
    )["identity"]
    result: str = identity_function(entry, manifest)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument(
        "--build-receipt",
        type=Path,
        default=BASE / "native-optimized-build01/receipt.json",
    )
    parser.add_argument(
        "--extension-config",
        type=Path,
        default=NEWROOT / "F2-fourphase01/main03-config.json",
    )
    args = parser.parse_args()
    build = Build.model_validate_json(args.build_receipt.read_bytes())
    host = next(step for step in build.steps if step.name == "sail")
    extension = F2Environment.model_validate_json(args.extension_config.read_bytes())
    if (
        host.returncode != 0
        or host.source_after.commit != "9f0aa7d2a50f1258544d37c05dd19b3ff3d915b3"
        or extension.binary != host.binary
    ):
        raise ValueError(
            "admitted optimized native9f runtime must bind successful4b wheel profile"
        )
    helper_pins = [
        pin(path)
        for path in sorted(SUPPORT.glob("*.py"))
        if not path.name.startswith("test_")
    ]
    clients = [
        *extension.expected_source,
        *extension.expected_client,
        extension.wheel,
        pin(args.build_receipt),
        pin(args.extension_config),
        pin(
            host.source_after.path
            / "crates/sail-common-datafusion/src/native_resource.rs"
        ),
        pin(
            host.source_after.path
            / "crates/sail-session/src/extensions/package_identity.py"
        ),
    ]
    unique = {record.path: record for record in clients}
    if any(pin(record.path) != record for record in clients):
        raise ValueError("original host/wheel/client/build source pins changed")
    args.output.mkdir(parents=True, exist_ok=False)
    plan = m.Plan(
        run_id="c3-native-accounting-local-01",
        output=args.run_root,
        binary=host.binary,
        repo=host.source_after.path,
        source=host.source_after.commit,
        tree=host.source_after.tree,
        extension_repo=extension.repo,
        extension_source="4b88c8fb4504ab1d2a896c9e49e4a09df4905bbb",
        extension_tree=extension.tree,
        helpers=helper_pins,
        client=list(unique.values()),
        native_package_identity=native_identity(host.source_after.path),
    )
    path = args.output / f"{plan.run_id}.json"
    path.write_text(plan.model_dump_json(indent=2) + "\n")
    worker, oracle = pin(SUPPORT / "native_probe.py"), pin(SUPPORT / "probe_oracle.py")
    config = run_probes.Config(
        root=args.output / "owner",
        python=extension.python,
        worker=worker,
        oracle=oracle,
        helpers=[
            item for item in helper_pins if item.path not in (worker.path, oracle.path)
        ],
        plans=[pin(path)],
        timeout_seconds=900,
    )
    (args.output / "config.json").write_text(config.model_dump_json(indent=2) + "\n")


if __name__ == "__main__":
    main()
