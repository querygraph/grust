# Construct marker payloads without panicking

Sail carries control markers inside Arrow batches. Their payload values are
unspecified, but the arrays must satisfy the declared schema. Use distinct fallible
constructors for nullable and nonnullable placeholders, preserving Arrow's encodings.

Arrow 59.2's null constructor panics when an Int16 run end must represent 32768
rows. Nullable structs, fixed-size lists and unions inherit that behavior through
recursive construction. Projection can encounter such adjacent marker runs even
when its input payload type has no capacity constraint. Return an execution error
when the requested representation cannot fit.

Replacing NULLs with non-null placeholders is insufficient. A nullable dictionary
can represent a row using a null key and zero values. Its value type may contain
a fixed-size list too wide for an Int16 run end. Constructing a representative value
then refuses a valid nullable dictionary. Splitting marker batches cannot solve this
single-row case.

Carry Arrow's small null-array implementation in Sail with its Apache license,
pinned attribution and retained comparison. Preserve its zero-length dictionary and
list children, null-parent semantics and exact nested fields. Make recursive calls
fallible, check run-end conversions and buffer/child-size arithmetic before allocation,
and use the checked Arrow builder. Keep Sail's non-null placeholder traversal and
route its nullable children through this constructor. Empty dictionaries need no
representative value. Use the same constructors for projection, empty results and
event encoding.

A separate preflight walker would duplicate Arrow's recursive layout decisions while
retaining its panic-prone constructor. Owning this routine keeps the required change
visible beside its source. These checks do not provide recoverable allocation failure;
task memory budgets remain necessary.

Verify run-end boundaries and nested forms, zero expression calls, full Arrow
validity, dictionary null encodings, metadata and fixed-size arithmetic failures.
Retain failing controls and compare the implementation with the pinned original.
