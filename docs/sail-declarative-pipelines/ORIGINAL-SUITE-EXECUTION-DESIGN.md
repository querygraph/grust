# Original SDP suite execution and Sail conformance

This is the user-notified Astra design checkpoint from CF-0455. The objective
remains all Spark4.2.1 SDP behavior, with batch before streaming/Iggy and CDC.
Selected native ports or reference passes do not complete that objective.

Spark source pin: `617618396087429b5627a86ce933bb0f5d6645cb`.
Sail source remains807d66b15; its product/runtime code matches604a91f8d.
No production Sail, catalog, streaming or CDC effect boundary changes here.

## What can actually execute

| Route | Execution and truthful verdict | Current state |
| --- | --- | --- |
| Original Python modules | Unmodified upstream test modules run against Sail's Connect endpoint; retain every loaded execution | Existing run.py loads all7 test modules,67 executions/63 unique IDs, passed on qualified604 |
| Client-facing Scala test bodies | Original bodies on a declared replacement fixture base targeting Sail; record every replaced helper/line | Not implemented; direct endpoint replacement alone is insufficient |
| Engine-internal Scala contracts | Original Spark suite supplies the reference; assertion-equivalent native Sail fixtures exercise Sail internals | 68 legacy partial ports; no whole-suite Sail verdict |

Original Scala classes importing classic SparkSession, DatasetManager,
SessionHolder or SparkConnectService cannot execute unchanged inside a Rust
engine. Their `original_scala_suite_executed_on_sail` flag remains false. Native
conformance is a separate verdict requiring all fixture/assertion obligations,
not an eventual relabeling of that flag. This respects Sail's architecture while
preserving the original test scope. No debug RPC or Spark-internal clone is added
to Sail just to satisfy a fixture's introspection API.

The same file can contain several routes. PipelinesHandlerSuite, although located
under Connect tests, calls a local static failure helper and checks cause identity
and diagnostics. It needs a native contract port, not an endpoint adapter.
PipelineEventStreamSuite bodies use client operations but the base still starts
Spark locally; classify each body after reading its complete fixture/assertions.

## Reference substrate now built

Grust [reference tool](../../scripts/sdp-scala-reference/README.md), code commit
70a634e2, uses twenty checksum-pinned Maven Central artifacts. Published SDP
sources byte-match all47 Scala files in the three owned package roots, including
HiveMaterializeTablesSuite. Published binaries/source artifacts are used; no
claim is made that we locally rebuilt the binary JARs from the Git pin.

The dependency-complete Java17/Python3.12 profile registers36 concrete Suite
classes,35 with tests,554 runtime names. There are no unresolved classes, ignored
tags or nested suites in this observed profile. Positions and tags are retained.
Registration does not execute assertions. Source positions in generic grid helpers
can point at SparkFunSuite rather than the original caller; those mappings remain
explicitly unresolved until reviewed.

The exact tool gate passed Ruff and collection, then the original Default and
Hive materialization suites:29 tests each,58 reference executions. Each suite runs
in a fresh JVM. Combining them in one JVM previously aborted at Hive initialization
with SparkEnv=null after Default passed; fresh Hive alone passed. The failed
combined profile and missing-dependency attempts remain evidence, not successes.

The installed distribution shades Connect gRPC/protobuf while published test
classes refer to unshaded packages. Registration succeeds after adding the pinned
test dependencies; full Connect server reference execution remains unqualified.
Use an appropriate unshaded reference build/profile before claiming those suites
execute. Do not rewrite assertions or redirect their Spark-local state to a
separate reference server while calling the result Sail acceptance.

## Scope is larger than the old folders

The legacy462 static declaration sites and554 owned-root runtime names are
**not a complete goal denominator**. A whole-repository source scan and inheritance
review found [additional obligations](spark-4.2.1-scope-expansion.json):

- Four parser files: shared CreatePipelineDatasetAsSelectParserSuiteBase and
  three concrete MV/ST parser suites. The shared14 declarations execute under
  two syntax variants; MV adds one declaration and plain ST adds another.
- DDLSuite: direct execution of CREATE MV and CREATE ST must reject, two sites.
- SessionHolder/SessionManager suites: pipeline execution cache and cleanup on
  session close, one site each.

That is20 identified additional declarations, not yet reconciled into the canonical
inventory or expanded at runtime. They are a completion blocker. Do not count
unrelated DDLSuite or session tests as SDP merely because they share a file.
The HQL materialized-view hit in HiveClientSuite is a separate Hive table-type
feature; its reviewed exclusion reason is retained in the expansion manifest.
Continue following inheritance and searching relevant symbols rather than assuming
a keyword scan proves no further obligations. The parser base itself was found
through inheritance rather than literal CREATE MV/ST strings.

## Required conformance ledger

Each runtime obligation needs the following evidence before it can pass:

1. A stable execution instance: concrete suite/class, full runtime test name,
   backend/parameter profile and registration-manifest hash. Preserve repeated
   Python IDs as separate executions; do not deduplicate67 to63.
2. Source binding: exact pinned source, declaration span, inherited fixture base,
   inner loops/parameter combinations and every assertion/stage. A registered
   name alone does not expand loops inside its body.
3. Reference outcome for that profile, with failures, aborts, cancellation,
   ignores, pending and unavailable fixture states kept distinct from pass.
4. Sail route, exact product/test commit and adapter revision. For a substituted
   Scala base, list the changed fixture lines and prove catalog reads, cleanup,
   row assertions and pipeline commands all reach the same Sail session/backend.
5. Every original input and comparison: table kind, nullability, names/order,
   rows, properties, partitions, origins/diagnostics, lifecycle/events and effects.
   Define the correspondence between Spark and Sail internal representations;
   preserve the comparison's meaning, including cause identity where required.
6. A verified Sail execution covering all required stages/variants and cleanup.
   A partial loop, unsupported feature or missing assertion stays incomplete.

No Table→MV substitution, streaming→batch substitution, schema weakening,
assertion normalization, xfail/deselection or omitted reset/CDC effect can produce
a pass. Different native representations are expected; weaker observations are
not equivalent. Catalog variants remain distinct: memory success does not prove
Hive or LakeCat behavior. Generic catalog fixes belong in Sail, with LakeCat one
supported adapter.

## Build order after this checkpoint

1. Extend the reference collector and canonical inventory to the additional
   parser/lifecycle obligations. Preserve legacy IDs/evidence; add inherited
   variants and manual grid/inner-loop mappings instead of inventing a total.
2. Establish the remaining reference classpath/build profiles and run their full
   suites. Keep per-suite isolation and exact name/count checks.
3. Implement the first client-facing Scala fixture adapter as a separate test
   tool, preserving original bodies and declaring its fixture differences.
   Use a batch case first; no public materialize-only or debug endpoint is implied.
4. Reconcile native ports with full assertion/stage ledgers, then drive missing
   batch behavior from actual failing original obligations. Streaming/Iggy and
   CDC follow their existing design/ownership checkpoints.

Completion requires all discovered SDP obligations satisfied for their required
profiles, with no unreviewed scope-expansion holes and no use of reference passes
as Sail passes. The original Python, adapted-body and native-equivalence verdicts
remain separately visible. This design does not declare any of those missing
Sail obligations complete.

Fable CF-0457/0459, Grust f255c89b/c82f925d, supports the route distinction and
withdraws PipelinesHandlerSuite from the client-only examples. Fable CF-0463/Grust2388c8fe confirms the20 outside-root declarations, including
the distinct no-query ST parser test missed in its first listing. No source assignment or
streaming/CDC activation authority was transferred.
