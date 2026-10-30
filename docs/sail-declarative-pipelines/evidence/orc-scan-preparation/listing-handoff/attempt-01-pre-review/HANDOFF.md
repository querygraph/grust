# Shared listing partition preparation

Frozen implementation in the four files inventoried by source-state.json. Root
owns independent review, gates and commits. No Cargo commands or runtime probes
were performed. Source evidence and the finite ordinary-read Spark observations
remain in /tmp/sail-sdp-listing-partition-binding-handoff and
/tmp/sail-sdp-orc-partition-schema-reference; those packets were not modified.

## Implemented contract

- With a prepared supplied schema and no explicit selectors, retain every
  discovered directory key. Use the supplied field name/type/metadata when it
  matches under the captured case policy, with nullable=true; otherwise append
  a nullable inferred field. Preserve directory order.
- With explicit selectors and a prepared schema, follow Spark DataSource196-217:
  search supplied fields first under the resolver, then discovered fields, else
  error. Preserve a selected supplied field's metadata and nullability. Preserve
  selector order/subset. Existing physical layout-prefix validation still applies.
- Remove from the full file schema only fields matching selected partition fields
  under that same case policy. Keep file-field order, metadata and nullability;
  also preserve schema metadata during partition extraction.
- With no prepared schema, leave the existing format infer_schema and unsupported-
  field normalization calls intact, then retain all discovered nullable fields,
  even when explicit selectors were supplied (Spark DataSource190-195).
- Do not change the explicit-schema hook: a format returning Some(empty) yields
  partition-only output without file inference. Legacy empty->None behavior remains
  that format's existing compatibility limitation; it is not Spark-empty parity.
- Existing physical-schema validation still receives only the remaining file
  schema after extraction. Existing logical/physical directory binding and filter
  rebinding remain unchanged.

Eight focused tests were added. They cover full discovery/omissions, actual case
policy, field and schema metadata, explicit supplied-field preservation versus
fallback/error, selector order/subsets, absent-schema explicit selectors,
case-sensitive file aliases, the inner-only prefix rejection, and integrated
explicit-empty override with partition-only schema and no file inference. Existing
format preparation and validation regressions remain enabled.

## Visible remaining boundaries

Inferred partition types remain the existing STRING policy; this change does not
implement Spark numeric/date/time inference or its configuration flags. The frozen
ordinary-read reference has west/east string values. Type inference remains an
acceptance requirement rather than a scope exclusion.

Mixed physical key casing, escaped key semantics, Unicode/locale matching,
default-null markers, cast-validation settings, basePath/recursiveFileLookup and
ambiguous duplicate case-folded supplied fields are not newly qualified. Matching
in this initial shared helper remains ASCII case-insensitive; exact matching keeps
original Unicode strings. The auto-discovery path is not a claim to reproduce all
CaseInsensitiveMap insertion behavior for duplicate supplied names.

Explicit selector subset/order handling is source-backed, not runtime-qualified by
the ordinary spark.read packet, whose partitionColumns are empty. Sail's existing
layout-prefix guard still rejects inner-only or reversed directory selections.
Do not silently remove that guard or claim these unusual internal cases have exact
Spark execution parity. No ORC-specific normalization/registration was introduced.
