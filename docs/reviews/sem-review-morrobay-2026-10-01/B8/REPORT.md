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

## All planned outcomes

Seconds below are retained launch-to-exit diagnostics, including warmups.

| Run | Role / block | Engine / host / oracle / producer | Seconds | Qualified |
| --- | --- | --- | ---: | --- |
| b8-cit-patents-adjacency-01-union | warmup / — | passed / passed / passed / passed | 24.7422323479841 | True |
| b8-cit-patents-adjacency-02-array-explode | warmup / — | passed / passed / passed / passed | 26.452753813995514 | True |
| b8-cit-patents-adjacency-03-union | measured / 1 | passed / passed / passed / passed | 23.861659278016305 | True |
| b8-cit-patents-adjacency-04-array-explode | measured / 1 | passed / passed / passed / passed | 24.759655600995757 | True |
| b8-cit-patents-adjacency-05-array-explode | measured / 1 | passed / passed / passed / passed | 24.94835299398983 | True |
| b8-cit-patents-adjacency-06-union | measured / 1 | passed / passed / passed / passed | 25.282584706001217 | True |
| b8-cit-patents-adjacency-07-union | measured / 2 | passed / passed / passed / passed | 24.20300557502196 | True |
| b8-cit-patents-adjacency-08-array-explode | measured / 2 | passed / passed / passed / passed | 25.334053991013207 | True |
| b8-cit-patents-adjacency-09-array-explode | measured / 2 | passed / passed / passed / passed | 31.036540164990583 | True |
| b8-cit-patents-adjacency-10-union | measured / 2 | passed / passed / passed / passed | 28.633492663007928 | True |
| b8-cit-patents-representatives-01-union | warmup / — | passed / passed / passed / passed | 12.492641918011941 | True |
| b8-cit-patents-representatives-02-array-explode | warmup / — | passed / passed / passed / passed | 14.802596956986235 | True |
| b8-cit-patents-representatives-03-union | measured / 1 | passed / passed / passed / passed | 13.416888692998327 | True |
| b8-cit-patents-representatives-04-array-explode | measured / 1 | passed / passed / passed / passed | 14.029291163984453 | True |
| b8-cit-patents-representatives-05-array-explode | measured / 1 | passed / passed / passed / passed | 14.217294821020914 | True |
| b8-cit-patents-representatives-06-union | measured / 1 | passed / passed / passed / passed | 12.250037891004467 | True |
| b8-cit-patents-representatives-07-union | measured / 2 | passed / passed / passed / passed | 12.867125743010547 | True |
| b8-cit-patents-representatives-08-array-explode | measured / 2 | passed / passed / passed / passed | 13.232399499014718 | True |
| b8-cit-patents-representatives-09-array-explode | measured / 2 | passed / passed / passed / passed | 13.978377391991671 | True |
| b8-cit-patents-representatives-10-union | measured / 2 | passed / passed / passed / passed | 11.634706148004625 | True |
| b8-cit-patents-min-label-initial-round-01-union | warmup / — | passed / passed / passed / passed | 27.058238920988515 | True |
| b8-cit-patents-min-label-initial-round-02-array-explode | warmup / — | passed / passed / passed / passed | 29.771948700974463 | True |
| b8-cit-patents-min-label-initial-round-03-union | measured / 1 | passed / passed / passed / passed | 27.440512963978108 | True |
| b8-cit-patents-min-label-initial-round-04-array-explode | measured / 1 | passed / passed / passed / passed | 29.60218809399521 | True |
| b8-cit-patents-min-label-initial-round-05-array-explode | measured / 1 | passed / passed / passed / passed | 30.07362869597273 | True |
| b8-cit-patents-min-label-initial-round-06-union | measured / 1 | passed / passed / passed / passed | 26.59141436900245 | True |
| b8-cit-patents-min-label-initial-round-07-union | measured / 2 | passed / passed / passed / passed | 26.56659177999245 | True |
| b8-cit-patents-min-label-initial-round-08-array-explode | measured / 2 | passed / passed / passed / passed | 29.29616962201544 | True |
| b8-cit-patents-min-label-initial-round-09-array-explode | measured / 2 | passed / passed / passed / passed | 30.737593389989343 | True |
| b8-cit-patents-min-label-initial-round-10-union | measured / 2 | passed / passed / passed / passed | 26.15527902098256 | True |
| b8-graph500-24-adjacency-01-union | warmup / — | error / error / None / oom | 122.4535779650032 | False |
| b8-tail01-graph500-24-adjacency-02-array-explode | warmup / — | error / error / None / oom | 109.88958832604112 | False |
| b8-tail01-graph500-24-adjacency-03-union | measured / 1 | None / None / None / None | None | False |
| b8-tail01-graph500-24-adjacency-04-array-explode | measured / 1 | None / None / None / None | None | False |
| b8-tail01-graph500-24-adjacency-05-array-explode | measured / 1 | None / None / None / None | None | False |
| b8-tail01-graph500-24-adjacency-06-union | measured / 1 | None / None / None / None | None | False |
| b8-tail01-graph500-24-adjacency-07-union | measured / 2 | None / None / None / None | None | False |
| b8-tail01-graph500-24-adjacency-08-array-explode | measured / 2 | None / None / None / None | None | False |
| b8-tail01-graph500-24-adjacency-09-array-explode | measured / 2 | None / None / None / None | None | False |
| b8-tail01-graph500-24-adjacency-10-union | measured / 2 | None / None / None / None | None | False |
| b8-tail01-graph500-24-representatives-01-union | warmup / — | passed / passed / passed / passed | 102.66056005901191 | True |
| b8-tail01-graph500-24-representatives-02-array-explode | warmup / — | passed / passed / passed / passed | 103.78165158699267 | True |
| b8-tail01-graph500-24-representatives-03-union | measured / 1 | passed / passed / passed / passed | 99.7241588269826 | True |
| b8-tail01-graph500-24-representatives-04-array-explode | measured / 1 | passed / passed / passed / passed | 103.09510506800143 | True |
| b8-tail01-graph500-24-representatives-05-array-explode | measured / 1 | passed / passed / passed / passed | 105.22988760698354 | True |
| b8-tail01-graph500-24-representatives-06-union | measured / 1 | passed / passed / passed / passed | 104.56956937198993 | True |
| b8-tail01-graph500-24-representatives-07-union | measured / 2 | passed / passed / passed / passed | 106.37410581298172 | True |
| b8-tail01-graph500-24-representatives-08-array-explode | measured / 2 | passed / passed / passed / passed | 104.34056061395677 | True |
| b8-tail01-graph500-24-representatives-09-array-explode | measured / 2 | passed / passed / passed / passed | 102.44530708598904 | True |
| b8-tail01-graph500-24-representatives-10-union | measured / 2 | passed / passed / passed / passed | 102.90860580198932 | True |
| b8-tail01-graph500-24-min-label-initial-round-01-union | warmup / — | error / error / None / oom | 100.05664344900288 | False |
| b8-tail01-graph500-24-min-label-initial-round-02-array-explode | warmup / — | error / error / None / oom | 109.46797223296016 | False |
| b8-tail01-graph500-24-min-label-initial-round-03-union | measured / 1 | None / None / None / None | None | False |
| b8-tail01-graph500-24-min-label-initial-round-04-array-explode | measured / 1 | None / None / None / None | None | False |
| b8-tail01-graph500-24-min-label-initial-round-05-array-explode | measured / 1 | None / None / None / None | None | False |
| b8-tail01-graph500-24-min-label-initial-round-06-union | measured / 1 | None / None / None / None | None | False |
| b8-tail01-graph500-24-min-label-initial-round-07-union | measured / 2 | None / None / None / None | None | False |
| b8-tail01-graph500-24-min-label-initial-round-08-array-explode | measured / 2 | None / None / None / None | None | False |
| b8-tail01-graph500-24-min-label-initial-round-09-array-explode | measured / 2 | None / None / None / None | None | False |
| b8-tail01-graph500-24-min-label-initial-round-10-union | measured / 2 | None / None / None / None | None | False |

