# ORC requested-schema adapter and ordinary file source

Two separately reviewed and gated Sail commits connect the native reader to the
normal file-execution path:

| Commit | Scope | Complete data-source library suite |
| --- | --- | ---: |
| `c3f9b77466` | Per-file requested-schema mapping after logical conversion | 169 passed |
| `f49b3f865c` | Ordinary FileSource/FileOpener with FileStream integration | 184 passed |

Both exact detached candidates pass formatting and strict all-target/all-feature
Clippy. No failed gates occurred. The earlier mapper candidate also passed its
166-test suite, but was not advanced: four fresh Spark observations required a
last-wins exact-name correction and exposed a separate map-key narrowing boundary.
Its complete candidate, patch and passing logs are retained, not relabeled as the
final verdict.

The mapper keeps full data schema separate from required output projection. It
checks positional STRUCT-only LTZ/NTZ compatibility first; native file projection
is sorted/unique while output order/duplicates remain intact. Missing fields are
typed nulls. Requested spelling, recursive read nullability, parent validity,
sliced offsets and TIME/interval metadata survive mapping. Safe numeric kernels
implement ordinary integer narrowing; same-storage TIME/interval interpretation
preserves values. Exact duplicate names select last; required case-insensitive
top-level ambiguity errors; tested nested ASCII matching is last-wins. `_col*`
fallback retains full-width checks. The real fractional TIME fixture traverses
native reader, logical bridge and requested adapter in a test.

Integer narrowing within map keys is explicitly unimplemented: the retained
Spark vectorized and row modes differ, so ordinary safe-null semantics are not
a qualified substitute. Unicode/default-locale case conversion, unequal decimal/
string/float conversions, nested timestamp conversion, forced positional mode,
calendar/configuration/error parity and default-value metadata remain acceptance
work. These limitations do not reduce the complete goal.

The source uses existing FileSource, SplitProjection/ProjectionOpener and FileStream,
with no additional execution engine or producer queue. It binds the local pool,
uses immutable listed identity, reads bounded metadata once and checks selected
stripe extents against object size. Every stripe offset is checked before native
usize range filtering. Captured Java reader timezone controls conversion; session
timezone labels output. Direct native streams own one active stripe; cancellation
drops owned futures/buffers while returned Arrow batches remain usable.

Integration tests cover expressions/repeated columns, missing/partition-only/zero
columns, batch size/limit/multiple groups, three-stripe half-open ranges, reference
timestamp contexts, identity changes, projected-out schema failures, all budgets,
pending tail/stripe I/O drops and reservation release. An empty physical root
returns no rows even with declared rows; zero projection from a nonempty physical
schema preserves rows. Automatic repartitioning remains disabled until worker/
optimizer range reconstruction is qualified; explicit ranges are tested.

Independent source review identified virtual-column projection as unsupported by
the reused ProjectionOpener path. Construction now rejects it before indexing,
with a regression and a successful ordinary-partition control. Read-only review
also caught compressed/uncompressed budget wording before the first source gate;
the fixture's uncompressed metadata and exact applicable failure are asserted.

[Mapper handoff](mapper-handoff/HANDOFF.md) preserves API, reuse rationale and
remaining listing/partition requirements. Public ReadFormat/factory registration,
worker codec, supplied-schema planning/partition bindings, semantic schema merge,
writer and public Spark assertions are still pending. This packet qualifies the
internal file-source path, not a new CLI/SDP count or streaming/Iggy/CDC runtime.
