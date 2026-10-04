"""Seal root-approved F0 metadata; input hashes are verified by the run, outside timing."""
from __future__ import annotations

import argparse
from pathlib import Path

import models
import run_native

BASE = Path("/Volumes/Apo/graph-tests/results/sem-review-20261001")
SSD = Path("/Users/alexy/src/grust-benchmark-data")


def source_pins(root: Path) -> tuple[models.FilePin, ...]:
    manifest = models.SourceManifest.model_validate_json((Path(__file__).parent / "source-manifest.json").read_bytes())
    result = tuple(models.FilePin(path=root / name, **pin.model_dump())
                   for name, pin in sorted(manifest.files.items()))
    run_native.inventory(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-receipt", type=Path, default=BASE / "F0-native-build01/receipt.json")
    parser.add_argument("--output", type=Path, required=True, help="fresh JSON config destination")
    parser.add_argument("--run-output", type=Path, default=BASE / "F0-native-run01")
    args = parser.parse_args()
    run_native.require(not args.output.exists(), "fresh config required")
    helper = Path(__file__).resolve().parent
    root = BASE / "F0-native-preparation01"
    built = models.RootBuild.model_validate_json(args.build_receipt.read_bytes())
    helpers = tuple(run_native.file_pin(helper / name) for name in
                    ("models.py", "run_native.py", "prepare_config.py", "source-manifest.json"))
    cit = models.Dataset(name="cit-Patents", vertex_rows=3774768, edge_rows=16518947,
        vertices=models.FilePin(path=SSD / "cit-Patents/cit-Patents-v.parquet", bytes=3861941,
            sha256="0969ea9ede0969e18e76a2c70191ed7ccecaecb9f1da6d954093dbefbc8958aa"),
        edges=models.FilePin(path=SSD / "cit-Patents/cit-Patents-e.parquet", bytes=70037384,
            sha256="70bcba17b5a7762ef5a0c3d16c1dc37a352461b83e338f550ae897d844f0268f"),
        evidence=run_native.file_pin(BASE / "A2-run04/validation04/container/artifacts/receipt.json"))
    graph = models.Dataset(name="graph500-24", vertex_rows=8870942, edge_rows=260379520,
        vertices=models.FilePin(path=SSD / "graph500-24/graph500-24-v.parquet", bytes=9119859,
            sha256="f186f0fac502106454ceae29a57c7f350ae60699b5a5087b3001cfd054983428"),
        edges=models.FilePin(path=SSD / "graph500-24/graph500-24-e.parquet", bytes=837233354,
            sha256="da4f324e619c97d68190c0eba4e2f9e59ebcd492d84c3e1bafe7624fdc7e2453"),
        evidence=run_native.file_pin(SSD / "graph500-24/preservation.json"))
    toolchain = Path("/Users/alexy/.rustup/toolchains/stable-x86_64-apple-darwin/bin")
    config = models.Config(source_root=root, source_files=source_pins(root), helper_files=helpers,
        output=args.run_output, lock=BASE / "serial-queue.lock", refuse_locks=(BASE / "gate.lock",),
        cargo=run_native.file_pin(toolchain / "cargo"), rustc=run_native.file_pin(toolchain / "rustc"),
        time=run_native.file_pin(Path("/usr/bin/time")), ps=run_native.file_pin(Path("/bin/ps")),
        build_receipt=run_native.file_pin(args.build_receipt), binary=built.binary,
        datasets=(cit, graph), ssd_root=SSD)
    run_native.validate_build(built, config)
    with args.output.open("x") as stream:
        stream.write(config.model_dump_json(indent=2) + "\n")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
