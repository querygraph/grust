# Morrobay takeover: typed Pecan experiments

Execution completed on Morrobay on 2026-10-01: **all 14 frozen steps passed**.
See the [returned evidence and comparison](morrobay-20261001/README.md).
The preparation narrative below is the retained handoff snapshot.

**Prepared, not launched.** The Morrobay agent takes execution ownership after
the operator hands over. The Capitola agent keeps independent review and will
not start a competing queue. Source checkouts, dependencies and helpers are
already staged; no new Sail server or benchmark cell has been started.

The [integration report](../pecan-validation-2026-10-01/README.md) establishes
the local correctness gates and reduced action count. This experiment asks
whether the integrated controller changes time or memory on a larger graph,
with the runtime, input and envelope held constant. It does not establish
multi-host scaling or a maximum supported Graph500 scale.

## Start here

Morrobay host directory:

```text
/Users/alexy/src/sail-extensions-gates/pecan-typed-tests-20261001
```

Docker context: `colima-sail-gate`, accessed with `/usr/local/bin/docker`.
Volume: `sail-extension-targets`. Inside it:

```text
/targets/pecan-typed-tests-20261001/
  baseline/   # detached cab6bacc0ad0d1fc8b3070e9e4267e99751909fe
  candidate/  # detached 6ae2e43a903c2cee02da170465c922c72b76198e
  deps/       # isolated Linux CPython 3.12 Pydantic dependency overlay
  support/    # frozen cell, oracle, smoke and host-wrapper source
  cells/      # empty at handoff; preserve all subsequent results
```

Read [plan.json](plan.json) and [run_one.py](run_one.py). The first command,
executed **on Morrobay**, is:

```sh
/usr/local/bin/python3.12 -I -B \
  /Users/alexy/src/sail-extensions-gates/pecan-typed-tests-20261001/run_one.py \
  --run-id typed-smoke-local --revision candidate --mode local --kind smoke \
  --support-sha256 0f378b86d2feaa93413d1fe573eef524c110f1c019f2dace955c22d1a8f5dc39
```

For each following plan step, substitute its `run_id`, `revision`, `mode` and
`kind`. `role` is metadata, not a CLI option. Run serially and inspect the host
`<run_id>/result.json`, producer `diagnostics/receipt.json` and container closure
before starting the next step. Stop on any nonzero exit, non-pass outcome or
uncertain closure. Do not automatically retry an ID or erase its output/lock.

The frozen sequence is two candidate compatibility smokes, four warmups (each
revision in each execution class), then four measured local runs in ABBA order
and four process-cluster runs in BAAB order. A is baseline; B is candidate.
Retain and report every cell, including warmups and failures. A process cluster
here runs inside one container on one host; it is not a two-host cluster.

## What is fixed

| Layer | Pin or boundary |
| --- | --- |
| Baseline controller | `cab6bacc0ad0d1fc8b3070e9e4267e99751909fe` |
| Candidate controller | `6ae2e43a903c2cee02da170465c922c72b76198e` |
| Runtime source | `56194b170155301ba91077f0ba3df31fe2c78b6b` |
| Runtime binary SHA-256 | `5b7f506c19afd76a28b84c1459397b4ab30ff4cfc761f4195789425b963facec` |
| Native source | `ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73` |
| Docker image | `sha256:f3518d652fbea8b9b9f9ebf9849277ca3bd39d0c21bb2c6e36fbaeaa2dc2678e` |
| Client | `/targets/graph-nuts-ffcfbd569/venv/bin/python`, PySpark 4.0.1 |
| Dependency overlay | Pydantic 2.11.10, core 2.33.2; [payload manifest](payload-manifest.json) |
| Fixed harness imports | Candidate `examples/extensions/benchmarks/{runtime,measurement}.py` |
| Workload | cit-Patents WCC, `randomized_fused`; 3,774,768 vertices, 16,518,947 edges |
| WCC envelope | 16 CPUs, 32 GiB cgroup, no swap; 16 partitions; local pool 24 GiB or three 8 GiB pools |
| Instrumentation | Warning-level server logs, durable iteration logs, 1-second sampler delay after each scan |

