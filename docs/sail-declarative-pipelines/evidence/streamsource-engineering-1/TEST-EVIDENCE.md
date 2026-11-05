# Executed marker probes and test coverage

## Scope and method

The probe compiled eight unchanged Sail source, build and protobuf files from
`85c6cca01cd521dd778bc200c987a34edf141de1` in an isolated Rust crate. It calls
the real event encoder, decoder and placeholder constructors, with Arrow
59.2.0 and DataFusion 55.2.0. Every dependency version matches an entry in the
reviewed Sail lockfile. DataFusion uses fewer optional features in this harness.

The copied files have source URLs, SHA256 hashes and `[CREDIT]` entries in
[marker-source-manifest.json](marker-source-manifest.json). They remained
byte-identical to the source checkout after execution. The source worktree
was unchanged. The harness lives at
`/Users/alexy/src/sail/tmp/streamsource-probes-20261105`, with its own target
directory and incremental compilation disabled.

These are executable component reproductions. They are not full Sail SQL,
optimizer, distributed execution, Spark, broker or durable-storage tests.
No production fix or general recovery protocol was implemented.

## Results and controls

| Case | Executed result | Discriminating control |
| --- | --- | --- |
| Empty data schema with three data rows | Encoding succeeds; decoding fails because the reconstructed zero-column batch has no row count | Arrow accepts the same empty schema with an explicit row count; a one-column data event round-trips |
| Empty data schema with each of four marker kinds | Encoding succeeds; every decode fails with the same missing-row-count error | Each marker round-trips with one ordinary string column |
| Nonnullable Decimal32, Decimal64, Decimal128 and Decimal256 with nondefault precision or scale | All four marker kinds fail encoding for each width, sixteen error cases | Nullable fields preserve the requested type and all markers round-trip; each width's actual default placeholder type also round-trips |
| Strict cast of a nonnullable string payload to Int32 | Each marker's empty-string placeholder fails expression evaluation | The real data value `12` succeeds |
| Strict cast predicate followed by `OR marker_present` | DataFusion's actual batch filter fails on every marker kind before the marker branch can protect it | Reversing the OR operands succeeds on these marker-only batches |
| Schema-level metadata | Encoding drops the metadata map | The input schema contains the asserted map before conversion |

The four marker kinds are latency tracker, watermark, checkpoint and end of
data. The program asserts twenty-nine expected error cases and all named
success controls. It separately asserts metadata loss. The successful process
exit means the predictions and controls held; it does not mean the reviewed
implementation passed those correctness properties.

Decimal placeholders expose these concrete mismatches:

| Requested type | Actual placeholder type |
| --- | --- |
| Decimal32 with precision 5, scale 2 | Precision 9, scale 2 |
| Decimal64 with precision 10, scale 2 | Precision 18, scale 6 |
| Decimal128 with precision 10, scale 2 | Precision 38, scale 10 |
| Decimal256 with precision 10, scale 2 | Precision 76, scale 10 |

The expression probe constructs the same `user_predicate OR marker_present`
shape used by the streaming rewriter and calls DataFusion's `batch_filter`.
It also evaluates the projection's strict cast directly. It does not execute
Sail's rewriter or a complete ProjectionExec plan. The reordered-OR control is
not a proposed general fix: projections remain exposed, and mixed batches and
arbitrary functions were not tested.

The results support three foundation corrections before durable sinks are
admitted: preserve row counts for empty schemas, preserve exact Arrow types,
and keep user expression evaluation off control markers. Schema metadata must
also survive encoding. Full Arrow type coverage, nested fields, mixed
data/marker batches, retractions, optimizer transformations and actual local
and cluster plans remain required follow-up coverage.

## Commands, failures and reproducibility

The preparation script copies pinned files unchanged and refuses to overwrite
an existing probe directory:

```sh
python3 docs/sail-declarative-pipelines/evidence/streamsource-engineering-1/prepare_marker_probe.py
```

The successful run used the probe directory as its working directory:

```sh
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=/Users/alexy/src/sail/tmp/streamsource-probes-20261105/target cargo run --locked > run-3.stdout.json 2> run-3.stderr.log
```

Two setup failures preceded execution and remain recorded. The first used
dependency versions from the workspace manifest rather than its resolved
lockfile and failed version selection. The second, after correcting those
pins, could not obtain a missing locked crate in offline mode. Neither ran
the probe. The successful command allowed retrieval of that locked dependency.
No failed runtime assertion was discarded or weakened.

[marker-run-receipt.json](marker-run-receipt.json) records exact commands,
exit statuses, compiler and protobuf tool versions, source and binary hashes,
and retained-file hashes. The raw results are
[marker-run-3.stdout.json](marker-run-3.stdout.json). The corresponding stderr
logs preserve the build's Finished line and both setup failures. The complete
probe is [marker_probe.rs](marker_probe.rs); its manifest and lockfile are
retained beside it. Copies and logs are kept without overwriting earlier runs.

## Other review claims

The semantic model in this evidence directory remains an algebra model,
not an engine execution. Independent inspection requested explicit assertions
for the combined-versus-split and equal-upsert counterexamples, and removal
of repeated permutations caused by identical events. Its owner made those
changes: the valid-input model has twelve distinct order/partition cases,
and the conflicting-input model has twenty-four. Its retained fingerprints
are unbounded; it does not prove that latest-state storage can detect conflicts
at every superseded version.

No fencing, distributed fan-in, slow-replica memory, source-bound race or
durable recovery test was executed here. Their source-review findings and
proposed checks must retain that distinction. All saved prompts and governing
instructions, including the new engineering directive, were read for this
review. Final document coverage review remains separate from these probes.
