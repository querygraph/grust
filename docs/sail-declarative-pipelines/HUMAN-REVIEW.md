# Human review: declarative pipelines, Extensions and performance on Sail

Sail Declarative Pipelines should maintain tables from declared computations, including
continuous ingestion and updates from database change logs. After a failure, a pipeline
should resume without duplicating writes or forgetting changes. The design also preserves
separately packaged native Extensions, adds an optional scalar-function interface from
Apache DataFusion Comet, a native accelerator for Spark,
and incorporates measured performance improvements.

The local implementation connects one Delta source, a SQL projection or filter, and a
Delta append target through Sail's continuous execution model. It saves ownership,
prepared output and input progress in the target's transaction log. Real process-crash
tests demonstrate restart without duplicate writes and rejection of replaced writers.
The [usage guide](APPEND-RECOVERY-USAGE.md) explains running and restarting it; the
[implementation contract](APPEND-RECOVERY.md) explains its choices and
[qualification evidence](evidence/append-recovery-1/README.md) records the exact scope.

The [decision memo](REDESIGN-REVIEW-PACKET.md) keeps alternatives and upstream architecture
choices reviewable. This local path covers process crashes while the operating system
and filesystem survive. It does not establish maintainer agreement, production readiness,
power-loss recovery or completion of the broader redesign.

## Fit with Sail

Sail already represents streaming computation as a continuous sequence of data and
control messages. Data can include retractions, which cancel earlier rows. Control
messages mark progress and completion. `StreamSource` describes a source, and the task
executing the plan owns its running reader.

The proposal builds recovery into those components. It uses Sail's local job runner
for local execution, its driver and task actors for distributed execution, and its
existing table writers and catalog interfaces for publication. It follows Sail's
Rust, Arrow and DataFusion conventions, including worker plan reconstruction, exact
schemas, memory accounting and temporary storage. Optional connectors remain separate
dependencies.

| Capability | Addition to that foundation |
| --- | --- |
| Recoverable ingestion | Save matching input positions and intended output; resume the same work after failure |
| Safe takeover | Make the destination reject new writes from a worker whose ownership has been replaced |
| Change capture | Order changes for each record and remember deletion versions so late updates cannot restore deleted data |
| Native Extensions | Preserve package loading and resource ownership; add an explicitly selected, version-pinned Comet scalar interface |
| Configuration | Validate YAML, JSON and API input through one typed model; optionally generate that input with Dhall, a typed configuration language |

Engineering guarantees govern Spark compatibility. Useful APIs and correct behavior
remain worth preserving. Undefined change ordering, permissive configuration and weaker
recovery are not requirements merely because Spark permits them.

## A short reading sequence

The proposals build on each other. Streaming explains recovery; change capture adds
record ordering; Extensions adds native code and memory lifetime. Each supplies the
context needed for its own decisions.

| Proposal | Question |
| --- | --- |
| [Streaming](STREAMING-ON-STREAMSOURCE.md) | How does continuous execution resume safely after failure? |
| [Change capture](CHANGE-CAPTURE-ON-STREAMSOURCE.md) | How do late, repeated and conflicting updates produce a consistent table? |
| [Extensions](EXTENSIONS-STREAMSOURCE-INTEGRATION.md) | How do packaged native functions participate safely? |

The [Flink comparison](FLINK-COMPARISON.md) explains how another continuous engine
solves related problems and where its guarantees depend on connectors. The
[delivery plan](REDESIGN-PLAN.md) explains implementation dependencies. Both are optional
references; neither adds another required approval sequence.

## What the code establishes

| Area | Demonstrated locally | Still required |
| --- | --- | --- |
| Flow events and expressions | Schema fidelity, data-only evaluation, worker reconstruction and error reporting | Resolve small outputs when data and control messages alternate; distributed recovery |
| Source controls and Delta reading | Live local controls, fixed source identity, saved file lists and the next row to read in each file | Initial snapshots from Delta checkpoints; distributed source controls |
| Append recovery | Process restart, lost replies, changed batch sizes, exact row multisets and rejection of replaced writers | Managed storage, machine failures, cleanup and runtime upgrades |
| Change capture | The bounded pipeline implementation supplies merge, validation and staged-write references | Streaming change operators, durable record versions and their integration with recovery |
| Native Extensions | Standalone Comet adapter checks and probes from an independently compiled, pinned Comet producer | Package loading, worker integration and limits on native resource use |
| Configuration | The local command uses strict versioned JSON bound to its saved computation | Wider SDP declarations, YAML frontend and optional Dhall authoring |

[Decoder component evidence](evidence/delta-add-payload-1/README.md),
[expression results](PROJECTION-COMPOSITION-RESULTS.md) and
[native adapter results](COMET-SCALAR-RESULTS.md) record their exact scope and limitations.
A worker panic or loss of status reporting now produces failure rather than successful
termination, with focused regression tests. The replacement is not ready to take over
production pipelines.

## Keep implementation maintainable and reviewable

Start with one replayable source and one append target that enforces ownership.
Append tests recovery without also deciding how to store record versions. Add keyed
changes after that path works. General streaming joins and transactions across
independent flows require further design.

Before each implementation, explain the problem, existing Sail behavior, alternatives,
recommendation and a test that distinguishes success from failure. Keep patches small
enough to explain, compare the cumulative change with its base, and test the exact
revision. Local experiments and specialist reviews support human decisions; they do
not make those decisions.

Performance remains part of acceptance. Keep slowdowns in the evidence, compare equal
results and resource use, and treat shared-machine timings as diagnostics. The existing
projection improvements do not resolve small-batch fragmentation or startup overhead.
The append writer also creates a file per output batch and repeatedly reads retained log
history. These costs and cleanup limits require work before production use; the local
correctness result is not a throughput or scale guarantee.
