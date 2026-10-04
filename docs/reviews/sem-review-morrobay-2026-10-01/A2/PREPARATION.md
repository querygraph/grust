# A2 and A3: matched Parquet input/output experiment

This directory contains the frozen plan and execution helpers. **Inputs
validated; compatibility adapter correction in progress; measured cells are pending.** Completed receipts will
supersede this preparation status. Grust's root `AGENTS.md` governs this work;
the experiment directory is evidence, not a repository policy source.

## Scope and pins

The comparison is on Morrobay, a shared host. Publish ratios within an execution
class; raw times are diagnostics, not dedicated-host performance results.

| Layer | Fixed identity |
| --- | --- |
| Pecan controller, including B9 and B10 | `querygraph/sail` `work/wcc-affine`, `f3b3ef8fc054ce7788ec2b46ec8b034ccec1f98a` |
| graphframes-rs source | `b4da56dabe20bba8e29563e06acc5179b2113ce3` |
| graphframes-rs release ELF SHA-256 | `b2a7fc0f077fafc158aaa8a45ac32e5f2af5b3d96b8050c348421fa79442722f` |
| Sail runtime source | `56194b170155301ba91077f0ba3df31fe2c78b6b` |
| Sail release ELF SHA-256 | `5b7f506c19afd76a28b84c1459397b4ab30ff4cfc761f4195789425b963facec` |
| Native package source | `ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73` |
| Native library SHA-256 | `eb0be839de652e059799dea3bba22cc0908998bd97cfa2f4cf04c67817e2ee50` |
| A1 container image | `sha256:f3518d652fbea8b9b9f9ebf9849277ca3bd39d0c21bb2c6e36fbaeaa2dc2678e` |
| Frozen runtime and measurement harness | `6ae2e43a903c2cee02da170465c922c72b76198e` |
| Guest interpreter | `/targets/graph-nuts-ffcfbd569/venv/bin/python`, Python 3.12.14 |
| Guest dependencies | PySpark 4.0.1, Pydantic 2.11.10, NumPy 2.5.3, PyArrow 21.0.0 |

This tests a new Python controller on the existing pinned runtime and native
package. It does not claim a runtime rebuilt from `f3b3ef8fc`. The source audit
records the unchanged protocol/runtime bridge; actual compatibility controls
must pass before the larger cells.

## Algorithms and contracts

Read [SOURCE-CONTRACTS.md](SOURCE-CONTRACTS.md) and the complete
[source audit](source-contract-audit.json).

- WCC: Pecan `randomized` and `min_label`, canonical minimum original IDs;
  graphframes-rs randomized contraction, seed 42. The `wcc-min-label` name in
  a graphframes cell identifies its comparison, not a graphframes method.
- BFS: directed unweighted hops from the same raw vertex ID, `5795784`.
  The first phase refused absent source `750000`; selection of the existing
  source used maximum outgoing edge-row count, ties by minimum raw ID, before
  any timing. Pecan's frontier
  implementation also computes parents and a convergence certificate
  internally; only full ID/distance output is compared. The additional work
  remains in its timer.
- PageRank: **not comparable pending a matching contract/B11**. Source review
  found different initial and terminal coefficients even with a fixed cap and
  zero graphframes threshold. Normalization does not repair the difference.
  No PageRank timing is admitted by this plan.

The B9 source audit identified a signed-ID/isolate collision. A separate tiny
control checks vertices `[1, 2, -7694170072594669674]` and edge `1 -> 2` at seed
42. Its expected partition is `{1,2}` plus the isolate. An exact reproduction
of the predicted false merge is retained as `known_mismatch`, never as a
correctness pass. The cit-Patents experiment may proceed only with independently
verified zero isolates and a full oracle on every cell. This is not a general
signed-ID WCC qualification. No algorithm is patched in this experiment.

## Input validation and references

The original LDBC cit-Patents Parquet inputs remain unchanged:

| File | SHA-256 |
| --- | --- |
| `cit-Patents-v.parquet` | `0969ea9ede0969e18e76a2c70191ed7ccecaecb9f1da6d954093dbefbc8958aa` |
| `cit-Patents-e.parquet` | `70bcba17b5a7762ef5a0c3d16c1dc37a352461b83e338f550ae897d844f0268f` |
| Independent WCC membership | `b07f8665c87f94286da7beb1ac5a9d13c4932fea31d8f1a382f9ecb1d3c0c8dc` |

