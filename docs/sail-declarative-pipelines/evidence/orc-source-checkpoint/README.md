# ORC source integration checkpoint

The shared identity transport is implemented separately at Sail `27ab945aa`.
This packet records the remaining source integration constraints and a focused
Spark 4.2.1 requested-schema experiment. It introduces no Sail runtime behavior
and does not change the full SDP acceptance denominator.

The [read adapter handoff](read-adapter/READ-ADAPTER-HANDOFF.md) captures the
existing listing, source, projection, schema evolution and resource interfaces.
Its 29 pinned source identities and 43 excerpts identify two general listing
requirements: all-file inference when requested, and case sensitivity carried
into per-file execution. Runtime pools can be attached at driver and worker
source construction without serializing their handles or adding an execution
engine. Concrete metadata/decode limits and reservation lifetimes remain design
work; the audit's alternatives are not adopted defaults.

The [Spark reference](spark-reference/README.md) records twelve requested-schema
cases under each of two vectorization settings: eight successful reads, twelve
dedicated timestamp-compatibility errors and four later conversion overflows.
The original full supplied schema must remain distinct from required/output
projection: supplying only the second NTZ field fails, while supplying the full
schema and then selecting that field succeeds. Matching reordered names do not
bypass the preceding positional check, which recurses into STRUCT. Appending a
missing LTZ or NTZ field returns nulls in this fixture.

Combined ARRAY/MAP type swaps fail later with overflow here. Both conversion
directions change together; these cases do not establish a universal or
one-direction rejection rule. The successful reads record configuration values,
not physical-plan captures. Their complete integer values are validated;
array/map failure stacks identify their actual reader paths. The
[independent review](independent-review.md) records these limits.

Preserve Spark's demonstrated full-schema check before projection in the next
adapter units. Requested TIME/interval/integer evolution, case ambiguity, Hive
positional mode, all-file semantic schema merging, calendar rebasing and resource
admission remain open. The next deliverable is the shared ORC read source with
worker execution, followed by writing and original SDP assertions; none is
replaced by this reference study.

Both owned reference JVMs exited normally; the first attempt failed on a Connect
write-mode spelling before any read case and is retained separately. Manifests
retain exact bytes, fixture, raw errors, scripts and pinned source excerpts.
