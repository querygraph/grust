#!/usr/bin/env python3
"""Add upstream participants to a separate copy of the frozen Docker context.

Historical sources and participants remain intact. The input context must already
have been produced by the companion's default (frozen) docker/prepare.py.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"companion integration anchor changed: {old[:90]!r}")
    return text.replace(old, new, 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen-context", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    if args.output.exists():
        parser.error("output must be a new directory; existing evidence is never replaced")
    original = json.loads((args.frozen_context / "sources.json").read_text())
    for name, digest in original.items():
        if hashlib.sha256((args.frozen_context / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"frozen context changed: {name}")
    shutil.copytree(args.frozen_context, args.output)
    target = args.output
    for name in ["Cargo.toml", "Cargo.lock", "README.md", "crates", "examples"]:
        source = root / name
        dest = target / "grust-upstream" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, dest, ignore=shutil.ignore_patterns("target", ".git", "__pycache__"))
        else:
            shutil.copy2(source, dest)
    compare = target / "benchmark/neo4j/compare.py"
    text = compare.read_text()
    text = replace_once(text, 'import bench\n', 'import bench\nimport participant_audit\nbench.execute = participant_audit.capture(bench.execute)\n')
    text = replace_once(text, '    args = parser.parse_args()\n', '    parser.add_argument("--include-upstream", action="store_true")\n    args = parser.parse_args()\n    os.environ["BENCH_AUDIT_LABEL"] = args.label\n')
    text = replace_once(text, '    results = []\n', '    if args.include_upstream:\n        native_executables.update(grust_upstream_direct="grust-upstream-direct", grust_upstream_cypher="grust-upstream-cypher")\n    results = []\n')
    text = replace_once(text, '"grustcat_cypher": "Grustcat Cypher"}', '"grustcat_cypher": "Grustcat Cypher", "grust_upstream_direct": "Grust upstream direct", "grust_upstream_cypher": "Grust upstream Cypher"}')
    text = replace_once(text, '                            native_queries = {}\n', '                            native_queries = {}\n                            native_details = {x: [] for x in native_executables}\n')
    text = replace_once(text, '                                    if repeat >= args.warmups:\n', '                                    if backend.startswith("grust_upstream") and metrics.get("provider") != "grust.algorithms":\n                                        raise AssertionError("upstream column used an unexpected provider")\n                                    native_details[backend].append(dict(metrics, warmup=repeat < args.warmups))\n                                    if repeat >= args.warmups:\n')
    text = replace_once(text, '                                        assert native_iterations[backend] == native_iterations["cpp"]\n', '                                        # Preserve historical iteration parity. Upstream uses the same\n                                        # L1 threshold but independently scaled floating-point arithmetic.\n                                        if not backend.startswith("grust_upstream"):\n                                            assert native_iterations[backend] == native_iterations["cpp"]\n')
    text = text.replace('"native_ms": native,', '"native_ms": native,\n                                    "native_details": native_details,')
    compare.write_text(text)
    entry = target / "entrypoint.py"
    entry.write_text(replace_once(entry.read_text(), "'--include-grustcat-cypher',", "'--include-grustcat-cypher','--include-upstream',"))
    report = target / "report.py"
    text = report.read_text().replace('Grustcat Cypher and Neo4j GDS', 'Grustcat Cypher, upstream Grust and Neo4j GDS')
    text = text.replace('| Grustcat Cypher ms | GDS ms |', '| Grustcat Cypher ms | Grust upstream direct ms | Grust upstream Cypher ms | GDS ms |')
    text = text.replace("|---|---:|---|---:|---:|---:|---:|---:|---|", "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---|")
    text = text.replace("{med('grustcat_cypher')} | {val}", "{med('grustcat_cypher')} | {med('grust_upstream_direct')} | {med('grust_upstream_cypher')} | {val}")
    text = replace_once(text, "lines+=['',", "lines+=['','Upstream direct includes kernel/result conversion, with projection separate. Upstream Cypher includes parsing, policy checks, projection and ordinary query execution; full-path distance verification is a separate query outside that timer. Per-phase and process times are retained in native_details. Upstream uses a 256 MiB working allowance; Cypher additionally has a disclosed 24-hour deadline. These boundaries differ from historical participants. No common allocation strategy or timer boundary is implied.','',")
    report.write_text(text)
    for name in ["participant_audit.py", "check_upstream.py"]:
        shutil.copy2(root / "benchmarks/algorithms" / name, target / "benchmark" / name)
    dockerfile = target / "Dockerfile"
    text = dockerfile.read_text()
    stage = '''FROM rust:1.97.1-bookworm AS upstream
COPY grust-upstream /src/grust-upstream
WORKDIR /src/grust-upstream
RUN --mount=type=cache,target=/usr/local/cargo/registry \\
    cargo build --release --locked -p grust-algorithm-procedures \\
      --example grust-upstream-direct --example grust-upstream-cypher

'''
    text = replace_once(text, 'FROM debian:bookworm-slim AS benchmark\n', stage + 'FROM debian:bookworm-slim AS benchmark\n')
    text = replace_once(text, 'COPY --from=build /out /opt/benchmark\n', 'COPY --from=build /out /opt/benchmark\nCOPY --from=upstream /src/grust-upstream/target/release/examples/grust-upstream-direct /src/grust-upstream/target/release/examples/grust-upstream-cypher /opt/benchmark/\n')
    text = replace_once(text, 'RUN python3 check_cypher.py --output /opt/benchmark/cypher-validation.json\n', 'RUN python3 check_cypher.py --output /opt/benchmark/cypher-validation.json\nRUN python3 check_upstream.py --output /opt/benchmark/upstream-validation.json\n')
    dockerfile.write_text(text)
    manifest = {str(path.relative_to(target)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(target.rglob("*")) if path.is_file() and path != target / "sources.json"}
    (target / "sources.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Staged {len(manifest)} files without changing the frozen input: {target}")


if __name__ == "__main__":
    main()
