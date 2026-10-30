# Worker and listing scan preparation

Two separately reviewed Sail commits pass exact detached gates:

| Commit | Scope | Library tests |
| --- | --- | ---: |
| `429d54e3d3` | Preserve checkpoint partitioning during worker preparation | 175 execution |
| `5563ea1659` | Discover and classify directory columns with supplied schemas | 201 data-source |

Both pass formatting and strict all-target/all-feature Clippy. Each had one
retained compilation failure before tests: worker code/tests used outdated
DataFusion APIs, and a listing test compared Arrow Fields with Vec<FieldRef>.
Mechanical corrections preserve all assertions. Frozen author handoffs match
those first candidates; final changes are in the qualified commit patches.

Worker preparation now retains decoded checkpoint output partitioning while
rebuilding unchanged groups/projections with preserve_order=true. A Parquet test
preserves projected Hash partitioning, empty groups and the same adapter Arc.
An ORC test decodes each task independently and proves that each reads only its
assigned files, including an empty group. Its real unprepared control consumes
all files from the empty partition, exercising the sibling queue regression.
These tests call the actual rewrite/codec/executor; they do not run a cluster,
actors or shuffle transport. No new malformed partition-count validator is added.

Shared listing preparation retains omitted discovered columns, uses captured case
policy to separate file fields from partitions, and distinguishes a preserved
explicit-empty schema from absent schema. Absent schema uses full discovery even
with explicit selectors. Auto partitions are nullable and drop user metadata;
Sail logical-type metadata and nested DataType fields remain intact. Explicit
selectors instead preserve supplied field metadata/nullability, falling back to
discovery if absent. The remaining file order and metadata survive validation.
Source review corrected the first draft's automatic user-metadata retention before
any code gate; both handoff versions remain archived.

Current inferred partition type is still STRING. Mixed physical directory casing,
Unicode/duplicate-case policies, typed inference/validation settings and unusual
explicit-selector layouts remain acceptance work. Existing layout-prefix checks
still reject inner-only/reversed selectors. These limits do not redefine the full
SDP objective. Public ORC registry/inference/writer integration and public CLI
acceptance remain separate; streaming/Iggy and CDC runtime are not implemented.
