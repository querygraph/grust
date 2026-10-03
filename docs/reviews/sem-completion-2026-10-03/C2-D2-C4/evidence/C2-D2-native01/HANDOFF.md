# C2/D2 native probe preparation

Source only. No engine, build, process probe, fixture generation, or benchmark has run during preparation.
The existing optimized native Sail9f is used without an extension or Rust rebuild.
The serial owner retains failed cells and locks. Root owns execution and the final owner-wait proof.

## Root-owned preparation and launch

Use the admitted zero-extension client:

`/Volumes/Apo/graph-tests/results/sem-review-20261001/native-optimized-build01/venv/bin/python`

First prepare the bounded 4096 signed vertex /32768 edge fixture, outside all engine timers:

```sh
/Volumes/Apo/graph-tests/results/sem-review-20261001/native-optimized-build01/venv/bin/python -B /Volumes/Apo/graph-tests/results/sem-completion-20261003/C2-D2-native01/support/prepare_fixture.py --output /Users/alexy/src/grust-benchmark-data/sem-completion-20261003/c2-d2-fixture01
```

Generate one initial P4 pair using only recorded build/client pins and the new fixture:

```sh
/Volumes/Apo/graph-tests/results/sem-review-20261001/native-optimized-build01/venv/bin/python -B /Volumes/Apo/graph-tests/results/sem-completion-20261003/C2-D2-native01/support/prepare_plans.py --kind c2 --count 1 --partitions 4 --fixture /Users/alexy/src/grust-benchmark-data/sem-completion-20261003/c2-d2-fixture01 --output /Volumes/Apo/graph-tests/results/sem-completion-20261003/C2-D2-native01/c2-smoke01 --run-root /Users/alexy/src/grust-benchmark-runs/sem-completion-20261003/c2-smoke01
```

Run the owner with the isolated sibling-import bootstrap. Direct `-I script.py` cannot import siblings.

```sh
/Volumes/Apo/graph-tests/results/sem-review-20261001/native-optimized-build01/venv/bin/python -I -B -c "import runpy,sys;sys.path.insert(0,sys.argv[1]);sys.argv=sys.argv[2:];runpy.run_path(sys.argv[0],run_name='__main__')" /Volumes/Apo/graph-tests/results/sem-completion-20261003/C2-D2-native01/support /Volumes/Apo/graph-tests/results/sem-completion-20261003/C2-D2-native01/support/run_probes.py --config /Volumes/Apo/graph-tests/results/sem-completion-20261003/C2-D2-native01/c2-smoke01/config.json
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
  Cold means first data action in a fresh server/session, with no OS-cache claim. Warm repeats the same query
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
- Process topology is driver+two workers,16 software threads each,10GiB software greedy pool each,64 task slots.
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
