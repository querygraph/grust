# Sail's internal gRPC clients keep Tonic's 4 MiB decode limit: a one-hunk fix, for review

This is an upstream candidate under `AGENTS.md` "Sail Discipline": built and
exercised in the `querygraph/sail` fork first, then cut to the smallest
manually verifiable change. The fork branch is `work/grpc-client-decode-limit`
(commit `9dc75bee8` on `b87fb27ac`); `0001-raise-client-decode-limit.patch` is
the reviewable copy. It has not been opened upstream; that is the user's call
now that the verification below has completed.

## What fails

`crates/sail-execution/src/rpc.rs` builds the driver, worker, Celeborn and
Flight clients through `impl_client_builder!`, which ends in
`<$client_type>::new(channel)`. A Tonic client decodes at most 4 MiB per
message unless `max_decoding_message_size` is raised. Sail's servers already
raise theirs: `DriverServiceServer`, `WorkerServiceServer`, both
`FlightServiceServer`s and the Spark Connect entrypoint all call
`.max_decoding_message_size(GRPC_MAX_MESSAGE_LENGTH_DEFAULT)` (128 MiB,
`sail-common/src/config/mod.rs`). The asymmetry means a server may send a
response the peer cannot read.

Observed on morrobay on 2026-09-29 (gate VM 32 CPUs / 110 GiB, container
`--cpus 32 --memory 100g`, Sail host `b87fb27ac`, process-cluster mode with
32 partitions and two workers), cell
`capacity-bfs-r1-scale25-nutmeg-datafusion-bfs-push_pull` of
`gn-capacity-b87fb27a`: a Graph500 scale-25 graph (33,554,432 vertices,
536,870,912 edges in 2048 Parquet files) failed after 331 s with

```
pyspark.errors.exceptions.connect.SparkRuntimeException: Error, decoded message
length too large: found 8234561 bytes, the limit is: 4194304 bytes
```

The hub-source rerun of the same matrix located the failure: the BFS itself
completes and writes its result on every relational path (six iterations,
1516 to 2764 s), and the message is raised inside the harness's distributed
certificate, at its first query (`vertices.count()` over the 33.5M-vertex
frame, after the traversal's checkpoints and native tables have accumulated
in the session), with a message of 8.23 MB every time (8233665, 8234369,
8234561, 8236609 bytes across four cells). That text is Tonic's
decompressed-length branch
(`tonic-0.14.6/src/codec/decode.rs:195`), so the message was one of the
zstd- or gzip-compressed responses Sail's servers send with
`send_compressed`. The same cell at scale 24 (1024 files) passed. Which
stream carried the 8,234,561-byte message is not identified here; the Flight
encoder targets 2 MiB per `FlightData` from `get_buffer_memory_size`, which
is an estimate, and the driver and worker services exchange task status and
metrics as well. The receipt is
`~/src/sail-extensions-gates/graph-nuts-b87fb27ac/capacity/cells/capacity-bfs-r1-scale25-nutmeg-datafusion-bfs-push_pull/artifacts/receipt.json`
on morrobay.

## The change

One hunk plus one import in `crates/sail-execution/src/rpc.rs`: the client
built by `impl_client_builder!` gets
`.max_decoding_message_size(GRPC_MAX_MESSAGE_LENGTH_DEFAULT)`, the same limit
the servers accept. No behavior changes for messages under 4 MiB.
`cargo check -p sail-execution` passes; the workspace's clippy and tests run
in the gate build below.

## Manual verification

Rerun the failing cell on a host built with the change and the same inputs.
This is queued on morrobay as the `capacity-bfs-relational` and
`capacity-sssp-relational` suites of `gn-capacity-ac000b6e.json` (twelve
scale-25 relational cells) on the gate built from `work/s0-argentea-engine`
(`63eaeb5fe`), which contains `work/gn-gate-next`, the merge of this branch
with `work/s2-stage-order`; the chain in
`~/src/sail-extensions-gates/graph-nuts-gate-next/chain.log` runs it after the
baseline matrices. The verification is complete when those cells no longer
fail with the message above. Their outcome will be recorded in
`GRAPH-NUTS.md` and the capacity findings record; until then this README says
"pending".

Status: **verified** on 2026-09-29 at 22:55 UTC. On the gate built from
`2557feaf1` (which contains this branch), cell
`capacity-bfs-relational-r1-scale25-nutmeg-datafusion-bfs-push_pull` of
`gn-capacity-2557feaf` passed: six BFS iterations, 17,048,727 vertices
reached, certificate completed, 1593 s. The identical cell on the `b87fb27ac`
baseline finished its traversal in 1516 s and failed the certificate's first
query with the 4 MiB message. Receipt:
`~/src/sail-extensions-gates/graph-nuts-gate-next/capacity/cells/capacity-bfs-relational-r1-scale25-nutmeg-datafusion-bfs-push_pull/artifacts/receipt.json`
on morrobay. Ready to be opened upstream as a one-hunk PR after your review.
