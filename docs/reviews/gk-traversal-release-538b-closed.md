# Campaign gk-traversal-release-538b: closed 2026-09-29T03:36:31.205806+00:00

The BFS/SSSP campaign on the four Graph Kernels inputs finished on
2026-09-29 00:01:44 UTC with every planned cell passed, and its independent
audit passed every cell. Nothing in the evidence was changed after the run.

| Item | Value |
| --- | --- |
| Run ID | gk-traversal-release-538b |
| Planned / completed / outcomes | 216 / 216 / {'passed': 216} |
| Launch | 2026-09-28T05:37:58.596911+00:00, pid 28382, `/usr/bin/python3 /Users/alexy/src/sail-extensions-gates/graph-kernels-traversal-1f18/host-harness/run_matrix.py --config /Users/alexy/src/sail-extensions-gates/graph-kernels-traversal-1f18/preparation/matrix-final.json --skip-prepare` |
| Configuration sha256 (launch pin) | ce41b082ca95eb70280463e15bbdd02df4560b4e23b594b14c779469447e8b17 |
| Harness source | 538b94cbb99298f94667cde29e94b3e4cefe60fc (`work/extensions-traversal-bench` lineage) |
| Runtime (host) source | 038c9b9597d3fcf7e0b8c30c1253d7d77563f012 |
| Native wheel source | 038c9b9597d3fcf7e0b8c30c1253d7d77563f012 |
| Image | sha256:f3518d652fbea8b9b9f9ebf9849277ca3bd39d0c21bb2c6e36fbaeaa2dc2678e (`sail-pecan-benchmark:release`) |
| Host | morrobay, Colima profile `colima-sail-gate` (24 CPUs, 64 GiB); Docker context `colima-sail-gate` |
| Container limits per cell | cpus 16, cpuset 0-15, memory 56 GiB, no swap, outer timeout 2400 s |
| Descriptor limit (`ulimit -n`) in the image | 1024 (container default; the harness at this revision did not record it per cell) |
| Defaults | partitions 16, threads 16, task slots 64, Sail pool 51539607552 B, native quota 34359738368 B, delta 4.0 |
| Evidence | `/Users/alexy/src/sail-extensions-gates/graph-kernels-traversal-1f18/campaign` (cells/, configuration.json, matrix-results.json sha256 `5d473adc0cde1ae2069c68f78ee430582bd36dfb4ac96cd53ddebde2e360b23b`) |
| Independent audit | `/Users/alexy/src/sail-extensions-gates/graph-kernels-traversal-1f18/audit/audit-report.json` sha256 `9ae42253cede55e04b3125f8962d26515f7a1796c90960b6624f9c2ff8c20deb`, {'passed': 216}; tool `docs/development/extensions/traversal-validation/independent-audit/audit_campaign.py` at `b87fb27ac` (`/Users/alexy/src/sail-extensions-gates/graph-kernels-traversal-1f18/tip-audit/`), run read-only in the campaign image with the datasets from the target volume, configuration pin ce41b082ca95eb70280463e15bbdd02df4560b4e23b594b14c779469447e8b17 |
| Not applicable | `summarize.py` (the PageRank/WCC verifier) flags every traversal cell for structural reasons; its output is kept under `summary-pagerank-verifier-not-applicable/` and is not a result |

Boundaries: complete-call timings from input handles to written results, on a
shared host under Colima; observations, not publishable numbers. Argentea is
not part of these cells. The report for these results belongs with the
fork's `docs/development/extensions` evidence tree, written from this
directory and the audit report.

## Findings, read from the 216 receipts on 2026-09-29

Median complete-call seconds over three repetitions, with the sampled peak
PSS of the whole process tree; shared host, observations only. BFS from
vertex 0, directed; SSSP with integer weights 1 to 16, delta 4.0. Every cell
passed its exact certificate, and the independent audit passed every cell.

