# Human review: declarative pipelines, Extensions and performance on Sail

Sail Declarative Pipelines should maintain tables from declared computations, including
continuous ingestion and updates from database change logs. After a failure, a pipeline
should resume without duplicating writes or forgetting changes. The design also preserves
separately packaged native Extensions, adds an optional scalar-function interface from
Apache DataFusion Comet, a native accelerator for Spark,
and incorporates measured performance improvements.

The work is ready for architectural review. Individual components have been tested
locally; a complete pipeline that recovers through process restart has not been built.
Resolve the choices in the [decision memo](REDESIGN-REVIEW-PACKET.md) before further
implementation that depends on them. The memo contains the context needed to decide;
code and test records are supporting evidence.

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
| Flow events and expressions | Schema fidelity, data-only expression evaluation, worker reconstruction and reporting of returned execution errors | Resolve costly small outputs when data and control messages alternate; complete termination handling and integrated recovery |
| Source controls and Delta reading | Requests reach live local readers; Delta descriptors record table identity, schema and starting positions; sorted replay releases consumed input buffers | Distributed controls, saved file lists, a reproducible reader and process restart |
| Delta file metadata | A private decoder preserves complete known metadata and rejects malformed supported fields | Input-format checks, memory limits and integration with saved file lists |
| Targets and change capture | The existing bounded pipeline implementation supplies merge, validation and staged-write references | Destination ownership enforcement, streaming change operators and recoverable publication |
| Native Extensions | Standalone Comet adapter checks and probes from an independently compiled, pinned Comet producer | Package loading, worker integration and limits on native resource use |
| Configuration | Strict typed configuration and optional Dhall authoring are specified | Shared validation and integration with recovery |

[Source and replay evidence](evidence/delta-add-payload-1/README.md),
[expression results](PROJECTION-COMPOSITION-RESULTS.md) and
[native adapter results](COMET-SCALAR-RESULTS.md) record their exact scope and limitations.
A recorded execution error is covered; a task panic before recording its outcome remains
an open completion case. The replacement is not ready to take over production pipelines.

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
Material regressions remain work to do before the affected path is ready.