## Withheld comparisons and cell failures

- b8-graph500-24-adjacency-01-union: actual failed/mismatched outcome retained; ratio withheld
- b8-tail01-graph500-24-adjacency-02-array-explode: actual failed/mismatched outcome retained; ratio withheld
- b8-tail01-graph500-24-adjacency-03-union: Actual calls were not started because warmup prerequisite failed: b8-graph500-24-adjacency-01-union, b8-tail01-graph500-24-adjacency-02-array-explode
- b8-tail01-graph500-24-adjacency-04-array-explode: Actual calls were not started because warmup prerequisite failed: b8-graph500-24-adjacency-01-union, b8-tail01-graph500-24-adjacency-02-array-explode
- b8-tail01-graph500-24-adjacency-05-array-explode: Actual calls were not started because warmup prerequisite failed: b8-graph500-24-adjacency-01-union, b8-tail01-graph500-24-adjacency-02-array-explode
- b8-tail01-graph500-24-adjacency-06-union: Actual calls were not started because warmup prerequisite failed: b8-graph500-24-adjacency-01-union, b8-tail01-graph500-24-adjacency-02-array-explode
- b8-tail01-graph500-24-adjacency-07-union: Actual calls were not started because warmup prerequisite failed: b8-graph500-24-adjacency-01-union, b8-tail01-graph500-24-adjacency-02-array-explode
- b8-tail01-graph500-24-adjacency-08-array-explode: Actual calls were not started because warmup prerequisite failed: b8-graph500-24-adjacency-01-union, b8-tail01-graph500-24-adjacency-02-array-explode
- b8-tail01-graph500-24-adjacency-09-array-explode: Actual calls were not started because warmup prerequisite failed: b8-graph500-24-adjacency-01-union, b8-tail01-graph500-24-adjacency-02-array-explode
- b8-tail01-graph500-24-adjacency-10-union: Actual calls were not started because warmup prerequisite failed: b8-graph500-24-adjacency-01-union, b8-tail01-graph500-24-adjacency-02-array-explode
- b8-tail01-graph500-24-min-label-initial-round-01-union: actual failed/mismatched outcome retained; ratio withheld
- b8-tail01-graph500-24-min-label-initial-round-02-array-explode: actual failed/mismatched outcome retained; ratio withheld
- b8-tail01-graph500-24-min-label-initial-round-03-union: Actual calls were not started because warmup prerequisite failed: b8-tail01-graph500-24-min-label-initial-round-01-union, b8-tail01-graph500-24-min-label-initial-round-02-array-explode
- b8-tail01-graph500-24-min-label-initial-round-04-array-explode: Actual calls were not started because warmup prerequisite failed: b8-tail01-graph500-24-min-label-initial-round-01-union, b8-tail01-graph500-24-min-label-initial-round-02-array-explode
- b8-tail01-graph500-24-min-label-initial-round-05-array-explode: Actual calls were not started because warmup prerequisite failed: b8-tail01-graph500-24-min-label-initial-round-01-union, b8-tail01-graph500-24-min-label-initial-round-02-array-explode
- b8-tail01-graph500-24-min-label-initial-round-06-union: Actual calls were not started because warmup prerequisite failed: b8-tail01-graph500-24-min-label-initial-round-01-union, b8-tail01-graph500-24-min-label-initial-round-02-array-explode
- b8-tail01-graph500-24-min-label-initial-round-07-union: Actual calls were not started because warmup prerequisite failed: b8-tail01-graph500-24-min-label-initial-round-01-union, b8-tail01-graph500-24-min-label-initial-round-02-array-explode
- b8-tail01-graph500-24-min-label-initial-round-08-array-explode: Actual calls were not started because warmup prerequisite failed: b8-tail01-graph500-24-min-label-initial-round-01-union, b8-tail01-graph500-24-min-label-initial-round-02-array-explode
- b8-tail01-graph500-24-min-label-initial-round-09-array-explode: Actual calls were not started because warmup prerequisite failed: b8-tail01-graph500-24-min-label-initial-round-01-union, b8-tail01-graph500-24-min-label-initial-round-02-array-explode
- b8-tail01-graph500-24-min-label-initial-round-10-union: Actual calls were not started because warmup prerequisite failed: b8-tail01-graph500-24-min-label-initial-round-01-union, b8-tail01-graph500-24-min-label-initial-round-02-array-explode

