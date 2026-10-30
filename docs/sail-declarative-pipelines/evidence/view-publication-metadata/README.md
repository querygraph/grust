# Persisted-view publication metadata extraction

Sail `5717f1c500feaae80f11c71ec4a4db650b135626` on
`954e025c5631adc1fa25d204613183ddd613a5f4` extracts private pure column and
namespace conversion helpers from the native CreateView resolver. Query
resolution, lazy field-name lookup, column-count error before catalog/namespace
lookup, SQL text, namespace selection and final command construction retain the
same order and values. No public helper/API, publication DTO, pipeline artifact,
provider owner or execution change. This is a prerequisite for reusing native
metadata rules when later deriving publication data during analysis.

Five tests check explicit aliases/comments/types/nullability without calling the
name closure; inferred user names with no inherited input comment; exact native
count-error priority; original name-error variant; and reserved namespace property
replacement while retaining unrelated duplicate properties in order. Tests use
integer, decimal and timezone-aware timestamp fields. Existing native error text
and PlanError variant are preserved.

Exact detached fmt/strict all-target/all-feature Clippy and83 Plan+139 Connect
libraries pass (222), with explicit venv/PYTHONPATH exposing PySpark4.2.1. Initial
7be13e283 strict-Clippy failure for the now-unused PlanError import is preserved;
corrected candidate reruns all gates. No scheduling/concurrency mechanism changes,
so no new optimized stress claim. Fresh combined public CLI qualification on5717f1c50 passes300 selected cases+67
upstream Python executions, client/server Spark4.2.1. Rebuilt CLI hash and exact
source pinned, owned server exit0/no remaining listener. This is not an original
Scala-suite verdict; historical09d2f0cb8 evidence remains retained.

Source review should compare call order around the helpers as well as the moved
conversion bodies. SHA256.json covers packet files except itself. Historical
absolute paths identify advancement-time inputs; replay into fresh outputs.

Fable's line-by-line helper review (CF-0230, Grust894c16f3, carried forward in
[updated batch review](../batch-provider-migration/fable-batch-review-updated.md))
confirms call order, native lazy names, type/nullability/comments and namespace
properties match the parent. No requested change; publication DTO still candidate.

public/ contains the complete fresh harness receipts, XML, selected identities,
logs and upstream result. The frozen reusable harness is archived in
[public harness](../local-runner-ownership/public-harness/README.md); supply the
full commit and a fresh output directory. No withdrawn flow-config assertions or
new capture-specific public coverage are implied by this regression selection.
