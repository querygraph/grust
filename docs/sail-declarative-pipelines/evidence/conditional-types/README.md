# IF/CASE common types before introspection

Sail a51bef4ce1b1b18b025fc697ace4b03c891380e8, parent982877d85, applies the
existing analyzer CASE coercion helper during IF and CASE lowering, after
string/temporal normalization. NVL2 delegates to IF; its extra wrapper is removed.
There are no dependency, worker-wire or optimizer-rule changes.

The fresh Spark4.2.1 pin617618396087429b5627a86ce933bb0f5d6645cb oracle and
exact Sail CLI agree on all8 typeof results and schemas, under both ANSI modes,
versus parent0/8. Three new native tests inspect types before analysis and after
the analyzer, reversed Int32/Int64 branches and decimal widening, true/false/NULL
predicates, CASE without ELSE, multiple branches, and typed NULL. An Immutable
throwing branch proves zero calls during coercion or skipping, one on selection.

Detached gates:122 plan library tests, formatting, strictClippy; production-only
coercion bypass retains the exact test blob and fails0/1. Fresh built CLI passes
300 selected public cases and67 upstream Python executions. Spark and Sail each
pass all15 selected conditional feature scenarios, including mixed string/date,
session-zone cases and NVL2. This is not the original Scala SDP suite.

manifest.json hashes the raw evidence; verify.py checks pins, hashes, original
0/8 parent evidence, type/row/schema parity, test-blob equality, native/control,
public receipts/CLI identity and both feature runs.

Fable47a61dc4 accepts this unit. The separate CASE ELSE nullability defect is
addressed in the following source unit and packet. Existing four NVL2 cast
nullability gaps, source-aware folding, decimal SQL routing and full SDP
acceptance remain required.
