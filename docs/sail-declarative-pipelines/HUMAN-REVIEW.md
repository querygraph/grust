# Human review: declarative pipelines, Extensions and performance on Sail

Build Sail Declarative Pipelines to maintain tables from declared computations,
including continuous ingestion, ordered change capture and recovery after failure.
Preserve separately packaged native Extensions and add Apache DataFusion Comet’s
Arrow-only C scalar interface. Incorporate measured performance improvements through
changes that Sail’s maintainers can understand, verify and maintain.

A pipeline declares what to compute. Sail plans and executes it; Extensions supply
additional functions or relations; recoverable publication makes table effects durable.
The full scope includes these capabilities together. Deliver them in increments,
starting with one replayable source and one fenced append target before adding keyed
changes. General streaming joins and transactions across independent flows are later
capabilities.

## Build on Sail’s execution model

Sail represents streaming work as continuous flow events: data with per-row retraction
flags, or ordered control markers. Retractions cancel earlier rows. `StreamSource`
describes a scan, while the executing task owns its running instance. Extend this
model through the existing streaming rewriter, local job runner, distributed driver,
task actors and catalog commit paths. Local execution does not need a new driver.

Follow Sail’s Rust, Arrow and DataFusion conventions. Preserve complete schemas,
worker reconstruction and existing query behavior. Use existing memory accounting
and temporary storage. Keep optional connector dependencies isolated. Where dependency
behavior must change, compare a focused upstream fix with an attributed Sail-owned
implementation; judge the maintenance cost of the actual change.

Engineering guarantees govern Spark compatibility. Deterministic change ordering,
validated output, commit-time ownership enforcement and precise configuration are
required. Spark behavior that undermines them must change explicitly. Matching an API
cannot justify weakening recovery or silently changing table behavior.

## Read the design as a sequence

Each proposal answers a different question. Shared guarantees receive a short recap
where needed; their complete arguments belong in the streaming proposal.

| Document | Question it answers |
| --- | --- |
| [Streaming](STREAMING-ON-STREAMSOURCE.md) | How do continuous events become recoverable table effects using Sail’s execution ownership? |
| [Change capture](CHANGE-CAPTURE-ON-STREAMSOURCE.md) | What ordering, validation and durable key state do replacements and deletions add? |
| [Extensions](EXTENSIONS-STREAMSOURCE-INTEGRATION.md) | How do existing packages and Comet scalar functions join that execution model safely? |

The [review agenda](REDESIGN-REVIEW-PACKET.md) identifies the decisions to discuss.
The [delivery plan](REDESIGN-PLAN.md) sizes the first milestone and explains implementation
dependencies. Detailed architecture, decision notes and evidence are references for
specific questions, not additional required chapters.

## What is demonstrated and what remains

| Area | Demonstrated locally | Still required |
| --- | --- | --- |
| [Flow-event foundation](PROJECTION-COMPOSITION-RESULTS.md) | Arrow fidelity, data-only filter and supported projection evaluation, source retention before pruning, worker reconstruction and terminal failure reporting passed component and selected public checks | Mixed-marker performance, remaining completion semantics and integrated recovery |
| [Sources and checkpoints](evidence/source-control-1/README.md) | Local execution owns live source controls; idle wakeup, ordered acknowledgements, cancellation and plan-codec reconstruction passed qualification | Replay-qualified source, distributed task controls, actual transport alignment, durable preparation and process restart |
| Targets and change capture | Existing bounded-runtime merge, receipt and staged-commit mechanisms provide implementation references | Complete fencing for each admitted target, streaming normalization and reduction, recoverable merges and migration |
| [Native Extensions](COMET-SCALAR-RESULTS.md) | Standalone adapter checks and independently compiled pinned Comet SDK probes passed | Existing host port, package and worker integration, bounded admission and any new C relation interface |
| [Configuration](TYPED-PIPELINE-CONFIG.md) | One strict typed model and optional Dhall authoring frontend are specified | Shared validation implementation and integration into durable computation identity |

Component qualification does not establish source-to-table recovery. SDK probes do
not establish package integration or compatibility with other Comet versions. The
replacement runtime is not yet ready to take over durable production pipelines.

## Build for review and maintainability

Before each implementation, explain its problem, existing Sail behavior, reasonable
alternatives, recommendation and a test that distinguishes success from failure.
Keep correctness requirements separate from mechanism choices. Resolve consequential
choices before their dependent code. Local experiments and specialist reviews provide
evidence; they do not imply human architectural agreement.

Keep patches focused enough to explain line by line. Retain reproductions that fail
without the repair, review the cumulative change against its base, and qualify the
exact revision. Preserve intentional semantic differences in tests. Existing code
remains a comparison until the replacement proves its complete contract.

Performance is part of that contract. Mixed data and marker batches still fragment
into costly small outputs, and short streaming plans retain startup overhead.
Projection-composition controls address specific deep-plan costs and destruction
failures; they do not settle those other limitations. Compare equal results and
resource use, retain slowdowns, and label shared-host measurements as diagnostics.
A material regression remains implementation work.
