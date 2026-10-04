# C3 native quota correction and readiness

Observed clock UTC: 2026-10-02 00:17:16 UTC.
Written UTC: 2026-10-02T00:23:03.895361+00:00.

Scope: read-only audit of finalized A3 metadata/logs/samples and exact source Git objects. No engine, VM, big input/output payload read, repository edit or new timing run. C3 remains **partial/open**.

## Source identities

Source checkout for navigation: `/Volumes/Apo/graph-tests/workspaces/sem-review-20261001/pecan-f3b3ef8fc`.
Git objects reviewed independently of directory names:

- Controller: `f3b3ef8fc054ce7788ec2b46ec8b034ccec1f98a`.
- Loaded harness: `6ae2e43a903c2cee02da170465c922c72b76198e`.
- Actual retained Sail runtime: `56194b170155301ba91077f0ba3df31fe2c78b6b`; binary SHA `5b7f506c19afd76a28b84c1459397b4ab30ff4cfc761f4195789425b963facec`.
- Actual native source: `ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73`; native `.so` SHA `eb0be839de652e059799dea3bba22cc0908998bd97cfa2f4cf04c67817e2ee50`.

These runtime/binding/manifest files have identical SHA-256 at all four source pins:

| File relative to source checkout | SHA-256 |
| --- | --- |
| `crates/sail-session/src/extensions/mod.rs` | `52fe53eede88e4cbd6269db7a7dba9d407fdbc522436bbe6d6cd779be0f17cb0` |
| `crates/sail-session/src/extensions/worker.rs` | `bcf9de29c2ee3cce1d3071761009ec84dfb532581995f3cfd65e308abfd20a81` |
| `crates/sail-common-datafusion/src/native_resource.rs` | `870519edc188b9f836d297f460c6a9c019ccfbb6058433111085e32ecb55b843` |
| `crates/sail-session/src/runtime/memory.rs` | `4423dd1def70c9a8c8070c5bdbd1fe710d071b0e59b4305c16bdb809ff183579` |
| `examples/extensions/nutmeg/python/sail_nutmeg/__init__.py` | `8ab1469a2f7411203604d2faaae29b30a35689599eb62d0bb397ab672cdb53ab` |
| `examples/extensions/nutmeg/python/sail_nutmeg/argentea_factory.py` | `b79bb66e6dab06a8d3b405fcad3633614f394e89a35012ed2d1fb2095e43271a` |

Archived A3 `identities_before.native.files_sha256` records the exact same two Python manifest hashes. Source paths above are absolute when prefixed by the checkout path.

## Precise correction

The sentence “Each Pecan process prepays its 256 MiB native quota from its pool” is not established by A3 receipts and overstates the source contract.

- Nutmeg manifest `__init__.py:18–19` declares `placement: driver` and `memory_bytes` from `SAIL_NUTMEG_MEMORY_BYTES`.
- `extensions/mod.rs:232–246` registers worker-placement relations without a driver reservation; for nonworker manifests with `memory_bytes`, it calls `resources.reserve(&runtime.memory_pool, &identity, bytes)` before `bind_with_resources`.
- `extensions/mod.rs:382–386` skips driver-placement manifests in `load_worker_extensions`.
- Argentea manifest `argentea_factory.py:23–24` declares `placement: worker` and `memory_bytes` from `SAIL_ARGENTEA_MEMORY_BYTES`.
- `extensions/worker.rs:352–386` checks `(WorkerJobIdentity, operation)` owner reuse, reserves the quota, then binds the worker owner. This is lazy per job/operation/worker when a worker-native relation is materialized.
- Pecan's measured WCC/BFS controllers use relational DataFrame operations and compiled graph-utils scalar functions; they do not request Argentea worker-native relations. Source review supports Nutmeg driver-session prepayment and no automatic Argentea quota per idle worker. This is a **source inference**, not an observed reservation count.

Suggested replacement wording:

> The harness configures 256 MiB native quota settings for Nutmeg and Argentea. Native quotas are admitted from a process's ordinary pool when the corresponding extension owner is bound. The current receipts do not measure native reservation events or actual native allocated bytes.

For A3, the three 10 GiB greedy pool caps sum to a **potential configured 30 GiB total**. `engine_pecan.py`'s `config.native_quota` and `potential_pool_total_bytes` are configured intent/source-derived values, not observations of allocation or reservation. They must remain unchanged in raw frozen receipts. A2 local uses one configured 30 GiB greedy pool. Source `runtime/memory.rs:10–37` creates one explicitly owned pool domain per process; equivalent configuration is not shared ownership across worker processes.

## What A3 actually proves

`/tmp/sem-c3-readiness-audit.json` retains each metadata identity, all 30 cell observations, raw sample coverage, per-PID sampled PSS and exact source blob/SHA pins. Every enumerated archived metadata/log/sample file was unchanged after the audit. The published source gate is `A2-run04/A3-final-exact/receipt.json`, for Grust commit `ff819c41214d1785a2047005aa76f5bcff248c43`.

