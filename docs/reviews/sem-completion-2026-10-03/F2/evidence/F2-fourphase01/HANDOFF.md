# Materialized Arrow bridge: source-only handoff

This is a separate profile from the completed native-Parquet F2a campaign.
Root admits and runs the tiny qualification before four main series. Author
performed source reads, Ruff/strict mypy and four in-memory source controls;
no Spark/Nutmeg/Arrow/native imports, builds, payload reads or engine launches.

## Execution and timing

Worker CLI is the unchanged isolated bootstrap of `f2a_worker.py --plan JSON`.
Plan uses the old flat fields, with `ids="int64"` and added `chunk_rows`.
Main:262144 rows per slice. Tiny:2 rows,3 calls; at least one input must require
several chunks. Source4b/native9f,16 workers,30GiB Sail pool/22GiB native quota
remain explicit settings. These are not an OS32GiB cap; root admits the shared
128GiB physical host, including client inputs/results, server caches and copies.

The worker's continuous clock starts immediately before materialized client
Parquet reads and ends after the last client Parquet write. Four sequential raw
spans and `exclusive_sem_phases` observed values are:

1. `read_parquet`: full projected original vertices/edges into client Arrow.
2. `csr_and_graph`: bound-check slice IPC; inline chunk transport and unsorted
   eager checkpoint jobs; balanced
   `unionByName` trees; native `asStaged` with integer identity; one ordinary
   `projectionStats` action using its default outgoing key.
3. `algorithm_materialize`: all identical ordinary WCC calls at concurrency16,
   selecting/casting `id` and `component` as Int64, materializing every complete
   Arrow result to the client. Includes result transport.
4. `write_parquet`: every previously materialized result written by client
   PyArrow to fresh `result-callN/part-0.parquet`.

These are disjoint bridge phase clocks. CSR includes serialization, validation
of byte bounds, upload, staging and projection; algorithm includes transport.
They are not native CSR-only or kernel-only clocks. The continuous total also
includes small between-phase bookkeeping; no subtraction supplies fake phases.
There is no default input validation/count job in the pipeline. One status
action after it proves one cached projection; graph/session/native shutdown
and all independent output oracles are outside it.

## Bounded transport proof

The admitted PySpark4.0.1 source first serializes an entire Arrow table's
LocalRelation before uploading it as an artifact. Direct whole-Graph500 input
therefore exceeds protobuf's2GiB boundary. The first tiny run established that
native9f rejects ArtifactStatus; preserve its complete failure and old source
freeze under `attempt-runtime01`. The replacement sets and observes
`spark.sql.session.localRelationCacheThreshold=67108864` inside phase2, encodes
each slice once for a strict32MiB byte bound, then calls actual `createDataFrame`.
Its logical chain must be an inline `LocalRelation`, bypassing the unsupported
artifact cache. The client may encode/copy the slice again; that cost is included.
Each bounded slice is immediately materialized using ordinary
`checkpoint(eager=True)` with no sorting. Its actual returned plan must be a
`CachedRemoteRelation` with a retained reference ID. Only those references enter
the balanced `unionByName` tree. No union plan aggregates all input Arrow bytes.

The smoke02 failure reached one bounded inline IPC slice but was rejected by
checkpoint planning because its server storage root was unset. Its exact four
helpers, configurations and plans are preserved under `attempt-runtime02`.
The server now receives `SAIL_EXECUTION__CHECKPOINT__PATH` as the file URI of a
new `output_root/checkpoints` directory. Receipt `checkpoint_base_uri` and
`checkpoint_directory_created` record that startup configuration; the parent
binds them to the admitted output and environment. The helper does not delete
checkpoint files. Native9f normally removes its session checkpoint namespace
on session shutdown; the base directory and any remaining files are retained,
without a claim that backend checkpoint files survive ordinary session cleanup.

The explicit execution profile is `chunk_checkpoint_arrow_client_four_phase`.
Additional checkpoint jobs and all their cost count inside CSR/graph; the source
counters are actual client operations, not claimed backend distributed-task
counts. This is not a native lazy-Parquet performance baseline.

Receipt `arrow_handoffs` ordered vertices/edges records full Arrow row count,
chunk size/count, checked IPC encoding and createDataFrame calls, attempted and
completed eager checkpoints, cached-remote count and reference IDs, maximum/total
checked IPC bytes and tree depth. Partial counters remain on failure. Parent
validates completed counts/depth/bounds; independent full WCC oracles separately
bind original physical graph inputs. Tiny executes the multi-chunk path, not
only the below-threshold branch. Source controls test signed extrema/order/
duplicates and balanced depth, reject artifact-cached input slices, reject
oversized IPC before `createDataFrame`, and reject missing remote checkpoint
references; they supply no engine qualification.

Receipt additionally records actual `pyspark_version`, `client_plan_source` and
`client_session_source` and `client_dataframe_source` file pins. Parent
requires4.0.1 and binds all three loaded
module sources to admitted purelib files. Root must include
`pyspark/sql/connect/{plan,session,dataframe}.py` in `expected_client`.

## Serial owner

`f2a_campaign.py` and `f2a_campaign_launch.py` retain old typed Config/Series/
Receipt schemas, RSS sampler, exact source/input/helper/client/wheel/binary pins,
shared locks, actual child waits and independent final driver/server group
absence. Config allows one tiny plan or four distinct main plans:
`{cit-Patents,graph500-24} × {calls1,calls3}`, all integer identity, n=1.
Root namespace is fresh below `sem-completion-20261003`, excluding/containing
no helper source. Configuration JSON belongs to that campaign root or this
source directory. The two shared locks remain at
`/Volumes/Apo/graph-tests/results/sem-review-20261001/{gate.lock,serial-queue.lock}`.
Old fixed BOOT basename stays `f2a_worker.py`; no broad alias replacement.

Root launches the waited launcher from a short-lived process with its own log:

```text
<metadata-python> -I -B -c <isolated runpy bootstrap for f2a_campaign_launch.py> <this-directory> --config <approved-config.json>
```

Parent positive outcome remains `completed_unvalidated_campaign`; actual waited
launcher outcome is `completed_unvalidated_waited_campaign`. Neither is a full
oracle verdict. They require four observed phase spans in order/nonoverlap,
actual loaded client pins, bounded cached handoffs, all full writes, one cached
projection, no query/cleanup error, natural driver0 and waited native0 or
requested SIGTERM(-15), all owned groups absent and source/pin/lock closure.
Forced cleanup/failure retains locks and attempted outputs; no retry is hidden.

Root owns host/disk admission, no explicit warmup or cache flush, n=1 shared-host
interpretation, full physical output/reference oracles and raw archive retention.
Prior GF WCC references qualify partitions on the original inputs. A new bridge
result is never substituted into or relabelled as the earlier native-Parquet
cohort. Four main series produce eight outputs; tiny produces three separately.
