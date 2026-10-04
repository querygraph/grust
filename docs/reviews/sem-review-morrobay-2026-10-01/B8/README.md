# B8: isolated relational shape comparison

Protocol: **completed_with_failures**. Qualification status: **incomplete_receipt_evidence**. 40/60 cells qualify by retained frozen queue plus declared host closure adapter, host, producer and full physical-oracle receipts. This is a metadata audit, not a new physical-payload comparison.

Ratios are **array-explode / union**, within each dataset and shape on shared Morrobay. Four measured samples per form, in two U A A U blocks; warmups remain in evidence and are excluded. Raw seconds are diagnostics. No absolute-performance, multihost or full-WCC performance claim follows.

| Dataset | Isolated shape | Median ratio | Block 1 | Block 2 | Status |
| --- | --- | ---: | ---: | ---: | --- |
| cit-Patents | adjacency | 1.02 | 1.01 | 1.07 | qualified_receipt_evidence |
| cit-Patents | representatives | 1.12 | 1.1 | 1.11 | qualified_receipt_evidence |
| cit-Patents | min-label-initial-round | 1.12 | 1.1 | 1.14 | qualified_receipt_evidence |
| graph500-24 | adjacency | withheld | — | — | withheld |
| graph500-24 | representatives | 1.0 | 1.02 | 0.988 | qualified_receipt_evidence |
| graph500-24 | min-label-initial-round | withheld | — | — | withheld |

## Boundaries and semantics

One fresh local Pecan engine per cell; 16 CPUs, 32 GiB, no swap; 30 GiB greedy pool with mimalloc and native_quota configured to 256 MiB. Pool/native reservation counters are not measured by this report. Pool budgets do not guarantee a physical memory bound. Source pins and every observed memory boundary/guest steal value remain in report.json.

The earlier A2/A3 statement that every Pecan process prepays this quota was corrected in [C3-NATIVE-QUOTA-CORRECTION.md](../C3-NATIVE-QUOTA-CORRECTION.md). Exact source review supports quota admission when the corresponding extension owner is bound, including lazy worker-native admission. These are source contracts; actual reservation events are unmeasured here. The correction preserves the original timings, cells, archived plans and generation receipts.

The timer spans child process launch through completed exit: startup, original reads, snapshots, shape preparation, explain recording before staging writes, materialization, result export and cleanup. Source/input/reference hashes, full physical output oracle and host archival are outside. Plans describe the relation immediately before its staging sink; they exclude the Parquet sink wrapper. The raw plan files are indexed artifacts, and recording them remains inside the child timer.

Adjacency is the distinct original/reverse pair set. Representatives cover active endpoints in the first contraction round after self-loop exclusion; they are not a full WCC partition. The initial min-label update includes isolated vertices and compares the whole labels/propagation update; it is not a complete WCC loop. Every qualifying oracle compares all raw signed64 pairs/IDs/values, schema, multiplicity and coverage against the selected sealed reference.

n=4, ordered blocks, shared-host activity and filesystem cache warming limit inference. Child phases may nest/overlap; phase totals sum only occurrences of the same name, and their medians are explanatory diagnostics. No phase subtraction or adjusted performance ratio is reported. Sampled engine PSS excludes the supervisor/PID1; whole-container and lifetime cgroup observations include broader costs and page cache, and final peaks include the parent oracle.

Both original dataset contracts, full reference phases, six tiny signed/high-magnitude/duplicate/loop/isolate controls and all prior attempts remain separately recorded. Missing, failed, mismatched or unqualified cells withhold that contrast. 60/60 qualification is false; 60/60 attempted calls are false; the protocol completed_with_failures with closed failures and explicit skips retained. B8 DONE denotes protocol completion with failures. The all60_qualified and all60_attempted fields are false.

See [report.json](report.json), [REPORT.md](REPORT.md), [evidence-index.json](evidence-index.json) and [evidence.tar.gz](evidence.tar.gz). Full physical payloads stay on Apo, linked through unchanged collected and guest archive manifests; this generator never reads or rehashes them.

## Retained prerequisite outcomes

| Kind | Reference or control | Outcome |
| --- | --- | --- |
| stage | stage | passed |
| full-reference | cit-Patents | passed |
| full-reference | graph500-24 | passed |
| tiny-control | tiny-adjacency-union01 | passed |
| tiny-control | tiny-adjacency-array-explode01 | passed |
| tiny-control | tiny-representatives-union01 | passed |
| tiny-control | tiny-representatives-array-explode01 | passed |
| tiny-control | tiny-min-label-initial-round-union01 | passed |
| tiny-control | tiny-min-label-initial-round-array-explode01 | passed |

## Host closure provenance

Host orchestration used the unchanged frozen queue abe3842e with the explicit b8-host-embedded-absence-v2 adapter 99c53056. Configuration preparation used the unchanged generator 504c0127 through wrapper a6e8e1d4. The only archived predicate correction requires embedded absence_verified and compares separate records excluding only that field; all other archived predicates remain unchanged. The original function SHA 7dd9fefe and its copied predicate guard are rechecked from retained source. Guest algorithms, source matrix, inputs and engine timers are unchanged. Structured host_closure_provenance in report.json pins these sources, prepared configuration, complete reference closure gate and the failed continuation01/generated-queues01 receipts.

## Finalized serial tail

The original Graph500 adjacency union warmup genuinely OOMed at the unchanged 32 GiB limit. The root-reviewed serial tail used fresh IDs and changed only config output paths; algorithms, inputs, resources and engine timers are unchanged. Both real warmups must qualify before that contrast’s measured calls. Failed warmups cause explicit not_started_due_to_failed_warmup rows with no synthetic PID, oracle or timing. Failed/skipped rows never enter ratios. Raw receipts are unchanged. A declared in-memory queue projection delegates passed cells to the unchanged frozen positive metadata predicates. All 31 original outcomes, mappings, controller/authorization/closure/lock evidence remain indexed. The original OOM prevents all 60 qualification and all 60 attempted calls under the warmup policy; the protocol can finish with closed failures/skips retained. The allocation cause remains unexplained. Packaging uses a finite per-chunk metadata deadline; physical payload manifests remain on Apo and are not rehashed here.

Protocol: **completed_with_failures**; 40/60 qualified, 44/60 attempted, 16 skipped. All60 qualification and all60 attempted calls are false.

Native quota: 256 MiB configured; actual reservation and prepayment events are unobserved.
