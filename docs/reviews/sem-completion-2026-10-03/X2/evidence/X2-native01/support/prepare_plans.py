"""Prepare two separately fresh, resource-admitted X2 controls; never launch."""

import argparse
import hashlib
from pathlib import Path
from typing import Literal

import probe_models as m
import run_probes
from pydantic import BaseModel, ConfigDict

SUPPORT = Path(__file__).parent
BASE = Path("/Volumes/Apo/graph-tests/results/sem-review-20261001")


class Recorded(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)


class BuildSource(Recorded):
    commit: str
    tree: str
    path: Path


class BuildStep(Recorded):
    name: str
    returncode: int
    binary: m.Pin
    source_after: BuildSource


class Build(Recorded):
    outcome: Literal["passed_optimized_native_binaries"]
    steps: list[BuildStep]


class Client(Recorded):
    python: Path
    python_version: Literal["3.12.6"]
    extensions: list[str]
    modules: dict[str, m.Pin]
    executable: m.Pin
    libpython: m.Pin
    lock: m.Pin


def pin(path: Path) -> m.Pin:
    if path.is_symlink() or not path.is_file():
        raise ValueError("regular preparation input required")
    return m.Pin(
        path=path,
        bytes=path.stat().st_size,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument(
        "--build-receipt",
        type=Path,
        default=BASE / "native-optimized-build01/receipt.json",
    )
    parser.add_argument(
        "--client-receipt",
        type=Path,
        default=BASE / "A5-native-supervisor01/native-client-admission01.json",
    )
    args = parser.parse_args()
    build = Build.model_validate_json(args.build_receipt.read_bytes())
    source = next(step for step in build.steps if step.name == "sail")
    if (
        source.returncode != 0
        or source.source_after.commit != "9f0aa7d2a50f1258544d37c05dd19b3ff3d915b3"
    ):
        raise ValueError("recorded optimized native9f build required")
    client = Client.model_validate_json(args.client_receipt.read_bytes())
    if client.extensions:
        raise ValueError("zero-extension native client required")
    manifest = m.FixtureManifest.model_validate_json(
        (args.fixture / "manifest.json").read_bytes()
    )
    originals = [
        m.Pin(path=args.fixture / name, bytes=value.bytes, sha256=value.sha256)
        for name, value in sorted(manifest.files.items())
    ]
    if any(pin(record.path) != record for record in originals):
        raise ValueError("prepared fixture differs from its manifest")
    helpers = [
        pin(path)
        for path in sorted(SUPPORT.glob("*.py"))
        if not path.name.startswith("test_")
    ]
    clients = [
        *client.modules.values(),
        client.executable,
        client.libpython,
        client.lock,
        pin(args.build_receipt),
        pin(args.client_receipt),
    ]
    graph_package = (
        source.source_after.path
        / "examples/extensions/graph-algorithms/src/pyspark_pecan"
    )
    clients.extend(pin(path) for path in sorted(graph_package.rglob("*.py")))
    if len({record.path for record in clients}) != len(clients):
        raise ValueError("client/library pins must be unique")
    args.output.mkdir(parents=True, exist_ok=False)
    plans = []
    for kind, pool in (("reference", 10737418240), ("pool-refusal", 1048576)):
        run_id = f"x2-{kind}-p16-01"
        plan = m.Plan.model_validate(
            {
                "run_id": run_id,
                "kind": kind,
                "output": args.run_root / run_id,
                "binary": source.binary,
                "repo": source.source_after.path,
                "source": source.source_after.commit,
                "tree": source.source_after.tree,
                "fixture": args.fixture,
                "fixture_manifest": pin(args.fixture / "manifest.json"),
                "originals": originals,
                "helpers": helpers,
                "client": clients,
                "partitions": 16,
                "pool_bytes_per_process": pool,
                "worker_task_slots": 8,
            }
        )
        path = args.output / f"{run_id}.json"
        path.write_text(plan.model_dump_json(indent=2) + "\n")
        plans.append(pin(path))
    worker, oracle = pin(SUPPORT / "native_probe.py"), pin(SUPPORT / "probe_oracle.py")
    owner_helpers = [
        record for record in helpers if record.path not in (worker.path, oracle.path)
    ]
    config = run_probes.Config(
        root=args.output / "owner",
        python=client.python,
        worker=worker,
        oracle=oracle,
        helpers=owner_helpers,
        plans=plans,
        timeout_seconds=1800,
    )
    (args.output / "config.json").write_text(config.model_dump_json(indent=2) + "\n")


if __name__ == "__main__":
    main()
