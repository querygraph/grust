# Test Case Generation review: source participation

## Public baseline before implementation

The public baseline confirms that moving streaming lowering earlier must preserve
foldable limits and offsets, bounded scalar subqueries, aliases, views and unions.
It also confirms that false predicates currently hide unsupported streaming
operators. These are different categories: accepted row-producing queries are
regression controls; source-erasing queries demonstrate the defect under repair.

Read the saved request, linked preceding prompts, repository AGENTS, LAKESAIL,
SHEHAB, CLARITY, WRITING-RULES and applicable Sail development/review instructions,
including rereading after compaction. Read the recorded first-principles plan
before proposing implementation tests. This role performed no source changes,
Rust builds, dependency installations or changes to the product environment.

The implementation worktree starts at
`327572240365e2507f348ee92bc009cbfc67abe9`, with cumulative upstream base
`b52144955b629314a000b1fe49eeea97fa3d0c5c`. These observations use the previously
qualified CLI, not a candidate binary:

```
/Users/alexy/src/sail/tmp/streamsource-projection-20261105-06dd7e237/review-logs/immutable-qualification/sail
SHA256 23a3ed7fe413b3bf4e31319520f10c8a0c442e346f3dce85aa80f59562273de6
```

The inspected immutable receipt names that source commit and binary digest. Both
probe runs independently checked that the binary digest stayed unchanged.
Each case started its own server, port and empty warehouse under the new worktree.
Each client had a 15-second subprocess deadline; every server was terminated after
its case. The read-only product interpreter was Python 3.12.14 with PySpark 4.2.1.
Every server reported version 4.2.1. `PYTHONDONTWRITEBYTECODE=1` was set, and the
embedded interpreter received the product site-packages directory through
`PYTHONPATH`. No previous worktree was mutated.

## Executed results

There were 26 distinct SQL cases. Version 1 recorded 18 executions and six
explain-only observations. Version 2 executed those six cases and added two scalar
subquery cases. Across the 26 executions, 21 matched their exact row multiset and
five raised the errors below. There were no row mismatches, setup failures or
timeouts. None of these observations is a JVM Spark comparison.

The fixture table `r` is the native rate source with one partition and 500 rows per
second. View `v` is `SELECT value + 1 AS n FROM r`. Rows below are multisets, with
duplicates retained. No global ordering guarantee is inferred from `collect()`.

| Case | Observed result |
| --- | --- |
| `SELECT value FROM r LIMIT 3` | `0, 1, 2` |
| Limit `CAST('3' AS INT)` | `0, 1, 2` |
| Limit `1 + 2` | `0, 1, 2` |
| Offset `CAST('2' AS INT)`, limit 2 | `2, 3` |
| Offset `1 + 1`, limit 2 | `2, 3` |
| `SELECT value, (SELECT 7) FROM r LIMIT 2` | `(0, 7), (1, 7)` |
| Predicate `value >= (SELECT 2)`, limit 2 | `2, 3` |
| Predicate `EXISTS (SELECT 1)`, limit 2 | Error: `streaming join` |
| Predicate `value IN (SELECT 1)`, limit 1 | Error: `streaming join` |
| Qualified alias and `value + 1`, limit 2 | `1, 2` |
| `SELECT n FROM v LIMIT 2` | `1, 2` |
| Rate limit 2 union all bounded values 10 and 20 | `0, 1, 10, 20` |
| Two occurrences of rate limit 2, union all | `0, 0, 1, 1` |
| Unbounded rate, false predicate, limit 0 | Empty |
| Unbounded rate, false predicate, limit 2 | Empty |
| Rate limit 2 beneath an outer false predicate | Empty |
| Visible distinct, limit 2 | Error: `streaming aggregate` |
| Distinct with false predicate, limit 2 | Empty |
| Visible row-number window, limit 2 | Error: `streaming window` |
| Row-number window with false predicate, limit 2 | Empty |
| Visible join with bounded scalar relation, limit 1 | Error: `streaming join` |
| Same join with false predicate, limit 1 | Empty |
| Predicate `EXISTS (SELECT 1 WHERE FALSE)`, limit 2 | Empty |
| Ordinary batch `SELECT (SELECT 7) LIMIT 1 + 1` | `7` |
| Scalar projection `max(x)` over values 7 and 9, rate limit 2 | `(0, 9), (1, 9)` |
| Scalar predicate `value >= max(x)` over values 1 and 2, limit 2 | `2, 3` |

