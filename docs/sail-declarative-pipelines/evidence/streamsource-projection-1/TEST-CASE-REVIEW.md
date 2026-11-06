# Streaming projection: independent test preparation

The reviewed starting source is
`06dd7e237eb5a343dcc6a6145e775f495e6c30de`, with upstream base
`b52144955b629314a000b1fe49eeea97fa3d0c5c`, in the dedicated detached worktree
`/Users/alexy/src/sail/tmp/streamsource-projection-20261105-06dd7e237`.
Read the saved request and the preceding governing AGENTS.md, LAKESAIL.md,
SHEHAB.md, WRITING-RULES.md and CLARITY.md, plus the source checkout's applicable
`.github` instructions. Read `STREAMSOURCE-PROJECTION.md` before writing tests.

This role prepared tests and performed targeted Rust formatting. No build or
test execution was performed by this role. The integration owner coordinates
compilation, failing controls and final qualification. The files below are now
frozen pending that work and the final source-review pin.

## Tests prepared

| File | Named tests | Observable contract |
| --- | ---: | --- |
| `projection_tests.rs` | 6 | Strict casts skip every marker kind; sliced control order and retractions survive; earlier data and markers precede real errors; marker-only invocation count is zero; data-only invocation stays per batch; aliases, repeated columns, literals and projected metadata remain correct; zero payload columns retain rows; exhausted input is released |
| `projection_types_tests.rs` | 1 | Nonempty identity data around a marker preserve every Arrow type family, all dictionary key widths, all run-end widths, nested fields and metadata, for nullable and nonnullable output fields |
| `projection_async_tests.rs` | 6 | Explicitly gated futures preserve marker ordering, propagate later failures and drop on cancellation; positive ideal batch sizes stay within data runs; empty/marker-only inputs do not invoke; zero ideal size is refused before execution |
| `test_projection.py` | 4 | Public bounded-branch marker counterexample, rate projection and metadata, zero-column cardinality, real-data failure, ordinary batch control |

Counts are thirteen Rust tests and four Python tests. Several named tests contain
multiple cases; case counts must not be reported as independently executed tests.
The generic type matrix covers type families and selected parameters, not every
possible Arrow representation or arbitrary invalid schema. It uses already
qualified typed placeholder arrays to construct valid nonempty input. Exact
datatype, schema, control columns and selected data slices are the assertions;
marker payload values are intentionally unspecified.

The retention fixture consumes its input batch instead of retaining earlier
batches inside a memory source. Its weak reference therefore measures projection
ownership. Async tests use oneshot gates and invocation/drop counters, without
deadline races or sleeps. They prove local future destruction when executed,
not cancellation of remote effects. They exercise supported array results;
the pinned async helper's scalar-result and empty ideal-batch limitations remain
outside the admitted scope in the design.

## Controls and integration evidence required

The smallest synchronous counterexample is valid string data, a marker with an
empty-string payload, and later invalid string data. Projection must expose the
earlier data and marker before the real cast error and must not expose the later
end marker. Replacing the operator with ordinary projection should fail on the
marker placeholder or the marker-invocation counter. Restoring ordinary async
execution should fail marker isolation; an ordering-only repair must still face
the gated-future and failure-order tests.

Native rate produces only data. The public counterexample therefore supplies an
explicitly nonnullable string local relation, casts it before union, and unions
it with a bounded rate branch. The bounded adapter supplies EndOfData with an
empty-string placeholder. Casting after nullable union coercion could conceal the
defect, and converting a numeric marker to a string first could turn its zero
placeholder into a valid string. The prepared test avoids both. It prints the
extended plan; retain that plan and an unchanged-source failing control before
claiming the public path reproduces the defect. This is currently a source-based
expectation, not an executed result.

The integration owner separately owns real logical rewrite/optimizer tests,
conservative constant properties, expression traversal and child replacement,
and executable worker-codec round trips. A Jev async codec round trip can establish
that the supported function survives reconstruction; it does not by itself prove
remote invocation. Keep that distinction alongside the independently controlled
async operator tests. Public Python checks must run against the freshly built
server. Ordinary batch controls must remain passing.

Final cumulative source review, exact source and patch pins, controls, actual
counts and immutable qualification are pending. Nothing here establishes
distributed checkpoint alignment, replay safety, volatile retraction semantics,
durable recovery or a production performance envelope.

## Public fixture correction before defect qualification

