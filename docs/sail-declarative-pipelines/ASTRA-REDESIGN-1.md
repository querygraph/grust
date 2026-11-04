# ASTRA-REDESIGN-1

## Verdict and status

The streaming redesign has a credible foundation in Sail's flow-event model. It is not ready for an implementation or submission approval. The next deliverable should be a corrected discussion packet that lets the maintainers decide the unresolved architecture before production code expands.

This document corrects [ASTRA-REDESIGN-0](ASTRA-REDESIGN-0.md). That document remains the historical technical review. Its findings have not been disproved. This correction supersedes its process and readiness recommendations: findings are evidence for design decisions, not an automatically authorized implementation backlog.

This is an internal review. Nothing has been posted, committed or proposed upstream through this review.

## Scope and evidence

The review covered the streaming and change-capture documents, the current bounded change-capture runtime, and these local prototypes:

| Subject | Reviewed reference |
| --- | --- |
| P4, including the P1 and P2 changes | `4fad33ca531ec44170d0e8d11c794df14835ff37`, compared with upstream `62251e0a2` |
| P3 Iggy stream source | `ef5f848a758ed48067a751165d8bf9a756f2c482`, isolating the prototype on the integration branch |
| Current runtime | `99dc47788941daf28eec847527949a4cadafdbd2` |

No Rust, Spark or broker suites were rebuilt or rerun. Findings come from source inspection. An independent Python transition model supported the partial-commit counterexample; it was not an execution of the Rust implementation. Existing test reports were historical evidence. No extension prototype was reviewed.

The unbuilt merge sink, planner wiring, durable position record and Spark end-to-end test are declared future work, not missing-code defects.

## What the original review did not fulfill

The lead reviewers had not read all of [LAKESAIL.md](LAKESAIL.md), [SHEHAB.md](SHEHAB.md) and [WRITING-RULES.md](WRITING-RULES.md) before the original assessment. They have now read them. The original assessment therefore cannot serve as evidence that the required review process was completed.

- The specialist work was divided by component. It did not include seven independent specialist reviews of the cumulative diff.
- The review did not independently verify the relevant Spark 4.2.1 source or execute Spark. It must not promote inherited semantic claims into newly verified facts.
- It did not establish that the proposing author could explain the changes line by line, or obtain maintainers' architectural decisions.
- It did not complete the outward-document reading pass, cumulative upstream regression review or immutable-commit integration gate.
- The full original prompt and maintainer instructions were not saved and propagated to every reviewer as required. No claim of full compliance is warranted.

Reading the governance documents afterward corrects our understanding. It does not retroactively complete those checks.

## Findings retained from the technical review

### 1. High: partial commits need an immutable recovery identity

