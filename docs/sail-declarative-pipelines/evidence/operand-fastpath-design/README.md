# Operand fast-path design checkpoint

Product baseline: `4070e895b69338eb19f22643f0e40815da89ff34`.
Spark 4.2.1 reference: `617618396087429b5627a86ce933bb0f5d6645cb`.
Every child here is test-only; no SQL lowering, execution mode, replay default,
or worker flag was activated. These are prerequisites for full SDP acceptance,
not acceptance of the Spark SDP suites. All failed evidence is retained.

## Optimized execution costs and order

Both release probes use workspace optimized/LTO settings, 1024 integer rows,
50 iterations, five median samples, equal-output assertions and one first-error
counterexample. Ratios were measured on the same shared host, without a dedicated
performance envelope; absolute timings and production throughput are not claimed.

| Probe | Row/native | Selected batch/native |
| --- | ---: | ---: |
| Original selected-batch prototype | 851.77 | 12.45 |
| All-active path avoids take/scatter | 901.43 | 3.53 |

These are separate runs, not a controlled before/after performance verdict.
The unchanged counterexample selects left-row0 in the ordered evaluator and
right-row1 in selected-batch evaluation. Success-path speed alone does not
qualify batch activation. The second algorithm also passes 18 Int32 mask cases:
three datasets, ANSI/legacy, original/empty/sliced batches. This is not float,
decimal, cancellation, memory-pressure, or production replay coverage.

## Actual Sail optimizer and Spark oracle

`optimizer.rs` resolves real Sail casts and uses Sail analyzer/optimizer rules.
Forty-eight observations cover four targets, two modes, NULL/zero divisor, and
three representations. Internal HOF variants intentionally use literal7 as the
operation to isolate conditional cast behavior; they do not prove arithmetic
lowering or result-schema parity. The test passes as an observation collector.

Fresh Spark Connect records 16 corresponding queries, effective ANSI, structured
errors, and shutdown with no remaining listener. Within these VALUES queries, Spark returns one NULL row for
rightNULL for all targets/modes. With right0 it raises CAST_INVALID_INPUT under
ANSI and returns NULL in legacy mode. Comparison covers row/null outcomes and
displayed Sail condition tokens only, not public RPC/schema/error-metadata parity.
Resolved SQL matches8/16; each internal representation matches10/16. Twenty of48
comparisons remain required failures. `check-conformance.py` deliberately exits1;
its failing assertions are retained, not replaced with the observed behavior.

ANSI primitive casts already use SparkAnsiStringCast and can be skipped inside
the internal evaluator. ANSI decimal casts and legacy DOUBLE still resolve to
Expr::Cast and can fail in simplify_expressions before conditional execution.
Both literal and captured-column internal forms reproduce this. Existing SQL
also fails these cases; no new production regression is claimed. A runtime
ordered fallback cannot repair an optimizer failure. Decimal38,10 in the error
for requested5,2 is an observation, not proof of a widening defect.

## Raw errors and replay permission

The prototype passes25 typed-error cases plus a real spawn_blocking panic that
becomes ExecutionJoin (two tests). CommonErrorCause collapses raw Execution,
ExecutionJoin and ResourcesExhausted to Execution. Its transport/job retry policy
cannot authorize arithmetic replay. The counterfactual replaces only the
prototype policy with transport categories; unchanged assertions fail0/1 on
resource admission. This is a prototype control, not a production-source control.
The initial ArrowError boxing compile failure is preserved in attempt-01.

Candidate raw classification unwraps only known DF/Arrow wrappers, requires
nonempty/all-admissible collections, and blocks unknown source envelopes,
resource/I/O/join/ownership/internal failures. Direct Execution can only be
considered after separate trusted-native-body admission; it never authorizes
replay of arbitrary immutable UDFs. No production classifier was introduced.

## Next implementation constraints

Repair general Sail cast semantics before arithmetic activation. Legacy floating
string casts need invalid-input-to-NULL behavior qualified against Spark; ANSI
decimals need lazy typed casting with rounding, overflow, metadata and wire proof.
Choose exact native-body admission after extraction/type resolution, recursively
including lambda descendants. Unknown/custom/async/volatile/stateful bodies keep
ordered semantics. Preserve original system errors without replay. Explicit mode
state, codec, classifier, selected-batch implementation, and SQL lowering should
be separate reviewable units, each qualified before activation. No blanket row
activation or fake-Volatile cast barrier has been selected.

Run `verify.py` to check source pins, hashes, probe results and the retained
conformance failure. Archived launch scripts name original worktrees and /tmp
paths; read them before reuse. They are evidence, not a portable runner.


## Source-scope correction after Fable review

The [source/phase follow-up](../source-dependent-cast-folding/README.md) confirms
that the VALUES result must not be generalised to arbitrary sources. Under ANSI,
Spark can fail a foldable bad cast at planning beneath a nonfoldable Parquet
column-dependent division, including an all-NULL divisor. Foldable wholes,
conditional branches and early local-relation evaluation have different folding
rules. The original sixteen oracle queries/assertions remain unchanged and valid.
Exact context/phase behavior is required; always deferring a cast is insufficient.
Legacy floating invalid-input behavior was corrected separately at63f5bd3b3.
