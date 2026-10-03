# X2 native controls: independent closed review

[The portable result](closed-controls.json) records a second, engine-free review of the closed producer receipts, independent oracles, actual owner waits, source and input identities, complete physical result, and task log byte windows. The reviewer verified 97 file identities. Its [source](review_closed.py) passed Ruff and strict mypy and read only the closed artifacts.

## Observed controls

| Control | Complete result or initiating cause | Actual execution | Closure |
| --- | --- | --- | --- |
| Reference BFS | All 4,096 original IDs, DOUBLE distance, BIGINT hops and parent match an independently recomputed queue BFS. 4,095 vertices are reachable; depth 11; 12 rounds. Parents are the minimum original ID among tight predecessors; source 0 has parent 0; the isolated signed-minimum ID has nullable fields. | Driver 55444; workers 55449/55450. Both execute workload tasks: 104 jobs and 1,209 distinct task attempts within the action log windows. | Actual server return code 0 and waits, both worker groups absent, unchanged source and inputs; outside oracle and owner return code 0; locks released. |
| Explicit greedy pool refusal | Each process has a 1 MiB software pool. The one-million-distinct-group aggregate produces typed `SingleHashAggregateStream` allocation errors. Ten worker-local execution-failure records precede matching task-failure reports for the same task, PID, worker and session. | Driver 55511; workers 55514/55515. Both execute workload tasks: one job and 33 distinct task attempts. Both workers have typed source witnesses. | Actual server return code 0 and waits, both worker groups absent, unchanged source and inputs; outside oracle and owner return code 0; locks released. |

The BFS comparison checks every physical row, the unique original ID domain, schema, all distances/hops, rooted minimum tight parents, and convergence. It independently re-reads the fixture's 4,096 vertices and 4,097 physical edges, including duplicate edges, loops, a reachable signed-maximum ID and an isolated signed-minimum ID. [The full result is portable CSV](full-reference-bfs.csv).

The reference uses native Sail `9f0aa7d2a50f1258544d37c05dd19b3ff3d915b3`, its optimized release binary, `bfs(method="reference")`, undirected edges, snapshot inputs and repartitioned checkpoints. It captures all 12 pre-write plans. P=16 and two workers with nine task slots each admit the observed 17-slot write region and still require both workers for a 16-partition stage. Each process has its own Tokio/Rayon setting of 16; this is not a 16-thread sum.

## The induced first cause is bound to a task

[Allocation local order](allocation-local-order.json) records exact byte positions and lines in both worker logs, bounded by the producer's query-start/query-end offsets. Worker 55514 first records a 256 KiB allocation refusal for job 1, stage 1, partition 6, attempt 0 at byte 23,964, then the matching task-failure report at 24,399. Worker 55515 first records a refusal for partition 13 at 24,452, then its matching report at 26,205. These records precede query teardown because they occur inside the pre-shutdown byte windows. The client itself receives a typed 256 KiB allocation refusal for partition 5.

This proves a local initiating allocation cause for the induced refusal and its later task report. Cross-process timestamps do not establish the globally earliest fault; `global_first_fault_proven` remains false. The 1 MiB cap is an explicit DataFusion software pool, not an OS memory quota, cgroup OOM, physical-memory measurement or spill result. Partial failed output is preserved and never treated as a completed answer.

## Retained unsuccessful attempts

All previous sources, configs, raw producer artifacts, actual wrapper waits and root's manual closure receipts are retained in the portable package:

| Attempt | Preserved cause | Qualification |
| --- | --- | --- |
| 01 | `SAIL_EXPERIMENTAL_EXTENSIONS="true"` did not activate the registry. GraphUtils Ping failed. | Admission failure; no reference BFS or pool-refusal qualification. |
| 02 | The trusted GraphUtils staging directory did not exist when the absolute file URI was canonicalized. | Session admission failure; no workers or algorithm qualification. |
| 03 | The write region required 17 task slots; two workers with eight slots offered 16. | Scheduler capacity preflight failure, distinct from memory refusal. Uncertain write state and original work directory remain retained; no complete result claim. |
| 04 | Flag `1`, precreated staging directory with file URI, and nine slots per worker. | Both scoped controls pass. |

The failed attempts were not repaired in place. Root checked their known process IDs and groups were absent before releasing only their owned locks. Their original failure receipts and manual closures bind the retained outcomes.

## Historical question remains open

The [historical source audit](evidence/X2-source-audit01/README.md) covers twelve original relational h2 failures with zero cgroup memory-event deltas. Their preserved logs do not record a typed initiating cause before session removal. Later teardown connection resets and later, separate OOM experiments do not explain those twelve cases. The fresh tiny native controls are not a replay of their scale-24 workloads. `historical_original_cause="unexplained"` remains explicit in both producer/oracle receipts and this independent result.

The two-host X1 run remains unqualified while SSH is unavailable. Native OS-32-GiB/PSS accounting, globally ordered first-fault capture and full server phase attribution are also unqualified.

## Package contents

The `evidence/` tree keeps source, configurations, receipts, actual waits, outside oracles, plans and small raw artifacts. `archives/complete-native-raw.tar.gz` preserves every native raw file for attempts 01–04, including full logs, telemetry, complete BFS Parquet and any partial failed output. `archives/historical-twelve-originals.tar.gz` preserves all twelve historical receipts, full server logs and memory sample streams. Both archives have member identity catalogs and were reopened to rehash every member. Tool caches were excluded; no original evidence changed. Executable/wheel/client identities remain in receipts. Absolute performance clocks stay in archival raw observations; this review makes no speed claim. Three historical logs contain no ERROR at all; the other nine first ERROR records occur after session removal.