There are 3,774,768 vertices and 16,518,947 directed edges. The WCC reference
was constructed locally by independent union-find; it is not a downloaded
official ground truth. Its construction evidence is retained with the earlier
cit-Patents experiment.

[prepare_inputs.py](prepare_inputs.py) runs once outside all engine timers:
schema, uniqueness, nulls, endpoint membership, source membership, and an
independent NumPy CSR/deque BFS with edge and predecessor certificates. Its
portable references are little-endian signed 64-bit IDs and hop counts in the
same sorted ID order; `-1` denotes unreachable. Reference and original input
hashes are checked before and after. Dataset-specific positive-ID assumptions
are explicit; they do not narrow Pecan's public BIGINT contract.

The [physical output oracle](output_oracle.py) verifies every vertex after
the engine exits: exact schema, IDs, coverage, uniqueness, WCC partition and
BFS hops. Engine-specific unreachable sentinels are decoded only in the oracle;
original output bytes are retained. No validation job is added to an algorithm.

## Resource and timing boundary

Every engine gets a fresh process and container: 16 CPUs, cpuset `0-15`, 32 GiB
cgroup, no swap, 16 partitions. graphframes uses its 30 GiB FairSpillPool and
SnMalloc; Pecan uses a 30 GiB greedy pool and mimalloc in local mode. In A3,
driver plus two workers each get 10 GiB; their total is 30 GiB. Each native
256 MiB quota is prepaid from its process pool. Pool accounting is not a proof
of a 32 GiB RSS bound: cgroup peaks, OOM events and headroom are observed.

The compared timer is **immediately before engine `Popen` through its completed
wait and certain exit**. It includes startup, input reads, Pecan's existing
snapshot rewrite, algorithm, complete Parquet output, cleanup and shutdown.
Hashing, reference construction, physical oracle and parent observation are
outside that timer. Identity reads can warm filesystem caches for both engines;
fresh processes do not imply cold storage. Snapshot and other phases are reported separately without
subtracting them from the stated launch-to-exit measurement.

Sampled engine PSS excludes the supervisor. Whole-container sampled memory and
cgroup lifetime peaks have separately labelled boundaries, including page
cache and parent observations. Guest steal and admission pressure are retained.
A3 runs Pecan's driver and two workers inside one container on one host.
Its graphframes control remains a single CLI process with 16 workers; the
comparison's `process-cluster` label does not turn graphframes into a cluster.
This experiment does not measure multiple hosts.

## Staging observation

The `stage01` producer passed at `f3b3ef8fc`, with unchanged binary and payload
hashes. Its host verdict is retained as `error`: the absence parser rejected
Docker's lowercase `no such object` message after successful removal. A fresh
name/ID inspection and idle-context observation confirmed closure; the closed
lock was archived, preserving its original owner record. See the
[closure review](stage01-closure-review.json). No algorithm ran in that attempt.

The parser now handles either case and continues to reject other inspection
errors. The corrected host driver is indexed separately under `controller-v2`;
the staged guest payload and its `0f4d700c` helper tree remain immutable.
Validation uses a fresh phase ID, rechecking every staged identity.

## Sequence and retained evidence

[plan.json](plan.json) fixes 60 steps: A2 local first, then A3 process cluster;
for each of randomized WCC, min-label WCC and BFS, one warmup per engine and
two measured ABBA blocks. There are 48 measured cells and 12 warmups.

One heavy gate job runs at a time. The host wrapper admits each cell afresh,
pins its container identity, copies the complete output tree, and verifies
certain closure before releasing the lock. Stop on any unexpected outcome,
failed oracle, OOM, timeout or uncertain closure. Retain failed IDs, logs,
receipts and locks; use a fresh explicit ID for any later attempt.

The [current plan](plan.json) records the active namespace; the
[initial plan](plan-initial.json) is retained. Failed preparation attempts are
under `A2-run01`, `A2-run02` and `A2-run03` in
`/Volumes/Apo/graph-tests/results/sem-review-20261001/`.
The host archive keeps large result Parquet files; Git keeps indexed portable
receipts, helper sources, gates and reports. After A2 and A3 close, B8 requires
its own paired plan and admission on cit-Patents and official scale-24 inputs.