Inspected the first baseline run: four failures were recorded. Three occurred in
PySpark `createDataFrame` configuration lookup before projection execution. The
fourth returned a rate projection starting with input value 1 rather than 0.
These failures are not four marker-isolation reproductions. The retained v1 test
file is `review-logs/projection-public-v1.py`, SHA-256
`ca686a1cde16703315464c6e1ed34fbadcd17b4a434b130f2b034718733ca382`.
The original failure log SHA-256 is
`27414b1870ab8bee9673790ce627c9852e9ce61ec7f85f14b0bc5817710055bf`.

Read Spark 4.2.1 at local source commit
`617618396087429b5627a86ce933bb0f5d6645cb`: `SQLConf.scala` defines the four
local-relation limits at lines 6865–6921, while `SqlApiConfHelper.scala` names the
chunk keys. The installed client's `connect/session.py` retrieves these in one
batch even for tiny inline relations. The test fixture now supplies only missing
values from those defaults: relation size 3 GiB, chunk rows 10000, chunk bytes
16 MiB and batch-of-chunks bytes 1 GiB. Each affected test restores absence by
unsetting only the values it supplied. It does not alter product configuration,
change pre-existing values or enable an assertion bypass.

Sail's `SparkRuntimeConfig` source falls back to 3.5 defaults when it cannot
identify its PySpark version. This explains why fixture isolation is appropriate,
but it is not an executed diagnosis of the particular baseline server. The
configured rerun must still establish that each query reaches projection.

The tentative explanation that rate timing permits a nonzero first value is not
supported by the inspected source: `BatchGenerator::try_new` initializes offset
0 and `generate` increments it after producing values. The exact expected start
remains 0. The first-row discrepancy remains unexplained pending the integration
owner's isolated fresh-server control; its assertion has not been weakened.

Prepared Python v2 SHA-256:
`308e2cc82564e50072537f4efd552df7bf1391644c13ebb436cb6fddf13e680e`.
No build or test execution was performed by this role for this correction.


## Public fixture correction after embedded-version control

Reread the saved request and applicable repository and Sail governance after
compaction. The integration owner reports that adding the product virtual
environment's site-packages to the server's embedded Python path made
`SparkSession.version` return 4.2.1 and allowed `createDataFrame` to reach the
projection path. This executed environment control supersedes the earlier
unconfirmed fallback diagnosis. Removed the temporary configuration fixture and
its three use marks; no product configuration workaround remains in the test.
The integration owner reports two passing and two failing tests in the corrected
environment baseline. The remaining strict-cast and invalid-data failures reach
qualified-field binding, before the cast. They do not yet establish the intended
marker-placeholder failure; qualification of the owner's source-adapter repair
and the final projection remains pending.

The retained rate output in the v2 run contained precisely the expected three
tuples, in a different order. The v3 baseline produced them in expected order.
The Spark correctness role verified the pinned Spark 4.2 LIMIT reference: this
query has no ORDER BY and therefore provides no deterministic global result
order. The public assertion now compares `sorted(actual)` against the unchanged
exact tuples, preserving values 0, 1 and 2, duplicate sensitivity, row count,
aliases, arithmetic and literal checks. A source comment states this boundary;
the Rust tests retain strict partition-local data and marker sequence checks.
The cause of the public ordering difference is not established; repartitioning
remains an inference. This correction does not assert a timing-dependent source
start and does not relax the expected values.

Preserved the complete diagnostic v2 file as
`review-logs/projection-public-v2.py`, SHA-256
`057433ca67a54f3c45d8c5a3ca17e18914088a560e838440ebdeced1584d76db`.
This version includes explain/output diagnostics added after the earlier
`308e2cc8` file hash. Previous files and failed-run logs remain unchanged. The
final prepared Python file SHA-256 is
`c3b712783bcd19ac2ffc21d0cf5118fa2b68c5c79ac2bc99ea7e67034bc0ab52`.
No builds or test executions were performed by this role for these edits.
The earlier prepared-test counts are historical; the owner has since added
async and logical-schema cases, with final counts and source review awaiting
the frozen candidate and execution receipts.


## Frozen cumulative review

Reviewed candidate tree `52cbe5f4281bf74b9d54615504ce7eb9e062f80d`, based on
`06dd7e237eb5a343dcc6a6145e775f495e6c30de`, against upstream
`b52144955b629314a000b1fe49eeea97fa3d0c5c`. Independently regenerated the binary
Git diffs and verified their SHA-256 values:

- Increment: `5fa79cdd5f911e5449ffb64b0991ef7a21d3d3101e2311576cddb0f143022ecc`.
- Cumulative: `70390f447d0b7425a49cc8cbec2649ec1a3a11a5f2cb5d5ea7a372c11dfc6b20`.

All 52 cumulative file hashes match `candidate-snapshot-final.json`; its file
inventory equals the upstream diff. The index tree matches, HEAD remains the
starting commit, and no tracked unstaged changes exist. Read the complete new
projection, logical rewrite, source-adapter repair, planner and codec changes,
all new tests and the current design. Revisited cumulative foundation and scalar
adapter interactions and their prior exact-pin reviews. All 33 inherited-only
paths remain byte-identical to the previously reviewed committed base. The saved
request was reread; the governance reread recorded above remains applicable.

The frozen increment contains 23 named Rust tests: seven synchronous operator
checks, six controlled async checks, one Arrow-family matrix, six production
planner/optimizer integration checks, two codec checks and one qualified-adapter
schema check. Four public Python tests retain their exact value and metadata
assertions. The additional synchronous empty-input counter requires zero
invocations. Session fixtures use Sail's production analyzer, logical optimizer
and physical optimizer rule sets. They execute synchronous and supported async
projections, two independent async results and the named nested-async refusal.
The reconstructed codec plan executes strict casts and a zero-payload variant;
the Jev case executes only markers and proves no service invocation is needed.
It does not establish remote-service data execution or a distributed worker run.

Inspected recorded controls: replacing marker placeholder construction with the
data projector causes all three selected strict-cast/counting/error-order tests
to fail. The restored earlier snapshot passes 19 focused tests. The later empty
synchronous-input control fails with one invocation where zero is required. The
final guard now handles empty batches before the synchronous fast path, as
verified by source inspection. The final 23-test run, public candidate run,
performance comparison and immutable qualification remain pending at this
review. These previous controls are not a final-tree execution verdict.

The corrected embedded-environment baseline receipt records server version
4.2.1 and two passing plus two qualified-binding failures. It does not reproduce
the intended public marker-cast failure independently of binding. The independent
Rust marker controls establish that defect without the binding obstacle. The
source-erasure probe separately reproduces the existing logical-optimizer
boundary: source detection can lose a source before the streaming rewrite. The
physical constant/filter test deliberately exercises the later physical phase;
it must not be represented as repairing that earlier boundary.

### Remaining test-role finding

Source inspection identifies one unexecuted overflow counterexample in nullable
marker placeholder construction. `project_markers` calls Arrow 59.2
`new_null_array`; `arrow-data/src/data.rs` converts a RunEndEncoded Int16 length
with `expect("run overflow")`. A valid marker-only input with 32768 adjacent
markers and a declared nullable Int16 run-end result can therefore panic while
constructing its output, without evaluating the user expression. The existing
Arrow-family matrix has one marker per run and does not cover this limit.

The minimal discriminating case is a typed counting expression whose declared
output is nullable RunEndEncoded with Int16 run ends, a valid control-only batch
of 32768 markers, and an assertion that expression calls remain zero and the
stream returns a checked capacity error rather than panicking. A fitting length
32767 is the positive control. Because the type cannot represent the longer
output as one array, graceful refusal is sufficient unless the design chooses
marker-run splitting. No reproduction was executed by this role; the finding
was sent to the implementation and research owners before a final no-must-fix
verdict. Nested fixed-size children using the same Arrow constructor deserve the
same domain assessment, rather than an unqualified exhaustive-type claim.

Apart from this pending finding, no assertion weakening or missing in-scope
counterexample was identified. Array coverage remains all type families with
selected parameters, not all lengths, nesting combinations or arbitrary producer
behavior. Local future destruction is not external effect cancellation. None of
this review establishes replay semantics, checkpoint alignment, durable recovery,
package admission or a production performance envelope. No source changes,
builds or tests were performed during this review.


## Prepared run-end capacity regressions