## Other retained attempts and gates

- `/Volumes/Apo/graph-tests/results/sem-review-20261001/B8-run01/cit-reference01/result.json`: passed; excluded from shape performance samples.
- `/Volumes/Apo/graph-tests/results/sem-review-20261001/B8-run01/data-stage01/result.json`: passed; excluded from shape performance samples.
- `/Volumes/Apo/graph-tests/results/sem-review-20261001/B8-run01/graph500-reference01/result.json`: passed; excluded from shape performance samples.
- `/Volumes/Apo/graph-tests/results/sem-review-20261001/B8-run01/stage01/result.json`: passed; excluded from shape performance samples.
- `/Volumes/Apo/graph-tests/results/sem-review-20261001/B8-run01/tiny-adjacency-array-explode01/result.json`: passed; excluded from shape performance samples.
- `/Volumes/Apo/graph-tests/results/sem-review-20261001/B8-run01/tiny-adjacency-union01/result.json`: passed; excluded from shape performance samples.
- `/Volumes/Apo/graph-tests/results/sem-review-20261001/B8-run01/tiny-min-label-initial-round-array-explode01/result.json`: passed; excluded from shape performance samples.
- `/Volumes/Apo/graph-tests/results/sem-review-20261001/B8-run01/tiny-min-label-initial-round-union01/result.json`: passed; excluded from shape performance samples.
- `/Volumes/Apo/graph-tests/results/sem-review-20261001/B8-run01/tiny-reference01/result.json`: passed; excluded from shape performance samples.
- `/Volumes/Apo/graph-tests/results/sem-review-20261001/B8-run01/tiny-representatives-array-explode01/result.json`: passed; excluded from shape performance samples.
- `/Volumes/Apo/graph-tests/results/sem-review-20261001/B8-run01/tiny-representatives-union01/result.json`: passed; excluded from shape performance samples.

