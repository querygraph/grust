# X2: original initiating cause remains unexplained

This is an independent source and retained-artifact review. It launches no
engine and makes no historical repair verdict. `audit.json` records its generated
UTC timestamp, all byte hashes and fourteen exact source snapshots at original
runtime `b87fb27a` and current native runtime `9f0aa7d2`.

## What the original evidence establishes

The scan selects exactly twelve original relational failures: Pecan or the
former `nutmeg-datafusion` (Grenada) path, a client `h2 protocol error: error
reading a body from connection`, and zero deltas in recorded cgroup `max` and
`oom_kill` counters. It covers baseline `capacity-hub`, `decide-gate3` and
`decide3-gate3`. Other native/certificate errors and later OOM replays are outside
this selected set.

All twelve retained server logs have **no ERROR record before session removal**
and no attributable typed task, pool-refusal or keepalive initiating cause.
Their available ERROR records occur during cleanup. Some logs have no ERROR
record at all. Absence of these records is a historical visibility gap; it
does not identify the missing failure or establish that memory was uninvolved.

For the selected original Grenada scale24 BFS-reference case:

- Exact runtime, native and harness source is
  `b87fb27ac29b930a9e83130bf4e31fb8e3e2125a`; binary SHA256 is
  `ce64f25b27c361c4b4d4ef0a16774c078c1d4a90ea2eac0cbd2a7b634544995d`.
- Input is the original generated scale24 graph: 16,777,216 vertices and
  268,435,456 undirected edge tuples; source13507776, P32, two workers and
  reference traversal. These are distinct from the official LDBC Parquet files.
- The producer fails 480.340084 seconds into its pipeline, 106.903209 seconds
  after the recorded start of iteration2. It had reached407203 vertices after
  iteration1. Its receipt contains the full failing Parquet-write stack.
- The cgroup limit is107374182400 bytes; its lifetime peak is54700847104 bytes
  (50.947GiB). Recorded max/oom/oom_kill counters remain zero. Sampled execute
  PSS is45975165952 bytes (42.818GiB); this is a separate measurement.
- Server log line23 removes the session, lines24–25 stop both workers, line26
  announces server shutdown, and line27 first reports a cleanup ConnectionReset.
  The log is only53 lines. There is no earlier typed cause to recover from it.

These observations do not justify assigning the later logging01/02 OOM kills,
h2 reset cap, keepalive expiry, scheduler starvation, pool refusal or a decode
limit as the initiating cause of this original cell.

## Why the outer error cannot settle causality

Original `task_runner/monitor.rs` turns a failed stream batch into failed task
status and `CommonErrorCause` without a worker warning that retains the original
error chain. Current runtime9f adds that warning before conversion, plus worker
task identity and Flight client/server phase, peer and stream-key diagnostics.
The current bounded logger limits text to4096 bytes and source depth to32;
this improves attribution but is not a global first-fault ledger.

`driver/job_scheduler/core.rs::infer_job_failure_cause` selects the task with the
most failed attempts, breaking ties by stage and partition, then uses its most
recent cause. It does not select the first chronological fault. A returned
generic transport error therefore cannot be treated as a timestamped root cause.
The driver also explicitly accepts failed-status reports caused by cancellation
and closed streams. Exact source snapshots and hashes are retained alongside
`audit.json`; current runtime9f source bytes were verified against the admitted
native source tree.

## Missing causal evidence

To diagnose an original-shape recurrence, preserve the first complete typed
operator/task/Flight/connection error before cancellation, worker stop and
session removal; bind it to PID, task/stream key, peer and effective configuration.
Record pool refusal and host-pressure/termination observations, along with
actual waits and the failed-write inventory. Zero cgroup OOM counters and sparse
process samples cannot supply that initiating observation retrospectively.

The original generated input and manifest directories are still present under
`~/src/sail-extensions-gates/graph-nuts-b87fb27ac/capacity-hub/datasets/scale24/dataset`.
Their presence is observed; this audit did not rehash all large physical inputs
or admit the original100GiB Linux envelope. A native9f replay would be a separately
declared changed platform/runtime/profile, not an exact historical reproduction.

## Source-ready native local controls for root

`functional_client.py`, `fixture_oracle.py` and `probe_models.py` pass Ruff and
strict mypy. `helper-source-admission01.json` pins their exact source and the
offline-created fixture. No engine control has run. The earlier mypy import-path
failure is retained separately; setting the explicit exact-package MYPYPATH
passes without any implementation change.

### 1. Current reference traversal, full physical-output oracle

Use a fresh native runtime9f process-cluster with two workers, P8 and four task
slots per worker. Reuse the root-owned lifecycle/worker launcher only after its
effective worker configuration and actual registration are verified. A declared
normal pool (for example512MiB per participating process) belongs to this tiny
functional profile; it is not the historical100GiB container.

The prepared fixture has4096 unique BIGINT IDs, source0, a reachable signed
maximum, an isolated signed minimum, preserved duplicate edges and self-loops,
and eight edge Parquet shards. Its undirected BFS reaches4095 vertices with
maximum hop distance11. The independent queue-BFS reference includes exact
distance/hops, source-parent0 and the rooted tight minimum-ID predecessor.

With the exact package source and this support directory in PYTHONPATH, root
runs on its owned existing endpoint:

```sh
python -B functional_client.py --endpoint sc://127.0.0.1:PORT \
  --case functional --fixture ABSOLUTE_FIXTURE --output FRESH_CELL --partitions 8
```

This producer uses `method=reference`, source0, undirected edges, snapshot inputs
and keyless checkpoint repartitions, cap32, full plan capture and complete
Parquet export. It preserves the existing distance/hops/parent contract. After
all engine/client processes have actually exited, root runs:

```sh
python -B fixture_oracle.py --fixture ABSOLUTE_FIXTURE \
  --cell FRESH_CELL --output FRESH_ORACLE_JSON
```

Require all4096 unique original IDs and complete schema/domain/null/parent
answers, unchanged source/input/output pins, both workers actually executing
tasks, and owned lifecycle closure. This qualifies the current reference shape
on a tiny native fixture; it does not diagnose the historical scale24 loss.

### 2. Deliberately induced pool refusal, separate fresh server

Start another owned fresh native two-worker server with an explicit greedy
pool of1048576 bytes **per participating process**, verify that effective value
on driver and workers, and retain PID/endpoint identities. Normal memory
admission and this tiny-pool configuration must remain separately named cases.

```sh
python -B functional_client.py --endpoint sc://127.0.0.1:PORT \
  --case pool-refusal --fixture ABSOLUTE_FIXTURE --output FRESH_FAULT_CELL \
  --partitions 8
```

The control groups1048576 distinct range IDs and writes the result. It deliberately
exceeds the small pool rather than host RAM. The producer records an induced
error as `expected_error_pending_log_qualification`; its zero exit alone is
never a causal or correctness verdict. Preserve partial output.

After engine exit require an attributable `execution_failure` record whose
original source names resource exhaustion/allocation refusal, during this query
and before cancellation/cleanup, along with task/peer/PID context. If logs show
only generic h2 errors, this diagnostic control remains unqualified. Record the
client’s observed error separately; it can be generic even when the initiating
operator refusal is specific. Require actual child waits, group absence, no
forced kill, unchanged input/source pins and a retained final inventory.

This control tests whether a non-kernel-OOM pool failure is visible and how it
propagates. Even if it succeeds, it is not evidence that a pool refusal caused
the original twelve failures. The historical verdict remains **unexplained**
until an original-shape recurrence captures its initiating cause.
