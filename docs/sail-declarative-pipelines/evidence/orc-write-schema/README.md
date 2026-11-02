# Primitive ORC writer schema admission

Recorded 2026-10-30T04:09:02.782340+00:00. Sail `71f24a87a2f2b5b38bd012388e3ce6589c7c6d46` adds OrcWriteSchema,
a pure preflight token retaining the original SchemaRef. It rejects unsupported
storage types and logical metadata before a future sink can open output. This is
W3 groundwork; the format factory still rejects every public ORC write.

The initial admitted storage types are Boolean, signed integers, Float32/Float64,
and regular/large UTF-8 and binary. Temporal, nested, decimal, unsigned, view and
other encodings remain unsupported by this component. These restrictions are
incremental implementation limits, not a redefinition of Spark's type support.
Spark4.2.1 timestamp/TIME/interval attributes and broader writer behavior remain
required in W7. Native physical timestamp support alone does not establish those
Spark semantics.

Admission rejects all Arrow extension and Sail Spark semantic metadata keys,
including unknown and orphaned keys, rather than silently serializing only their
underlying primitive values. It parses the Spark column-metadata JSON object and
rejects character/collation type annotations. Invalid JSON/nonobject metadata is
a planning error with field context. Ordinary annotations and nullability remain
in the retained schema; this does not promise that native ORC serializes arbitrary
column metadata. The shared CHAR/VARCHAR key remains one constant with the reader.

Six new tests cover later-column semantic rejection, unknown/orphaned tags,
character/collation annotations, malformed metadata, unsupported physical types,
empty schema, all11 admitted physical forms constructing native empty files, and
nullable multi-batch/multi-stripe round trips of integer/string/binary/boolean data
inside one file. All237 data-source library tests, formatting and strict Clippy
pass. No dependency or lockfile changes. A read-only peer review found no blocking
issue and specifically confirmed that future sink/worker paths must invoke this
preflight before output; those paths are not activated in this commit.

sources.json pins exact source excerpts for Sail metadata construction, native
builder support, Spark ORC Catalyst attributes and Spark collation metadata. These
are source observations, not new Spark runtime comparisons. Native round trips do
not qualify full Spark writer parity. The exact four-file patch and raw gate logs
are hashed in provenance.json. No new public SDP count or original Scala-suite
execution is claimed.