The corresponding optimized logical plans replace the false-filter cases with
`EmptyRelation: rows=0`. The visible EXISTS and IN predicates become semi-joins
and fail at collection. They must not be described as previously supported
streaming paths or as successful compatibility cases.

Extended explain has a separate baseline limitation: its physical section embeds
`Physical plan error: ... stream source should be rewritten during logical
planning` even for queries whose subsequent collection succeeds. The six
`explain_ok_not_executed` records mean only that the explain API returned text.
They do not mean physical planning succeeded. The follow-up actually executed all
six cases to resolve that ambiguity. Raw records and the summary explicitly retain
the physical-error flag; no error was relabeled as a pass.

## Required regression distinctions

Preserve the accepted casts/arithmetic, bounded scalar subqueries and aggregate
scalar subqueries through the real analyzer, logical optimizer and physical
planner. A test of already constructed flow nodes would miss an early rewrite
that rejects those input forms. Preserve the batch scalar control independently.

For participation, use controlled sources to prove actual polling, every marker
kind in sequence and errors after zero output. Retain separate source occurrences
under aliases and union branches. Empty public results alone cannot establish
source participation. A positive finite consumer over a permanently false
unbounded filter may remain live after this repair; the old empty result is not
an acceptance oracle for the continuous contract. Do not use an unbounded collect
as an untimed test.

`LIMIT 0` needs a different control: no child execution or poll, exact empty schema
and rows, and prompt completion demonstrated by counters rather than a timing
threshold. It is consumer cancellation, not final checkpoint completion.

Visible unsupported distinct/window/join cases must remain named refusals. Their
false-filter counterparts must no longer bypass the selected admission contract.
EXISTS and IN cases remain explicit error observations unless implementation
deliberately admits them within the agreed scope. Verify explain uses the same
streaming lowering as execution, since the baseline currently does not.

## Retained reproductions

All paths below are relative to
`/Users/alexy/src/sail/tmp/streamsource-participation-20261105-327572240`.
Each directory contains the exact SQL corpus, generator, per-case JSON, extended
plan text, client log, server log and fresh warehouse. The scripts refuse to
overwrite a completed receipt. For a new run, copy a probe into a new sibling
directory so historical artifacts remain unchanged.

```
PYTHONDONTWRITEBYTECODE=1 /Users/alexy/src/sail-pipelines-proposal/.venv/bin/python review-logs/participation-baseline-v1/probe.py
PYTHONDONTWRITEBYTECODE=1 /Users/alexy/src/sail-pipelines-proposal/.venv/bin/python review-logs/participation-baseline-v2/probe.py
```

| Artifact | SHA256 |
| --- | --- |
| `review-logs/participation-baseline-v1/probe.py` | `b3f380d34d418ec0100b968af486ff6106cd645acd1aebe4c0f1e37937b8a0e7` |
| `review-logs/participation-baseline-v1/receipt.json` | `d246aed986c8aac457ed7fb8ef499f638bc0cdf5bb4ef254043d6d9a57b0b7c0` |
| `review-logs/participation-baseline-v2/probe.py` | `1d0f406d21e3a514f770fc41b56ff6a13860d87278f990719affb5c7fd9258d3` |
| `review-logs/participation-baseline-v2/receipt.json` | `7d968b232a10261ec0a6803ab1c970cc4be671d249d40c9ce8d93c2486c4ea52` |
| `review-logs/participation-baseline-summary-v1.json` | `f7af6cbeabfa84ad7c9494df321db0ad86cd865bfe9e4638aecf5bffe65e5e81` |

The summary includes a hash inventory of the raw files and versions generated in
the same command as its timestamp. Candidate regression tests, candidate public
execution, worker transport, source-recovery behavior and final cumulative review
remain pending. This baseline establishes local current behavior only.

## Independent regression fixtures prepared

Read the revised first-principles plan before writing the assigned tests. The
revised design uses a mandatory shared compiler after analysis, with the actual
session optimizer context, rather than an optional registered analyzer/optimizer
rule. This role wrote only the four assigned new test files. Rustfmt and Ruff
formatted only those files; no build or test execution is claimed here.

The first revision contains eight Rust tests and 15 parametrized public cases:

- Six session tests call the real shared compiler with configured production
  analysis and logical/physical optimization. A recording source proves scans,
  execution and polling after false, null and foldable false predicates, and
  forwards latency, watermark, checkpoint and end-of-data markers in exact order.
  A separate source emits an error after those markers. Both ordinary optional
  settings and `max_passes=0` with `skip_failed_rules=true` are exercised.
