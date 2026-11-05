# Regression audit: StreamSource integration and durable change capture

## Scope and evidence

This is source inspection, not execution of the proposed replacement. No Rust,
Spark, broker, distributed or external-engine tests were run. Previously
reported prototype test counts are not new evidence from this audit. The saved
request and AGENTS.md, LAKESAIL.md, SHEHAB.md, WRITING-RULES.md and CLARITY.md were
read. The latest engineering directive controls over compatibility defaults.

| Reference | Checkout and verified HEAD |
| --- | --- |
| U, current upstream | `/Users/alexy/src/sail/tmp/streamsource-review-20261105-85c6cca01`, `85c6cca01cd521dd778bc200c987a34edf141de1` |
| R, bounded runtime | `/Users/alexy/src/sail-pipelines-proposal`, `99dc47788941daf28eec847527949a4cadafdbd2` |
| P4, stacked P1/P2/P4 | `/Users/alexy/src/sail-proto-p4`, `4fad33ca531ec44170d0e8d11c794df14835ff37`; compared with `62251e0a27bbab0a15547562e829cad2a418f353` |
| P3, Iggy prototype | `/Users/alexy/src/sail-proto-p3`, `ef5f848a758ed48067a751165d8bf9a756f2c482`; prototype commit inspected separately from its integration ancestry |

The new CHANGE-CAPTURE-SEMANTICS, FENCED-TABLE-COMMITS and
STREAMSOURCE-ENGINEERING-REVIEW documents were read end to end. Their proposed
ordering, migration and mandatory fencing contracts improve the inspected
runtime without claiming those changes are implemented. Two source-admission
details need explicit treatment before an Iggy-based replacement is qualified.

## Source-admission corrections

### High: bind checkpoint positions to source identity and topology

[P3 positions](/Users/alexy/src/sail-proto-p3/crates/sail-iggy-bounded/src/stream.rs:68)
encode partition number, incarnation and next offset. They do not bind the
broker, stream, topic or decoding contract. On restart,
[starts](/Users/alexy/src/sail-proto-p3/crates/sail-iggy-bounded/src/stream.rs:274)
enumerates the current partition set and starts an unrecorded partition at
its first retained offset. Missing old partitions fail, but newly discovered
ones enter implicitly. This is not necessarily an invalid connector policy;
it is insufficient as an unspecified durable-recovery policy.

Bind every prepared checkpoint to its source descriptor, admitted partition
set and decoding semantics. Define an explicit discovery/bootstrap boundary
for added partitions. Do not silently treat a retained-only start as complete
history. Test changed source configuration, missing and added partitions,
and an added partition whose earlier data has already expired.

### High: checkpoint identity does not automatically become event identity

[P3 raw rows](/Users/alexy/src/sail-proto-p3/crates/sail-iggy-bounded/src/decode.rs:18)
contain offset and message id but no partition or incarnation. JSON decoding
at line 84 exposes payload columns. The
[envelope schema](/Users/alexy/src/sail-proto-p3/crates/sail-iggy-bounded/src/envelope.rs:175)
includes source, stream, topic, partition and offset, but no incarnation.
The reader has an incarnation in its control state; it does not attach that
identity to each emitted normalized event.

The new complete-order contract therefore needs a provenance mechanism or an
explicitly admitted immutable event envelope. Preserve required provenance
through projection and filtering; give expanding transforms stable emission
ordinals. Source position and business order remain different concepts:
sorting unrelated broker partitions is not an order of changes to one key.
Test identical offsets from different partitions and recreated partitions,
including projections that remove user-visible metadata columns.

## Obligations that cannot be inherited from the prototypes unchanged