- 30 finalized A3 hosts passed; 15 Pecan cells, including 12 measured cells.
- All parent cgroup phases (`before`, `after_engine`, `after_oracle`, `final`) recorded zero `oom` and `oom_kill`; Docker `OOMKilled` was false in all 30 cells.
- For the 12 measured Pecan cells, sampled owned-engine PSS peaks were **1.913–3.703 GiB**, with **165–817** engine-present, complete PSS scans per cell. Declared cadence is 0.1 s; actual scan duration/gaps are retained per cell. Raw engine-present and complete-PSS row counts match the finalized receipt counts in all 30 cells.
- Final container lifetime memory peaks were **2.419–4.220 GiB** for measured Pecan cells. This includes page cache and earlier identity reads; the final boundary also includes the parent oracle. These peaks qualify this observed cit-Patents campaign, not a larger graph or a future physical memory guarantee.
- Sampled engine PSS excludes the supervisor/PID 1; sampled container PSS includes them. Per-process identities include the engine-controller PID and Sail driver PID, but samples do not independently label worker IDs or their pool identities.
- `memory.stat` exposes anon/file/kernel/sock at the four snapshots. It does not record concurrent peak transport buffers; a zero final `sock` value cannot prove zero transport memory during execution.
- Scratch directory scans measure files/bytes while the tree is moving. Checkpoints and exports share that scope; these are not operator spill counters.

Neither `32 GiB minus final cgroup peak` nor `PSS minus configured/reserved pool bytes` proves nonpool headroom. Pool reservations are accounting values and may include unallocated prepaid quota; PSS/cgroup peaks have different scopes and times. Current successful cells did not drive these 10 GiB pools near their limit.

## Requested fields and readiness

| C3 field | Current classification | Evidence / gap |
| --- | --- | --- |
| Per-process pool type/cap, potential total | Configured; source verified | A3 engine config, `runtime.py:144–173`, `runtime/memory.rs` |
| Actual ordinary pool reservation/current/peak | Unavailable | No periodic `MemoryPool::reserved()` trace or such receipt field |
| Native quota setting | Configured | Both native env values set to 256 MiB |
| Actual native quota admission/release | Unavailable in A3 | No native audit file or `pool_reserved` log; source supports opt-in audit |
| Actual native allocated/highwater bytes | Unavailable | Quota bytes are not allocated/RSS bytes |
| Transport queue/buffer bytes | Unavailable | Local overflow and Flight buffers lack retained byte counters |
| Owned-engine/container PSS and sample coverage | Measured | Full JSONL and receipt boundaries, gaps/counts retained |
| Cgroup lifetime/current/stat/event observations | Measured | Four parent phases plus raw engine before/after |
| Operator spills/count/bytes/rows | Unavailable in A3 | Runtime telemetry supports them; current logs/receipts do not retain them |
| Refusal/timeout/OOM distinction | Supported outcome categories; pressure behavior unproven | All A3 cells passed; no targeted memory-pressure cell |

`native_resource.rs:65–85,124–149` supports `SAIL_NATIVE_RESOURCE_AUDIT`: admitted/released JSONL events include UTC, PID, event ID, extension identity, quota bytes and `pool_reserved`. The reservation is nonspillable. Release is logged after the last lease owner's reservation is dropped (`:88–98`). These are lifecycle samples, not a periodic reservation peak trace or native allocation trace.

`stream/local/memory.rs:60–64,85–126` retains per-replica `VecDeque` overflow to avoid bounded-channel deadlocks. These queues hold Arc-backed batches and do not call `MemoryConsumer`/`MemoryReservation` in this file. Consequently a configured pool sum cannot bound their memory. Flight encode/decode in `stream/service/{server,client}.rs` also has no archived buffer byte counter. Logical queued bytes across replicas can double-count shared Arrow buffers; label the metric accurately.

`telemetry/data/metrics/registry.yaml:55–106` and `telemetry/src/execution/metrics/default.rs` map DataFusion spill count/bytes/rows and operator memory usage to optional execution metrics. `telemetry/src/telemetry.rs:152–196` activates metrics only when `export_metrics` is configured. Operator memory metrics are not aggregate `MemoryPool::reserved()` or transport queue accounting. The A3 warn logs contain no pool/native/spill counters and no metrics payload is archived.

## Minimal next audit, separate from timings

1. Use a fresh C3 namespace and a declared diagnostic profile. Keep the existing 16 CPU / 32 GiB / no-swap envelope, controller/runtime/native identities and full physical oracle. One cit-Patents min_label process-cluster cell exercises the highest observed A3 PSS and real exchanges; retain all output/failure/closure evidence. Treat its timing as diagnostic, not an addition to ABBA.
2. Enable existing `SAIL_NATIVE_RESOURCE_AUDIT` before server launch and retain its JSONL. Record actual process environment/roles and reconcile admission/release by `(PID,event ID)` and extension identity. Empty worker logs remain an observed zero-event scope, not a claim of 256 MiB worker prepayment.
3. Enable and export existing operator spill metrics; retain all per-job/stage/partition/attempt/operator attributes and final emission before teardown. Report missing operators/failed collection as unavailable, not zero. Include a small separate pressure control if zero-spill/refusal handling is to be qualified.
4. The remaining full C3 accounting requires a **small new instrumented runtime**, with its own source/binary pin: periodic/current/peak pool reservations keyed by process/domain, native actual allocation/highwater if applicable, and task-stream/Flight queue current/highwater logical bytes/batches with drop/release accounting. Preserve shared-buffer semantics and distinguish these counters from physical PSS.
5. Correlate simultaneous counters/PSS/cgroup observations and select total pool caps with measured nonpool allowance. Preserve resource refusal, successful spill, timeout, mismatch and OOM separately. Do not infer a safe cap from the existing cap sum or low-load cit peaks.

No C3 DONE claim is justified until actual pool/native/transport/spill accounting and the resulting headroom policy are proven.