- The source pushdown fixture advertises Exact or Inexact support for `value >= 3`.
  Exact returns three selected rows. Inexact returns all six rows, so losing the
  residual filter changes the expected output. It records requested projection,
  simplified predicate, materialized rows and bytes, and allocates its 4096-byte
  string payload only if requested. This discriminates actual narrow scan
  requests from filtering a wide preallocated fixture afterward.
- Other session tests execute two occurrences of the same provider beneath
  aliases and union, refuse a stream in a scalar expression and an unexpanded
  raw ViewTable, and compare ordinary batch preparation with the unchanged plan
  and original optimizer result. Reentering mandatory preparation must preserve
  an already compiled plan.
- The logical identity test checks one provider's fresh occurrences differ,
  clones and reconstruction retain identity, ordering is consistent in both
  directions, and HashSet membership agrees with equality.
- The limit test first proves positive demand executes and polls its controlled
  pending source. Zero demand with two offsets then returns fused EOF without
  opening or polling that source, retaining nullable field and schema metadata.
  It uses immediately polled futures and counters, with no clock thresholds.
- Public tests retain source/filter/limit nodes in explain, verify zero-demand
  completion and the named refusal for an unbounded collector, preserve ten
  supported baseline lowerings, and reject three unsupported shapes hidden by
  false predicates. No test collects an unbounded false filter with a positive
  row limit.

A provider that hides both its logical plan and its source protocol cannot be
identified from that absent information. The view refusal fixture uses a real
ViewTable exposing the nested source; it does not claim to recognize arbitrary
opaque undeclared providers. These tests do not establish distributed transport,
restart-stable identity or checkpoint completion.

First-revision file digests, before coordinator compilation:

| Source file | SHA256 |
| --- | --- |
| `crates/sail-session/src/streaming_participation_tests.rs` | `2b8099392418f91b7ce1d6ca2bf432ed64e62a0682041a121241ada03c73851d` |
| `crates/sail-logical-plan/src/streaming/source_wrapper_tests.rs` | `458ae8315f20efe14883ed0a122e8ef9b687a393994f2a0add563758fadf22d4` |
| `crates/sail-physical-plan/src/streaming/limit_tests.rs` | `203a293af10c3b1733f97356eed278d193cd97dbad9c817afbb53c13e260051b` |
| `python/pysail/tests/_dev/spark/streaming/test_participation.py` | `e9c346ab4cc7222ba49f936da448ea3709d6d5ad7e12d4a4215e7844953e29d0` |

Compilation, negative controls, candidate execution and final cumulative review
remain pending. Failures must distinguish fixture applicability from a subject
failure before any result is generalized.

## First execution and boundary additions

Inspected the coordinator's `review-logs/affected-tests-v1.log`: 208 tests ran,
207 passed, one failed and one was skipped. Seven of the eight new tests passed.
The failure was fixture applicability, not lost source participation: DataFusion's
high-level scan builder inlined ViewTable into an exposed logical plan. The error
output showed the correctly retained collector, filter, limit and source wrapper.
That construction did not exercise an unexpanded provider.

After the run terminated, the fixture was corrected to construct TableScan
directly and assert its provider remains ViewTable. The named-refusal assertion
is unchanged. An additional positive control executes the exposed view and checks
all four markers. The exact first fixture is retained at
`review-logs/streaming-participation-tests-first-fixture.rs`, with its original
digest `2b8099392418f91b7ce1d6ca2bf432ed64e62a0682041a121241ada03c73851d`.
It was reconstructed from the isolated edits and verified against that previously
recorded digest; the failed log remains unchanged.

The recording source now supplies an explicit row count when a requested
projection has no columns. A new positive test requires an empty requested
projection, six data rows and every marker for both empty and literal-only output.
The source must allocate zero payload bytes. This fixes fixture applicability for
zero-column scans without relaxing existing output or pushdown assertions.

Five new boundary tests in `streaming_participation_boundary_tests.rs` exercise:

- Scalar, EXISTS, IN and set-comparison subqueries, with both ANY and ALL,
  hidden inside a false Boolean branch. Both discovery and the real shared
  compiler must return the named expression-subquery refusal before pruning.
- An unknown extension above a stream. Its projection-pushdown callback must
  remain untouched before Sail's named refusal; a bounded optimizer control
  proves the same callback can actually be reached.
