# Construct marker payloads without panicking

Sail carries ordered control markers inside Arrow batches. Their payload values
are unspecified, but every payload array must satisfy its schema. Construct them
through one fallible placeholder helper, including nullable fields and children.

A projected run-end encoded column uses an integer to represent its final row
position. An Int16 run end cannot represent 32768 rows. Arrow 59.2's null-array
constructor panics there, including inside nullable structs, fixed-size lists and
unions. Projection can encounter that length in adjacent marker rows even when
its input payload type has no such constraint. A schema-capacity refusal must be
an execution error rather than an unwinding panic.

Sail already owns a recursive placeholder implementation with checked run-end
conversion. Its nullable-child branches still delegate to Arrow's infallible null
constructor. Remove those branches and recurse through the same helper regardless
of nullability. Check fixed-size child-length arithmetic. Use this path for both
projection and event encoding, the production callers that construct marker payloads.
Nullable fields permit valid non-null values; user data remains untouched.

An Int16-only guard leaves nested cases exposed. Splitting marker batches introduces
a type-dependent batching policy. Copying and correcting Arrow's null constructor
would preserve its null encodings but add another type traversal. Prefer the existing
owned traversal and a named error when the requested array cannot fit its type.

This choice can allocate more for nullable dictionaries with wide nested values,
because a valid placeholder needs a representative dictionary value. Do not claim
allocation neutrality. Resource admission and schema-dependent costs still need
qualification before production readiness.

Verify 32767-row positive controls, 32768-row errors, nested nullable and nonnullable
children, exact fields and marker order, and zero expression invocations. Keep the
panicking controls and run the complete Arrow/event tests afterward.
