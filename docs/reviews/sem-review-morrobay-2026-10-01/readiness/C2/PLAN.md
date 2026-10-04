Written UTC: 2026-10-02T00:44:03.964471+00:00.

Source-audit SHA-256: `bbfcc751d0e69c02dcce6dd4d4988b8d2221eb5f25771998bbf5f49718a5fc6b`.

# C2: distributed job fixed-cost probe plan and interface

Status: **readiness partial; C2 remains open**. This is a source and retained-metadata audit, with a proposed executable contract. No Docker, VM inspection, engine, benchmark, large data read, source edit or live lock action was performed. No complete probe helper was authored: the required runtime observations do not exist at the actual binary pin. A wrapper alone cannot manufacture them.

## 1. Exact identities and historical scope

Governing repository: `/Users/alexy/src/grust`, `AGENTS.md`, `docs/SEM-REVIEW-2.md` C2 row and section 9. Source checkout for navigation: `/Volumes/Apo/graph-tests/workspaces/sem-review-20261001/pecan-f3b3ef8fc`. Git object identities, rather than its directory name, were checked:

| Role | Pin |
| --- | --- |
| Pecan controller | `f3b3ef8fc054ce7788ec2b46ec8b034ccec1f98a` |
| Loaded Python harness | `6ae2e43a903c2cee02da170465c922c72b76198e` |
| Actual Sail runtime | `56194b170155301ba91077f0ba3df31fe2c78b6b` |
| Retained runtime binary SHA-256 | `5b7f506c19afd76a28b84c1459397b4ab30ff4cfc761f4195789425b963facec` |
| Native source | `ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73` |
| Native shared object SHA-256 | `eb0be839de652e059799dea3bba22cc0908998bd97cfa2f4cf04c67817e2ee50` |

`/tmp/sem-c2-source-audit.json` records twenty source files' Git blobs and SHA-256 at all four commits. It also records before/after hashes of the small governing and historical evidence files, which were unchanged. The actual runtime and controller may agree for a file while the older native/harness commit differs; the JSON retains each identity independently.

The old `wcc-fused-worker-plan/{probe.py,run_probe.py,actual-control-audit.json}` uses runtime `2894a962076d3cc404dd72ec736ebeb9239901f6`, controller `3a9028057c6c6c5034492845926fc4bc18f9626f`, two process workers and P=4. It used an 8-CPU/12-GiB control, with an overlapping build on disjoint CPUs. Its two 17-row representative results passed the full oracle; 24 actual Partial/FinalPartitioned task assignments succeeded on both workers. It did not measure C2 phase timings, directly bind each case name to a job ID, or exercise the current removed-`wcc_fused` surface. Preserve it as historical correctness and placement evidence only.

## 2. What the current runtime can expose

These are source-supported observations, **not measurements obtained in this audit**. Existing A2/A3 receipts do not contain the optional phase traces.

| Requested observation | Existing support at runtime 561 | Remaining gap |
| --- | --- | --- |
| Full client action wall time | Python monotonic timer around raw Arrow action | New wrapper must define exact boundary and preserve all outcomes |
| Python relation construction and Connect protobuf plan construction | Wrapper can time separate calls | Not server planning or wire serialization |
| Server resolve / logical optimization / physical planning | `sail-plan/src/lib.rs:34–78` performs them | No dedicated phase durations; `plan_executor.rs:123` combines the call |
| Distributed physical plan encoding | `job_scheduler/core.rs:724` calls the encoder | No separate clock; definition construction also builds stream inputs/outputs |
| Stage definition construction | `driver/actor/handler.rs:636–654` logs `Instant` duration per job/stage | Combined scope; definitions are cached per stage per scheduling snapshot, not one encoding per task |
| Worker batch protobuf decode | `task_runner/actor/handler.rs:63–66` decodes once per batch | No separate decode timer |
| Per-task blocking preparation queue and work | `task_runner/preparation.rs:199–217` logs wait and duration | Work combines plan conversion, scan and shuffle rewrite; it is not a stream-only or scheduling-only duration |
| Task monitor lifetime | Optional `TaskMonitor::run` span, `monitor.rs:61–78` | Lifetime overlaps execution; not fixed setup overhead |
| Jobs, stages, partitions and statuses | Optional SystemEvent export / system store | Task event omits worker ID; job event omits Spark operation ID |
| Worker assignment and actual plans | Debug task/driver records and structured source identities | Need direct per-operation association, no sequential-job guessing |
| Scheduling queue, dispatch and worker admission | State transitions and RPC code exist | No complete phase clocks or direct causality record |
| Stream creation, first batch, EOF and final release | Local and Flight code contains lifecycle operations | No dedicated complete setup/teardown timing events |
| Session/server teardown | Wrapper can time owned stop/wait/closure | Not query stream/resource release; measure separately |