| Priority and inspected source | Required preservation or correction |
| --- | --- |
| High: [P4 coordinator](/Users/alexy/src/sail-proto-p4/crates/sail-common-datafusion/src/streaming/checkpoint.rs:74) stores positions in memory; [append sink](/Users/alexy/src/sail-proto-p4/crates/sail-physical-plan/src/streaming/append_sink.rs:191) skips any id at or below the table high-water mark | Bind each accepted id to immutable input, state and effects. Recording positions alone is not a durable prepared record. Preserve separate outcomes for partial effects. The optional gate at line 197 cannot establish this by itself. |
| High: [P4 merge](/Users/alexy/src/sail-proto-p4/crates/sail-physical-plan/src/streaming/merge.rs:135) adds ended and closed counts for the same input; [P3 source](/Users/alexy/src/sail-proto-p3/crates/sail-iggy-bounded/src/stream.rs:448) closes after its next checkpoint | Count distinct participants. An intermediate checkpoint after one partition ends must not terminate another live partition or leave final checkpoint requests awaiting a closed participant. Test staggered ends with an intermediate checkpoint. |
| High: [P3 bound capture](/Users/alexy/src/sail-proto-p3/crates/sail-iggy-bounded/src/stream.rs:198) records a frontier without checking incarnation; [early completion](/Users/alexy/src/sail-proto-p3/crates/sail-iggy-bounded/src/stream.rs:459) precedes the later identity check | Coordinate capture with the actual reader and verify incarnation before accepting an empty or already-reached bound. Recreate an empty partition between scan and bound; also let reading race past a captured frontier. |
| High: [P4 state store](/Users/alexy/src/sail-proto-p4/crates/sail-physical-plan/src/streaming/state_store.rs:73) rewrites a checkpoint's files; retention at line 132 is justified by recording a newer position | Preserve snapshots referenced by incomplete effects and all valid restart points. Reuse needs immutable publication, explicit durability and operator-configuration identity, not only column names and types. No active retention call was established. |
| Medium: [P4 requests](/Users/alexy/src/sail-proto-p4/crates/sail-common-datafusion/src/streaming/checkpoint.rs:98) are concurrent; [P3 control](/Users/alexy/src/sail-proto-p3/crates/sail-iggy-bounded/src/stream.rs:170) uses a latest-value watch channel | Serialize or queue requests. Bind acknowledgements to source/task attempts and the accepted participant set. Missing a request can leave inputs at different barriers. |
| High, unexecuted inference: [P4 Delta planning check](/Users/alexy/src/sail-proto-p4/crates/sail-delta-lake/src/physical_plan/planner/op_write.rs:51), followed by [creation-time snapshot adoption](/Users/alexy/src/sail-proto-p4/crates/sail-delta-lake/src/transaction/mod.rs:1390) | Revalidate transaction identity at actual acceptance after adopting a concurrently created table. Loading the newest snapshot can skip the intervening-version check at line 1456. Test two plans prepared against an absent table with the same transaction identity; do not claim this race was reproduced here. |

Current upstream has the same foundational contract gap: its
[source interface](/Users/alexy/src/sail/tmp/streamsource-review-20261105-85c6cca01/crates/sail-common-datafusion/src/streaming/source.rs:15)
offers a scan but no durable replay capability. Its
[collector](/Users/alexy/src/sail/tmp/streamsource-review-20261105-85c6cca01/crates/sail-physical-plan/src/streaming/collector.rs:122)
discards markers and ignores retractions. The existing event model is useful,
but durable success cannot be inferred from this collector ending.

## Preserve validation and recovery while replacing semantics

The bounded runtime's
[prepare path](/Users/alexy/src/sail-pipelines-proposal/crates/sail-spark-connect/src/pipelines/autocdc/write.rs:420)
validates the original logical input before reduction, then collects reconciled
winners once at line 478. This is valuable sequencing, but validation executes
the lazy plan separately from reduction. A nondeterministic expression can
therefore produce different values. The proposed normalize-once rule fixes a
real gap. Do not claim merely keeping the two calls preserves exact validation.

[Durable preparation](/Users/alexy/src/sail-pipelines-proposal/crates/sail-spark-connect/src/pipelines/autocdc/durable.rs:672)
restores archived winners by digest, or archives them and records their digest
before effects. Lines 737 and 753 check auxiliary and target outcomes separately;
line 774 completes the batch after both. Preserve these properties even if a
single target transaction replaces the sidecar. The stronger
[validation receipt model](/Users/alexy/src/sail-pipelines-proposal/crates/sail-spark-connect/src/pipelines/autocdc/prepared.rs:11)
is explicitly unwired, so its type-level guarantee is not a production receipt
guarantee. Admission must prove the actual effect path uses the validated values.

[P4 reduction](/Users/alexy/src/sail-proto-p4/crates/sail-physical-plan/src/streaming/changes.rs:45)
chooses the later row of a supplied batch for equal sequences. It neither
validates original rows nor establishes cross-partition order. The new total
per-key order and duplicate/conflict contract must replace that rule, not be
described as functionality already provided by this reducer.

## Fencing and ordinary-table interoperability