This compares two Python controllers on the same existing Linux binary. It
does not test a complete runtime rebuilt from the candidate commit. The earlier
local integration gate used a different runtime, so both Linux smokes must pass
before timing. [smoke.py](smoke.py) checks SSSP, BFS and WCC with sparse signed
IDs, an isolate and zero-weight ties, plus cleanup and source identity.

[cell.py](cell.py) records input hashes, module origins, runtime/native identity,
rounds, timing boundaries, memory, steal and shutdown. Input files and the
reference live under
`/targets/sail-stream-experiments-20260930/sem-wcc-pilot-inputs/`.
[oracle.py](oracle.py) checks every output vertex against the pinned exact
minimum-ID WCC membership, outside the algorithm timer. It rejects false
merges, splits, duplicates, omissions and physical-schema changes. It is a
benchmark oracle, not an input-validation job added to Pecan.

The public timer starts after creating lazy input handles; it includes public
WCC and complete result export, including observer overhead. Startup, hashing and physical verification
are separate. Report cgroup lifetime peaks separately from sampled process
memory and phase measurements. Keep local and process-cluster comparisons
separate. Treat Morrobay measurements as **ratios on a shared host**, disclose
steal and host pressure, and retain raw diagnostic times without presenting them
as dedicated-host performance. Historical debug-log runs are not the baseline.

## Admission and existing evidence

[readiness01.json](readiness01.json) records an earlier observation, not a
continuing reservation. At preparation, the host had about 32.3 GiB free,
`/Volumes/Apo` 60.9 GiB free and the guest volume 81.3 GiB free. Apo is not
currently a source of 6 TB free space. Refresh admission before each cell; the
wrapper checks Docker idleness, guest disk and available memory.

The old Graph500 queue has already stopped. Its final receipt is at:

```text
/Users/alexy/src/sail-extensions-gates/stream-experiments-20260930/
  next-graph500-20261001-supervisor/receipt.json
```

Pecan scale 25 reached producer/certificate success, but its physical output
audit remains pending. Grenada scale 24 stopped after a Docker observer exceeded
its deadline; this is not an algorithm verdict. Grenada scale 25 did not launch.
Leave the old `next-graph500.lock` and stopped
`sail-next-capacity-grenada-s24-1` container intact for diagnosis. The new wrapper
uses its own `cell.lock`. Never remove a retained lock just to advance the queue.
Argentea's two-host scale-24 diagnosis remains a separate task; see
[the existing handoff](../graph500-next-scale-2026-10-01/ARGENTEA-EARLY-FAILURES.md).

## Evidence and return handoff

[bootstrap01.json](bootstrap01.json) proves source/dependency staging and a real
Linux Pydantic import. [support-stage01.json](support-stage01.json) proves the
guest helper hashes, an empty cells directory and no running
containers in the experiment context after staging. Neither launches Sail.

[offline-controls03/receipt.json](offline-controls03/receipt.json) binds the
frozen helper hashes to **50 passing offline controls**: exact physical oracle,
legacy/Pydantic events, timer delegation, failure classification and wrapper
ownership/final-fault handling. Wrapper subprocesses were mocked. Earlier
receipts remain beside it; they are superseded helper gates, not extra engine
evidence. The Linux compatibility smokes and all timed cells are still pending.

Return the source/support pins, every host and producer receipt, raw logs,
memory samples, physical oracle verdict and container closure. Audit those
independently before summarizing a speed or memory change. Keep plans and reports
in Grust; code changes belong on named `work/` branches in `querygraph/sail`.
After this sequence closes, admit any larger-scale experiment separately rather
than extending this queue implicitly.