- Raw memory-table creation and PREPARE through Sail's public execution wrapper,
  with stream-bearing false-filter inputs. Bounded controls create/read a table
  and prepare/execute a statement, both returning the exact value seven.
- Real product resolver paths for tail counting, pivot-value inference and
  crosstab inference. Stream inputs require the operation-specific eager refusal;
  bounded controls resolve, compile and execute with the expected row counts.
- The real time-travel scalar-bound resolver before terminal source creation.
  A stream-bearing scalar bound is refused without scanning; a bounded value
  reaches the fixture data source as `versionAsOf=2`. The terminal format is a
  captured fixture named `delta`, not a Delta storage implementation. This tests
  resolver ordering and does not qualify actual time-travel storage behavior.

The revision now contains 14 new Rust tests and 15 public cases. The Python
capture fixture also has an explicit type annotation. These additions and the
corrected fixture have been formatted but not executed by this role.

| Revised source file | SHA256 |
| --- | --- |
| `crates/sail-session/src/streaming_participation_tests.rs` | `3f3df96d3133f3ece6aace9b0e6e2580ee8766e824022442c7c871c641d2100e` |
| `crates/sail-session/src/streaming_participation_boundary_tests.rs` | `24d27618b17450b2f5e4787ae754432cb242adc9134941e4c86fc07fec3527aa` |
| `python/pysail/tests/_dev/spark/streaming/test_participation.py` | `bfe60d44ffce2026ac38baa8b2c20e0a5ac459a5bd9a095e1cdc85c21973b8a7` |

The identity and zero-demand test files remain at their previously recorded
digests. Updated compilation/execution, negative controls and final cumulative
review remain pending.

## Additional fixture and optimization controls

Inspected `affected-tests-v2.log`: 214 tests ran, 211 passed, three failed and
one was skipped. The corrected raw-view test and positive zero-column test
passed. The three boundary failures were recorded separately: the raw memory-table
bounded control requested DataFusion's unsupported temporary-table mode, while
resolver controls lacked the required PlanService session extension. These did
not establish introduced source defects. The exact failed boundary fixture is
retained at `review-logs/streaming-participation-boundary-tests-v2-fixture.rs`,
digest `24d27618b17450b2f5e4787ae754432cb242adc9134941e4c86fc07fec3527aa`.

The correction registers the real PlanService using DefaultCatalogDisplay with
SparkCatalogObjectDisplay and SparkPlanFormatter, explicitly creates the default
in-memory catalog/schema, and uses supported memory-table mode. Bounded resolver
controls now run first to establish applicability before the refusal assertions.
The assertions remain unchanged. The corrected boundary file digest is
`44d21c1e36839c288a9579703514970693b9a431ea3576377063f509f22d59f5`;
its execution remains pending at this entry.

The independent performance probe demonstrated an actual work regression before
common-expression preparation was added. Inspected
`review-logs/performance/cse-before-v2.log`: three identical immutable aliases
returned identical values, but the former late compiler performed one invocation
over four rows and early lowering performed three invocations over twelve rows.
This is an executed work counter, not a timing estimate. The earlier probe's
type-coercion fixture failure remains a separate artifact.

A new independent module, `streaming_participation_optimization_tests.rs`, adds
three regression tests with the former late compiler as an executable control:

- Identical immutable expressions must retain the established one invocation
  over four rows per source occurrence. Both one and two source occurrences are
  checked, including actual scan counts and exact rows.
- Volatile expressions must retain three separate invocations over twelve rows.
- A partial immutable function rejects values at or below two. Inside a CASE
  branch selecting only larger values, both compilers must produce the exact
  conditional result; candidate calls and row evaluations cannot exceed the
  baseline. The baseline runs first so an invalid fixture cannot masquerade as
  an introduced regression.

Each test executes and inspects checkpoint and end-of-data markers. Their zero
payload placeholders are outside the counted function's domain, so accidental
marker evaluation fails rather than merely inflating a counter. Runtime counters
are reset after physical planning to distinguish execution work from preparation.
Union output is compared as an exact multiset; single-source marker order is exact.

The module digest is
`c3accb1122a859f2254eb9711c991bd532c590bcfe1fbb7452a8de79f7dff35c`.
It is formatted and frozen, with execution pending. This brings the proposed
regression set to 17 Rust tests and 15 public cases. No production code or old
test files were changed for this addition, and this role ran no build.


## Cumulative v3 source review and retained execution evidence

