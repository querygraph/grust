# C2/D2 native probe preparation

Source only. No engine, build, process probe, fixture generation, or benchmark has run during preparation.
The existing optimized native Sail9f is used without an extension or Rust rebuild.
The serial owner retains failed cells and locks. Root owns execution and the final owner-wait proof.

## Preserved failed smoke and narrow v2 fix

Source01 and actual smoke01 remain immutable. Both4096-row cold/warm actions completed;
server return code0, waited shutdown without SIGKILL, and root recorded manual owned closure.
The cell failed at the first post-action system-table collection with retained `PySparkTypeError()`.
Source inspection identifies unsigned job/stage/task/worker IDs that PySpark4 Arrow conversion
cannot convert; the old receipt lacks the detailed error, so this is the source-backed diagnosis
pending the fresh runtime control, rather than an observed full error message.

V2 projects every system-table column explicitly: unsigned IDs and nested stage IDs to BIGINT,
worker port to INT, and telemetry VARIANT value to JSON. These queries run after all measured
queries. Actions, parameters, timing boundaries, source/client/pool settings, full-row oracle,
server shutdown, locks and acceptance predicates are unchanged. The receipt now retains exact
evidence SQL plus the exception string and traceback. A pure control checks the actual projection
function without importing Spark or running an engine. `source01-to-source02.patch` binds the delta.

## Preserved smoke02 placement failure and source03

Smoke02 completed both full4096-row actions and all system evidence, then its unchanged oracle
rejected the cold action: only worker1 executed its8task attempts. The actual log shows job1 admitted
before both worker registrations. Stage0+stage1 share each of four TaskSets, so8task attempts use4slots.
Source task_assigner/core.rs consumes one slot per TaskSet; its scheduler test spreads tasks once both
workers are active. Source03 waits for both exact native registration lines and exec identity files
before any dataset action; no SQL or data warmup is performed. The retained readiness duration and
log boundary are outside the cold action. Slots are now exactly P/2 per worker (2/8/16 for P4/16/32),
so a P-set region requires both workers. This is software capacity, without an OS CPU/memory cap.
No predicate is weakened: the full answer/log oracle still requires executed tasks on both workers.
Source01/source02 and both failed runs remain unchanged; root alone preserved their manual closure.

## Root-owned preparation and launch

Use the admitted zero-extension client:

`/Volumes/Apo/graph-tests/results/sem-review-20261001/native-optimized-build01/venv/bin/python`

Reuse the already prepared bounded fixture01. Its original files remain unchanged.

Generate one initial P4 pair using only recorded build/client pins and the new fixture:

```sh
/Volumes/Apo/graph-tests/results/sem-review-20261001/native-optimized-build01/venv/bin/python -B /Volumes/Apo/graph-tests/results/sem-completion-20261003/C2-D2-native04/support/prepare_plans.py --kind c2 --count 1 --partitions 4 --fixture /Users/alexy/src/grust-benchmark-data/sem-completion-20261003/c2-d2-fixture01 --output /Volumes/Apo/graph-tests/results/sem-completion-20261003/C2-D2-native04/c2-smoke04 --run-root /Users/alexy/src/grust-benchmark-runs/sem-completion-20261003/c2-smoke04
```

Run the owner with the isolated sibling-import bootstrap. Direct `-I script.py` cannot import siblings.

```sh
/Volumes/Apo/graph-tests/results/sem-review-20261001/native-optimized-build01/venv/bin/python -I -B -c "import runpy,sys;sys.path.insert(0,sys.argv[1]);sys.argv=sys.argv[2:];runpy.run_path(sys.argv[0],run_name='__main__')" /Volumes/Apo/graph-tests/results/sem-completion-20261003/C2-D2-native04/support /Volumes/Apo/graph-tests/results/sem-completion-20261003/C2-D2-native04/support/run_probes.py --config /Volumes/Apo/graph-tests/results/sem-completion-20261003/C2-D2-native04/c2-smoke04/config.json
```

For a long campaign root should detach a short-lived `Popen(['/usr/bin/nohup', ...], start_new_session=True)`
waited launcher and retain its actual owner wait/return code; do not use bare shell `nohup &`.
Use fresh metadata and SSD roots for every attempt. No stale lock removal or ID reuse.

After the initial scoped control passes, generate C2 with `--count 20 --partitions 4 16 32`:
60 fresh-server cold/warm pairs, partition counts rotated within each repetition.
Generate D2 separately with `--kind d2 --count 1 --partitions 4 16 32 --repetitions 20`.
The two existing shared locks are checked by the owner. Root must not overlap these with another heavy job.

