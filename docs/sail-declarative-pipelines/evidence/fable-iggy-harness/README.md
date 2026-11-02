# Fable unit 6: Iggy capability and fault observations on the pinned broker

Handoff item 6 asked for committed readable frontiers, retention before the
first acknowledgement, partition incarnation and ownership, gaps and request
uncertainty, established with pinned broker tests, without importing the Iggy
client into the control model. This packet does that with Apache Iggy at
`153fdf466aea94b7bcb90681ee7274f9f76ec00d`, built from a detached worktree
into its own target directory, driven through Iggy's own integration harness
(`integration` crate, `TestServerConfig::executable_path`) from a standalone
Cargo project here. Nothing in Sail links the Iggy client; the unit-3 contract
in Sail stays dependency-free and these observations are what its Iggy adapter
must honour. `provenance.json` pins the objects, binary hash, toolchain,
commands and every observation and log hash; `observations/` holds the raw
JSON each scenario wrote; `logs/` holds the harness and pinned-test runs.

## Observations (single node, TCP, root client, SDK defaults)

| Contract | Scenario | Observed |
| --- | --- | --- |
| committed readable frontier | `s1_frontier` | 5 sent; partition `current_offset` 4, `messages_count` 5; poll from 0 returns offsets 0–4 and nothing past the frontier; no stored offset before any ack; incarnation 1 |
| retention before the first ack | `s2_retention_s4_gap` | 12,000 sent (1 KiB payloads) into a topic capped at 4 MiB with 1 MiB segments, cleaner every 100 ms, bus message cap 2 MiB (the pinned `message_cleanup` test's settings; with the 64 MiB default cap no size retention fires, which the first run showed); within 1 s `messages_count` fell to 3,000 and 4 segments; **polling offset 0 returned offset 9,000 with no error**; no stored offset. The first-offset check is the only gap detector (design review A4), confirmed on the pinned broker |
| incarnation and ownership | `s3_incarnation_s4_restart` | poll captures incarnation 1, owner generation 0; a position stored with that context is read back (2); deleting and recreating the single partition reuses id 0 under **incarnation 4** with offsets restarting at 0 and the stored offset gone; storing a position captured under the old incarnation fails with **`HistoryUnavailable` (87)** and does not create a stored offset |
| gaps | `s2`, `s3` | two kinds: retention moves the first readable offset forward silently (9,000); recreation restarts offsets at 0 under a new incarnation. Neither is an error at poll time |
| request uncertainty | `s5_uncertainty` | after SIGKILL of the only node a `get_consumer_offset` hangs past 5 s (the SDK reconnects with unlimited retries by default), yet `store_consumer_position` **returns accepted in 0.66 s**; after restart, before any new store, the stored offset is already 1: the SDK retained the store and replayed it on reconnection. A fresh-context store then lands at 2. The harness handle still reports the node as running after its own SIGKILL; the timed-out read is the evidence that it was down |

## Pinned Iggy tests run at the pin (release, same target directory)

| Group | Result | What it establishes for SDP |
| --- | --- | --- |
| `sdk::consumer_group_membership` | 16 passed | ownership change raises `owner_generation` while incarnation stays; a stale owner's `store_consumer_position` fails with `ConsumerGroupPartitionNotOwned` (5009); the stored offset survives a crash under weak offset durability |
| `server::message_cleanup` | 7 passed | expiry after rotation, active-segment protection, size-based and combined retention, multipartition fairness, and **retention respecting a committed consumer offset** |

## Consequences the Sail adapter must carry (unit 3 contract)

- `scan` must compare the first returned offset with `start` and fail closed
  on a retention gap; the broker gives no error (s2).
- Every captured range carries the partition incarnation; a mismatch at
  acknowledgement time is `HistoryUnavailable` and the position must be
  dropped, not retried (s3).
- An "accepted" acknowledgement is not a confirmed commit while the SDK is
  reconnecting: it may be retained and replayed later, or lost with the
  process. SDP acknowledges only after its own durable progress record, and
  treats the stored offset as advisory, as the design review states (s5).
- Retention never deletes past a committed consumer offset
  (`expiry_respects_consumer_offset`), so an SDP consumer that never
  acknowledges pins retention; a reset must delete or re-store the offset
  deliberately (design review §5.8).

## Boundaries

Single node only; no cluster, QUIC, HTTP or WebSocket transport; no
`OperationUncertain` was induced (that needs a mid-request connection loss
with the retained-operation protocol, which the pinned `partition_dedup`
lost-reply tests cover on their side and were not run here); no measurement
of timing beyond the recorded elapsed values. The harness depends on absolute
paths to the pinned worktree and binary recorded in `provenance.json`.
