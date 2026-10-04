# Sail graph implementation and benchmark review

The unexplained relational stream loss remains **unexplained**. The retained
evidence does not identify the first failing peer, stream or task cause. The
next useful run needs better error capture; the proposed logging-only change
does not expose all the missing information. Separately, this review found
correctness-checking, protocol-validation, scalability and reporting defects.

## Scope and source identities

- Fable's completed handoff: Grust `b91828b2765ec2018e21011aea686e931af68c99`,
  [STREAM-LOSS-STATUS.md](../../STREAM-LOSS-STATUS.md), plus the campaign record
  and [WHICH-PATH.md](../../WHICH-PATH.md).
- Sail runtime and graph implementations: `work/s5-frontier-build-side`,
  `ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73`.
- Inspected working checkout: `837a8ecf5c2c3b8ad24e044c72c1cb69d9fc71f4`;
  its only change from the runtime target is two-host qualifier environment
  passthrough. Host matrix runner also reviewed at `ae3b08f4f`.
- Pecan/Grenada controllers, Banda staging/admission and native kernels,
  Argentea core/worker adapters, transport and task lifecycle, benchmark
  certificates/exporter, and selected original receipts/logs were inspected.
  This is not a new full-workspace or distributed qualification.

Sail code links below resolve in the local checkout. Their line references
describe the pinned implementation above. Evidence and reproductions are
retained beside this report; no Sail implementation was changed.

## Findings

### 1. P1: WCC certification can accept a wrong component partition

