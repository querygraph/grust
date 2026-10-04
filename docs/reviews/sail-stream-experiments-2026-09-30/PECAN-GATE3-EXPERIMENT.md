# Pecan: production integration and paired weighted trials

Prepared for a later launch on Morrobay's existing `colima-sail-gate` VM. No
remote load was launched while preparing these scripts. This is a bounded
diagnostic experiment on a shared host; any timing comparison is a paired
shared-host ratio, not an absolute performance result.

The controllers are base `ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73` and candidate
`edc2c7c8cfc17cfc02f4f3a794bd4a3ec86ee3ed`. Both use the existing gate3 executable,
Python environment and installed native wheel from `ffcfbd569`; there is no
native rebuild, wheel installation, or dependency update. Bootstrap checks
that the two detached sources are clean and that their benchmark execution,
sampling, fixture, and reference modules are byte-identical. Each cell records
the executable hash and complete installed native module hashes. Compare those
identities before interpreting measurements; version labels alone are not proof.

## What runs

1. Entire package tests for base/local, candidate/local, base/process-cluster,
   candidate/process-cluster. Each gets a fresh container and server. The
   production `GraphUtils` performs Ping and an owned-run allocation/removal
   before pytest. No receipt substitute or external pytest plugin is injected.
   Pytest gets no test selector, plugin autoload is disabled, and its JUnit
   failures/errors/skips are recorded separately. A skipped test means an
   incomplete gate. The package's own scoped unit-test mocks remain normal tests.
2. One excluded warmup per controller, A then B.
3. Eight measured SSSP/frontier trials, ordered **ABBA BAAB**, four per controller,
   with a fresh container/server for each. Every trial validates the complete
   distance vector against an independent Dijkstra reference, plus parent edges,
   rooted parent chains, row cardinality, and reachability using the existing
   `graph_cell.py` harness. No physical-plan recording is enabled during timing.

The base's existing `test_push_pull_distances_and_trace` is expected to expose
its stale event fixture; its failure is retained as a failure. The candidate
fixes that fixture by selecting iteration-end events while preserving the
assertions. **Any candidate package-gate failure prevents all performance
trials.** A baseline failure does not get reclassified as a pass. Each benchmark
trial must independently pass its correctness checks before its timing is used.
The runner exits nonzero if any cell is not passed, including baseline gates.

This is production GraphUtils and process-cluster validation on one VM, not a
two-host transport qualification. The full candidate package includes dominated
overflow rejection, signed-parent/hop tie breaking, cleanup/schema checks, and
the new regression proving that only materialization executes the expansion
plan in each weighted round (all three SSSP methods).

## Matched resources and fixture

| Property | Both controllers |
| --- | --- |
| Container | Pinned gate3 image; fresh private PID/cgroup namespace; `--init` |
| CPU / memory | 8 CPUs, cpuset 0–7, 12 GiB, no additional swap allowance |
| Execution | 2 process workers; 4 partitions; 4 Tokio/Rayon threads per process |
| Admission | 16 task slots per worker; 3 GiB Sail pool per process; 256 MiB native quota |
| Connection | 120-second HTTP/2 keepalive timeout; otherwise harness defaults |
| Graph | Existing bounded traversal fixture, 16,384 vertices, degree 32, seed 42 |
| Edges | 529,723 directed weighted edges, exact integer-double weights 0–15 |
| Source / method | Vertex 0; SSSP frontier; 100-iteration cap |
| Validation | Independent full reference and parent-tree validation |

The fixture includes zero-weight cycles, duplicate edges, skew, ties and an
isolate. It gives repeated broad weighted expansion without a large dataset
copy. It is synthetic and is not evidence about scale24 memory or all graph
families. Preparation happens once inside the VM. All trials read the same
manifest-pinned Parquet bytes, and checksum reads warm the OS cache before
timing. No cache flush or host reboot is performed.

The timed boundary is input DataFrame handles through a completed full result
Parquet write. It includes snapshotting, validation, all algorithm rounds and
result export; server startup and independent result verification are excluded.
`algorithm_ready_seconds`, iteration events and `end_to_end_seconds` are retained.
This experiment measures the complete call; it is not an isolated join benchmark.

The existing sampler records 50-ms samples of all visible processes and phase
peaks. Summary fields come directly from
`memory.phase_peaks.execute.{rss_bytes,pss_bytes,cgroup_current_bytes,fd_total}` and
top-level `guest_steal_fraction`. RSS sums count shared mappings repeatedly; PSS
apportions them. Sampled peaks can miss shorter spikes. Cgroup `memory.peak`
covers the whole fresh container lifetime, including verification and page cache;
it is not an execution-only peak. Preserve all these boundaries when reporting.
The VM-wide steal fraction is not a CPU-set-specific measure. Keep every cell,
including regressions, errors, timeouts and OOM outcomes.