Added four named tests in `projection_types_tests.rs` for the finding above:
direct nullable RunEndEncoded Int16 output; nullable FixedSizeList output with
size one; nullable Struct output; and nullable dense/sparse Union output with
nonzero type ID 3. The nested shapes cover both nullable and nonnullable child
fields. Each of the nine shapes has a fitting 32767-row control followed by a
32768-row checked-error assertion. The input contains only valid control columns;
its expression declares the result type and fails if invoked. Both outcomes
require zero expression calls. Fitting output retains exact types, full Arrow
validity, control columns and row counts. The run values field is nullable so
Arrow's old all-null positive construction remains valid and cannot fail first
for an unrelated child-nullability condition.

Prepared test-file SHA-256:
`c2954bdff68e78e4d13be689851773fa903a5d32b59da599e3a69b16f5466de9`.
Only the assigned test file was edited, followed by targeted rustfmt. No build
or execution was performed. The owner will execute the old-constructor control
before repairing the subject; no failing or passing result is claimed here.
The proposed all-placeholder traversal also needs recursive handling of nullable
children, because the existing helper delegates those to the same Arrow null
constructor. The previous frozen pin is historical after this test addition.


## Capacity fixture applicability correction

The owner executed the first four boundary tests against the unchanged subject.
All failed with `oversized run-end output was accepted`, not with an Arrow panic.
These results do not reproduce the reported constructor failure. The cheapest
source check established that DataFusion 55.2 `DataSourceExec::execute` wraps its
source in `BatchSplitStream` using the session batch size. The helper's default
8192 split every 32768-row fixture before it reached projection.

Corrected only the fixture: construct the node locally with a task context whose
session batch size equals the requested row count. First execute the identical
source plan and assert that exactly one batch is delivered, equal to the entire
input, then execute projection with that same context. The named capacity-error
assertion and zero-invocation assertion remain unchanged. The amended test-file
SHA-256 is
`c30be8094f9508c5b90813922eae7b7f0facaa2dbfbe0d1a416b34aa134e6e4f`.
The old failures remain retained. The constructor panic remains source-inferred
until the corrected fixture runs. No builds or tests were run by this role.


## Prepared checked-null utility regressions

The owner selected an owned, checked version of Arrow 59.2's null layout after a
valid dictionary counterexample rejected replacing every null with a nonnull
placeholder. A null Dictionary Int8 with FixedSizeList of nullable Int16 run-end
values and list size 32768 needs zero dictionary values. Materializing one dummy
value instead expands an unneeded oversized child. This distinction changes the
required representation, not merely an error message.

Prepared six named tests in the new `array/null_tests.rs`, SHA-256
`fa46df4ac06b09686a5a9b94b671719c758edac89bb03692b5c21600067eba91`:
shared type-family fixtures at lengths 0, 1 and 10; all run-end index widths at
zero, one, maximum and overflow lengths; nested fixed-size-list, struct and union
run-end limits; the valid empty-dictionary-value counterexample; empty nested
dictionary/run/list representations; and checked byte, offset, child-count,
dense-union-index and allocation-layout capacities. Exact type equality includes
nested names, nullability and metadata. Full Arrow validity is required.

The null oracle checks actual selected union child slots rather than Arrow's
known faulty logical-null helper. Run-end maximum-length cases inspect their
single physical null value and do not allocate a logical-length bitmap. Source
inspection of the owner's current constructor confirms the deliberately huge
arithmetic-capacity cases reject before their first buffer allocation. These
checks do not promise recovery from memory exhaustion for representable sizes.
The valid Arrow datatype precondition remains in force; malformed-type expansion
is outside this test set. Only the new assigned file was written and formatted;
no builds or tests were executed by this role. The owner's revised design and
final snapshot will receive a separate cumulative review.


## Final cumulative review and finding closure

**Verdict: no outstanding must-fix source or test finding within this role's
specialty.** This verdict applies to staged tree
`b67d1a9416d22241ab0359e2ef96dcdf3c678757`, based on
`06dd7e237eb5a343dcc6a6145e775f495e6c30de`, with upstream base
`b52144955b629314a000b1fe49eeea97fa3d0c5c`. It supersedes the pending source
finding on the earlier `52cbe5f4` tree; it is not an immutable-gate verdict.

Independently verified all 54 cumulative file hashes, both complete changed-path
inventories, the index tree, unchanged starting HEAD and absence of unstaged
tracked changes. Regenerated binary Git diffs match:

- Increment, 26 paths:
  `0a556ee174bbd47da7148e8ae8f999707482b8078b6fcabed553882fa015bea3`.
- Cumulative, 54 paths:
  `c34dcc56ba6d8f7260e7d6eb0997a7dd016fd07de6e79d5a2424da574d6cf1bf`.