No outstanding must-fix test or source finding was found within this role's
specialty on tree `c1e9563dec7527ed11c2e2bf5476816229317a93`. This is a source
review, not an immutable-gate verdict. The parent is
`327572240365e2507f348ee92bc009cbfc67abe9`; the cumulative upstream base remains
`b52144955b629314a000b1fe49eeea97fa3d0c5c`.

Independently verified all 77 manifest file hashes, all 24 increment paths, the
77-path cumulative inventory, index tree, parent HEAD, saved patches against
regenerated binary diffs, and absence of unstaged tracked changes at that freeze.
The increment SHA256 is
`cddf405cb8205cfce54b14f97190b135bcd8b843f79724a8ffc90eb0b756694c`; the cumulative
SHA256 is `28c0c0b0400fc61662667d08d878ff629ca4a3b303c4637f6c3c5cbf3437c066`.
The 53 cumulative-only files are byte-identical to the reviewed parent. Their
previous foundation, C scalar, Arrow layout, projection, async, metrics, codec and
terminal-error reviews carry forward unchanged; this review also checked their
interaction with the mandatory compiler and collector schema changes. The full
participation increment and the changed existing projection tests were reviewed.
The DataFusion 55.2 ownership comparison retains the original orchestration and
error handling, with public accessors and mandatory preparation inserted in both
normal and Explain branches.

The tests distinguish mandatory semantics from optional optimization. They check
source scan and poll participation, every marker and bounded completion under
false, null and folded predicates, including disabled optional passes and skipped
optional-rule failures. Exact and inexact pushdown tests require the simplified
predicate, requested narrow projection, materialized row count, absence of wide
payload allocation, exact output values and markers. Zero-column positive scans
retain six rows. Repeated provider occurrences execute separately. Raw views,
exposed views, hidden expression subqueries and unknown extension callbacks have
applicability controls and named outcomes. Zero demand proves the child is usable
in a positive pending control before asserting no execute/poll, preserved schema
and repeated termination.

Complete compilation re-entry is now checked in addition to preparation re-entry.
The test calls the public compiler on its compiled result, compares the entire
logical plan, then physically executes that recompiled result. This covers the
configured analyzer and optional optimizer, rather than merely the preparation
function. The original preparation assertion remains.

The final fixture corrections preserve the expected behavior. The boundary context
now registers the real CatalogManager as well as PlanService, retains the custom
source registry and enables DataFusion's default memory catalog. The bounded
controls therefore reach the same resolver paths as the stream refusals. The v3
missing-CatalogManager failure remains in `affected-tests-v3.log` with its exact
fixture archive. Replacing prohibited expect calls with fallible Result handling
keeps each assertion and rejects every formerly panicking fixture failure. No
failure became a success or skip.

Inspected evidence, with its original execution scope:

| Evidence | Observed outcome and limit |
| --- | --- |
| `affected-tests-v4.log` | 217 passed, one pre-existing skip. This includes all 17 new Rust tests before the later full-reentry assertion and lint-only edits. |
| `participation-public-v3-pytest.log` and receipt | 38 passed, comprising 15 new participation cases and 23 existing selected public cases, using the fresh native build and server PySpark 4.2.1. Exact multisets preserve values, counts and duplicates without inventing global collect order. |
| `controls/preparation-bypass-before.log` | Two failures after bypassing mandatory preparation, both reporting loss of the streaming collector. |
| `controls/preparation-bypass-restored.log` | Both tests pass after restoring preparation, including their full compiler re-entry assertions. |
| `controls/identity-limit-before.log` | Two failures with the parent identity and zero-limit implementations: fresh occurrences compare equal, and zero demand does not immediately finish. |
| `controls/identity-limit-restored.log` | Both tests pass after restoring the repairs. |
| `performance/cse-before-v2.log` | Equal immutable outputs required three invocations and twelve row evaluations under initial early lowering, versus one invocation and four evaluations under the former late compiler. |
| `affected-tests-v3.log` and `affected-tests-v4.log` | All three sharing regressions pass: immutable work remains shared, volatile work remains separate, and conditional partial evaluation remains safe. |

