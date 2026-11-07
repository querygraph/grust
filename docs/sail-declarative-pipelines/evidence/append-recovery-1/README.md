# Local Delta append recovery

The local implementation reads one Delta source through Sail's continuous `StreamSource`,
applies a SQL projection or filter, and appends to a new Delta target. Restart finishes
saved output before reading beyond its recorded input position. The target orders changes
of ownership, prepared writes and publication in the same transaction log. It rejects new
writes from a replaced process and requires ordinary mutation commands to refuse the table.

The source is committed locally at `bddb46709f966238a946ec4c9b40c9f09b125b31`, with parent
`07cb40965e1c89e1477d35aa3b13be4768ce10a6`. The cumulative comparison uses upstream
`b52144955b629314a000b1fe49eeea97fa3d0c5c`. Source remains unpushed. The
[implementation contract](../../APPEND-RECOVERY.md) preceded the code; the
[usage guide](../../APPEND-RECOVERY-USAGE.md) describes the command.

## What the checks establish

| Check | Result and boundary |
| --- | --- |
| Complete recovery path | 38 real-process cases passed on the committed revision, with no case skips |
| Focused components | 84 tests passed on the exact source tree, including source positions, target ownership, resource limits and query termination |
| Rust workspace | 2,226 tests passed on the committed revision; one pre-existing type-inference test remains ignored |
| Ordinary Sail behavior | 1,835 distinct Python cases passed; 33 expected failures and four skips are retained |
| Mechanical checks | Formatting, strict workspace Clippy, strict Rust documentation and Python lint passed |
| Artifact identity | CLI, default production CLI and Python native library rebuilt from the committed source and matched the tested bytes |
| Cost experiment | All 164 invocations passed independent row and completed-retry checks |

The process cases kill or pause actual CLI processes before and after saving output and
publishing it. They add input during uncertain writes, resume with changed batch sizes,
retry completed requests, and race replacement processes. Ordinary Sail Delta reads verify
exact row multisets, preserving legitimate duplicate rows and nulls. Scalar, nested and
Variant fixtures verify values through restart. This covers the applicable Delta value
domain, not every Arrow type as a Delta output type.

Two new run identifiers cannot silently interrupt one another. A completed request can
return its result while a later request has saved its starting boundary. A conflicting
third request must leave ownership and progress unchanged. Acquisition also checks the
exact inspected log version, closing the race where the current owner saves work between
inspection and takeover.

Negative controls reproduce creator reacquisition, mutation by a refused run request, and
incorrect query termination in the earlier implementations. Separate retained failures
exposed an early Delta mutation check that occurred after file creation and a mapped-column
restoration error. The repaired cases retain their original assertions.

The Python regression selections are disjoint after reconciliation. Their 364 JVM-fixture
cases were explicitly excluded, and the pre-existing flaky concurrency module remains
skipped during collection. This is Sail execution through the PySpark 4.2.1 client, not a
new JVM Spark or Delta interoperability qualification. Lifecycle expectations were also
checked against Spark 4.2.1 source at `617618396087429b5627a86ce933bb0f5d6645cb`.

The first regression run had failures comparing query-plan text with saved expectations
because its temporary-directory layout was unsupported by the existing normalizer.
Those failures are retained. The exact parent binary reproduced them; the same assertions passed
with the existing normalizer's supported fixture layout. All 110 affected candidate cases
then passed unchanged. The evidence also retains a source-verifier failure caused by Git's
quoting of Unicode fixture paths; the verifier now reads NUL-delimited paths.

## Resource and storage limits

This path covers process crashes while the operating system and local filesystem survive.
It does not establish power-loss durability, storage rollback protection or distributed
recovery. Source files must remain immutable and available at canonical table-relative
paths. First snapshot capture requires contiguous JSON transaction history. Once captured,
a segment's saved file list permits restart after valid history pruning; current table
identity must still be discoverable.

The first writer emits one Parquet file per nonempty batch, with small row groups and no
Delta data-skipping statistics. It repeatedly inspects retained log history and accounts
for retained files. Startup also hashes the executable. These are visible costs to address
before claiming a production performance envelope.

The cost experiment compares a limit of one versus 128 files per checkpoint, using the
same input bytes, query and 8,192-row batch size. Each case processes an initial snapshot
and twelve appends, ending with 425,997 rows. Three trials alternate case order. The table
reports shared-host ratios from development builds; cache state was uncontrolled and
process startup was included. These are diagnostics of repeated bounded CLI runs.

| Trial | Append-time ratio, limit 1 / 128 | Later / earlier appends, limit 1 | Later / earlier appends, limit 128 | Peak-RSS ratio, limit 1 / 128 |
| --- | --- | --- | --- | --- |
| 1 | 1.305 | 1.461 | 1.071 | 1.001 |
| 2 | 1.334 | 1.536 | 1.077 | 1.001 |
| 3 | 1.283 | 1.446 | 1.127 | 1.000 |

Append-time and RSS ratios are medians of version-matched appends. Growth compares each
case's last three append times with its first three. Every case produced the same exact
row multiset and 65 output files. Log versions ended at 194 for limit one and 64 for limit
128. Both cases still emit one file per batch; reducing file fragmentation requires a
separate writer change. This experiment does not isolate individual startup costs or
establish optimized-release throughput, continuous steady-state performance or scale limits.

Memory reservations are accounting, not a hard process RSS limit. The default 512 MiB
retained-file budget includes published output, so continuous execution stops safely when
that budget is exhausted. A filesystem quota is needed for a hard limit across concurrent
processes. Automatic cleanup, runtime upgrades, managed targets, keyed change capture and
distributed execution remain separate work. Configuration currently accepts strict JSON;
YAML and optional Dhall authoring remain planned frontends.

The [qualification record](qualification.json) pins the source, artifacts, commands,
independent reviews, raw results and retained failures. The
[human review summary](../../HUMAN-REVIEW.md) keeps these results distinct from completion
of the wider SDP and Extensions redesign.