Reviewed every changed area since the preceding cumulative review and its
interactions with the already-reviewed projection, planner, codec, foundation
and scalar adapter. The 28 inherited-only files remain byte-identical to the
committed base. The saved request was reread, and the previously reread full
repository and Sail governance remains applicable. No source edits or builds
were performed during this final review.

The final null constructor retains Arrow's null layouts, including empty values
for null dictionaries, and replaces unchecked sizing/conversion/building with
fallible operations. Nullable children remain nullable representations rather
than being populated with unnecessary dummy values. The nonnull helper now uses
that constructor for nullable children and avoids creating a value for an empty
dictionary. Both marker encoding and projection use the same checked null path;
empty projection data also avoids the unchecked empty-array constructor without
invoking expressions.

Verified the ownership artifacts against the pinned Arrow 59.2 source and the
final Sail method: original source hash, extracted method hash, exact initial
copy, final method and source hashes, and comparison patch all match. The
comparison SHA-256 is
`806c40919188abb6ce157601049835c5eec1d496969c832ad7f53eecf39171f6`.
The changes are checked arithmetic and allocation-layout capacity, fallible
index conversions, recursive error propagation and checked Arrow builders.
The constructor still requires a valid Arrow datatype and does not promise
recovery from allocation exhaustion for representable sizes.

Inspected the executed controls and repaired results:

- The first four oversized-input failures remain fixture nonapplicability:
  default source splitting concealed the boundary. They are not panic evidence.
- With the corrected one-batch precondition, all four projection cases panic
  with Arrow's `run overflow`. The same control run records fixed-size child
  multiplication overflow. A separate empty-dictionary control also panics on
  run overflow. These are six distinct failing panic controls.
- The attempted all-nonnull representation fails the valid nullable-dictionary
  encoder case with a named capacity error. This separate rejected-design
  counterexample is not counted as an additional panic.
- `owned-null-tests.log` records 334 affected tests passing, zero skipped,
  including all four corrected projection boundaries, all six new null utility
  tests, the empty-dictionary and child-sizing cases, and the encoder regression.
  The log SHA-256 is
  `b6eb7154cb65cef8f83650a950bbc79301b5bdbb3bc280edafc1e1cee174f0dc`.

These results close the nullable run-end overflow, nested-null overflow,
fixed-size child sizing and empty-dictionary findings without weakening their
assertions. The increment adds 36 named Rust tests; 334 is the affected-suite
count, not the number of new tests. Type-family coverage and selected boundary
shapes remain distinct from exhaustive coverage of all Arrow parameterizations.
Maximal run-end tests inspect physical children and do not expand logical null
bitmaps. The union null oracle follows selected type IDs and offsets rather than
the known faulty Arrow logical-null helper.

The public receipt records four tests passing against the newly built
`owned-null-sail` binary, with the server version probe returning 4.2.1. The final
Python test file removes explain/print diagnostics and uses
`table(...).select(...).limit(...)` for the same bounded rate relation. Exact
expected values, duplicate sensitivity, row counts, aliases, metadata and named
real-data errors remain asserted. The ordinary batch control now also compares
its exact row multiset, consistent with its lack of ORDER BY; strict
partition-local event sequence remains checked in Rust. No timing-dependent
source-start interpretation is introduced. The affected Clippy log records
successful completion.

Full immutable qualification remains pending and must name its eventual commit
and tree. The earlier source-erasure limitation remains explicitly reproduced
and unresolved by this increment. Supported async array execution, local future
destruction and codec reconstruction do not establish remote-service cancellation,
worker-network execution, volatile replay semantics, barrier alignment, durable
recovery, package admission or a production performance envelope.


## Prepared observability regressions

The integration owner identified an additional existing-projection contract:
standard physical output metrics and expression-evaluation telemetry must survive
replacement by the streaming node. The earlier final pin is historical after
this increment. Prepared one direct operator test and one telemetry-emitter test;
no operator, dispatch or dependency code was edited by this role.

`projection_metrics_tests.rs` executes a strict cast over two data rows, one
marker and a final data row. It requires four encoded output rows, three output
batches, the exact sum of DataFusion's standard per-batch output memory sizes,
and a registered elapsed-compute metric. All baseline metrics must identify
partition zero. The test intentionally counts marker rows as physical output.
It requires timing presence without assuming a positive or exact duration.
File SHA-256:
`47d4053b4e2e8f35994c19f24bca635b160111266b7a56d07c2b542787ea2d21`.

