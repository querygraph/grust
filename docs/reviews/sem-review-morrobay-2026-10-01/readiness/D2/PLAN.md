# D2: declared-layout source readiness and minimum cluster probe

Recorded 2026-10-02T00:37:29.125935+00:00. Governing querygraph/grust AGENTS.md and
`docs/GRAPHFRAMES-RS-PARITY.md` read. Source fetch and isolated checkout only:
no build, compilation, engine/container, algorithm edit or external correspondence.

## Available exact source

- Public `querygraph/sail` branch `work/declared-layout` resolves
  **17f8461f1cb042ea0375537cf8fa16c7ba6594eb**.
- Clean detached worktree:
  `/Volumes/Apo/graph-tests/workspaces/sem-review-20261001/sail-declared-layout-17f8461f1`.
  Fetched into the existing Sail common Git with `--no-tags --no-write-fetch-head
  --refmap=`; no frozen heads/ref/worktree changed. Common root's existing dirty
  status was preserved. Receipt: `/tmp/sem-d2-source-checkout-receipt.json`.
- No tracked or physical AGENTS.md anywhere in this exact source; no ancestor
  AGENTS.md in its Apo path. Grust governs future experiment helpers/docs.
- Four declared-layout commits on baseb87fb27ac:
  `4a7ffda0389d717f37af5c4f37db43d2f6219da7` reader/Pecan layout;
  `74ca2b57d0475fe0f208a691359e8da31b3f4138` host column restatement;
  `844b5cbb60d858dc6ff179d50ea54607609adb63` truthful driver writer;
  `17f8461f1cb042ea0375537cf8fa16c7ba6594eb` hash UDF/distributed writer.
- Source files/locks and exact Git blobs/SHA256 are retained in
  `/tmp/sem-d2-source-review.json`. Source/locks/scripts are available for a future
  independent Linux build; cached55.1/59.3 crates exist. No new build is qualified.
- Referenced Capitola `layout-exp/baseline.py`, `declared_join.py`,
  `partitionby_probe.py` are **not tracked at this pin** and were not located in
  searched Morrobay gate/results/review roots. Published doc describes them;
  their exact source, arguments and complete raw plans/results remain a Fable
  delivery need. Historical timings in the parity doc are local-mode evidence,
  not a process-cluster qualification or a new observation here.

## Source mechanism and ABI/build boundary

`nutmeg_bucket(key,n)` is an `any`-placed functions-only entry point. It computes
DataFusion55.1's `create_hashes([key],REPARTITION_RANDOM_STATE) % n`, retaining
key type. Its test compares full output partitions against RepartitionExec.
Distributed checkpoint adds BIGINT `__bucket`, repartitions/sorts by(bucket,key),
and uses Sail's `partitionBy(__bucket)` writer. Driver mode instead owns concurrent
Hash repartition→per-bucket sort→ArrowWriter to every `part-i.parquet`.

`CheckpointedTable` groups files by bucket index/directories, declares
Hash(key,P), and declares ascending/nulls-last key ordering **only when every
bucket has one file**. Multiple files per bucket still declare Hash but no
ordering. It trusts true bucket membership/order; file names alone do not prove it.
Host `declared_properties` restates foreign FFI `name@index` leaf expressions only
when name/index match the schema, enabling host equality/projection reasoning.
`NativeRelationExec` remains a **local opaque** scan wrapper; actual worker placement
and transfer behavior must be inspected, not inferred from the client or writer mode.

Versions remain API1/DataFusion55.1.0/Arrow59.3.0 and the existing named MemoryLease
ABI; manifest/mod.rs match runtime561. But **runtime561 lacks the host restatement**.
An existing561 binary plus a new wheel does not establish the intended optimization.
The frozen nativeffcf package lacks checkpoint/bucket exports; inspected existing
Linuxde8 wheel ZIP also lacks checkpointed client/bucket_factory. No exact17-bound
Linuxhost/wheel receipt was located in searched local gate roots.

This branch predates the frozen f3 typed/B9 controller and runtime561 stream,
diagnostic and compact-struct-min work. Do not replace the benchmark controller
or silently downgrade the runtime. Options for root review: build exact17 as a
separately named baseline for both probe forms, or have Fable deliver a granular
host/wheel port onto the reviewed current runtime with new exact identities/gates.
A direct relation microprobe needs no edits to either Pecan algorithm source.

