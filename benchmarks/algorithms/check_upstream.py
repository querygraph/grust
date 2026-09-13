#!/usr/bin/env python3
"""Check separately named upstream binaries against the retained C++ participant."""
import argparse
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import bench


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipts = []
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        for family in ["path", "hub", "clusters", "layered", "uniform", "rmat"]:
            n = 128
            edges = bench.generate(family, n)
            graph = directory / "graph.txt"
            graph.write_text(f"{n} {len(edges)}\n" + "".join(f"{a} {b} {weight}\n" for a, b, weight in edges))
            for algorithm in ["bfs", "dijkstra", "dijkstra-full", "wcc", "scc", "pagerank"]:
                reference_metrics, expected = bench.execute(ROOT / "legacy", graph, algorithm, 0, directory / "reference.bin")
                for participant in ["grust-upstream-direct", "grust-upstream-cypher"]:
                    receipt = dict(family=family, nodes=n, algorithm=algorithm, participant=participant)
                    try:
                        metrics, values = bench.execute(ROOT / participant, graph, algorithm, 0, directory / "actual.bin")
                        receipt["metrics"] = metrics
                        if metrics.get("provider") != "grust.algorithms":
                            raise AssertionError("upstream participant did not identify the registered upstream provider")
                        assert len(values) == n and all(math.isfinite(value) for value in values)
                        if algorithm == "pagerank":
                            assert max(abs(a - b) for a, b in zip(values, expected)) <= 1e-9
                            assert abs(sum(values) - 1.0) <= 1e-8
                        else:
                            assert values == expected
                        if algorithm == "dijkstra-full" and family == "path":
                            assert metrics["reachable"] == n
                            assert metrics["path_entries"] == n * (n + 1) // 2
                            assert metrics["node_sum"] == (n - 1) * n * (n + 1) // 6
                            assert metrics["cost_sum"] == sum(expected[i] * (n - i) for i in range(n))
                        receipt["status"] = "pass"
                    except AssertionError as error:
                        receipt.update(status="mismatch", error=str(error))
                    except subprocess.TimeoutExpired as error:
                        receipt.update(status="timeout", error=str(error))
                    except FileNotFoundError as error:
                        receipt.update(status="unavailable", error=str(error))
                    except Exception as error:
                        receipt.update(status="error", error=str(error), stdout=str(getattr(error, "stdout", "")), stderr=str(getattr(error, "stderr", "")))
                    receipts.append(receipt)
                    args.output.write_text(json.dumps(receipts, indent=2) + "\n")
    failures = sum(row["status"] != "pass" for row in receipts)
    print(f"{len(receipts) - failures} passed, {failures} failed; {args.output}")
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