`plan_executor.rs:119–140` creates a random root span and a `JobRunner::execute` child. Resolution happens before the local root guard is installed. The root carries no explicit Spark operation/session property. `job_runner.rs:120–140` sends `ExecuteJob` and returns the stream without a client operation/job correlation field. `SystemEvent` job/task events (`sail-system-store/src/event.rs:30–87`) contain UTC timestamps and execution IDs, but task events contain no worker ID. System task tables also omit that field.

Optional trace export requires `telemetry.export_traces` and an OTLP endpoint; the default uses a no-op reporter. SystemEvent bodies can be exported by existing log telemetry, or queried from the system store outside measured actions. Neither provides the missing phase split. Default human log prefixes use `buf.timestamp()` (`telemetry.rs:208–214`), observed historically at seconds precision; they cannot qualify a 100-ms budget. The embedded `Instant` durations are a distinct, higher-resolution observation.

Key exact runtime SHA-256 values, with full absolute paths and all commit/blob identities in the JSON:

| Path relative to source checkout | SHA-256 |
| --- | --- |
| `crates/sail-spark-connect/src/service/plan_executor.rs` | `80f3e1d0627a65f022af7fc02bf273e91eb7e9c13e7c9ce6171f50f719eb16c7` |
| `crates/sail-plan/src/lib.rs` | `c30b1f77e2c3b231a6e5ee1d7909fd3e542a6f7d755f785e8dbc070a7309d548` |
| `crates/sail-execution/src/driver/actor/handler.rs` | `b9d9de437ed2765443fd8b3e9ed42bf097d4b867bed6f98854e61460f7e6db92` |
| `crates/sail-execution/src/task_runner/preparation.rs` | `24237bfe3a6012953fcc29964d840ef0e65f08206d197057c5f83babdc144e30` |
| `crates/sail-system-store/src/event.rs` | `e67cbb858061d90ba341cc5fd2090121af2edb5436397cee3696e157add09853` |

## 3. Bounded fixture and query

Use a neutral grouped MIN/COUNT query to measure one ordinary distributed job. This measures its own execution shape, not complete WCC/BFS or Pecan round latency. It requires no native graph extension setup query. The frozen B8 eight-ID GF42 representative fixture is useful source-contract material, but eight groups alone can leave most P=32 partitions empty; do not substitute it and assume adequate task coverage.

Preparation, once and outside every action timer:

- Eight immutable Parquet fragments, each containing the same 4096 unique `key: int64` values and a `value: int64`; no nulls. Total 32,768 rows, 524,288 uncompressed logical bytes before Parquet metadata.
- Eight special keys: `-2**63`, `-2**53-1`, `-7694170072594669674`, `-1`, `0`, `1`, `2**53+1`, `2**63-1`; add integers 1000 through 5087 inclusive to reach exactly 4096 keys.
- For fragment `j` in 0..7 and key ordinal `i`, ordinary values are `17*(i+1)-j`. For the minimum key use `-2**63+j`; for the maximum key use `2**63-1-j`. Every value is exactly signed64.
- Independently derive all expected `(key,minimum,count)` using Python integer dictionary MIN and count. Write sorted signed64 little-endian triples, a schema/row receipt, and original file identities. Do not derive the reference from the engine output or shared engine expressions.
- Pin every original fragment/reference file by bytes and SHA-256; inspect its actual Arrow/footer schema, nulls and bounded rows once. Retain ordering and original generation immutability.