| Input | Algorithm, method | Pecan | Banda | Grenada |
| --- | --- | ---: | ---: | ---: |
| hub-2097152 | BFS reference | 126 s, 8.2 GiB | 27 s, 3.0 GiB | 132 s, 8.3 GiB |
| hub-2097152 | BFS frontier | 89 s, 8.9 GiB | 23 s, 3.2 GiB | 83 s, 8.3 GiB |
| hub-2097152 | BFS push-pull | 30 s, 1.9 GiB | 27 s, 3.3 GiB | 30 s, 1.9 GiB |
| uniform-4194304 | BFS reference | 239 s, 14.1 GiB | 52 s, 4.7 GiB | 256 s, 14.3 GiB |
| uniform-4194304 | BFS frontier | 149 s, 14.3 GiB | 52 s, 4.7 GiB | 154 s, 14.5 GiB |
| uniform-4194304 | BFS push-pull | 57 s, 2.4 GiB | 70 s, 5.4 GiB | 57 s, 2.5 GiB |
| hub-2097152 | SSSP reference | 466 s, 10.1 GiB | 31 s, 3.1 GiB | 466 s, 9.1 GiB |
| hub-2097152 | SSSP frontier | 282 s, 9.7 GiB | 27 s, 3.3 GiB | 285 s, 9.1 GiB |
| hub-2097152 | SSSP delta-star | 396 s, 10.2 GiB | 33 s, 3.4 GiB | 397 s, 9.6 GiB |
| uniform-4194304 | SSSP reference | 991 s, 16.7 GiB | 82 s, 5.1 GiB | 1052 s, 16.6 GiB |
| uniform-4194304 | SSSP frontier | 567 s, 14.8 GiB | 63 s, 5.1 GiB | 571 s, 14.7 GiB |
| uniform-4194304 | SSSP delta-star | 650 s, 14.6 GiB | 66 s, 5.9 GiB | 653 s, 14.5 GiB |

The full grid (four inputs, two algorithms, three paths, three methods) is
in the receipts; the rows above are the two ends of it.

1. **Banda leads every SSSP cell by ten to seventeen times, at a third of
   the memory.** Its three SSSP methods are within noise of each other on
   these inputs. The relational SSSP rounds are the whole cost: 280 to
   1,050 s.
2. **Direction-optimizing BFS makes the relational path competitive with
   Banda, and at 4 M vertices faster.** Push-pull BFS on Pecan or Grenada
   runs in 30 to 57 s at 1.9 to 2.5 GiB; Banda's BFS runs in 23 to 70 s at
   3 to 5.4 GiB, and on both 4 M-vertex inputs Banda is the slower one
   (62 to 70 s against 49 to 57 s). Once the pull phase takes over, the
   relational round scales with the frontier, not the edge count. This is
   the strongest evidence so far for the relational path where the
   algorithm is frontier-shaped; it does not carry to SSSP, where the
   relational delta-star method is slower than the frontier method.
3. **Reference and frontier BFS on the relational paths are dominated by
   materialized state**: 8 to 15 GiB PSS against 2 GiB for push-pull on the
   same inputs, and two to four times the time.
4. **Pecan and Grenada agree everywhere**, within the run-to-run spread:
   Grenada is an entrance to the same machinery, as documented.
5. **Scaling from 2 M to 4 M vertices** (twice the edges) costs Banda about
   twice, the relational paths about 1.6 to 1.9 times.
6. **Outliers retained, not explained**: Banda delta-star on uniform-2 M
   once at 107 s against a 28 s median; Grenada SSSP reference on
   uniform-4 M once at 1,333 s against 1,052; Pecan SSSP frontier on
   uniform-4 M once at 994 s against 567. The host was shared with other
   work during the campaign; the S0 accounting exists to tell such cells
   apart from real behavior.

Banda staged the 33.6 M-edge inputs under the qualified 32 GiB native
allowance in every cell; the staging cost is inside its numbers and is not
separated at this harness revision.
