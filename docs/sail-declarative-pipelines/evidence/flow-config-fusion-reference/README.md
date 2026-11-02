# Spark flow configuration reference and Sail baseline

This packet establishes thirteen public Connect observations on Spark4.2.1 and
compares the identical graph/query/config inputs with Sail163b2fb52. **Three match;
ten differ.** This is an uncovered parity gap, not an acceptance gate passing.
The [design](../../FLOW-CONFIGURATION-DESIGN.md) separates ordered input binding,
first semantic analysis, conflict/union processing, repeat analysis and batch
command reanalysis. No product code or ownership guarantee changed here.

| Case | Spark result | Sail result |
| --- | --- | --- |
| upstream_true | unresolved column | accepts/writes |
| upstream_false_over_consumer_true | duplicate flow SQL conf | missing attribute |
| left_true_right_false | duplicate flow SQL conf | accepts/writes |
| left_false_right_true | unresolved column | accepts/writes |
| repeated_last_true | unresolved column | accepts/writes |
| transitive_raw_conf | unresolved column | accepts/writes |
| table_boundary | writes Foo=1 | same |
| same_value_compatible | writes Foo=1 | same |
| disjoint_keys_compatible | writes foo=1 | same |
| transitive_conflict | duplicate flow SQL conf | accepts/writes |
| nested_projection_before_last_false | duplicate flow SQL conf | accepts/writes |
| scalar_subquery_last_true | duplicate flow SQL conf | accepts/writes |
| external_read_after_true | unresolved column | accepts/writes |

The historic name transitive_raw_conf is retained as an input identifier: its
result demonstrates transitive **accepted union**, not a lack of transitive fusion.
Consumer caseSensitive starts false, and remains false after every run on each
engine. Each case has its own database and graph. The native default catalog is
recorded per engine (Spark spark_catalog, Sail sail); no catalog-name equivalence
is assumed. Table format is explicitly parquet. No ORC write or withdrawn ORC
flow-default assumption is used.

`reference.py` is the common probe; `spark/observations.json` records complete
queries, settings, streamed messages and exceptions. Runtime4.2.1 jar hashes and
source617618396 are separate provenance: the installed jars are not claimed built
from the local source checkout. `source-audit.json` records source hashes/excerpts.
`sail-baseline.py` verifies immutable detached163b, a clean source tree, and the
binary hash from the prior exact300+67 CLI gate before/after the thirteen probes.
Its receipt, raw logs and written fixtures remain under `sail/`. Server exit0/no
listeners is verified; the Spark session also stops with no15002 listener.

Run `verify.py` to validate inputs, source/version/harness identities, expected
Spark outcomes, actual Sail differences, session isolation and Sail artifact
hashes/teardown. It prints the saved `comparison.json`. The packet's SHA256 manifest
covers all archived files. This proves only these cases, not all configuration
phases, arbitrary callback behavior, concurrency, full Scala suites or SDP parity.

## Retained attempts and corrections

- attempt-01: the first eight probes accessed a nonexistent event.level. Several
  event iterators aborted with AttributeError. These observations are invalid for
  parity; raw script/log/results are retained. Event text fixed in attempt-02.
- attempt-02: eight completed reference cases, including the SQL-read-order pair.
- attempt-03: thirteen completed cases adding same/disjoint settings, transitive
  conflict, nested projection and scalar subquery; Spark listener absent after stop.
- attempt-04-spark: same thirteen completed cases in the generalized engine harness.
- attempt-01-sail: hardcoded spark_catalog failed at graph creation on Sail's sail
  catalog in every case. No parity conclusion. Fixed by querying each engine's
  current catalog. The corrected final Spark/Sail runs share the exact harness.

Fable review snapshots68a11000 and2bc290f7 are retained as peer source analysis;
CF-0251/0253 record discussion and the accepted failure-order qualification.