[Runtime target selection](/Users/alexy/src/sail-pipelines-proposal/crates/sail-spark-connect/src/pipelines/autocdc/execute.rs:119)
mistakes catalog ordering for sufficient ownership and sends managed Delta and
Iceberg to the plain path. That path also performs
[refresh and schema changes](/Users/alexy/src/sail-pipelines-proposal/crates/sail-spark-connect/src/pipelines/autocdc/run.rs:322)
outside the fenced protocol. Removing this fallback is necessary under the new
directive; retaining it for compatibility would preserve an engineering defect.

The existing
[fenced Delta data commit](/Users/alexy/src/sail-pipelines-proposal/crates/sail-delta-lake/src/physical_plan/commit_exec.rs:1035)
refuses new and catalog-managed tables, stages exact bytes and ratifies them
before publication. Its
[authority property](/Users/alexy/src/sail-pipelines-proposal/crates/sail-common-datafusion/src/fenced_commit.rs:63)
and process-local registry are useful cooperating-Sail mechanisms, not proof
that external writers or distributed workers enforce ownership. The new fencing
document correctly requires creation, reset, maintenance, unknown outcomes,
worker-to-authority transport and every permitted writer to share enforcement.
Acceptance before takeover may authorize publication of those exact bytes;
takeover must prevent new acceptance by the obsolete owner.

The new atomic key-state reference is a capability proposal, not an existing
Delta/Iceberg guarantee. Qualify metadata preservation, external readers,
permitted external writers, snapshot restoration and maintenance before reuse.
A physical state table plus view changes public table identity and is not a
transparent substitute for an ordinary table.

## Migration and evidence boundary

Existing target rows include
[the Spark-style metadata column](/Users/alexy/src/sail-pipelines-proposal/crates/sail-spark-connect/src/pipelines/autocdc/schema.rs:23),
while [merge predicates](/Users/alexy/src/sail-pipelines-proposal/crates/sail-spark-connect/src/pipelines/autocdc/merge.rs:229)
use different equal-sequence rules for upserts and deletes. The new event
contract cannot reinterpret pending old work or infer a lost secondary order.
Resolve pending effects under their recorded contract, fence old owners, and
use a verified migration, complete rebuild, or explicitly admitted baseline
and frontier. Preserve key/name/schema checks until a deliberate replacement
defines their meaning. Snapshot plus change-log frontier can replace an
absolute-offset-zero bootstrap when its consistency is established.

The inspected P2 tests
[retain positions in memory and abort a reader task](/Users/alexy/src/sail-proto-p4/crates/sail-physical-plan/src/streaming/append_sink_tests.rs:431).
They are simulated single-file-sink restart cases, not process-crash,
power-loss, fenced external-write or multi-effect qualification. P3 tests cover
bounded resume, retained-offset refusal and recreation before resumed scan;
they do not establish the capture, topology and per-event identity cases above.
Migration, reordered events/checkpoints, lost responses and external-writer
bypass require tests against the selected real source and commit authority.

## Source SHA-256 manifest

The following hashes identify the source bytes inspected for the findings.
Reference letters resolve to the checkout table above. Hashes do not imply
those files were executed.

