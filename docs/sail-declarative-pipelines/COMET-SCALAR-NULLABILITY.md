# Nonnullable native results must exclude logical nulls

A native scalar declares its result field during planning. Callers may use its
nullability to simplify expressions. A nonnullable declaration must therefore mean
that no result row evaluates to null, independent of its Arrow encoding.

Physical validity bits are insufficient: dictionary keys can select null values,
and run-end or union arrays derive nullness from selected contents. Arrow 59.2.0’s
logical-null helper also mishandles a single-child dense union with a nonzero type
ID. Nested dictionary/run-end values inherit that defect. A full bitmap can expand
compressed runs merely to answer whether any null exists.

Use a small Sail-owned null-presence predicate over Arrow’s public typed APIs.
Ordinary arrays use physical null counts. Dictionaries follow referenced keys;
unions follow actual type IDs and offsets; run-end arrays inspect physical runs
intersecting the current slice. Recurse when encoded values are themselves encoded.
Null arrays are null whenever nonempty. Unselected null children must not reject
an otherwise nonnull slice.

The alternative is copying Arrow’s full union bitmap implementation and repairing
its ID handling. That carries private gathering/bitmap machinery for a simpler
existence question and retains logical-row expansion. Refusing those encodings
would weaken Sail’s Arrow support. Prefer the direct predicate without adding
a dependency fork or type-specific fallback that misses nested forms.

Run these checks only for planned nonnullable outputs, after the constant-time
row-count check. Test nullable preservation, nonnullable refusal, nonzero union IDs,
nested encodings and valid slices. Retain failing physical-only and Arrow-helper
controls. Budget selected-key/union traversal and recursion; preserve compressed
run structure. Trusted foreign-buffer correctness remains a separate obligation.