[graph_cell.py:255](https://github.com/querygraph/sail/blob/ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73/examples/extensions/benchmarks/graph_cell.py#L255)
checks coverage, non-null labels, edge consistency and existence of the named
label vertex. It does not prove that a reported component is connected.

Counterexample: vertices `0,1,2,3`, edges `0–1` and `2–3`, every output label
`0`. Every accepted predicate passes, including cardinality, but two real
components have been merged. The label-existence join also does not itself
require that the named vertex carry that label.

The receipt discloses `component_count_verified=False`, which is useful, but
the outer outcome is still `passed`. These checks establish a partial
property, not exact WCC. The docstring reverses the gap: **coarser** partitions
can pass, not finer partitions that split a connected component.

Require a connectivity witness per label, or distinguish partially checked
WCC from independently verified WCC in outcomes and prose. Retain the
counterexample as a corruption control. Evidence:
[predicate reproduction](benchmark/wcc_predicate_counterexample.py),
[result](benchmark/wcc_predicate_counterexample.json). This reproduces the
actual predicates without Spark; it is not a Spark integration test. No
incorrect campaign output is alleged merely because its verifier is weak.

### 2. P2: transport errors and first-failure provenance are lost

[stream/error.rs:38](https://github.com/querygraph/sail/blob/ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73/crates/sail-execution/src/stream/error.rs#L38)
reduces an ordinary Tonic status to `Unknown(status.message())`. Unless it
contains Sail's special serialized task-stream cause, this loses the gRPC
code, metadata and error source. The outer body-read message alone cannot
distinguish several transport causes.

Task failures are **not** sent to the driver as status alone:
[handler.rs:161](https://github.com/querygraph/sail/blob/ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73/crates/sail-execution/src/task_runner/actor/handler.rs#L161)
forwards both `message` and `cause`. However, its debug log at line 142 omits
both. The scheduler stores them, then
[infer_job_failure_cause:586](https://github.com/querygraph/sail/blob/ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73/crates/sail-execution/src/driver/job_scheduler/core.rs#L586)
chooses by number of failures and stage/partition order, not by the first
failure's time. A downstream cancellation can therefore obscure the useful
originating error in the returned diagnosis.

Changing `RUST_LOG` alone cannot print fields absent from the log call.
Before rerunning, record failures at the worker before conversion/teardown,
including task key, worker/process identity, full error chain and gRPC code.
Record the stream key and peer at the Flight boundary; keep the first observed
job failure separately from later cancellation errors. The harness also
[overwrites RUST_LOG](https://github.com/querygraph/sail/blob/ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73/examples/extensions/benchmarks/runtime.py#L169),
so a recorded, configurable log setting is needed.

### 3. P2: the local reset-limit hypothesis counts the wrong resets

Handoff lines 151–161 connect ordinary dropped task streams with the 1,024
local-reset threshold. In the **locked h2 0.4.15 source**, that threshold is
for locally generated **protocol-error** resets. Explicit user resets and
implicit response-body cancellation do not increment the same counter.
Remote resets before server acceptance have a different limit and remain a
separate hypothesis.

A standalone control completed 1,100 accepted response-body cancellations,
observed `CANCEL` at the peer, then received another response on the same
connection with `max_local_error_reset_streams=1` on both peers. It passed
in debug and three release runs with one load process per logical CPU.
[Source and lockfile](h2-cancellation-probe/src/main.rs),
[debug log](h2-cancellation-probe/run.log),
[loaded release results](h2-cancellation-probe/release-loaded.json).
This tests h2 cancellation semantics, not Sail transport qualification.

In the retained two-host log, first FAILED is line 2305 at `06:12:10`;
the reset warning is line 2748 at `06:12:11`, after **443 FAILED entries**.
There are 651 FAILED entries overall. The warning has no process identifier.
The merged log cannot establish causality or safely identify which process
emitted it. It is consistent with a cascade after an earlier fault.
[Log hash and extracted observations](two-host-log-observations.json).

Count actual per-connection resets and their reasons before attributing this
failure to partition count. `32 × 32` logical shuffle channels is not by
itself a count of protocol-error resets on one connection.

### 4. P2: memory exclusions overstate what the receipts establish

The handoff lists 15 relational failures, excludes three with memory events,
then says eleven remain with 34–80 GiB headroom. That leaves **twelve**, and
one is near the limit: baseline scale-24 Grenada BFS frontier has **91.903 GiB
PSS but 99.925 GiB cgroup usage** in a 100 GiB container, with zero recorded
`max` or OOM events.

PSS is not the cgroup's entire charge. Zero OOM events rules out a recorded
cgroup OOM kill; it does not rule out cache pressure, host swapping or stalls.
Some other failures do have substantial cgroup headroom, so the non-OOM
problem is real. Narrow the exclusion to those cells, use cgroup usage for
container headroom, and keep process-liveness evidence separate from a claim
that the process was responsive.

[Receipt-derived evidence](benchmark/collect_receipt_evidence.json) includes
the paths and exact byte values. No new large benchmark was run.

### 5. P2: Argentea BFS accepts an inconsistent completion record

[bfs/protocol.rs:232](https://github.com/querygraph/sail/blob/ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73/examples/extensions/argentea/src/bfs/protocol.rs#L232)
compares completion totals with producer statistics for Topology, Pull and
Done, but omits Reference/Push. In a core fault-injection control for `0 → 1`,
discarding the sole candidate and changing its completion sequence to zero
causes both Reference and Frontier to certify convergence with vertex 1
unreachable. The previously supplied producer `frontier_edges` statistic
would reveal the inconsistency.

Check the total against the applicable producer statistic in those modes.
[Reproducer](native/bfs-completion-reproducer.rs),
[output](native/bfs-completion-result.txt),
[exact-build provenance](native/provenance.json).
This requires an inconsistent producer/completion; it is not proof that
ordinary transport truncation is silently accepted or that this happened in
the campaign.

### 6. P2: Pecan delta-star checks overflow after a saturating integer cast

[traversal_stepping.py:22](https://github.com/querygraph/sail/blob/ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73/examples/extensions/graph-algorithms/src/pyspark_pecan/traversal_stepping.py#L22)
computes SQL `floor(distance/delta)` before checking `math.isfinite(bucket)`.
Sail's Float64 floor returns Int64 using a saturating cast: infinity becomes
`9223372036854775807`, so the overflow check cannot reject it. Finite
quotients above the Int64 range also collapse into the same bucket.

The query control observed this for `1.0 / 1e-310`, and observed identical
buckets for `1e20` and `2e20`. The native Banda stepping implementation checks
the floating quotient before selecting the frontier. Validate the quotient before floor
and make the supported bucket range explicit across backends.

[Evidence](pecan/floor-query-receipt.json),
[runtime/source provenance](pecan/provenance.json). The query used an older
verified executable whose floor implementation is byte-identical to the
reviewed commit. It is not a gate for the current runtime. A supplemental
local storage-shim controller experiment is retained and explicitly labeled;
it is not distributed or GraphUtils lifecycle evidence. These examples do
not establish incorrect shortest-path distances in the campaign.

### 7. P2: Argentea SSSP keeps doing graph-sized work after convergence

[sssp/partition/protocol.rs:186](https://github.com/querygraph/sail/blob/ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73/examples/extensions/argentea/src/sssp/partition/protocol.rs#L186)
unconditionally allocates a pending mask, copies every label and scans the
candidate array even in `SsspMode::Done`.
[Values::copy:120](https://github.com/querygraph/sail/blob/ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73/examples/extensions/argentea/src/sssp/partition.rs#L120)
also allocates full active-vector capacity. Every unused unrolled phase can
therefore add O(V) work and transient allocation after convergence; a larger
round cap is not free. BFS already skips its corresponding update in Done.

Add a Done relay path that preserves the protocol checks without copying
the graph-sized state, and account for finish-side work in diagnostics.
This is a source finding, not a measured attribution of the campaign's time
or memory failure.

### 8. P2: current campaign outcomes cannot be exported consistently

[graph_cell.py:547](https://github.com/querygraph/sail/blob/ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73/examples/extensions/benchmarks/graph_cell.py#L547)
does not classify Argentea's typed round-cap failure. The scale-24 SSSP
delta-star decision cell has native audit records `sssp_round_cap`,
`outcome=nonconverged`, `rounds=max_rounds=30`, while receipt and summary say
generic `error` after the client received cancellation. Use scoped native
failure evidence to preserve nonconvergence distinctly from transport errors.

The shipped [summarize.py:140](https://github.com/querygraph/sail/blob/ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73/examples/extensions/benchmarks/summarize.py#L140)
still expects three single-file datasets and PageRank parameters. It rejects
the partitioned Graph500 certificate fixtures. Its display-name table also
lacks Argentea, and the actual `tables()` call raises `KeyError('argentea')`.
The [repository map](../../GRAPH-NUTS.md) already acknowledges that this older
summary tool is not applicable; that prevents treating its false failures as algorithm failures,
but leaves the current harness without this complete export path.

[Executed receipt/exporter controls](benchmark/collect_receipt_evidence.json)
retain both issues. Update schema-aware validation and outcome rendering
together, with explicit controls for pass, certificate failure, cap,
admission refusal, timeout and transport error.

## Additional corrections to the interpretation

- **Deployment and distribution:** Pecan also distributes work across Sail
  workers, with an explicit PageRank/WCC two-host workflow in its `TESTING.md`; Argentea
  is not the only path capable of spanning hosts. Pecan needs no native
  graph-kernel package, but its constructor requires the server's
  `gf.utils.v1` owned-run storage capability
  ([utils.py:42](https://github.com/querygraph/sail/blob/ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73/examples/extensions/graph-algorithms/src/pyspark_pecan/utils.py#L42)).
  “Runs anywhere Sail runs” omits that requirement. Grenada's benchmark
  adapter aliases GraphTables columns and calls the same Pecan controller;
  its comparison establishes entry-path parity, not an independent native
  traversal implementation. The two-host workflow establishes distribution
  capability, not large BFS/SSSP qualification.
- **Scale-25 verification:** the baseline Pecan push-pull and Grenada
  push-pull/frontier outputs were written but failed their certificate query;
  their receipts have `outcome=error` and no correctness result. Baseline
  Pecan frontier passed. The later gate-2 **Grenada push-pull did pass with a
  certificate**, as did Pecan frontier again. Keep that success: use its
  identity, not the uncertified baseline's timing, in the decision guide.
  The recommendation is partly supported; the four baseline completions are
  not four verified results.
- **Scale 22:** its manifest/campaign use 67,108,864 edges, not the guide's
  16.8M. Scale 22 to 24 grows fourfold in edges at the stated edge factor,
  not sixteenfold. Correct both derived scaling statements.
- **Iteration attribution:** weighted Pecan reference/frontier execute the
  overflow-check expansion query *before* `iteration_start`
  ([traversal.py:57](https://github.com/querygraph/sail/blob/ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73/examples/extensions/graph-algorithms/src/pyspark_pecan/traversal.py#L57)).
  Delta-star records its start earlier, but explains `relaxed`, not the
  overflow-check action. `materialize` adds repartition and a Parquet sink.
  Name individual actions/jobs and capture their executed plans before
  asserting which join failed or comparing time inside a round.
- **Idle-probe attribution:** the actual idle predicate requires both vacant
  slots **and no tracked local streams**. Native stages are constrained to
  the same region/group/bucket. A logged worker stop alone does not prove
  that the stopped worker owned required live native state or shuffle output.
  Preserve the observed stop; establish its job/owner relationship before
  calling the specific mechanism closed.
- **Banda admission formula:** supported primitive/Utf8 sort keys use
  `key_bytes_bound`; the cited `16× buffers + 128 bytes` rule is a fallback.
  Preserve the refusal and its recorded allocation components, but identify
  the actual staged schema before attributing it to that fallback formula.
- **Performance causality:** different core counts, OS/runtime execution,
  Rosetta and shared-host interference do not isolate shuffle cost from
  kernel cost. Report phase CPU/wait evidence before concluding where time
  went. Retain observed ratios with their boundaries; no timing measured
  during this review is offered as a performance result.
- **Population and timers:** “every scale-24 Banda/Argentea cell passed”
  excludes recorded refusals, failures and the SSSP cap. Variable time since
  iteration start does not exclude a timer measured from a different event.
  A larger timeout not curing a failure is narrower evidence than ruling
  the mechanism out. Several document times also mix measurement boundaries;
  reconcile them against receipts before using them in ratios.

## Next diagnostic step

Do one instrumented reproducer after validating the instrumentation cheaply.
Do not start another broad matrix to identify this failure.

1. Add and test the failure capture described in finding 2. A deliberately
   failed small task must produce its first cause, key and peer before cleanup.
   Record effective settings, exact executable/wheel/controller identities,
   and separate per-process logs or process labels.
2. Run one previously failing cell with unchanged dataset, source, partition
   count, memory limits and algorithm. Include connection diagnostics, task
   causes, named query boundaries, cgroup counters and sampler gaps. Establish
   that this exact build/settings combination still reproduces the problem.
3. Select the next control from the observed first failure. Test keepalive
   only if a ping timeout is implicated; test reset protection using its
   actual reset reason and connection. Fewer partitions changes memory,
   scheduling and work distribution as well as stream count.
4. Treat a changed outcome as evidence, not sole proof of a cause. Shared-host
   variability and changing multiple settings require matched repeat/control
   runs when necessary. Preserve all failed attempts and distinct outcomes.

The worker-to-worker Flight client uses the shared client builder with the
128 MiB decode setting. Thus the specific “Flight bypasses the decode fix”
branch of H4 is refuted by source inspection. This does not prove that every
possible message-size boundary is irrelevant.

One additional hypothesis worth testing is executor responsiveness:
Argentea initialization, finishing and some emission scans perform substantial
synchronous work during async polling. Yielding between output batches does
not bound the time spent producing a batch. This warrants a bounded-work or
heartbeat responsiveness control; it does not explain Pecan's relational
failure without further evidence.

## Validation and limits

- 92 Argentea core release tests passed at the exact runtime SHA in a clean
  detached worktree with a separate target and incremental compilation off.
  [Full output](native/argentea-core-release-tests.txt). This is core
  functional evidence, not a distributed or concurrency-stress gate.
- The BFS malformed-completion counterexample reproduced against that build.
- The h2 cancellation control passed once in debug and three times in release
  with ten concurrent load processes, all terminated and reaped afterwards.
- The WCC predicate counterexample and actual exporter/receipt controls passed.
  Their scope and dependency limitations are recorded with their results.
- Pecan's floor semantics were observed with verified artifact provenance and
  byte-identical relevant source; no current full-runtime Pecan gate is claimed.
- Original Morrobay evidence was read only. No remote benchmark or production
  action was launched. No full Sail workspace, full Banda gate, book build or
  crate publication was needed for this review-only delivery.
