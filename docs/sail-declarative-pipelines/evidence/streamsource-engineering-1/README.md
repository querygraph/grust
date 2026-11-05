# StreamSource engineering review evidence

The active technical verdict is to extend Sail’s continuous flow-event model,
repair its marker/transport/completion foundations, and make deterministic change
ordering, enforced commit fencing, bounded resources and strict configuration
requirements of every admitted durable path. The reader-facing arguments are
self-contained; this directory retains the source inventory, experiments and
review receipts that support them.

## Source boundaries

| Subject | Revision |
| --- | --- |
| Documentation baseline | `f23da50ccdf4ac1258fa1c6803aeb54df042a03e` |
| Fetched upstream Sail | `85c6cca01cd521dd778bc200c987a34edf141de1` |
| Prototype comparison base | `62251e0a27bbab0a15547562e829cad2a418f353` |
| Stacked checkpoint, append and state prototypes | `4fad33ca531ec44170d0e8d11c794df14835ff37` |
| Iggy prototype on integration ancestry | `ef5f848a758ed48067a751165d8bf9a756f2c482` |
| Bounded runtime | `99dc47788941daf28eec847527949a4cadafdbd2` |
| Spark 4.2.1 source | `617618396087429b5627a86ce933bb0f5d6645cb` |

P1 and P2 are subsets of the stacked P4 worktree. Its changes were inspected
against the older upstream base. The Iggy source was inspected on its integration
ancestry, without treating every branch change as part of that source. Existing
source worktrees were left clean. The current upstream was inspected in a detached
worktree, and executable probes used a separate isolated directory and target.

The foundation inventory covers complete StreamSource, event, logical/physical
streaming and native source modules, plus relevant planner, codec, task, transport,
query lifecycle, documentation and test paths. Larger integration files were
reviewed in their relevant sections. This is not a whole-engine dependency audit.

## Findings and evidence types

| Report | Evidence and purpose |
| --- | --- |
| [Foundation](STREAMSOURCE-FOUNDATION.md) | Source inventory and current upstream event/execution gaps |
| [Semantics](SEMANTICS-AUDIT.md) | Twenty-seven engineering decisions, pinned Spark/runtime anchors and migration requirements |
| [Fencing](FENCING-AUDIT.md) | Actual authority, enrollment, commit, worker and managed-target boundaries |
| [Performance](PERFORMANCE-AUDIT.md) | Inspected buffering, memory, snapshot and retention costs; no benchmark claims |
| [Regression](REGRESSION-AUDIT.md) | Fresh prototype/runtime inspection, source identity and provenance gaps, preserved recovery obligations |
| [Typed configuration](TYPED-CONFIG-RESEARCH.md) | Three configuration surfaces, exact parser experiment and primary Dhall/CUE/schema research |
| [Test evidence](TEST-EVIDENCE.md) | Executed marker probes, controls, retained setup failures and reproduction instructions |
| [Scope](SCOPE-AUDIT.md) | Architecture and audience checks, legacy supersession and derived identity corrections |

The marker harness compiled eight byte-identical upstream files with resolved
Arrow 59.2.0 and DataFusion 55.2.0 dependencies. It reproduced twenty-nine expected
error cases with success controls, and separately asserted schema metadata loss.
It did not run Sail SQL planning or distributed execution. Its receipt, exact
source, dependency lockfile and all setup/build logs are preserved here.

Nine focused project-parser cases used the existing PySpark 4.2.1 client and
PyYAML 6.0.3, without a Spark session. They exposed duplicate replacement, scalar
coercion, weak nested-field validation and alias priority. The research report
contains the command, exact inputs/output, versions and hashes.

The Python semantics model demonstrates source-derived Spark grouping examples,
twelve valid complete-order cases and twenty-four conflicting cases with full
fingerprint retention. It is not a storage implementation and does not prove
historical conflict detection by the proposed latest-version default. No new
Spark, broker, table-fencing or full engine suite was executed. No Dhall/CUE
integration, production repair or performance benchmark was implemented.

## Cumulative document review

`candidate-files.json` pins all twenty-two changed design/governance/reference
files; `cumulative-documents.patch` contains their changes from the documentation
baseline. Evidence and append-only coordination records are excluded from that
patch to avoid recursive artifacts; they are included in the documentation commit.
`candidate-0-*` preserves the initial cumulative candidate.

The final candidate adds a semantic clarification identified during review:
checking only reduced winners can hide an original event conflicting with the
current durable version. Preparation must compare original versions against a
pinned state snapshot and bind that snapshot to commit preconditions. The
three affected documents contain the example and required acceptance case.

Seven specialty receipts named `FINAL-*-REVIEW.md` record exact candidate hashes,
findings, resolutions and evidence limits. They qualify the documents, not the
unbuilt engine. The source audits remain distinct from these document verdicts.

Run the retained documentation validator from the repository root:

```sh
python3 docs/sail-declarative-pipelines/evidence/streamsource-engineering-1/validate_review.py --write
```

It verifies candidate hashes, patch identity/application, local links, active
document and note lengths, evidence syntax and hashes, model output, source pins
and clean worktrees. `--staged` additionally checks staged content and scope.
It does not run an engine qualification suite. The committed validation receipt
records the actual command boundary and limitations.

The exact request is saved in [REQUEST.txt](REQUEST.txt). Governing instructions
were read and distributed, and reread after compaction. Existing historical
review artifacts and execution results were preserved. Conflicting legacy
requirements are explicitly scoped as bounded-implementation references; the
new active proposals carry the engineering replacements.
