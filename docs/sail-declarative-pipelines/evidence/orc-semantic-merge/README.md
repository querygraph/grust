# Spark file-schema semantic merge

Sail `1462cc9c92c01ea36ce55a02c07db409fe32d95a` adds a focused field-aware Arrow schema merger in
sail-common-datafusion. It preserves left metadata/order, unmatched nullability,
Spark TIME precision and interval qualifier union. Decimal precision may widen
only at fixed scale; ordinary numerical and Null promotion are rejected. Root
case matching follows the captured setting, while nested STRUCT matching resets
to case sensitive. Final duplicate-name validation remains a separate caller
step, including the single-file case.

The helper validates semantic metadata throughout both input trees and explicitly
rejects unsupported extension/noncanonical types. It reuses existing typed TIME
and interval metadata. The existing pipeline spec merger and normalization remain
unchanged. The [source proposal](proposal/HANDOFF.md) explains why extracting that
spec merger alone would not provide the Arrow conversion needed by ORC.

Formatting, strict Clippy and all 76 common-datafusion tests pass, including ten
new tests comparing complete Fields, nested semantics and malformed map shapes.
The [frozen implementation](implementation/HANDOFF.md) retains exact source copies.
No failed gate attempts occurred. Root source review passed. General Unicode/
Java-locale equivalence, enumeration order and exact Spark error classes are not
qualified here. ORC caller/registry integration remains separate; this unit adds
no public runtime or full SDP acceptance result.
