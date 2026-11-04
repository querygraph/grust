# ASTRA-REDESIGN-0

Original technical review, preserved as delivered in the conversation. The
corrected review in [ASTRA-REDESIGN-1.md](ASTRA-REDESIGN-1.md) supersedes its
process and readiness recommendations.

**Astra’s verdict: keep the direction, but make one correction pass before posting.** The prototypes establish useful mechanisms; they do not yet establish the complete recovery protocol.

Astra reviewed P4 `4fad33ca5` against `62251e0a2`, covering P1/P2/P4; P3’s `ef5f848a7` commit separately from its integration ancestry; and the current runtime at `99dc47788`. No files changed. Rust, Spark, and broker suites were not rerun.

The highest-priority design findings are:

1. **A prepared checkpoint must retain its exact boundary through partial commits.**
   [S6](/Users/alexy/src/grust-sdp/docs/sail-declarative-pipelines/DECISION-NOTES-STREAMING.md:165) resumes from the least committed sink, while the [architecture](/Users/alexy/src/grust-sdp/docs/sail-declarative-pipelines/STREAMING-ARCHITECTURE.md:107) allows reusing an uncommitted checkpoint ID at a new boundary. These conflict.

   Suppose both sinks committed checkpoint 1 at position 3. Checkpoint 2 records position 6; A commits it, B does not. Restarting at 3 and reusing ID 2 at position 10 makes A skip rows 6–9. Using ID 3 instead duplicates rows 3–5 in A. The two CDC merges have the same partial-commit problem.

   Preserve immutable prepared records tying together boundaries, operator state, sealed rows and individual sink effects. Recover pending checkpoints at their original boundaries before creating new ones. The existing single-sink tests do not establish this guarantee.

2. **State cleanup must follow the recovery frontier.**
   [S5](/Users/alexy/src/grust-sdp/docs/sail-declarative-pipelines/DECISION-NOTES-STREAMING.md:136) and [StateStore::retain_from](/Users/alexy/src/sail-proto-p4/crates/sail-physical-plan/src/streaming/state_store.rs:132) permit deleting earlier state once later positions are recorded. Recording happens before commits, so a crash can still require that earlier state. Retain everything needed by incomplete effects and the oldest recoverable checkpoint. This is an unsafe contract; no active cleanup call site was found.

3. **Validate every original CDC row before reduction.**
   The [proposal](/Users/alexy/src/grust-sdp/docs/sail-declarative-pipelines/CHANGE-CAPTURE-ON-STREAMSOURCE.md:37) places reduction before sink validation. An invalid losing row can disappear during reduction. The current runtime explicitly [validates before reconciliation](/Users/alexy/src/sail-pipelines-proposal/crates/sail-spark-connect/src/pipelines/autocdc/write.rs:420).

   Preserve that order and bind validation evidence to the sealed interval. Add a test where an invalid row loses to a valid row with the same key.

4. **The deterministic tie claim needs stable source provenance.**
   [changes.rs](/Users/alexy/src/sail-proto-p4/crates/sail-physical-plan/src/streaming/changes.rs:20) resolves ties by input row index; the [merge](/Users/alexy/src/sail-proto-p4/crates/sail-physical-plan/src/streaming/merge.rs:223) interleaves asynchronous arrivals. That establishes deterministic reduction of already ordered input, not deterministic winners across different replay schedules. Define an ordering over source/partition/offset provenance, or narrow the guarantee to stability after winners have been archived.

The prototype code also has these findings:

5. **High: merge completion counts one input twice.**
   [merge.rs:135](/Users/alexy/src/sail-proto-p4/crates/sail-physical-plan/src/streaming/merge.rs:135) adds `ended + closed`; an input that emits end-of-data and then closes contributes to both. This can emit global end-of-data while another input remains live. The rate source also [closes after any checkpoint following its local end-of-data](/Users/alexy/src/sail-proto-p4/crates/sail-data-source/src/formats/rate/reader.rs:313), making staggered completion with periodic checkpoints unsafe.

   Track completion per input and distinguish the globally final checkpoint from ordinary checkpoints.

6. **High: Iggy can miss recreation between scan and bounding.**
   [bound_now](/Users/alexy/src/sail-proto-p3/crates/sail-iggy-bounded/src/stream.rs:198) captures the frontier without validating incarnation; the reader [checks for end-of-data before validating incarnation](/Users/alexy/src/sail-proto-p3/crates/sail-iggy-bounded/src/stream.rs:459). Resume an old partition at offset 10, recreate it empty, then bound: the new frontier is zero, so the reader can finish successfully using the obsolete position.

   Validate incarnation while establishing bounds. The existing recreation test recreates before scanning and misses this interleaving.

7. **Medium: overlapping checkpoint requests can deadlock alignment.**
   The [coordinator](/Users/alexy/src/sail-proto-p4/crates/sail-common-datafusion/src/streaming/checkpoint.rs:98) allocates IDs without serializing requests, while sources use a latest-value watch channel. One partition can observe C1 and another only C2, leaving both blocked at different barriers. Enforce one in-flight checkpoint or queue every request, including periodic/final overlap.

8. **High, requiring reproduction: concurrent Delta table creation may bypass idempotency.**
   The new transaction check runs [during planning](/Users/alexy/src/sail-proto-p4/crates/sail-delta-lake/src/physical_plan/planner/op_write.rs:51). Two plans can both observe an absent table. The second commit then [adopts the first commit’s snapshot](/Users/alexy/src/sail-proto-p4/crates/sail-delta-lake/src/transaction/mod.rs:1390), bypassing the intervening-version conflict check without rechecking the transaction identity.

   Before extracting the standalone Delta PR, prepare two same-token writes against an absent table and execute both. This is a source-path finding, not an executed reproduction or a claim that all concurrent writes fail.

**For the next decision:** use one streaming discussion with CDC as the second proposal, retain S1–S4 first, and make prepared-checkpoint recovery the next prototype. Its tests should cover partial multi-sink commits, crashes between CDC merges, immutable replay boundaries, and state retention. Driver-to-task coordination should follow.

The reuse table should preserve sealed archives, validation, contract identity, separate effect receipts and fencing. Checkpoint IDs do not eliminate those obligations. The current [durable recovery path](/Users/alexy/src/sail-pipelines-proposal/crates/sail-spark-connect/src/pipelines/autocdc/durable.rs:672) already preserves important parts; the stronger [ValidationReceipt model](/Users/alexy/src/sail-pipelines-proposal/crates/sail-spark-connect/src/pipelines/autocdc/prepared.rs:11) explicitly remains pending wiring.

Also revise bounded runs to permit periodic checkpoints plus a mandatory final checkpoint: otherwise the append sink buffers the entire available backlog. Update the stale plan/packet and narrow the results document’s “whole exactly-once path” claim.

The unbuilt CDC merges, planner wiring, durable position record and Spark end-to-end test were treated as design work, not missing-code defects.