The new streaming test in telemetry `execution/metrics/projection.rs` follows
`MetricEmitterTester`, executes mixed data and marker input and requires the
standard baseline exports plus `execution_expression_evaluation_time`. The
existing ordinary projection test remains unchanged. File SHA-256:
`5b8184aeda205b8abe931e27e1432d7467cd02a68388775596af789ea38d2dea`.
The owner will run failing controls before repairing baseline collection and
streaming-node dispatch. These tests have only been written and formatted;
no build or execution result is claimed by this role.


The owner reports both initial metrics controls failed: direct output rows were
absent rather than four, and telemetry lacked the required baseline/expression
exports. A further lifecycle test now guards against an early end timestamp
caused by dropping per-run owning copies of DataFusion's `BaselineMetrics`.
Source inspection confirms those copies share the end timestamp and their drop
records completion.

The new test requires one partition end timestamp, unset before execution polling
and after the first output while later input remains. It separately exercises
EOF, a later cast failure and explicit stream cancellation. Terminal timestamp
presence and exact successfully emitted row counts are checked; timestamps are
never compared against clock thresholds. The metric test-file SHA-256 is now
`8b2a70aa24fd644abaa7ee0fa2c04748fe4474dc3fbd21cc7ce904d6bd98b2bc`.
No builds or tests were run by this role. Execution receipts and the revised
source pin remain to be independently reviewed.


## Metrics cumulative review at tree 5a8f4f67

**Source/test verdict: no outstanding must-fix finding in this role's specialty
for tree `5a8f4f67535644e0cb8e4eb52389cfb4395bc3d9`. Overall readiness remains
pending because performance review identified a meaningful data-only slowdown;
the owner is preparing a further revision.** This verdict covers this exact tree
only, not that upcoming change or the eventual immutable gate.

The parent remains `06dd7e237eb5a343dcc6a6145e775f495e6c30de`; upstream remains
`b52144955b629314a000b1fe49eeea97fa3d0c5c`. Before subsequent edits began,
verified all 58 file hashes, the complete 31-path increment inventory, the full
58-path upstream inventory, unchanged HEAD, index tree and no unstaged changes.
Regenerated binary diffs match increment
`e0ed57aa267daafbc6c4517a2712c4b1e9cbc050bf544bc62e4f7a1e9e4200f5`
and cumulative
`450642c939973266f80b2e7bcb52fe60dad7bc0f69fac5d733b9e18f34c77023`.
Seven paths differ from the previously reviewed `b67d1a94` tree: projection,
its metrics tests, telemetry dependency/dispatch/tests, lockfile and a Rustdoc
link correction. Reviewed every delta and the complete operator in context;
all preceding cumulative test and source findings remain closed. The saved
request was reread and the prior full governance reread remains applicable.

One `BaselineMetrics` owner now lives in the stream state. Each emitted batch
records output exactly once, including markers. EOF, errors and cancellation
release that owner and finish its end timestamp; no per-run owning clone can
finish it early. The lifecycle test checks timestamp absence before polling and
between outputs, then presence at each terminal path, with exact successful-row
counts and no timing thresholds. Baseline row, batch and byte assertions remain
unchanged. Replacing `sum_by_name` with a `MetricSet::sum` predicate selects the
standard metric variants correctly; it does not loosen the expected values.

Source inspection confirms input polling and async suspension are outside the
compute timer. Active boundary scanning, synchronous projection, placeholder
construction, each async future poll, array conversion and final projection are
timed. Tests require timing presence rather than an exact duration; they do not
independently measure excluded suspension time. The typed telemetry dispatch
selects the existing projection exporter for the new node, with ordinary batch
projection dispatch preserved.

Inspected the original two-test control: missing output rows and missing
baseline/expression exports both fail. The separate dispatcher-only control,
with baseline metrics repaired, fails solely on missing expression-evaluation
telemetry. `metrics-tests-v2.log` then records 347 affected tests passing across
six binaries, zero skipped, including both new direct metrics tests, the new
streaming exporter test and the unchanged ordinary projection exporter test.
Its SHA-256 is
`4d47b30d876d7f03296dd21c3adc866776c6d71d4063dd33e380b297eb823441`.
The increment contains 39 new named Rust tests; 347 is the affected-suite count.
The affected Clippy log also records successful completion.