The added grouped boolean has approximately one logical bit per resident group
in the optimized `bool_or` accumulator, plus capacity/alignment and possibly a
null-state bitmap. Partial groups and expression/output batches add storage.
Removing a sequential expansion action reduces work but does not establish a
lower peak. Compare measured memory independently of elapsed time.

## Commands

Create the small commit bundle on the development machine; it contains only
the candidate commit beyond the already-installed base:

```sh
pecan_artifacts=/Users/alexy/src/grust/docs/reviews/sail-stream-experiments-2026-09-30
test "$(git -C /private/tmp/sail-pecan-single-expansion rev-parse HEAD)" = edc2c7c8cfc17cfc02f4f3a794bd4a3ec86ee3ed &&
git -C /private/tmp/sail-pecan-single-expansion bundle create "$pecan_artifacts/pecan.bundle" ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73..work/pecan-single-expansion
```

Copy only `pecan.bundle`, `run_pecan_gate3.py`, `pecan_gate3_cell.py` and
`test_pecan_gate3.py` to a new small directory on Morrobay. The host runner's
`--matrix` must point to the already-staged diagnostic harness directory
containing `run_matrix.py`, `runtime.py`, `traversal_source.py` and
`traversal_methods.py` from `3a9028057c6c6c5034492845926fc4bc18f9626f`.
The runner records hashes of every supplied harness Python file in its plan.

From that directory on Morrobay, inspect the plan first (no Docker calls):

```sh
python3 -m unittest -v test_pecan_gate3.py
python3 run_pecan_gate3.py --matrix /absolute/path/to/existing/diagnostic/harness > plan.json
```

Once the current replay has finished and the VM is idle, launch:

```sh
python3 run_pecan_gate3.py --matrix /absolute/path/to/existing/diagnostic/harness --execute
```

Default VM output is
`/targets/sail-stream-experiments-20260930/pecan-gate3`; host output is
`/Users/alexy/src/sail-extensions-gates/stream-experiments-20260930/pecan-gate3`.
Both are created new and may not already exist. For a new attempt use
`--root /targets/.../pecan-gate3-attempt2 --output /Users/alexy/.../pecan-gate3-attempt2`.
Do not delete an earlier result to rerun. The host output's parent must exist.
Bootstrap uses `/targets` as its working directory so the image's default
working directory cannot conflict with the read-only `/work` bind mount.

The runner delegates lifecycle supervision to the existing `run_container`,
with `copy_paths={}`. Full dataset, staging and result trees stay in the VM
volume. Only the allowlisted flat receipt, manifest, logs, JUnit and memory
samples are collected afterward; no graph Parquet data returns to the host.
Candidate source and the small container gate script are staged in the VM.
Nothing is built or installed. Native source and runtime are constant.

For an integration-only manual cell after bootstrap, the container command is:

```sh
/targets/graph-nuts-ffcfbd569/venv/bin/python \
  /targets/sail-stream-experiments-20260930/pecan-gate3/scripts/pecan_gate3_cell.py \
  --repo /targets/sail-stream-experiments-20260930/pecan-gate3/source-edc2c7c8 \
  --expected-sha edc2c7c8cfc17cfc02f4f3a794bd4a3ec86ee3ed \
  --sail-binary /targets/graph-nuts-ffcfbd569/sail-linux-x86_64-ffcfbd5690e3-release \
  --mode process-cluster --output /targets/pecan-candidate-manual-gate
```

Run it in the same pinned fresh container envelope, not in the host shell.
The generated `plan.json` contains all exact container Python commands for
both package gates and all trials.

## Budget and validation limits

A planning estimate is 20–60 minutes total on an otherwise idle VM; this is not
a measured runtime estimate for gate3. Each full pytest invocation is limited
to 1,200 seconds; each benchmark execution and verification phase is limited
to 600 seconds, with a 1,350-second outer container cap. Four gates and ten
warmup/measured cells therefore have a combined outer cap of 5 hours 15 minutes,
plus bounded setup/collection. Abort or investigate repeated limits rather than
turning them into timing samples.

The local recipe check generated 529,723 edges in 1,575,385 bytes of Parquet
input/reference files (about 1.5 MiB). Remote generation records its own hashes;
Parquet writer versions may produce different bytes for the same logical graph.
Allow several GiB for source, transient stages, retained logs and samples;
bootstrap requires 12 GiB VM free and the runner requires 2 GiB host free. These
are guardrails, not measured upper bounds. The container enforces the 12-GiB
memory envelope, and the runner preserves OOM outcomes.

Local script checks are in `pecan-gate3-scripts-validation.json`. They validate
orchestration/receipt logic and the dry plan only. Production GraphUtils,
distributed execution, and performance remain unqualified until the Linux
gate runs. Earlier shim-based local algorithm evidence is kept separately in
`pecan-single-expansion/` and does not satisfy this gate.