The fresh `performance/planning-v3` diagnostic ran
`compare_participation_planning_v2`, matching its retained executed source SHA256
`d8fca5d4f536e372908d373928cf69944137e66bbc581c3a99fdda3afb73e098`.
Its receipt records exit zero and unchanged source. For all four cells, it checks
direct analyzed execution, the old compiler and the new compiler independently
against the expected values before timing. It uses distinct aliases at successive
projection levels. The earlier same-alias discrepancy, where the direct graph
returned 13 through 16 but both optimized paths returned 2 through 5, remains a
failed diagnostic with unassigned cause. The intermediate stale-executable v2
receipt remains invalid and is not counted as a pass. These are shared-host
planning diagnostics, not a production performance envelope.

After the v3 freeze, strict Clippy identified deliberate raw-command fixture API
uses. The two prohibited command types now have a narrow import-level exception
explaining the bypass control. The bounded raw-memory-table read retains its
original `context.table` behavior under a statement-level exception explaining
that it reads DataFusion's raw command catalog. An attempted SQL read did not
compile because Sail disables DataFusion's SQL frontend; its source and failed
log remain retained. No feature was enabled and no assertion was weakened. The
production import exception is similarly limited to eager-command inspection.
These declaration-only corrections require the next exact source pin and gates;
the v3 verdict does not silently cover a different tree.

The saved request, literal continuation request and governing AGENTS, LAKESAIL,
SHEHAB, CLARITY, WRITING-RULES and applicable source instructions were reread after
compaction. No builds or tests were run by this role during this final review.
Only the explicitly assigned fixture corrections and this report were edited.
The full immutable gate remains pending. These tests do not qualify recovery,
fencing, checkpoint completion, distributed execution, arbitrary source effects,
external service behavior, real Delta time travel or JVM Spark parity. The raw
DataFusion planning API remains a batch entry point; the tested mandatory boundary
is Sail's shared compiler and its guarded eager entrances.

Review entry recorded at 2026-11-06T06:13:43.467572+00:00.


## Final v4 exact-tree verdict

**No outstanding must-fix source or test finding within this role's specialty
for tree `1501e3dcaf84158319a99fd4c3122c2dcb84bfc1`.** Independently verified all
77 file hashes, all 24 increment paths and the full cumulative inventory, both
regenerated binary patches against their saved v4 artifacts, parent HEAD, index
tree and absence of unstaged tracked changes. The parent and upstream base remain
those recorded in the preceding review.

- Increment SHA256: `2bc3f0275441454387ed32baa8764642bf4f35edef299f63dc796b65ed4aea6d`.
- Cumulative SHA256: `e4f922d5c38697aa487fe256d9b1885227bbe506e600500a30be9e9e9b978b1a`.

The complete v3-to-v4 diff affects exactly two files: the production raw-command
imports and the boundary fixture's corresponding imports and raw-catalog read.
Both import exceptions are limited to the prohibited command types; the method
exception is limited to its single positive-control statement. No runtime code,
expected value, error assertion or test selection changes. The final fixture
returns to the same table read that passed previously. All preceding cumulative
source and test findings remain closed with their recorded evidence limits.

Inspected `affected-clippy-v5.log`, which records successful completion after
these corrections. The historical Rust runs, public runs and negative controls
retain the scope stated above. The full immutable gate is still pending; this
review does not claim it passed. No builds, tests, source edits or remote actions
were performed during this final pin check.

Final pin checked at 2026-11-06T06:14:16.340184+00:00.


## Final v5 documentation-only confirmation

**No outstanding must-fix source or test finding within this role's specialty
for tree `f71f8c5c97b08baa0c7f0f914ea7a2e24d150622`.** Independently verified all
77 file hashes, 24 increment paths, complete cumulative inventory, both saved
binary patches, parent HEAD, index tree and absence of unstaged tracked changes.

- Increment SHA256: `15fd96913eecd7d1d1e64fd1083d12bc34630a13c93802541d2cd14bb73941c7`.
- Cumulative SHA256: `0b71c28974776dedaf643028bf12cc7959a0856b751db223b883393818e3d59a`.

The only v4-to-v5 change adds inline-code backticks around the CREDIT marker in
the compiler's attribution comment. Verified the complete optimizer file differs
by exactly that replacement; executable code, test assertions and all other
files are unchanged. The previous cumulative review and its limitations therefore
carry forward. Inspected strict Rustdoc's successful completion in
`strict-rustdoc-v2.log`. The earlier precommit receipt still records its exit-101
Rustdoc failure on v4 after fixture and format checks passed; it is not relabelled
as a successful gate or commit. Full immutable qualification remains pending.
No builds, tests or source edits were performed for this confirmation.

Final pin checked at 2026-11-06T06:21:57.926173+00:00.
