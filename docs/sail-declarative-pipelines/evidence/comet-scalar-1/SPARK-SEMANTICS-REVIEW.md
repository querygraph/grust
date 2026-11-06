# Spark semantics and correctness review

## Verdict

The human-review compendium and standalone adapter plan have no unresolved
correctness objection in this review. They preserve engineering guarantees as
the governing contract, retain both extension routes in the full scope, and
explicitly distinguish the adapter work in progress from qualified implementation.
This is a document/source-inspection verdict, not test execution or runtime parity.

Reviewed snapshots:

- `HUMAN-REVIEW.md` SHA-256 `eed251526e19a5380b73d1d704430f28a61447ed935170cb6551d7d41719e3fe`.
- `COMET-SCALAR-ADAPTER.md` SHA-256 `34b73dc0aa059e0aa24f16773995b404e21f6b9f2909a398f8505779dbedd4e5`.

## Pipeline and change-capture semantics

The compendium defines a complete per-key order, stable event identity and common
comparison semantics for upserts and deletes. Retaining deletion versions prevents
stale upserts from resurrecting rows. Validating original rows before reduction
preserves invalid-loser and durable-state conflict checks. Default conflict checking
is accurately limited to the prepared interval and current durable version, with
historical fingerprint retention treated as additional scope.

A prepared record binds original input, computation and effect identity before
publication. Immutable saved output or demonstrably identical replay is required.
The text does not treat source offsets, a package digest or scalar purity alone
as sufficient replay proof. Unknown commits must be reconciled using original
identities. Writer fencing is enforced at commit acceptance and cannot be replaced
by a lease or by reloading the latest table head. Separate target effects do not
claim cross-table atomic visibility. These remain necessary guarantees independent
of Spark compatibility choices.

## Extension and StreamSource integration

Inspected existing extension behavior at `99dc47788941daf28eec847527949a4cadafdbd2`
and foundation behavior at `2c9fa84994d317aade0d1c69faa9a378c780127d` in the
previous extension review. The existing identity/name codec and worker lookup
are reusable mechanisms; boundary selection and durable binding remain additions.
The existing registry retains the full bound owner. HUMAN-REVIEW explicitly
identifies separating process-retained code from scoped session state as new work.
It does not misrepresent that distinction as an already proven cleanup contract.

Marker-safe filtering exists at the foundation pin. Projection still prepends
control columns to ordinary expressions, so arbitrary native expressions require
further isolation. The compendium and adapter note retain that prerequisite.
Finite relation output does not automatically establish live source controls,
snapshot replay identity or checkpoint participation.

The Comet adapter note requires trusted pure immutable producers and rejects other
declared volatility before loading. It correctly says that numeric ABI checks
cannot prove pointer safety, callback concurrency, absence of unwinding or truthful
purity. Process-retained library code protects result callbacks independently of
function lifetime; the registry must not retain session state or kernel instances.
The initial standalone opening policy is explicitly distinct from bounded package
admission. Field metadata and planning-versus-execution checks are qualified as
requirements, not successful tests. The reserved scalar initialization pointer
remains null rather than silently extending the pinned interface.

## Evidence limits and verification status

The compendium labels the existing host as integration-branch reference code and
the standalone adapter as in progress. Initial compilation is explicitly weaker
than test success or package integration. Foundation tests do not qualify integrated
recovery, and handwritten fixture success does not qualify SDK interoperability.
The optimized filter observations remain component evidence with profile/host
limits. No new source pin, test count or pipeline readiness is inferred here.

Spark 4.2.1 source was inspected in the preceding extension review at
`617618396087429b5627a86ce933bb0f5d6645cb`: Scala and Python UDF determinism
combines the function declaration with deterministic children. This supports
preserving explicit function semantics, without making Spark API conformance the
Comet or durable-pipeline contract. No new Spark-engine differential execution
was performed in this review.

Read the exact saved steering in `REQUEST.txt`, the prior objective and the
AGENTS/LAKESAIL/SHEHAB/CLARITY/WRITING-RULES governance. No context compaction
occurred. No production edits, builds, tests, cleanup or external communications
were performed. Only this report was written.


## Revised frozen source review

Independently checked all twelve file hashes in `candidate-snapshot-v2.json`
against the files in
`/Users/alexy/src/sail/tmp/comet-scalar-20261105-2c9fa8499`. The index tree is
`fd9a3568c6227dea942c54368b3f6282f8bb3370`. The binary-capable increment against
`2c9fa84994d317aade0d1c69faa9a378c780127d` hashes to
`7310da99c78170079e056387260c4544bf8776b729d58e3a5afb1b35f4138017`; the full
cumulative diff against `b52144955b629314a000b1fe49eeea97fa3d0c5c` hashes to
`292a6b7d08656e2b092148921fe9c5fa65929a65b0601be8493fe5b21dfb860a`.
This review covers that exact frozen source, not an unchecked later tree.

No additional correctness blocker was found. The standalone adapter leaves
existing streaming plans, package loading and worker codecs unchanged. The
foundation’s earlier semantic qualification does not become a package/worker
or durable-recovery qualification merely because these crates are added.

The host signature now accepts `Nullary` or `VariadicAny`; kernel initialization
owns the actual arity/type refusal. This permits zero-argument immutable kernels
without weakening errors from functions that require arguments. The fixture
exercises a nullary function through actual DataFusion planning and execution.
The precise signature-only control failed that test while retaining the other
repairs, establishing the earlier declaration’s applicability gap. These are
inspected retained results, not tests executed by this reviewer.