## Boundaries and qualification

- C2 times `collect()` from call entry to complete returned rows. Schema resolution precedes this span.
  Cold means first data action after both worker registrations in a fresh server/session, with no OS-cache claim. Warm repeats the same query
  in that server. The independent oracle checks every signed row, actual P-way executed exchange, and task
  attempts on two distinct logged workers. Missing evidence stops the queue without changing assertions.
- D2 follows Fable's `checkpoint_round_cost.py` route: **only** `repartition(T,key).checkpoint()`.
  No sort, bucket-name inference, or monotonically increasing IDs is used. Initial plain write, edge checkpoint,
  state checkpoint, round actions, isolated whole state/edge reads, and repeated state write/checkpoint costs
  are recorded separately. Full integer answers preserve the Pregel-shaped join/group reduction while avoiding
  an output-dependent floating tolerance. Source fixture order is deliberately nonmonotonic and includes high bits.
- D2's layout-preservation field remains false until root examines actual executed join plans. The measured setup
  costs must accompany round timings; do not call a round excluding setup the complete checkpoint strategy cost.
- Driver debug plans, per-worker exec-only PID logs, and system jobs/stages/tasks/workers are retained. System-table
  reads occur after all measured actions. Existing definition/preparation diagnostic timings are inclusive;
  full planning/serialization/stream-release attribution remains false and needs the separate C2 observer build.
- Process topology is driver+two workers,16 software threads each,10GiB software greedy pool each,P/2 task slots per worker.
  This is up to48 configured threads with30GiB aggregate software pools; there is no native16CPU/32GiB OS cap.
  Benchmark numbers are diagnostic/shared-host ratios, not dedicated-host absolute results.
- Per-PID sampled RSS and macOS `proc_pid_rusage` footprint are retained every500ms. Missing footprint reads are
  explicit null/error. Per-PID values are not PSS or deduplicated physical memory and their observed maxima are
  not OS lifetime peaks. The source binds rusage_info_v0 to the actual SDK96-byte structure; actual API qualification
  is still root-owned. Operator memory/spill metrics remain raw, separately scoped observations.
- Normal owned SIGINT is recorded. SIGKILL, spontaneous server exit, observer error, missing worker identity,
  live owned group, changed original/helper/client/source, or incomplete answer/log evidence cannot pass.
- The stream-logging action writes a successful physical two-group Parquet result and runs the typed sentinel.
  Its physical/sentinel oracle is a separate required control; this oracle deliberately refuses to qualify it.

## Open C2/C3 requirements

The preserved c2-observer patch is partial and unbuilt, including a missing observation_tests.rs sibling.
It must be completed in a new isolated worktree and built/gated before detailed phase attribution can be claimed.
Existing native9f records actual job/stage/task events, stage-definition elapsed time, and preparation queue/work.
It does not isolate logical/physical planning, physical/protobuf serialization, scheduler latency, stream ownership
release, transport allocation, or allocator deallocation from those spans.

C3 pool reservations and native admission/release can be observed through native_resource.rs's existing opt-in
`SAIL_NATIVE_RESOURCE_AUDIT` boundary hook when a native extension is admitted. A configured quota is not evidence
of an observed admission or physical allocation. This relational no-extension profile has no native lease audit.
DataFusion `execution.memory_used`/spill metrics describe instrumented operators, not all pool reservations or
total process memory. Output-size metrics are not transport wire bytes or transport-buffer memory.
There are no native cgroup/PSS/OS32GiB-cap claims. Root's Banda profile can reuse darwin_memory.py and the native
resource boundary hook under a separate pinned diagnostic profile.

## Explicit metadata-only session creation

The prior readiness attempt preserved its failure: Connect SparkSession.create() created only a lazy
client, so no session or initial workers existed during its readiness wait. Source now explicitly
calls SparkSession.version before readiness. In the exact admitted client, that property sends
AnalyzePlan(spark_version); native9f server.rs:167–179 gets/creates the actual SessionContext,
and session_manager/actor/handler.rs:174–177 waits driver.activate() before AnalyzePlan returns.
The driver activation requests initial workers. AnalyzeSparkVersion returns version metadata without
JobRunner.execute or a data job. The receipt records this metadata bootstrap duration/version/log
offsets separately, then worker readiness separately. The unchanged job-log guard requires no
executed job before readiness; no SELECT1, data warmup, or fixture count was added. Cold remains the
first fixture data action after session metadata bootstrap and worker readiness, without an OS-cache
claim. Prior sources/failure remain unchanged. Root alone runs the new fresh attempt.