The performance receipt names this exact tree and successful optimized probe
execution, but successful probe execution does not establish acceptable speed.
The owner's reported slowdown remains unresolved here. Earlier four-public-test
success applies to the preceding runtime build; the final immutable build and
public suite must qualify the revised source. No builds, tests or source edits
were performed by this role during this review. Distributed recovery, remote
service effects, unsupported async result shapes and exhaustive Arrow nesting
remain outside the claims established by these tests.


## Prepared direct-polling input regression

After the owner completed the in-flight benchmark, added one focused synchronous
input test to `projection_metrics_tests.rs`. A channel-backed physical source and
counting waker establish an initial Pending result, a wake caused by input
arrival and the exact projected data result. The source then supplies an error
followed by unread buffered data. The test requires the original input error
once, immediate receiver and buffered-payload release, a terminal timestamp,
repeated Ready(None) results and exactly one successfully emitted row. It uses
no sleeps, deadlines or scheduler timing assumptions.

Existing metrics and EOF/error/drop assertions remain unchanged. New file
SHA-256:
`584e1712fe5803a519a301241bc34a3c57eb3c1509adf8e6b764bfcbc6926756`.
Only the assigned test file was edited and formatted. No builds or executions
were performed by this role; qualification and the next frozen pin remain with
the integration owner. The prior tree-specific verdict does not automatically
cover the direct-polling implementation.


## Final v7 cumulative verdict

**No outstanding must-fix source or test finding within this role's specialty
for tree `bb8699fdfbc4ca88fa6c0e816e189af80e560efd`.** The parent remains
`06dd7e237eb5a343dcc6a6145e775f495e6c30de` and upstream base remains
`b52144955b629314a000b1fe49eeea97fa3d0c5c`. Independently verified all 58 file
hashes, the complete 31-path increment and 58-path cumulative inventories,
matching index tree, unchanged HEAD and no unstaged source changes. Regenerated
binary diff hashes match:

- Increment: `9414d2b00491eedfd76e52e212459f92735963e46a6eb0d3c9f79b444e4693a2`.
- Cumulative: `7f2cf1d64419f8968e311f04b4b132bed8ee05e5e94be995dcf083b10dd9f8aa`.

Only projection and its metrics test file differ from the preceding reviewed
`5a8f4f67` tree. Reviewed both complete changes in their cumulative context;
the other 56 files remain identical to that reviewed tree. The saved request was
reread and the previously reread governance remains applicable.

The direct synchronous polling path retains state on Pending, forwards the
input waker, counts each successful output once and clears state on input error,
projection error or EOF. Its subsequent polls return None. Drop releases any
remaining state. It shares boundary extraction and projection helpers with the
async path, preserving empty-input isolation, marker sequencing, metadata and
retractions. Input polling stays outside the active-compute timer. Synchronous
work uses one timer scope; async invocation still times individual polls and
excludes suspension. The single baseline owner remains attached to state.

The new channel/waker test passed with its exact assertions intact: Pending,
wakeup, projected value 7, original upstream error once, immediate unread-payload
and receiver release, terminal timestamp, repeated None and output row count
one. `cost-tests-v7.log` records all 53 physical-plan and telemetry tests passing,
zero skipped, including prior marker, async, capacity, metric and lifecycle
checks. Log SHA-256:
`607b87bf64a36f386466a2ad74904e0f041586c55a04f41e56c370d1b3ce3f8d`.
The earlier 347-test result and public-test receipt retain their earlier source
scope; they are not relabelled as v7-wide qualification. All earlier failed
controls, fixture nonapplicability and rejected-representation evidence remain
retained with the distinctions recorded above.

Reviewed the v7 optimized probe's assertion path and receipt. It checks exact
ordered records against an independently computed expected sequence for ordinary,
previous and candidate projections in all eight cells before timing. Timed
samples retain exact row-count checks and consume outputs. All cells completed;
no-marker median ratios are approximately 1.0303 and 0.9580. Mixed-marker costs
remain material and disclosed. These are shared-host diagnostic ratios for one
synchronous expression, not a production performance envelope or evidence that
arbitrary expressions are safe under ordinary projection.

The full immutable gate is pending. This review authorizes no broader execution
claim, and does not establish distributed alignment, durable recovery, remote
service cancellation or unsupported async shapes. No builds, tests, source
edits or remote actions were performed by this role during final review.