## Exact raw plans

Each listed relative member is inside evidence.tar.gz; its recorded SHA binds the raw file to the producer and physical archive manifests.

- `archives/B8-run01/b8-cit-patents-adjacency-01-union/container/artifacts/engine/plan-shape-result.txt`: 2929 bytes, SHA-256 `e6cb9a868ed48e53c3ee705ba8fd420c3a89d0ef54f23bc3c0ecca7b3ff53b77`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-adjacency-02-array-explode/container/artifacts/engine/plan-shape-result.txt`: 1837 bytes, SHA-256 `087c44e00948eae5a7b01ccaf91bd8af0d47670d17c4e5be35d9ff3e64ee5b3a`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-adjacency-03-union/container/artifacts/engine/plan-shape-result.txt`: 2917 bytes, SHA-256 `0b81d85f1934279f110911ba2b22f99affcb677bcbcd3fcbfd9d93bb860b006d`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-adjacency-04-array-explode/container/artifacts/engine/plan-shape-result.txt`: 1837 bytes, SHA-256 `4c9e1fa53655c4d248064fc95d12ebbfa13a54ef41af2c7c3f3d431a42a7ec42`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-adjacency-05-array-explode/container/artifacts/engine/plan-shape-result.txt`: 1835 bytes, SHA-256 `03e69fe1acdee9d07fa343b715752d86a8ce6bf86d2518f7f8593199c8b92249`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-adjacency-06-union/container/artifacts/engine/plan-shape-result.txt`: 2929 bytes, SHA-256 `2f2b887547b689d70d8e6198446df7a500f98d0b04791f6ede557ba79e9efc15`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-adjacency-07-union/container/artifacts/engine/plan-shape-result.txt`: 2913 bytes, SHA-256 `60556ae07d7c2368df1a50ef69333bd6ff9f2779f80e72856f6dad874ee58d6d`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-adjacency-08-array-explode/container/artifacts/engine/plan-shape-result.txt`: 1839 bytes, SHA-256 `8c6897401df4fb9966b0fa597f0aa5be2bb64ce36d98fc71f08a27fbbaccc510`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-adjacency-09-array-explode/container/artifacts/engine/plan-shape-result.txt`: 1845 bytes, SHA-256 `a623d0fd011b5e30678d274468433559fba46241b65d4a84aa9f9927a912abf1`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-adjacency-10-union/container/artifacts/engine/plan-shape-result.txt`: 2929 bytes, SHA-256 `4e49ac99c5761402c41c917eee462c7401866b49bc41e2a366125d21aacff349`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-representatives-01-union/container/artifacts/engine/plan-shape-result.txt`: 3461 bytes, SHA-256 `8f82fc1ead91e387ce9c53c38b7acb9d83a8f2f2171b7b82b16cf0f455410d56`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-representatives-02-array-explode/container/artifacts/engine/plan-shape-result.txt`: 2229 bytes, SHA-256 `4e21dcf55c78c28d15522f873106ffcfe309d862c1e9a9c7e8ffa200d39ec401`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-representatives-03-union/container/artifacts/engine/plan-shape-result.txt`: 3461 bytes, SHA-256 `2b91c4f77a342591ca8d90903049454a27c4e33b30803f36edcb8a5bd6642ce1`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-representatives-04-array-explode/container/artifacts/engine/plan-shape-result.txt`: 2239 bytes, SHA-256 `6c0ca09a49461dd82c35de17e3ac767fac8690fffd0231980540d69b48314d3a`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-representatives-05-array-explode/container/artifacts/engine/plan-shape-result.txt`: 2233 bytes, SHA-256 `04d9e13058dd54d21a01cab1d6d996504ec6f65c5b29afb6292ed940e595f53f`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-representatives-06-union/container/artifacts/engine/plan-shape-result.txt`: 3473 bytes, SHA-256 `18175069ee9b8aea70de7f3f2fb42a28886cdf655bb566cc0423b7650aa52457`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-representatives-07-union/container/artifacts/engine/plan-shape-result.txt`: 3473 bytes, SHA-256 `8bc1cc534807ce4d23a4d1a6c8eff9cc60067f8d636dc692a1c74668922f6ba3`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-representatives-08-array-explode/container/artifacts/engine/plan-shape-result.txt`: 2233 bytes, SHA-256 `24eca49163e885a7d9a26d4aff89414ca29df28242982195db0f91ae10222cb4`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-representatives-09-array-explode/container/artifacts/engine/plan-shape-result.txt`: 2231 bytes, SHA-256 `a6461e32c5ef2993a34bc45db16d01e68fa85f844c08e4d8225059639ff7733b`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-representatives-10-union/container/artifacts/engine/plan-shape-result.txt`: 3473 bytes, SHA-256 `23f3a960914610dc88145afc38ce1faa160e5dd9e7f50a8c770b140e4a31f9d4`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-min-label-initial-round-01-union/container/artifacts/engine/plan-initial-adjacency.txt`: 3081 bytes, SHA-256 `d85f49bfa645b2d313f9b8eb73c78a936a804ee69f7f6bf5e159fadc0e12389b`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-min-label-initial-round-01-union/container/artifacts/engine/plan-initial-labels.txt`: 1473 bytes, SHA-256 `97ef96eb5cacfa362a60d62606f0cb56160f86125181c41b70055f77fd71bc65`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-min-label-initial-round-01-union/container/artifacts/engine/plan-shape-result.txt`: 4910 bytes, SHA-256 `e0f954fa3f01958dd760a3bbbc62813bb2e49bc6db56b4e66b76177f5c358913`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-min-label-initial-round-02-array-explode/container/artifacts/engine/plan-initial-adjacency.txt`: 3181 bytes, SHA-256 `9c5bd736c6cbecf8d471b252064e5ee630047191cc79e3d9e379acd8870ae113`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-min-label-initial-round-02-array-explode/container/artifacts/engine/plan-initial-labels.txt`: 1527 bytes, SHA-256 `69fba4ca98c6f237054ecd2b8771810a26292e071b0747a26eef544745a207cc`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-min-label-initial-round-02-array-explode/container/artifacts/engine/plan-shape-result.txt`: 3860 bytes, SHA-256 `9d57abbe262282dd1d67f3b4ed6210d761ce0059f9a4be586451606527c1b888`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-min-label-initial-round-03-union/container/artifacts/engine/plan-initial-adjacency.txt`: 3097 bytes, SHA-256 `e0c6bb0e57069e7b059b7270dcaefff4fd2a23a6450cc4671ad85cab8adc9f4d`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-min-label-initial-round-03-union/container/artifacts/engine/plan-initial-labels.txt`: 1479 bytes, SHA-256 `b5efcfc2e9911aa23cf59cfe6cab9aae56f4f923103175cd159817f5e9b863bf`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-min-label-initial-round-03-union/container/artifacts/engine/plan-shape-result.txt`: 4910 bytes, SHA-256 `7f224fe785674859d8449b310bbab247fbc756e734c895c44fdd97fc1581c339`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-min-label-initial-round-04-array-explode/container/artifacts/engine/plan-initial-adjacency.txt`: 3193 bytes, SHA-256 `07f9270964be0f11d212db919f2fb5fdb054671318d4bc9e68138cfd72134b51`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-min-label-initial-round-04-array-explode/container/artifacts/engine/plan-initial-labels.txt`: 1527 bytes, SHA-256 `d55d5911fb19f3fe6e49eab6ff70b5fef1374badd87523dc826758e555170b1f`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-min-label-initial-round-04-array-explode/container/artifacts/engine/plan-shape-result.txt`: 3868 bytes, SHA-256 `3191328f8008d48970b88a61a117b438260ae01a8ba8d28e909e30c22f01c933`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-min-label-initial-round-05-array-explode/container/artifacts/engine/plan-initial-adjacency.txt`: 3193 bytes, SHA-256 `4637a1f2ce8ba038458aa794e6c62e337646d12060b9b4e07075504802888c34`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-min-label-initial-round-05-array-explode/container/artifacts/engine/plan-initial-labels.txt`: 1527 bytes, SHA-256 `f293d2e68ac5f7a3b02e297db87ff039ecdbbfccde9bf399e6ef37f6b70d182e`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-min-label-initial-round-05-array-explode/container/artifacts/engine/plan-shape-result.txt`: 3874 bytes, SHA-256 `44b6aff72e2acfeaeb71b33ecdbc75dea8f0b28aa73f38826a150d119da43e41`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-min-label-initial-round-06-union/container/artifacts/engine/plan-initial-adjacency.txt`: 3085 bytes, SHA-256 `703282eaaef1e7ad5760e378908ce5703598bd13087594117a31c29db2822392`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-min-label-initial-round-06-union/container/artifacts/engine/plan-initial-labels.txt`: 1479 bytes, SHA-256 `a437ce50afb957120afa745377de6cb256866d8069257175c83a9c883d62049a`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-min-label-initial-round-06-union/container/artifacts/engine/plan-shape-result.txt`: 4910 bytes, SHA-256 `1c477dbfa162a2c1d984f388b4f0dc439113a5aec57facd6c4d5771361ab00db`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-min-label-initial-round-07-union/container/artifacts/engine/plan-initial-adjacency.txt`: 3081 bytes, SHA-256 `330f70beb58b1c7911c874a7411a16b237bcd479bc4b4956a8533e48e8b11b11`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-min-label-initial-round-07-union/container/artifacts/engine/plan-initial-labels.txt`: 1473 bytes, SHA-256 `6ec59b65152636c866a3c5223d0eb0fb6d171934719abc930403d74d9505acb4`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-min-label-initial-round-07-union/container/artifacts/engine/plan-shape-result.txt`: 4892 bytes, SHA-256 `1c0fd003fef8fbe422baf7dd9cb05dac1af2054e18edd20e1e874c5442783a73`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-min-label-initial-round-08-array-explode/container/artifacts/engine/plan-initial-adjacency.txt`: 3177 bytes, SHA-256 `7f199ae7c6ce2d369deb62bddd9afd8e95fa7093a5c4eee763692a91007cc980`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-min-label-initial-round-08-array-explode/container/artifacts/engine/plan-initial-labels.txt`: 1519 bytes, SHA-256 `b3bb5a76467538a4980b16959cbaf583bbb16887c73c811566a613a5e6fd9c33`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-min-label-initial-round-08-array-explode/container/artifacts/engine/plan-shape-result.txt`: 3858 bytes, SHA-256 `cb020ef44de74d97b746b69b0d9ecf2f32cbb33b724fcc716694be62c5bea03f`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-min-label-initial-round-09-array-explode/container/artifacts/engine/plan-initial-adjacency.txt`: 3173 bytes, SHA-256 `bcc73fd4f5366b3e00bca5b96dc18ecd0731598aa0c976ebdc7f7653e83c7b24`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-min-label-initial-round-09-array-explode/container/artifacts/engine/plan-initial-labels.txt`: 1521 bytes, SHA-256 `e718722527c16ec3b79c4030b4a5f49ecc2e942378c2db053c81b6ebd69202bd`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-min-label-initial-round-09-array-explode/container/artifacts/engine/plan-shape-result.txt`: 3868 bytes, SHA-256 `e7554091dd9a9c7570e1a54ff045e78b64f79e72ecbfce94f79fc40287711c6b`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-min-label-initial-round-10-union/container/artifacts/engine/plan-initial-adjacency.txt`: 3097 bytes, SHA-256 `9955bd387b157f720337d517c464e4c5ceea3eb38f11fe45c89c31a0ae691084`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-min-label-initial-round-10-union/container/artifacts/engine/plan-initial-labels.txt`: 1479 bytes, SHA-256 `9f1604b2466028546d38b2e9ccf832e8292669f5e6fa471b771dd53bdb473349`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-cit-patents-min-label-initial-round-10-union/container/artifacts/engine/plan-shape-result.txt`: 4910 bytes, SHA-256 `af3786e0f5edde2a0523b381afe46ea696a3b57df2d11925059ae09ea67c6bf9`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-tail01-graph500-24-representatives-01-union/container/artifacts/engine/plan-shape-result.txt`: 3575 bytes, SHA-256 `dc8c69ea2627ffbf3d14e427e5f0dded952025ce4af411d9ed9b3b7356edeb56`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-tail01-graph500-24-representatives-02-array-explode/container/artifacts/engine/plan-shape-result.txt`: 2290 bytes, SHA-256 `63b4d8e1dfe3f4185fdd7870541107f5d2171127c104ec719f40cfb0696d14bd`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-tail01-graph500-24-representatives-03-union/container/artifacts/engine/plan-shape-result.txt`: 3575 bytes, SHA-256 `fd2d0c19c8fe257b3c3dbd28aad073fa483613d0af688668386f11cf192122a0`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-tail01-graph500-24-representatives-04-array-explode/container/artifacts/engine/plan-shape-result.txt`: 2290 bytes, SHA-256 `add7bed9dcccdd7b7c74d624af05c71c2cf01524a145c72f174817ecd7c31f25`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-tail01-graph500-24-representatives-05-array-explode/container/artifacts/engine/plan-shape-result.txt`: 2290 bytes, SHA-256 `a692095feaed6536367b6a089abe8a48bf826b151c603ae4b049955686722990`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-tail01-graph500-24-representatives-06-union/container/artifacts/engine/plan-shape-result.txt`: 3575 bytes, SHA-256 `065662c7c965744c75b9c0c0ee99f43b442d681a7b86be697e63bd5a7c41b909`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-tail01-graph500-24-representatives-07-union/container/artifacts/engine/plan-shape-result.txt`: 3575 bytes, SHA-256 `bbc29fb4265933fd036f502bffb65cf5ee2698a137bec069ddbb07f18ab5f00d`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-tail01-graph500-24-representatives-08-array-explode/container/artifacts/engine/plan-shape-result.txt`: 2290 bytes, SHA-256 `a521b64e54905641a9bc287e6a6021ae097a34166f3a0b6b0339fcaedf6df678`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-tail01-graph500-24-representatives-09-array-explode/container/artifacts/engine/plan-shape-result.txt`: 2290 bytes, SHA-256 `bc1958414f34b0546f3467c032cd6bcbe5323aa635e1ee5546cd1a02a92f3b50`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.
- `archives/B8-run01/b8-tail01-graph500-24-representatives-10-union/container/artifacts/engine/plan-shape-result.txt`: 3575 bytes, SHA-256 `5b957f83c5bf71f8af07eb2e73e62df4908dacc00eb17bee813397ebfb5100a1`; explain of relation.repartition(16) immediately before staging write; excludes Parquet sink wrapper.

