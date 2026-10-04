# Larger controller-only follow-up

Prepared, locally checked, **not launched by this agent**. This follow-up asks
whether removing the duplicate weighted expansion becomes useful when expansion
work grows. It compares the original `ffcfbd569` Python controller and
`edc2c7c8` controller on the same original gate3 `ffcfbd569` binary and native
wheel. It does not include the compact struct-MIN runtime change.

The preceding 16k shared-host comparison did not establish a controller speedup:
its candidate median was slower. This larger fixture is a separate workload,
not a replacement for those retained cells. Four measured cells provide a
bounded follow-up, not a claim about broad scaling or statistical significance.

## Fixture, envelope and order

- Directed SSSP/frontier, source 0, seed 42; 65,536 vertices, degree 64 and
  **4,216,091 edges**. The existing traversal fixture includes integer weights
  0–15, ties, duplicates, a zero-weight cycle, skew and an isolate. The edge
  count follows its recipe: `6 + (V-1)*degree + ceil((V-1)/3)`.
- Generate this fixture once inside the VM with the unchanged existing fixture
  generator and independent heap-Dijkstra reference. All cells reuse its exact
  manifest and Parquet paths. No dataset is copied to the host.
- Same 8 CPUs, cpuset 0–7, 12 GiB container memory/no additional swap,
  two process-cluster workers, 4 partitions/threads, 16 task slots per worker,
  3 GiB Sail pool per process, 256 MiB native quota, 120-second HTTP/2 keepalive.
- Fresh container/server each cell. Two excluded warmups: base, candidate.
  Four measured cells: **base, candidate, candidate, base** (ABBA).
- Existing full no-shim candidate integration gates must have passed and all
  preceding suite outcomes must exist. Baseline test failures remain recorded.
  This follow-up does not rerun or relabel those gates.

The input has roughly eight times the preceding fixture's edges. Its Python
reference/validation still fits the generator's explicit bounds (at most
100,000 vertices and degree 64). Resource feasibility for this exact fixture
has not been measured. An initial planning allowance is 15–30 minutes for
preparation plus six cells; that is an estimate, not a measured runtime or
promise. Preparation is capped at 600 seconds, each algorithm at 600 seconds,
and each outer cell at 1,350 seconds. Six outer caps total 135 minutes, plus
preparation/preflights/collection. A timeout or OOM remains an outcome.

## Running

Place [run_pecan64k_gate3.py](run_pecan64k_gate3.py) beside the unchanged
[run_pecan_gate3.py](run_pecan_gate3.py) on the Docker host. Use the same diagnostic
matrix directory from the preceding experiment (`3a9028057c6c6c5034492845926fc4bc18f9626f`)
and the preceding real host `plan.json`, not this repository's dry-plan example.
The runner checks both helper and matrix hashes against that plan.

```sh
python3 run_pecan64k_gate3.py \
  --matrix /path/to/pinned-harness/examples/extensions/benchmarks \
  --prior-plan /Users/alexy/src/sail-extensions-gates/stream-experiments-20260930/pecan-gate3/plan.json
```

Add `--execute` to launch after the current remote work has finished. Defaults
are fresh roots:

```text
VM:   /targets/sail-stream-experiments-20260930/pecan64k-controller
Host: /Users/alexy/src/sail-extensions-gates/stream-experiments-20260930/pecan64k-controller
```

Existing roots cause failure; nothing is overwritten. `--root` and `--output`
can name fresh sibling paths. The runner requires 8 GiB free VM disk and 2 GiB
free host disk, reuses the already staged source trees, performs no builds or
package installs, and uses `run_container(copy_paths={})`. Only flat receipts,
manifests and diagnostic logs are collected; result/staging/dataset trees stay
in the volume.

Each cell retains raw orchestration and receipt outcomes, reference correctness,
runtime/native identity, end-to-end algorithm seconds, execute-phase memory
peaks and guest steal. Runtime/native identities must match the preceding
successful cells; all new cells must use the same new dataset manifest.
Identity mismatches cannot become passes. Failed cells remain failed even if
they also have identity mismatches. Compare warmup-excluded cells only, inspect
the raw `algorithm_iterations` and convergence fields, and report every cell.
These are shared-host observations; zero steal is not proof of dedicated CPUs.

## Local validation

[Six tests](test_pecan64k_gate3.py) passed in the existing detached Grust gate
worktree using Python 3.12. They check real matrix commands, exact resources and
source isolation, changed-runtime rejection, order, required candidate gates,
identity consistency and the edge-count formula against a small invocation of
the actual degree-64 fixture generator. The complete six-cell dry plan also
passed without launching containers.

See [validation receipt](pecan64k-gate3-scripts-validation.json) for exact script
hashes, commands and gate base; its verdict covers the uncommitted script
snapshot, not that base commit's content or a production run. The
[dry plan](pecan64k-gate3-dry-plan.json) is retained separately. Existing 16k
scripts and their build/validation receipts were not changed.
