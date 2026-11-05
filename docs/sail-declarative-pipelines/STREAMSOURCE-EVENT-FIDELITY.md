# Preserve exact Arrow data through streaming events

A streaming query must preserve row counts and types when control markers travel
beside its data. A query selecting no source columns still has rows, and a decimal
field must keep its declared precision and scale. Repair these properties within
Sail’s existing event encoding before adding durable sinks.

This increment preserves the event model and wire-column layout. It does not add
checkpoint coordination, a sink, a new source contract or event-time semantics.

## Existing behavior and the failure

Sail represents a flow event as data with per-row retraction flags, or an ordered
control marker. Encoding adds marker and retraction columns to an Arrow batch.
Decoding removes those columns and restores data batches and marker events.
Markers use placeholder payload values so the encoded batch has the stream’s
ordinary field types and nullability.

Three repairs follow directly from that representation:

| Boundary | Existing defect | Required behavior |
| --- | --- | --- |
| Removing control columns | An empty data schema loses its row count when reconstructed from columns alone | Supply the encoded batch’s row count explicitly |
| Adding or removing control fields | Rebuilding a schema drops its schema-level metadata | Preserve metadata and the original field definitions |
| Constructing marker placeholders | Decimal builders use default type parameters; run-end arrays can replace field attributes or reject an empty array | Return the exact requested valid Arrow type and length, including nested field metadata |

A run-end encoded array represents repeated values by the positions where each
run ends. An empty array has no runs, not a run ending at zero. Its run-end and
value fields are part of its type and must survive placeholder construction.
Invalid precision, scale or run-end capacity should produce a normal error,
not an incorrect type, truncated length or panic.

The same row-count rule applies where a rate source emits a projection with no
columns. Fix that constructor if the public query regression reaches it; preserving
row count only in the decoder would leave that valid query broken earlier.

## Decision: retain the current representation

The smallest repair keeps the two leading control fields and changes their
surrounding constructors. Explicit Arrow record-batch options preserve zero-column
length. Schema metadata is copied when fields are added or removed. Decimal
builders receive the requested precision and scale; run-end construction preserves
its declared field attributes and uses no run for an empty result.

An alternative makes every encoded payload nullable, eliminating some non-null
placeholders. That changes the schema seen by optimizers, sources and workers
and still does not keep user expressions away from markers. A separate control
transport is a larger protocol change. Neither is necessary to restore faithful
encoding, so this increment preserves the existing schema contract.

Use Arrow’s checked constructors and existing Sail helper functions. Do not
rewrite all array creation or add a dependency fork. Reusing the exact requested
type is appropriate only after constructing valid buffers and child arrays.
Tests must verify data type equality, not just physical null counts or length.

## Verification that can reject the repair

Exercise empty-schema data with positive row counts, all four marker kinds,
retraction flags, sliced batches and mixed data/marker batches. Decode must retain
event order, data row counts and retractions. Empty data batches may remain
elided according to the existing decoder’s behavior; that is distinct from
losing positive-length zero-column data.

Compare complete schemas, including nested field and schema metadata, before
encoding and after decoding. Cover nullable and nonnullable fields, all decimal
widths with nondefault positive and negative scales, and nested decimals inside
lists, structures, dictionaries, unions and run-end arrays. Extend the existing
placeholder type matrix to assert exact types for every supported Arrow family,
with empty and nonempty construction where meaningful.

These are internal encoding utilities whose control-event inputs are constructed
directly in Rust. Add focused Rust regressions rather than claiming ordinary
Python data can originate every internal marker. Also run public streaming
projection/filter/limit tests, including a zero-column or literal-only rate query,
against the freshly built Sail binary. Run the new regressions against unmodified
source to demonstrate that they discriminate the defects.

Use resolved dependency versions, format and strict Clippy checks, affected crate
tests and a freshly built executable. Record the tested source tree and preserve
failed controls. The bounded pipeline integration suites are not present on the
upstream foundation branch; this increment must not claim qualification of that
separate runtime or the future durable path.

## Decision boundary before the next increment

Preserving row counts, exact types and metadata restores existing behavior and
requires no product semantic choice. The next independent question is how
projection and filtering evaluate data without evaluating marker placeholders.
That needs its own operator/optimizer/codec design before implementation.

Reserved control-field collisions and malformed input admission remain separate
questions unless a regression demonstrates they prevent this repair. No production
source or target becomes durable merely because its event encoding is corrected.