## Host closure provenance

Host orchestration used the unchanged frozen queue abe3842e with the explicit b8-host-embedded-absence-v2 adapter 99c53056. Configuration preparation used the unchanged generator 504c0127 through wrapper a6e8e1d4. The only archived predicate correction requires embedded absence_verified and compares separate records excluding only that field; all other archived predicates remain unchanged. The original function SHA 7dd9fefe and its copied predicate guard are rechecked from retained source. Guest algorithms, source matrix, inputs and engine timers are unchanged. Structured host_closure_provenance in report.json pins these sources, prepared configuration, complete reference closure gate and the failed continuation01/generated-queues01 receipts.

## Finalized serial tail

The original Graph500 adjacency union warmup genuinely OOMed at the unchanged 32 GiB limit. The root-reviewed serial tail used fresh IDs and changed only config output paths; algorithms, inputs, resources and engine timers are unchanged. Both real warmups must qualify before that contrast’s measured calls. Failed warmups cause explicit not_started_due_to_failed_warmup rows with no synthetic PID, oracle or timing. Failed/skipped rows never enter ratios. Raw receipts are unchanged. A declared in-memory queue projection delegates passed cells to the unchanged frozen positive metadata predicates. All 31 original outcomes, mappings, controller/authorization/closure/lock evidence remain indexed. The original OOM prevents all 60 qualification and all 60 attempted calls under the warmup policy; the protocol can finish with closed failures/skips retained. The allocation cause remains unexplained. Packaging uses a finite per-chunk metadata deadline; physical payload manifests remain on Apo and are not rehashed here.

