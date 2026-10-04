# Production WCC representative aggregate control

Recorded 2026-09-30T19:46:50.683674+00:00. The tiny Linux control passed; the independent
[audit](actual-control-audit.json) verifies all 11 collected file hashes, both
exact result sets and explicit worker task assignments. This closes the earlier
[component probe's](../min-by-probe/README.md) missing production-plan check for
this expression. It is not a full WCC, convergence, certificate, performance,
scaling or memory test.

The unchanged `wcc_fused.representatives(edges, 1, 0)` from controller
`3a9028057c6c6c5034492845926fc4bc18f9626f` ran on runtime
`2894a962076d3cc404dd72ec736ebeb9239901f6` with the original `ffcfbd569` venv/native
package. Source and binary guards passed before and after, with no cleanup
errors. The executable SHA-256 matches the retained
[289 Linux build receipt](../linux-builds/integration289/final/rebuild-receipt.json).
The [configuration](configuration.json) fixes two process workers, P=4, four
threads, 8 CPUs (16–23), a 12 GiB container and a 3 GiB participating pool.
The shared VM concurrently hosted the disjoint-CPU 561 build; no timing or
memory comparison is drawn from this run.

## Exact answer and actual worker path

The 14-edge fixture has 17 active vertices, including signed Int64 extrema,
values on both sides of the 2^53 precision boundary, duplicate/reversed edges
and a self-loop. With `a=1, b=0`, GF64 preserves every signed BIGINT ID. Both
input orders returned exactly the closed-neighborhood minimum for each active
vertex, with unique IDs and `id BIGINT, representative BIGINT` schema. Vertices
absent from the edge relation are outside this one-step function's contract.
The independent audit recomputes the oracle rather than accepting a passed label.

Both [explain plans](wcc-fused-representatives289-cpu16-23/cell/diagnostics/forward-input-plan.txt)
and the [actual task execution log](wcc-fused-representatives289-cpu16-23/cell/diagnostics/server.log)
contain partial and final-partitioned aggregates with:

```text
last_value(#3) FILTER (WHERE #4 IS NOT NULL)
  ORDER BY [#4 DESC NULLS FIRST] as min_by(#3,#4)
```

The audit pairs each aggregate plan's complete `(job, stage, partition, attempt)`
key with that same key's `worker_task_status ... SUCCEEDED` event. It does not
infer execution from adjacent merged log lines or from live PIDs alone.

| Job | Partial tasks on worker 1 / 2 | Final tasks on worker 1 / 2 |
| --- | --- | --- |
| 2 | 4 / 4 | 2 / 2 |
| 3 | 4 / 4 | 2 / 2 |

All 24 aggregate tasks have one matching RUNNING and SUCCEEDED event on the
same worker. For example, job 2/stage 2/partition 0/attempt 0 has its partial
aggregate at log line 104 and worker 2 success at line 234; job 2/stage
3/partition 0/attempt 0 has its final aggregate at line 194 and worker 1 success
at line 256. Every assignment and line number is retained in the audit receipt.
The per-case receipt does not record job IDs; naming job 2 as the first input
order and job 3 as the second would additionally rely on sequential call order.

This directly refutes the generic `MaxMinByAccumulator` route as the execution
path for this controlled expression. Selection of DataFusion's specialized
Int64 value state with scalar-vector ordering state follows from the observed
ordered LAST_VALUE expression, BIGINT inputs and the pinned factory source.

## Bridge to the component allocation evidence

The audit proves `Cargo.lock` and `crates/sail-function/src/aggregate/max_min_by.rs`
are byte-identical between actual runtime source `2894a962` and reviewed source
`b569e75d`. The wrapper also matches the component probe's copied source.
DataFusion aggregate/common 55.1.0 and Arrow array/data 59.3.0 have the same
version, registry source and package checksum in both lockfiles. The copied
`first_last.rs` matches the local registry source and its cached `.crate` member;
the archive SHA-256 equals the lockfile checksum. These identities are recorded
in [the audit](actual-control-audit.json).

The earlier System-allocator results remain standalone component measurements:
for example, 100,000 groups retained 11,692,032 requested bytes under that
probe's growth schedule. This Linux control does not measure those bytes,
process RSS, whole-query peak memory or aggregate group counts. It also does
not show that `EmitTo::First` occurs; the probe's prefix-emission allocation
finding remains conditional on that path being used. Compact struct MIN does
not apply to ordered LAST_VALUE or the separate Int64 `min(priority)` here.

[Preparation review](independent-preparation-audit.json),
[executable collection audit](audit_actual_control.py),
[collected results](wcc-fused-representatives289-cpu16-23/result.json) and
[raw receipt](wcc-fused-representatives289-cpu16-23/cell/diagnostics/receipt.json)
are retained. The initial audit runner expected registry checksum metadata that
was absent; its [failed attempt](actual-control-audit-attempt01.json) is preserved.
The completed audit instead verifies the cached crate archive and member bytes.
No implementation changed and the independent reviewer launched no workload.
