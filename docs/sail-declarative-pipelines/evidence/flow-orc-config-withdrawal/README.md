# Withdrawn flow ORC configuration candidate

Recorded 2026-10-30T04:33:40.204528+00:00. Candidate `42c65ecf6426c0c3b7c01aaed03745e6f257103f` was never advanced onto
`work/spark-declarative-pipelines`. Sail remains at `71f24a87a2f2b5b38bd012388e3ce6589c7c6d46`.
The proposed implementation and tests are preserved unchanged in withdrawn.patch
and candidate-source. They are evidence of a rejected approach, not active code
or a passing compatibility test suite.

The candidate copied graph/flow SQL configuration into a private DataFusion
context, applied ORC read/write defaults and timezone there, and rebuilt persisted
dependency reads per consumer. Its new test assumed graph-level ORC mergeSchema
would change a direct-read flow's inferred schema. Real Spark4.2.1 contradicted
that assumption. We withdrew the whole unit instead of changing its assertions
to pass or activating broader semantics without an established reference.

| Experiment | Observed result | Interpretation |
| --- | --- | --- |
| Sail baseline, four candidate cases | Two passed, two failed | Raw receipt calls these expected regressions; the graph-default failure is also Spark behavior, so that label does not establish two Sail defects |
| Spark4.2.1, three generic candidate cases | Graph-default failed; flow-false and explicit read-option cases passed | Candidate's expected merged graph-default schema is invalid for this fixture |
| Spark probe: graph true, flow empty | Captured maps match; only id:int and all11 rows | Not an accidental per-flow override from the client |
| Spark probe: graph false, flow true | Captured flow true; only id:int and all11 rows | Explicit flow override also does not change this direct-read schema |
| Spark SQL-path probe | Destination id:int conflicts with execution id:int,extra:int | Rewriting the fixture as SQL does not qualify the proposed behavior |
| Spark named-path probe | Interrupted without a completed result | Inconclusive; not a pass or a Spark failure verdict |
| Candidate Rust gate | Formatting passed; strict Clippy failed | New test used Sail-forbidden DataFusion catalog_list; Rust tests and candidate public runtime were not executed |

Spark transforms direct DATA_SOURCE relations during DefineFlow and eagerly
analyzes reader.load before pipeline flow overrides are applied. Flow analysis
then installs a private SQLConf for analyzer use, while ORC schema inference also
contains direct sparkSession.sessionState.conf reads. These phase boundaries must
be checked per operation; the existence of isolated flow SQLConf does not prove
that every format observes it. Exact pinned excerpts are retained in source-audit.
This experiment does not establish ORC write-time configuration behavior.

The fourth candidate test was a Sail-only unsupported-Hive consumer guard, not an
original Spark assertion. It failed on the baseline, but its desired per-consumer
behavior depends on the same unsettled configuration contract; it is withdrawn
with the unit. No coverage count changes and no original Scala-suite execution
are claimed. Existing immutable ORC defaults and primitive writer preflight remain
committed. Public ORC writing, local runner ownership, streaming/Iggy and CDC
remain unfinished.

The harnesses contain original absolute paths and record the exact test source
hash. To reproduce, recover candidate-source into a separate checkout and adjust
the harness paths and owned ports explicitly. The probe's final interrupted case
has no recorded outcome, and the probe is diagnostic rather than an all-pass gate.
The retained input ORC files and all raw logs are hashed in provenance.json.

A read-only peer review checked candidate/source hashes and outcome boundaries.
The probe log retains a teardown NO_ACTIVE_SESSION diagnostic after interruption;
no clean-shutdown verdict is claimed for that probe.
