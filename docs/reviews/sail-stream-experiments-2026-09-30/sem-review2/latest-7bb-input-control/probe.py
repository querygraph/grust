"""Bounded input-claim audit; no large graph scan or engine execution."""
from collections import deque
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[5]
REVIEW = "7bb00a299db9a24c35a47022614d6f572309b9a2"
paths = {
    "own_manifest_receipt": "docs/reviews/sail-stream-experiments-2026-09-30/logging01/diagnostics/receipt.json",
    "own_reach_evidence": "docs/reviews/sail-graphs-2026-09-30/benchmark/collect_receipt_evidence.json",
    "official_statistics": "docs/reviews/sail-stream-experiments-2026-09-30/sem-review2/input-catalog/finding.json",
}
data = {name: json.loads((ROOT / path).read_text()) for name, path in paths.items()}
manifest = data["own_manifest_receipt"]["dataset"]
# Locate the retained named successful source receipt, without assuming its outer layout.
def find_key(value, key):
    if isinstance(value, dict):
        if key in value:
            return value[key]
        for nested in value.values():
            found = find_key(nested, key)
            if found is not None:
                return found
    return None
reach = find_key(data["own_reach_evidence"], "certified_banda_gate3")
assert reach["receipt_outcome"] == "passed"
reached = reach["correctness"]["reached"]
assert reached == 8862601
external = next(x for x in data["official_statistics"]["selected_official_statistics"] if x["Name"] == "graph500-24")
external_v = int(external["#Vertices"].replace(",", ""))
external_e = int(external["#Edges"].replace(",", ""))
assert manifest["canonical"]["edges"]["duplicate_policy"] == "preserved; not counted or deduplicated"
# Exact counterexample to the cross-input-ratio inference, not a model of Graph500.
vertices = list(range(5))
edges = [(0, 1), (1, 2), (3, 4)]
adjacency = {v: set() for v in vertices}
for a, b in edges:
    adjacency[a].add(b)
    adjacency[b].add(a)
seen = {0}
queue = deque([0])
while queue:
    for target in adjacency[queue.popleft()]:
        if target not in seen:
            seen.add(target)
            queue.append(target)
isolates = [v for v in vertices if not adjacency[v]]
other_graph_vertex_count = 3
assert len(seen) == other_graph_vertex_count and len(vertices) - len(seen) == 2 and not isolates
review_bytes = subprocess.check_output(["git", "show", REVIEW + ":docs/SEM-REVIEW-2.md"], cwd=ROOT)
result = {
    "recorded_utc": datetime.now(timezone.utc).isoformat(),
    "review_commit": REVIEW,
    "review_blob_sha256": hashlib.sha256(review_bytes).hexdigest(),
    "source_files": {name: {"path": path, "sha256": hashlib.sha256((ROOT / path).read_bytes()).hexdigest()} for name, path in paths.items()},
    "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "own_input": {"vertices": manifest["counts"]["vertices"], "edges": manifest["counts"]["edges"], "reached": reached, "unreached": manifest["counts"]["vertices"] - reached, "self_loops": manifest["canonical"]["edges"]["self_loops"], "duplicate_count": None, "isolated_count": None, "distinct_endpoint_count": None, "canonical_vertices": manifest["canonical"]["vertices"], "canonical_edges": manifest["canonical"]["edges"]},
    "external_reported_input": {"vertices": external_v, "edges": external_e},
    "arithmetic_only": {"reached_over_own_vertices": str(Fraction(reached, manifest["counts"]["vertices"])), "reached_over_external_vertices": str(Fraction(reached, external_v)), "cross_input_ratio_decimal": float(Fraction(reached, external_v)), "edge_count_difference": manifest["counts"]["edges"] - external_e},
    "counterexample": {"own_vertices": vertices, "own_edges_undirected": edges, "own_source": 0, "own_reached": sorted(seen), "own_unreached": sorted(set(vertices) - seen), "own_isolates": isolates, "other_graph_vertex_count": other_graph_vertex_count, "cross_graph_ratio": 1.0},
    "conclusion": "Cross-graph reach/vertex ratio cannot establish the own graph's isolated count or giant-component share among incident vertices. Existing own manifest counts self-loops but explicitly does not count duplicates. Exact decomposition of the cross-input edge difference remains unverified.",
    "scope": "Source/receipt audit and a five-vertex Python counterexample. No scan of either large dataset, no new Sail or external engine execution, no claim that the own large graph actually has extra nontrivial components."
}
out = Path(__file__).with_name("receipt.json")
with out.open("x") as stream:
    json.dump(result, stream, indent=2)
    stream.write("\n")
print(json.dumps({"outcome": "SOURCE_AUDIT_AND_INFERENCE_COUNTEREXAMPLE_PASS", "receipt": str(out)}))