[S6](DECISION-NOTES-STREAMING.md#s6-how-a-sink-commits) resumes from the least committed sink. The [architecture](STREAMING-ARCHITECTURE.md#failure-cases-by-component) also allows an uncommitted checkpoint identifier to be reused at a new boundary. Those rules conflict when another sink already committed that identifier.

For example, both sinks commit checkpoint 1 at position 3. Checkpoint 2 records position 6; sink A commits it and B does not. Restarting at 3 and reusing identifier 2 at position 10 loses rows 6 through 9 from A. Issuing identifier 3 instead duplicates rows 3 through 5 in A. The auxiliary and target tables create the same partial-effect problem for change capture.

The maintainers should decide the checkpoint domain and supported scope. Options include immutable prepared boundaries with separate effect receipts, or a narrower initial execution model. A single logical sink does not remove the two-table change-capture question. Any claimed solution needs a controlled crash between effects, not another single-sink happy path.

### 2. High: recorded positions are not a safe state-retention boundary

[S5](DECISION-NOTES-STREAMING.md#s5-the-state-store) permits deleting older state after a later checkpoint is recorded. [StateStore::retain_from](/Users/alexy/src/sail-proto-p4/crates/sail-physical-plan/src/streaming/state_store.rs:132) encodes that contract. Recording precedes sink commits, so recovery can still need the older state.

No current call site was found: this is an unsafe proposed contract, not observed live deletion. The recovery decision must specify which manifests remain necessary while effects are incomplete, and when reclamation becomes legal.

### 3. High: validation must cover original change rows

The [change-capture proposal](CHANGE-CAPTURE-ON-STREAMSOURCE.md#what-has-to-exist) places reduction before a sink that validates. A losing row with a null sequence can disappear during reduction. Current production [validates first](/Users/alexy/src/sail-pipelines-proposal/crates/sail-spark-connect/src/pipelines/autocdc/write.rs:420), reconciles afterward and seals the winners once.

Preserving that behavior requires validation before reduction, or equivalent evidence covering every original row. The design question is how that evidence belongs to the sealed interval, not whether validating winners alone suffices. A losing invalid row is the discriminating test.

### 4. Medium: the deterministic tie claim exceeds the prototype evidence

[reduce_interval](/Users/alexy/src/sail-proto-p4/crates/sail-physical-plan/src/streaming/changes.rs:20) chooses the later row in one batch. The [merge](/Users/alexy/src/sail-proto-p4/crates/sail-physical-plan/src/streaming/merge.rs:223) accepts asynchronous arrivals. Neither establishes a stable ordering across source partitions.

The maintainers should choose between a defined provenance order and the narrower guarantee that archived winners remain unchanged during recovery. The existing test proves the rule for already ordered input. Reverse partition arrival order to test the broader claim.

### 5. High: end-of-data accounting can finish a live stream

The [merge](/Users/alexy/src/sail-proto-p4/crates/sail-physical-plan/src/streaming/merge.rs:135) adds ended and closed counts, although one input can contribute to both. A finite input emitting end of data and then closing can therefore cause a global end marker while another input remains live. The next checkpoint ends the [collector](/Users/alexy/src/sail-proto-p4/crates/sail-physical-plan/src/streaming/collector.rs:132).

The [rate source](/Users/alexy/src/sail-proto-p4/crates/sail-data-source/src/formats/rate/reader.rs:313) also closes after any checkpoint following its local end marker. A focused test should separate input termination from global completion and place a periodic checkpoint between different inputs' end markers.

### 6. High: Iggy can accept a recreated partition while bounding

[bound_now](/Users/alexy/src/sail-proto-p3/crates/sail-iggy-bounded/src/stream.rs:198) captures an end without checking incarnation. The [reader](/Users/alexy/src/sail-proto-p3/crates/sail-iggy-bounded/src/stream.rs:459) can emit end of data before its later incarnation check.

Resume an old partition at offset 10, recreate it empty, then bound the run. The old position exceeds the new frontier of zero, permitting successful completion. The existing recreation case occurs before scan. Test recreation between scan and bound, including an empty replacement.

### 7. Medium: overlapping checkpoint requests can deadlock

The [coordinator](/Users/alexy/src/sail-proto-p4/crates/sail-common-datafusion/src/streaming/checkpoint.rs:98) allocates identifiers without serializing requests. The [rate source](/Users/alexy/src/sail-proto-p4/crates/sail-data-source/src/formats/rate/checkpoint.rs:116) uses a latest-value watch channel. One input can stop at checkpoint 1 while another misses it and stops at checkpoint 2. Neither barrier then aligns.

The protocol must choose serialized requests or a mechanism preserving every request. A controlled periodic/final overlap tests that choice.

### 8. High, unexecuted inference: concurrent Delta creation may bypass idempotency

The new check runs during [planning](/Users/alexy/src/sail-proto-p4/crates/sail-delta-lake/src/physical_plan/planner/op_write.rs:51). Two plans can both observe an absent table. The second commit then [loads the winner's snapshot](/Users/alexy/src/sail-proto-p4/crates/sail-delta-lake/src/transaction/mod.rs:1390), removes creation metadata and may skip intervening-version checks because its refreshed baseline already equals latest.

Before claiming this path safe or proposing its standalone PR, prepare two writes with the same transaction identity against an absent table, then execute both. This is a source-path inference, not a reproduced failure or a claim that all concurrent idempotent writes fail.

## Decisions before implementation

Keep one small decision register with these fields: question, options, recommendation, evidence and limits, maintainer answer, and implementation scope that answer permits. Mark unanswered questions as proposed. Do not convert recommendations into accepted decisions.

The corrected packet should prioritize recovery identity, checkpoint scope, sealed change rows and validation evidence, then coordinator ownership and source participation. It should also ask whether bounded runs permit periodic checkpoints: one final checkpoint makes the current append buffer encompass the whole available backlog.

Correct the reuse table. Checkpoint numbering does not eliminate archives, contract identity or separate effect evidence. Current [archive restoration](/Users/alexy/src/sail-pipelines-proposal/crates/sail-spark-connect/src/pipelines/autocdc/durable.rs:672) and effect tracking are reusable contracts. The stronger [ValidationReceipt model](/Users/alexy/src/sail-pipelines-proposal/crates/sail-spark-connect/src/pipelines/autocdc/prepared.rs:11) explicitly awaits wiring; describe it accordingly.

Local, unpushed prototypes may answer a narrowly stated decision with a falsifiable test. Do not automatically build a larger recovery subsystem from this review. Fold each result and its limits into the corresponding decision note.

## Human review and development sequence

For future sessions, preserve the full prompt and governing instructions at intake, distribute both to every reviewer, and reread both after compaction. For implementation work, record the starting HEAD and target merge base, maintain the cumulative patch, and retain artifacts until cleanup is approved. These are prospective requirements, not checks completed retrospectively for this review.

1. Prepare the exact discussion packet. Verify relevant Spark semantics from source, distinguish intended behavior from inconsistencies, and state what was inspected, run and left uncertain. Read every outward document end to end under the writing rules.
2. Have the author understand the proposed code and explain its fit with upstream line by line. Give the owner a concrete packet for outbound approval. Maintainers then decide architecture early enough to change the direction.
3. Offer a few larger reference PRs only as reference material when authorized. Let maintainers select pieces. Each selected upstream implementation then becomes a small, single-purpose PR after its design conversation. This avoids both an unsolicited forty-PR queue and a large implementation presented as inevitable.
4. For a submission candidate, obtain seven independent specialist agent reviews: Spark correctness, performance, regression, scope, test generation, research and design quality. Run them in waves if needed. Review the cumulative diff and repeat affected reviews after changes. Agents support human judgment; they do not replace it.
5. Integrate through the required gate on an immutable detached commit with its own target directory. Include formatting, strict clippy, library tests, verified CLI build, required optional features, frozen Spark ports, pipeline suites, CLI and metastore profiles, and Delta comparison against baseline. Compare the whole tree against upstream, not only the latest integration increment. Preserve failed runs and receipts. Landing must match the gated tree and parent.

The immediate deliverable is the corrected discussion packet, with explicit decisions still open. No production implementation, submission or cleanup is authorized merely by this review.