| Ref | Relative source path | SHA-256 |
| --- | --- | --- |
| U | `crates/sail-common-datafusion/src/streaming/source.rs` | `8ad95175cc7e9bc1c7f54cf80c0dfcf975d6f95f3023dfd2ee26022b084ede2d` |
| U | `crates/sail-common-datafusion/src/streaming/event/marker.rs` | `4535f7f0413ed1f44184247ac61fb1950da446498572a9d8f8be3682c3954061` |
| U | `crates/sail-physical-plan/src/streaming/collector.rs` | `e2e975eaaf44bc7ee516cd8a070604e5e3d2f576f7e7c31d60525a4e493980bd` |
| R | `crates/sail-spark-connect/src/pipelines/autocdc/write.rs` | `6fc4559adcf6e1412e1db215c6278a546cc1c2d5899c6c7c7bdc3b4bdfcf5d16` |
| R | `crates/sail-spark-connect/src/pipelines/autocdc/durable.rs` | `bf294baff3ec8eccd569855abba57ce051311a0dbbb251a56474c298d04050ce` |
| R | `crates/sail-spark-connect/src/pipelines/autocdc/prepared.rs` | `b826cbd47999f427235cb946f99fc5ecf66760332802066f7baeefe0eae99cb1` |
| R | `crates/sail-spark-connect/src/pipelines/autocdc/microbatch.rs` | `45140bf693d764618725158da99ded09457c33818fa08614178d3254d265b993` |
| R | `crates/sail-spark-connect/src/pipelines/autocdc/execute.rs` | `7210cfc8fb7a61cd8671ab82b0ee07f4ed5c92586a8174ca82465cdb924d95fc` |
| R | `crates/sail-spark-connect/src/pipelines/autocdc/run.rs` | `9b3885e85135f7cbf5e48946253a695b3332ac4a42747f156ab27a881ba3fbf7` |
| R | `crates/sail-spark-connect/src/pipelines/autocdc/schema.rs` | `63b37925e0e73dc3c5b3dce0034a83440dbb2d36793987ce9a1278762a4cbd4f` |
| R | `crates/sail-spark-connect/src/pipelines/autocdc/merge.rs` | `9ca0dd284650eb437d6374af2d63e166adb4b0ff8c411c39c67c5211050a20e4` |
| R | `crates/sail-spark-connect/src/pipelines/autocdc/reconcile.rs` | `983c745c91e1d000f27a37ef6942a8c4006f12b542c8b87ad9995fa26eb5f8a0` |
| R | `crates/sail-common-datafusion/src/fenced_commit.rs` | `f5905e807f6bbd5ae76db5e8343a0864188bbb42165b797a0c0418ca51e8a538` |
| R | `crates/sail-delta-lake/src/fenced.rs` | `def5134e4e564db0497dd60fac433e809fc09255ba76b019339ce67b3d2356ca` |
| R | `crates/sail-delta-lake/src/physical_plan/commit_exec.rs` | `c0437b8d79fe6d98bb617a9df0073f1e5ee7eb6c7e17efd4e894c6535bf238fd` |
| P4 | `crates/sail-common-datafusion/src/streaming/checkpoint.rs` | `33413f2988839a4cc0b098d03e4fc03206be59c0a66add5a200bbe24aa8e4842` |
| P4 | `crates/sail-physical-plan/src/streaming/append_sink.rs` | `d64459638e2459596a89d7f3e787c8e4eaf3e31b9af632eb6779a4a641fbc992` |
| P4 | `crates/sail-physical-plan/src/streaming/append_sink_tests.rs` | `795114dc84755917d5283cdf6c13c824c7c41c12ead182d0e9c51460597d4ccc` |
| P4 | `crates/sail-physical-plan/src/streaming/merge.rs` | `48eac7ee771f7b40fa9ff2dfcdcbc3cef26f190ef6c71fa1278f851ec36fba02` |
| P4 | `crates/sail-physical-plan/src/streaming/changes.rs` | `b5f25b607169063f6a9dc49f094ace8638e27b869388ab66c4c53c703acabc3e` |
| P4 | `crates/sail-physical-plan/src/streaming/state_store.rs` | `40217bb71f3dfeb4de569542c14bc3136e2be51d54a9f31eff8e3d0d8c434089` |
| P4 | `crates/sail-physical-plan/src/streaming/window.rs` | `39e69755580b7e2e37114d181b18167e2c79dee3ea221efaba6f283b8dda65a8` |
| P4 | `crates/sail-data-source/src/formats/rate/reader.rs` | `7b8589f5f20d0764bee15de8a6e68b05945444434da9c828ad03203ba7b962cd` |
| P4 | `crates/sail-delta-lake/src/physical_plan/planner/op_write.rs` | `383f738259d1716799def65c4b6ea176654c42e1b93092c0af8cfbe3d7a30073` |
| P4 | `crates/sail-delta-lake/src/transaction/mod.rs` | `5d68bfd56d9c99ebf298f59533aff82a9d3f6994b94386a16c8a1b39d13acc85` |
| P3 | `crates/sail-iggy-bounded/src/stream.rs` | `831aaaae180e67542d044fcfba74cc101509fd091cf9471852e70c36319a15e2` |
| P3 | `crates/sail-iggy-bounded/src/decode.rs` | `6e728984e70422226b0b108213919fdece45f85080cb99a8286c6f57acc9d022` |
| P3 | `crates/sail-iggy-bounded/src/envelope.rs` | `b7d6af0d497612de0384e96efcd68298025d999d04f000bcfea20318e6ece092` |
| P3 | `crates/sail-iggy-bounded/src/range.rs` | `ff71b41ae8e9e74f14c628cef3c88ac6537b3283893a6a1a35abfa65ab162f99` |
| P3 | `crates/sail-iggy-bounded/tests/stream.rs` | `c4e7bb372a10c4d3c9ed8032533729274eb17ce80adfa4c70e3aae9c991dbbe1` |