Proposed relational expression: read the fragment directory; `repartition(P, "key")`; `groupBy("key")` with `MIN(value)` and `COUNT(1)`; project exactly `key,minimum,count`. Do not add `orderBy`, sink writing, a count-only result, `limit`, or checkpoint. Cross-fragment repeated keys require global reduction, but **API repartition is not the qualification**.

At each P=4/16/32, separate fresh-server validation must show an actual hash exchange separating cross-fragment rows before their complete grouped reduction, aggregate output stage partition count P, and successful aggregate tasks on both worker processes. Retain each actual aggregate mode, the JobGraph edge, concrete task attempt keys, worker IDs/PIDs and output row counts per partition when available. Partial/FinalPartitioned is one qualifying route; a complete single aggregate per correctly hash-partitioned key group also qualifies. The explicit repartition can change aggregation modes, so do not require the historical probe's exact mode pair. Scan and any Partial task counts may differ from P; record actual counts rather than assuming P for every stage. No exchange, missing mapping, unexpected driver-only final work, incomplete trace, or absent worker success is a distinct nonqualification, even if the answer is correct.

Every measured action also needs its own actual execution/task evidence; validation of a previous server is not a proof that a later action used the same physical route.

## 4. Raw collection and exact full oracle

The proposed adapter is a **pinned private Connect `_to_table()` boundary**. Its returned Arrow table is the uncast physical result; retain its raw schema and all values. Time the full operation that constructs the Connect proto, submits it, and drains Arrow batches; additionally record nested component intervals with clear overlap semantics.