Protocol: **completed_with_failures**; 40/60 qualified, 44/60 attempted, 16 skipped. All60 qualification and all60 attempted calls are false.

Native quota: 256 MiB configured; actual reservation and prepayment events are unobserved.

| Original planned ID | Actual fresh ID | Disposition |
| --- | --- | --- |
| b8-graph500-24-adjacency-02-array-explode | b8-tail01-graph500-24-adjacency-02-array-explode | closed_oom |
| b8-graph500-24-adjacency-03-union | b8-tail01-graph500-24-adjacency-03-union | not_started_due_to_failed_warmup |
| b8-graph500-24-adjacency-04-array-explode | b8-tail01-graph500-24-adjacency-04-array-explode | not_started_due_to_failed_warmup |
| b8-graph500-24-adjacency-05-array-explode | b8-tail01-graph500-24-adjacency-05-array-explode | not_started_due_to_failed_warmup |
| b8-graph500-24-adjacency-06-union | b8-tail01-graph500-24-adjacency-06-union | not_started_due_to_failed_warmup |
| b8-graph500-24-adjacency-07-union | b8-tail01-graph500-24-adjacency-07-union | not_started_due_to_failed_warmup |
| b8-graph500-24-adjacency-08-array-explode | b8-tail01-graph500-24-adjacency-08-array-explode | not_started_due_to_failed_warmup |
| b8-graph500-24-adjacency-09-array-explode | b8-tail01-graph500-24-adjacency-09-array-explode | not_started_due_to_failed_warmup |
| b8-graph500-24-adjacency-10-union | b8-tail01-graph500-24-adjacency-10-union | not_started_due_to_failed_warmup |
| b8-graph500-24-representatives-01-union | b8-tail01-graph500-24-representatives-01-union | passed |
| b8-graph500-24-representatives-02-array-explode | b8-tail01-graph500-24-representatives-02-array-explode | passed |
| b8-graph500-24-representatives-03-union | b8-tail01-graph500-24-representatives-03-union | passed |
| b8-graph500-24-representatives-04-array-explode | b8-tail01-graph500-24-representatives-04-array-explode | passed |
| b8-graph500-24-representatives-05-array-explode | b8-tail01-graph500-24-representatives-05-array-explode | passed |
| b8-graph500-24-representatives-06-union | b8-tail01-graph500-24-representatives-06-union | passed |
| b8-graph500-24-representatives-07-union | b8-tail01-graph500-24-representatives-07-union | passed |
| b8-graph500-24-representatives-08-array-explode | b8-tail01-graph500-24-representatives-08-array-explode | passed |
| b8-graph500-24-representatives-09-array-explode | b8-tail01-graph500-24-representatives-09-array-explode | passed |
| b8-graph500-24-representatives-10-union | b8-tail01-graph500-24-representatives-10-union | passed |
| b8-graph500-24-min-label-initial-round-01-union | b8-tail01-graph500-24-min-label-initial-round-01-union | closed_oom |
| b8-graph500-24-min-label-initial-round-02-array-explode | b8-tail01-graph500-24-min-label-initial-round-02-array-explode | closed_oom |
| b8-graph500-24-min-label-initial-round-03-union | b8-tail01-graph500-24-min-label-initial-round-03-union | not_started_due_to_failed_warmup |
| b8-graph500-24-min-label-initial-round-04-array-explode | b8-tail01-graph500-24-min-label-initial-round-04-array-explode | not_started_due_to_failed_warmup |
| b8-graph500-24-min-label-initial-round-05-array-explode | b8-tail01-graph500-24-min-label-initial-round-05-array-explode | not_started_due_to_failed_warmup |
| b8-graph500-24-min-label-initial-round-06-union | b8-tail01-graph500-24-min-label-initial-round-06-union | not_started_due_to_failed_warmup |
| b8-graph500-24-min-label-initial-round-07-union | b8-tail01-graph500-24-min-label-initial-round-07-union | not_started_due_to_failed_warmup |
| b8-graph500-24-min-label-initial-round-08-array-explode | b8-tail01-graph500-24-min-label-initial-round-08-array-explode | not_started_due_to_failed_warmup |
| b8-graph500-24-min-label-initial-round-09-array-explode | b8-tail01-graph500-24-min-label-initial-round-09-array-explode | not_started_due_to_failed_warmup |
| b8-graph500-24-min-label-initial-round-10-union | b8-tail01-graph500-24-min-label-initial-round-10-union | not_started_due_to_failed_warmup |