`invoke_with_args` uses DataFusion’s supplied argument fields, checks their count,
types and permitted input lengths, and expands scalar arguments to the requested
row count. It keeps the reserved constant pointer null. DataFusion 55.2.0’s
`ScalarFunctionExpr` obtains argument fields from children and passes the planned
return field into invocation at `scalar_function.rs:243–260`. Ignoring only the
top-level output name is compatible with its schema-facing naming behavior.
Exact nested DataType and field-metadata comparisons prevent hidden changes;
accepting a nonnullable kernel field under a nullable planned field is safe
widening. The reverse is refused. The strengthened guard test rejects changed
type, metadata and unsafe nullable narrowing after successful initialization;
its isolated comparison-removal control fails as intended.

The returned-array `null_count` check is a physical-validity diagnostic. It is
not logical-null validation for Null, dictionary, union or run-end arrays. Arrow
59.2.0 distinguishes those concepts, and RecordBatch itself applies physical
null-count checks. Thus the adapter must not claim validation of arbitrary foreign
buffers or truthful producer schema declarations. Its unsafe trusted-producer
contract remains necessary. Empty-array family coverage does not establish
populated semantics for every encoding. The source and evidence boundaries
remain consistent with that limitation.

The loader refuses declared Stable/Volatile functions before library loading,
then retains opened code before foreign probe/discovery callbacks. Its registry
stores only library handles; it does not retain kernel instances or session state.
Declared Immutable does not prove purity, so the unsafe contract remains explicit.
The lifetime fixture checks code after dropping loader/function owners and uses
sliced retained results. This establishes the narrow process-retention mechanism;
it does not prove cancellation, host memory governance or package admission.
Native calls are synchronous and this C interface provides no cancellation or
preemption guarantee. Those lifecycle concerns remain integration work.

The revised ABI records and named symbols are pinned to Comet SDK commit
`0f7f8e45399847715093b3d3affdfa97614b39dc`. Preserving literal layout is necessary
but not proof of arbitrary SDK-release compatibility. The retained independent
SDK producer evidence is stronger than the handwritten fixture, but its exact
producer/host pairing remains the claim. No general Comet release or Sedona
interchangeability is inferred. Spark 4.2.1 remains a source reference for retained
semantics; no Spark-engine execution or parity claim was added in this source pass.

The lead reports fourteen focused adapter tests and strict Clippy passed; retained
logs and isolated failure receipts were inspected. The final cumulative gate was
still pending at this review. No new builds, tests, timing runs or production
changes were performed by this reviewer. REQUEST, HUMAN-REVIEW and the applicable
governance were read; no context compaction occurred during this pass.


## Final v5 source confirmation and logical-null closure

Verified final snapshot `candidate-snapshot-final.json`, index tree
`455101575ecbfbec6f843464ce178e0d09046f51`, and all fifteen recorded file hashes.
The increment against foundation `2c9fa84994d317aade0d1c69faa9a378c780127d`
hashes to `7477e67e9b6262e5aec067714c586ef7ac49790e8e6ac7d14116829213bdf325`;
the cumulative diff against upstream `b52144955b629314a000b1fe49eeea97fa3d0c5c`
hashes to `743a1346feb7ae62a4cded0224b007312b471b09d80d149b2b0bdf5c25c25b30`.
This final confirmation supersedes the earlier frozen source pin for readiness.

Read the complete standalone nullability contract. It explicitly chooses a
logical scalar guarantee: a planned nonnullable result has no row that evaluates
to null, regardless of encoding. That is stronger than checking an Arrow parent
validity bitmap. It is a deliberate correctness contract justified by callers’
ability to simplify expressions using nullability, not an accidental type-specific
restriction introduced to obtain passing tests.

No correctness blocker was found in the final `nulls.rs`. The helper returns
false for empty arrays before considering Null type. Physical nulls are a valid
early positive result. Dictionaries follow selected keys and recurse into encoded
values; unused dictionary nulls do not cause refusal. Unions use their actual
selected type ID and offset. Run-end arrays inspect only physical values whose
runs intersect the logical slice, and selected run lookup includes slice offset.
The Arrow 59.2 public accessors were inspected for these offset contracts. The
recursion supports encoded values inside other encoded arrays. List or struct
child nulls do not make a present list/struct scalar null, and the default branch
correctly respects that parent distinction.

The algorithm answers presence without constructing a logical-length null bitmap.
The constant-time result row-count comparison precedes traversal. Ordinary arrays
avoid encoded traversal. Selected dictionary keys and union rows can require
linear work, while a large compressed run remains compressed; the contract calls
out those costs rather than presenting this as constant-time validation.

Reviewed the fixtures for nonzero single-child union ID 3, dictionary/run-end
nesting, valid offset slices and the million-row compressed run with an unused
null run. They avoid using Arrow’s known-failing single-child-union helper as the
oracle for that case. Nullable outputs remain unchanged, while nonnullable outputs
reject selected logical nulls. The retained physical-only and Arrow-helper controls
are meaningful counterexamples, not a justification to weaken assertions.

This closes the earlier report’s physical-only limitation for the stated logical
null-presence contract. It does not establish memory safety of arbitrary foreign
buffers, truthful purity or ABI compatibility outside the admitted pinned pair.
Producer validity, non-unwinding callbacks and concurrency remain unsafe admission
obligations. Package and worker loading, cancellation, memory governance and durable
recovery are still outside this standalone source qualification.

The integration owner reports seventeen focused tests, strict affected Clippy,
Rustdoc and two pinned SDK producer probes passed. Those are retained reported
results, not execution by this reviewer. The final cumulative gate remains the
lead’s separate responsibility. No source changes, builds or tests were performed
for this confirmation. Saved request, HUMAN-REVIEW and governance compliance remain
confirmed; no context compaction occurred in this pass.