Primary source:
[hash function/test](https://github.com/querygraph/sail/blob/17f8461f1cb042ea0375537cf8fa16c7ba6594eb/examples/extensions/nutmeg/src/bucket.rs#L42-L51),
[client writer](https://github.com/querygraph/sail/blob/17f8461f1cb042ea0375537cf8fa16c7ba6594eb/examples/extensions/nutmeg/python/sail_nutmeg/client.py#L88-L143),
[reader properties](https://github.com/querygraph/sail/blob/17f8461f1cb042ea0375537cf8fa16c7ba6594eb/examples/extensions/nutmeg/src/checkpoint.rs#L238-L279),
[host restatement](https://github.com/querygraph/sail/blob/17f8461f1cb042ea0375537cf8fa16c7ba6594eb/crates/sail-session/src/extensions/plan.rs#L73-L124).

## Concrete pre-timing correctness concern

Source-derived witness, **not run**: a nonempty relation with fewer distinct keys
than P has unpopulated hash buckets. Distributed partitionBy normally creates no
files for those values. Reader requires all buckets (`checkpoint.rs:171–180`);
client `checkpoint` catches any error containing **"is missing"** and substitutes
an empty DataFrame (`client.py:131–136`). Thus the empty-input fallback can mask a
missing bucket of a **nonempty** checkpoint, losing rows. The driver writer creates
all bucket files and does not take this fallback. Retain this witness with P16,
eight signed/high-bit IDs and exact input/output rows; classify mismatch/refusal
before any timing, without silently patching or relaxing its assertion.

Other retained controls: full populated-bucket signed BIGINT fixture; isolated
vertices; duplicate edges and loops; permuted input order; both join sides derived
from different input order/fragments; multi-file bucket with no ordering declaration;
nonempty overwrite refusal; actual hash-UDF versus engine repartition membership.
The doc's prior duplicate distributed-write occurrence had no retained directory;
any recurrence must retain every file/schema/row/hash and task attempt.

## Minimum paired process-cluster contract

1. Admit one reviewed host+wheel pair in an isolated namespace; exact package,
   binary/source/ABI/helper/input guards before/after, fresh output paths and lock.
   Same16CPU/32GiB/noSwap/init envelope,2worker processes,P16; use declared summed
   pools (e.g.driver10GiB+worker10GiB each=30GiB,2GiB headroom), same native quotas
   and worker slots for both forms. Measure actual peak/cgroup/pool observations.
2. Start with a bounded synthetic typed Parquet graph: ~8192 vertices plus signed
   extrema and2^53±1 IDs, ~65536 edges with duplicate/loop/isolate witnesses.
   Admission requires actual nonempty bucket coverage in the populated-case; the
   <P missing-bucket witness remains a separate mandatory result, not filtered out.
   External full oracle binds IDs/schema/bag multiplicities, exact join rows and
   integer aggregate values. No input-validation/count/cert job inside timed probe.
3. First read-only pair isolates declaration: **same already verified physical
   bucketed/sorted files**, A ordinary Parquet scan versus B checkpointed scan;
   same inner join on vertex id=edge source, grouped destination messages and
   left join back to vertices, full result Parquet. Left-CollectLeft planner rule
   (`job_graph/planner.rs:128+`) still unconditionally repartitions its children;
   retain observed join mode/extra exchanges instead of assuming none.
4. Separately named complete-layout pair includes writing: A plain write/re-read,
   B distributed truthful bucketed/sorted checkpoint/re-read, same relational
   query/full export. Includes sorting/bucketing/new message materialization costs.
   Keep layout construction outside the first pair's timer and inside this complete
   pair's timer; never subtract setup and call the remainder complete E2E.
5. Retained warmups and two ABBA blocks per admitted pair, one heavy job at a time.
   Engine launch→exit boundary includes server/input handles/planning/write/read/
   query/export/session/server cleanup; independent reference/full oracle/hashes/
   archive verification outside. Disclose Explain capture/observer costs if inside.
6. Retain logical/physical and actual job/task plans, join modes, required/satisfied
   distribution and ordering, bucket/file inventories/footers/actual sortedness,
   all unique(job,stage,partition,attempt,worker) RUNNING/SUCCEEDED assignments,
   native source placement and transfers, schema/full-output oracle and samples.
   An optimizer plan alone does not prove cluster execution or removed transfer.
7. Every error/timeout/mismatch retained, no retries, no positive verdict before
   exact container exit/removal/absence plus complete host collection/archive hashes.
   Shared-host comparisons are ratios with boundary, never hardware-neutral timings.

## Remaining delivery/decision items

Exact buildable current-host port or separate17 host+wheel; Capitola probe sources
and raw receipts; missing-bucket control outcome/fix identity; caller scope for
ordering/multi-file buckets; observer/task evidence on the selected runtime;
root-bound envelope/timer/paired order. No source implementation or probe launched.