`toArrow()` is unsuitable for this physical-output/cold contract: in official PySpark 4.0.1 it requests `self.schema` before execution and casts the Arrow table to that schema. `collect()` converts it to Python rows. Freeze and hash the actual installed Connect adapter sources before any private boundary is used. [Apache Spark 4.0.1 Connect DataFrame source](https://github.com/apache/spark/blob/v4.0.1/python/pyspark/sql/connect/dataframe.py)

The client `to_table` path creates a request then collects raw Arrow batches; it does not itself expose distinct server phases. Request creation and RPC serialization are different operations. A scoped client observer must retain the actual generated operation UUID and actual serialization interval, rather than call `SerializeToString()` twice and label the extra call as wire cost. Preserve one logical execution and disable hidden transport retries/reattachment, or record their real request count explicitly. [Apache Spark 4.0.1 Connect client source](https://github.com/apache/spark/blob/v4.0.1/python/pyspark/sql/connect/client/core.py)

Outside the action timer, write the untouched Arrow table to an IPC artifact and verify:

1. Exactly the three unique required names, each raw Arrow signed int64; retain physical column order and read by name. Reject added, duplicated or wrong-type fields; never cast.
2. Exactly 4096 rows and 4096 unique keys, no nulls and complete key coverage.
3. Every minimum and count equals the independent reference. Include the two signed-extreme value groups, which make Float64/lossy adapters observable.
4. Hash all original/result/reference artifacts before and after. A failed oracle preserves the actual raw table and a durable mismatch receipt.

Required small offline controls for a later helper: wrong minimum, count, duplicate/omitted key, wrong physical type/extra field, mutated input/reference identity, missing/broken operation↔job association, missing exchange or worker task, missing phase end, uncertain closure, hidden retry, and quantile boundary examples. These are proposed controls; no runnable helper or gate verdict is claimed here.

## 5. Twenty cold/warm pairs at each P

Use 20 fresh server/session **pairs** per P. Each pair contains:

1. Owned server startup and session bootstrap, separately timed but outside the action timer. No explain, schema, validation, GraphUtils capability probe or previous data job in this server. Record all bootstrap requests, worker creation and lazy first-use behavior.
2. One first data action: `cold`, meaning first query in a fresh server/session. Lazy worker start or connection setup incurred by this action remains included. This is not a cold OS page-cache claim.
3. Full raw output/oracle outside the action timer. Require successful job/stream release before advancing; query the audit export after its measured terminal event, never as a hidden pre-timer job.
4. Rebuild and execute the same relation once: `warm`, meaning the second identical data action with the same live worker processes. Verify their identities and retain any unexpected restart. It is not a 20-query steady-state definition.
5. Full oracle and owned session/server/container closure. Record teardown at pair scope, separately from per-action query resource release.

This gives 20 cold and 20 warm observations per P, 120 timed data actions across 60 fresh server pairs. Rotate P order by repetition (`4,16,32`; `16,32,4`; `32,4,16`) with one gate job at a time. Fresh independent validation runs for the three P values precede the campaign; their server state is discarded.

Primary action wall time begins before constructing the relation and ends when the last raw Arrow result has been received. Components include relation construction, protobuf plan construction and server/RPC drain. Also report RPC-only and first-batch/last-batch boundaries if instrumented. Preserve all overlapping intervals; do not sum parallel task durations or subtract overlapping subphases into an invented overhead value.

Report median p50 (average of the middle two for n=20), nearest-rank p95 (19th sorted observation for n=20), all 20 raw observations, task counts and failures, separately for each `(P,cold|warm,phase,scope)`. No automatic retry/replacement after a failed ID and no partial denominator disguised as 20. A phase with missing events is `unavailable`, never zero. C2 is not DONE without the requested phase coverage and actual distributed gates.

Host envelope: A1 image, 16 total CPUs, 32 GiB cgroup limit, no swap, one driver plus exactly two process workers, configured greedy pool caps 10 GiB/process (potential 30 GiB total), native environment settings 256 MiB, 64 task slots/worker, one task attempt. Keep budgets constant across P. These are configured caps, not observed reservations or a physical memory bound. Record actual process identities, PSS/cgroup observations and final OOM state. Preserve the C3 native quota correction; do not assert 256 MiB prepayment on idle workers. Capture steal/load; Morrobay shared-host output is diagnostic, not a dedicated-host absolute result or a qualified 100-ms P16 promise.

## 6. Minimal missing runtime observer

One opt-in observer with a new explicit source/binary pin is needed. This is a requested interface, **not an authorized Sail edit in this task**. Use a structured append-only event export, with durable flush/coverage receipt before owned teardown. Do not use debug log adjacency to synthesize relationships.

Identity in every applicable event:

- campaign/pair/action ID; client operation UUID; session ID; job ID(s).
- Stage/partition/attempt, worker ID and PID/process start identity; driver placement explicitly represented.
- Event/span ID and parent ID, phase, outcome, per-process sequence counter.
- Monotonic nanoseconds from a declared shared Linux clock with kernel boot ID; UTC for provenance. Rust `Instant` durations alone provide no serialized common origin. Shared-kernel alignment must be explicit.
- For stream events, immutable reader/writer/channel identity and source/destination task keys. For definition events, stage cache hit/miss, plan bytes and task batch size.

Mandatory observation points:

| Phase | Boundaries / source site |
| --- | --- |
| Logical resolution | Before/after `PlanResolver::resolve_named_plan` |
| Optimization / physical planning | Before/after `optimize` and `create_physical_plan`; retain actual plan identity |
| Job graph and topology build | Separate before/after `JobGraph::try_new` and topology creation |
| Definition plan encode | Before/after `encode_remote_physical_plan`; preserve cache reuse and bytes |
| Scheduler | Ready → selected/assigned → driver dispatch → worker batch admission; record task keys and both placements |
| Worker decode / prepare | Batch `PhysicalPlanNode::decode`; per-task blocking queue and plan/scan/shuffle preparation boundaries |
| Stream setup | Reader/writer creation plus actual lazy open/handshake, distinguishing declarations from first polling |
| Stream consumption | First batch, last batch, EOF/error/cancel; complete output bytes/batches where needed for scope |
| Query teardown | Logical terminal status, task completion, final stream owner drop and per-query resource release |
| Session/server teardown | Explicit separate wrapper intervals and owned process closure |

Existing fastrace TaskMonitor and TaskPreparation spans can be reused, with missing correlations/properties and phase spans added. Export count/sequence coverage must detect incomplete or dropped events. Runtime task/stream durations need an agreed per-job critical-path versus per-task distribution definition; publish both only when observed, not a sum masquerading as wall time. Include observer mode in every receipt and keep it the same across all P/cold/warm cells. An instrumented result describes that binary/profile, not the frozen A2/A3 runtime.

## 7. Proposed pure-Python wrapper contract after observer readiness

Use module imports, typed definitions, Pydantic/slotted records, a pinned Connect-private boundary behind a typed Protocol, repo Ruff and strict mypy. Distinct helpers may implement preparation, guest probe/oracle, supervisor and serial host queue; no local imports or changes to frozen A2/A3/B8 helpers.

CLI design:

- `prepare --config PREPARE.json`: bounded fragment/reference generation and receipt, no engine.
- `validate --config PROBE.json`: fresh server, one action at its declared P, actual exchange/task/schema/full oracle, fresh durable output.
- `pair --config PROBE.json`: fresh server cold then warm, same full gates, all raw observations, own closure.
- `queue --config CAMPAIGN.json`: immutable 60-pair plan, three pinned validation prerequisites and preparation receipt, global serial queue/gate ownership. Stop on nonpass/uncertain closure; queue never cleans engines itself.

Configuration record (proposed fields):

| Record | Required typed fields |
| --- | --- |
| `FilePin` | absolute path, bytes, SHA-256 |
| `RuntimePins` | source/controller/harness/native commits, binary/native/installed-client file pins, observer schema/source/export pins |
| `FixturePin` | fragment FilePins, 32768 input rows, 4096 groups, schema, reference FilePin and preparation receipt FilePin |
| `Envelope` | image digest, CPUs=16, memory=32 GiB, swap=0, workers=2, all process pool settings, threads, task slots/attempt count, declared deadlines |
| `ProbeConfig` | fresh ID/output, kind, P literal 4/16/32, fixture, pins, envelope, raw action boundary, observer mode |
| `CampaignConfig` | immutable plan/config-index FilePins, preparation and three validation proofs, support manifest, archive target/admission, global lock paths |
| `ActionReceipt` | outcome, actual method/config, operation/job binding, raw intervals, complete task/worker/exchange proofs, oracle, file identities, observer coverage, resources |
| `PairReceipt` | both action receipts, same-worker proof, actual parent/engine processes, cleanup/wait/no-OOM/closure, final archive and payload ownership |

Reuse the reviewed ownership/archive protocol, with exact frozen helper/source manifest identities, private cgroup and owned-process sampler, full archive hash verification to Apo, no removal until certain closure and verified archive, failed payload retained pending root review, no silent retries or altered deadlines. C2 observations are a separate campaign; no cells, times or instrumentation costs are appended to A2/A3 ABBA.

**Next concrete step:** agree and implement the small runtime observer/correlation export at a new pin, then author/gate the Python wrapper against that exact contract. A wrapper using only runtime561 can legitimately report raw wall time, actual task counts and its two existing combined duration fields as a partial diagnostic, but cannot close C2's requested breakdown.
