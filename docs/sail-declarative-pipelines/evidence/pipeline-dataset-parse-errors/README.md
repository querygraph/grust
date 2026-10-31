# Pipeline dataset parser restrictions

Candidate7d7c3640fd780499cfa9658a4501c97d82c11f29 adds pipeline-specific normalization before either direct execution or registration lowering. It rejects bucketing, OPTIONS, STORED AS, Hive SerDe and LOCATION in Spark's fixed order, and rejects missing materialized-view queries. Ordinary table lowering remains unchanged and streaming declarations without queries still normalize.

The five original forbidden-clause declarations are CreatePipelineDatasetAsSelectParserSuiteBase.scala:89,131,145,197,212 under both inherited MV and streaming-table syntaxes. The missing-query declaration is CreateMaterializedViewAsSelectParserSuite.scala:30. The native extra no-query streaming case corresponds partially to CreateStreamingTableParserSuite.scala:31; absent collation and Spark-internal plan/privilege representation remain distinct. Grammar constraints and collation are separate open obligations.

Spark's legacy condition _LEGACY_ERROR_TEMP_0035 has no SQLSTATE. The structured error representation now documents empty state as absent, and Connect omits that metadata key. The transport regression checks this directly; no synthetic SQLSTATE is substituted. Native fixtures compare exact original message parameters and error bodies across both lowering routes and both syntaxes, plus ordinary-table and validation-order regressions. Public tests retain all11 original inputs, run on both engines.

Spark's query contexts are passed back as their own expected contexts in the original forbidden-clause tests; they specify no independent origin bounds. This port does not claim complete query-context/origin support. Original JVM suites remain unexecuted on Sail; these are native/public behavioral ports, with reference suites qualified separately. Initial Python lint source is retained; assertions were unchanged by the formatting correction.

## Regression: production candidate is not accepted

The exact candidate passes262 native tests, formatting and strict Clippy, and
its11 public input assertions pass on Spark. Its fresh Sail CLI gate fails with
299 passing cases and one failure: pipeline-file LOCATION rejection loses the
filename `location.sql` when the new typed parse error follows the preparation
evaluation-error route. The frozen test is unchanged. Upstream67 were not run
after this failure, and no Sail11-case feature pass is claimed. Candidate7d7 is
preserved separately and has not advanced the product branch. This is the
announced next pipeline wrapper/source-origin design boundary; do not weaken
the filename assertion or claim the native pass establishes public acceptance.

## Oracle correction after the initial failed gate

Fable reviewed the pinned processSqlFile/parsePlan/origin construction path and
identified that the filename expectation belonged only to the old Sail test.
Actual DefineSqlGraphElements probes on Spark4.2.1 and candidate7d7 confirm all11
inputs return raw ParseException, exact legacy condition/message params, absent
SQLSTATE and no filename, with no created table. Thus the file-wrapper requirement
above is withdrawn for parser errors; it would contradict the reference.

Candidate14eb7766f7efc3c39b1df0df396d13cd9551dc7d rebases the same production
change onto19b7 and corrects exactly that BDD step regex.22 stronger tests cover
both direct SQL and registration. The old299/1 result remains an observed failed
gate, not a production wrapper defect. Registration-level wrapper/origin design
remains a separate future checkpoint, with no new wrapper implementation here.

The refreshed public harness preserves every old source hash and all300 case IDs.
Its audit exposed previously omitted BDD feature/helper inputs;23 are now newly
bound, with the before/after feature hash and exact one-line change recorded.
The old harness and failed run are retained. See verify-public-harness.py.

## Accepted final qualification

14eb7766f is committed after271 native tests, formatting/strict Clippy, fresh
300 selected public plus67 upstream executions and22 diagnostic tests on each
engine pass. Independent production-only validation-bypass and empty-state
controls fail the unchanged corresponding tests0/1. Seven declarations become
partial ports, with explicit internal-plan/collation/context limits; canonical
accounting is486sites116reviewed87partial399unmapped. The inventory snapshot
records this exact increment; no full SDP or JVM-on-Sail verdict is claimed.
