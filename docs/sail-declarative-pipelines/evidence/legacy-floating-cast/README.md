# Legacy floating string casts

Sail `63f5bd3b3f0f8bd9b23607161d5988df853a738c`, parent
`4070e895b69338eb19f22643f0e40815da89ff34`, changes one resolver match arm:
legacy Utf8/LargeUtf8/Utf8View to Float32/Float64 uses the existing TryCast path.
Malformed values return NULL per row rather than aborting the query. No UDF,
worker wire, ANSI branch, arithmetic lowering or replay mode changed. Native
conditional malformed casts with rightNULL/right0 now survive optimization.
This general Sail correction is a prerequisite for lazy arithmetic activation.

Three native fixtures use Sail resolution and Sail optimizer rules: all three
Arrow string representations/two widths over valid, malformed, NULL, signedzero,
NaN/infinity and overflow/underflow rows; literal/conditional SQL; and ANSI versus
explicit TRY_CAST behavior. No assertion relies on a particular Expr variant.
All117 plan libraries, formatting and strict Clippy pass. A production-only
control restores the parent resolver file, leaving test bytes unchanged; all
three regression tests fail0/3. Test coverage is not inferred from source names.

The exact detached candidate rebuilt the CLI and passed a fresh300-case public
selection plus67 upstream Python tests. Those selections are not the original
Spark Scala SDP suites and do not establish full SDP acceptance. Both owned
public servers stopped, with no remaining listeners. CLI hashes/source pins are
retained; root source was advanced only after these checks and the feature probe.

Fresh Spark4.2.1 Connect at source617618396087429b5627a86ce933bb0f5d6645cb
records136 cases (two modes, two widths, CAST/TRY_CAST,17 values), effective ANSI,
values encoded as hex floats/special markers, schema and structured failures.
Sail public RPC repeats identical queries on the qualified CLI. Outcomes match
120/136. Suffix1.0f and hexadecimal0x1.0p2 differ in all eight combinations:
Spark accepts them, Sail ANSI CAST errors and other casts returnNULL. These16
behavior gaps remain required. Of124 cases returning rows in both engines,
104 schemas match and20 differ: ANSI CAST reports nullablefalse where Spark
reports nullabletrue. That ANSI branch is unchanged by this commit; no parent
runtime comparison or claim of exhaustive non-regression is made.

`check-conformance.py` deliberately exits1 for the16 behavior and20 schema gaps;
its failure log is retained. `verify.py` checks the packet, source/control pins,
exact test counts and the retained failures; passing evidence verification does
not mean those conformance assertions pass. Full error-parameter/message parity
is not qualified by the behavior comparison's condition/sqlstate checks.

Two failed native drafts are retained: attempt-01 violates test Clippy rules;
attempt-02 passes116 tests and fails the column fixture because it omitted Sail
field registration. The final fixture registers the internal field and preserves
its expected outputs. The first public feature launch also remains retained:
its server environment omitted PYTHONPATH and version negotiation failed with
ModuleNotFoundError for pyspark before queries. The corrected launcher sets the
same site-packages path as the main public runner and uses a fresh result path.
No failed evidence or assertions were removed to obtain a passing gate.

Next: ANSI-decimal conditional casts can still fail during simplification before
the lazy evaluator; the [prior checkpoint](../operand-fastpath-design/README.md)
retains the required baseline. Wider floating syntax/nullability, generic CASE,
ordered SQL activation, streaming/CDC and the full Spark SDP suite remain open.
Archived launchers use original absolute worktrees and /tmp paths; inspect before
reuse. No push, release, provider or streaming activation was performed.

Independent Fable review f03967f0 accepts this source unit. The exact
[review extract](peer-review.md) is pinned to its source commit and verified.
The broader folding/replay review bdd5962d distinguishes VALUES from Parquet
planning behavior; see the current operand design before decimal activation.
