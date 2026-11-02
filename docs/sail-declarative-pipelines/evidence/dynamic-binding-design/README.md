# Dynamic/reference binding design evidence

The user-notified design phase is active. The selected first unit is literal
identifier normalization; computed binding and Connect reference lifetime remain
open in [the design](../../DYNAMIC-REFERENCE-BINDING-DESIGN.md).

## Literal identifier unit

`ccb6fb21240b1b4d2962da833a74a17ade5e84c3` makes a non-null string literal in
IDENTIFIER into the same NamedTable spec as ordinary table syntax. Computed/cast/
null expressions remain DynamicTable. It reuses the existing name parser and
preserves aliases and samples. The parser gains the missing optional TABLESAMPLE
field for Identifier factors; both read variants retain it. Original stored SQL
is unchanged. The runtime test is renamed because literal syntax no longer
constitutes a computed-dynamic resolver witness; its assertion is unchanged.

Exact fmt/strict Clippy and six library packages pass:139 common +240 source +92
Plan +176 Connect +25 SQL analyzer +6 SQL parser =678 tests. The unchanged control
restores only the old always-dynamic Identifier branch: literal equivalence fails,
computed/null preservation passes (1 pass/1 fail, exit101). Fresh exact-source CLI:
300 selected public +67 upstream Python tests pass.

The expanded thirteen-input Spark/Sail runtime comparison is10 matching outcomes,
three different. Differences are computed_external_unrelated_true, cast_local and
concat_local: configured computed identifiers remain refused by the current trace.
They are implementation debt, not a proposed restriction or accepted end state.
The literal local/external/CTE/producer/sample cases and static-view ordering match.
This is not execution of the original Scala suites.

## Spark design oracles

- spark-dynamic-initial/: nine initial literal/computed observations, original
  harness reference-initial.py retained. They establish literal local reads versus
  concatenated local names. The expanded spark-dynamic/ has13 cases, adding computed
  external/CTE, cast and100-percent sampling controls.
- spark-relations-six/: six public protobuf observations, original six-case harness
  retained. Used/nested scalar references contribute configs; unused references,
  including unused generic aliases, do not. SQL parameter local graph input fails
  at registration, while an external-table parameter succeeds.
- spark-relations/: repeats those cases and adds a binding-lifetime witness.
  After registration, external_input is replaced with another external table whose
  current rows are bar10. The already registered pipeline still returns Foo9 from
  the original source. Preserving only schema or re-resolving by name is insufficient.
  Original external files remain available; this does not qualify deletion/recovery.

Source blobs are pinned in reference-source.json. Runtime Spark4.2.1 is recorded
separately; the local source checkout is not claimed built into the runtime jars.
Protocol bytes are retained as deterministic base64. Registration errors, run
errors and successful rows are separate observations. All reference sessions stop;
listener receipts and owned Sail teardown are checked.

## Retained attempts

literal-attempt-01/ passes the other selected libraries but fails SQL analyzer
24-pass/1-fail: the comparison exposed missing Identifier TABLESAMPLE grammar.
The query/assertion is retained and the grammar is fixed. literal-ready/ contains
the final exact gate; literal-control/ proves the new branch is required.

relations-attempt-01/ fails before cases because warehouse configuration was set
after session creation; it is moved into the builder. relations-attempt-02/ retains
one unexecuted case before create_dataflow_graph's missing sql_conf argument failed.
The corrected probes pass None explicitly. The initial packet verifier assumed
flow conflicts were in events only; verify-attempt-01 retains that failed check.
The corrected check inspects both exception and event carriers. These are probe infrastructure failures,
not protocol or product verdicts. Their original harnesses/logs/partial reports remain.

The former nine metadata and thirteen config packets remain pinned to their own
source verdicts. No new provider/session/streaming effects or opaque bindings are
activated by this parser unit. Full SDK lifetime, protocol scopes/cycles/duplicates,
computed helper errors, command closure changes and original Scala acceptance remain.

Run verify.py for source/gate/control identities, oracle assertions and comparison.
