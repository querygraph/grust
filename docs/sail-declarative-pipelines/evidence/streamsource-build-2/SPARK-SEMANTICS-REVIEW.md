# Spark semantics and extension correctness review

## Verdict and scope

The revised documents preserve the existing DataFusion extension route while
making the Comet scalar boundary an additional explicitly selected route.
Their distinctions among source inspection, reported prototype tests and unbuilt
integration are appropriate. No runtime or Spark parity verdict is supplied.
There is no unresolved blocker to the proposed architectural separation; the
implementation prerequisites below must remain visible.

Reviewed documentation snapshot:

- `EXTENSIONS-STREAMSOURCE-INTEGRATION.md` SHA-256 `e10caf7e12b29a944d97179835644287d808cb7c9f69bc66513aa910a371e423`.
- `EXTENSIONS-ON-ARROW-C-ABI.md` SHA-256 `077b88d8f7e20e11bcdeaddf15e3796a3bf3841fba48e6c1bbad8a26b251f93a`.
- `DECISION-NOTES-EXTENSIONS.md` SHA-256 `7b7af5d7ffe5ffb7f4da2366f0fe83025c7b6fd3d61be5247dda65c737efdeb7`.

Inspected the existing extension source at
`99dc47788941daf28eec847527949a4cadafdbd2` in
`/Users/alexy/src/sail-pipelines-proposal`, with clean tracked source. Inspected
StreamSource foundation commit `2c9fa84994d317aade0d1c69faa9a378c780127d` and the
standalone C scalar prototype at `ef7286ca2`. No production source was edited.

## Observed identity and admission behavior

`crates/sail-session/src/extensions/mod.rs` validates manifests before native
capsule access, derives package identity, rejects duplicate extension names and
scalar collisions, and creates `OwnedScalar` wrappers. Worker loading derives
its own package identity and populates the process-local registry before plan
decoding. `native_scalar.rs` encodes identity and name, checks descriptor size
and prefix, rejects encoded-name mismatch, and refuses an unavailable identity.
The documents accurately treat boundary selection as an additional identity
requirement rather than an existing implementation detail.

`manifest.rs` requires the exact compiled DataFusion and Arrow version for the
existing DataFusion-FFI route. Retaining those checks for mixed packages is
necessary. Separate C admission must not bypass them for other exported objects.

A comment on `retain_scalar` describes immutable functions, but neither that
function nor the inspected loader enforces the wrapped signature’s volatility.
`OwnedScalar` forwards that signature unchanged. Thus immutable/pure Comet
admission is required implementation work, not a proven existing host guard.
Purity remains an author contract; metadata cannot verify absence of external
mutations. The proposed effect protocol/refusal for such mutations is necessary.

The process registry retains the entire `OwnedScalar`, whose owner includes the
bound session/exporting object. The current code therefore does not by itself
prove the proposed separation of process-retained code from scoped session state.
That separation and quota settlement need their own implementation and tests.
These two precision points were sent to the integration owner.

## Markers, replay and ownership

Foundation `StreamFilterExec` forwards contiguous marker runs without calling
the predicate and applies one selection to data plus retractions. Its ordinary
no-marker path remains direct. The logical projection rewrite still prepends
marker/retraction columns to ordinary expressions. The documents correctly say
projection and asynchronous expression isolation remain prerequisites. They must
not claim arbitrary native expressions are already marker-safe everywhere.

The existing package identity and codec are useful building blocks; they do not
prove deterministic replay. Requiring fixed source/snapshot identity and prepared
output when identical replay cannot be established preserves the redesign’s
correctness. Native relation output alone establishes neither live StreamSource
checkpoint participation nor durable input identity.

The prototype retains `Arc<Library>` in its UDF but returned Arrow arrays can
outlive that UDF. The revised documents expose the missing lifetime proof and
recommend process-retained code without using that to justify retaining session
allocations. Full argument-field metadata is also absent in execution initialization,
which reconstructs fields from array types. Both are actual integration work.

## Primary-source semantic checks

Spark 4.2.1 source at `617618396087429b5627a86ce933bb0f5d6645cb` was inspected
using Git objects in `/Users/alexy/src/spark-sdp-4.2.1`. `ScalaUDF.scala` and
`PythonUDF.scala` both define determinism as the function declaration combined
with deterministic children. This supports preserving explicit function semantics;
it does not imply Spark’s API or optimizer is the contract for Comet kernels.
No Spark engine was executed and no intentional Spark difference was runtime-qualified.

Also inspected the pinned official
[Comet C ABI source](https://github.com/apache/datafusion-comet/blob/0f7f8e45399847715093b3d3affdfa97614b39dc/native/comet-udf-sdk/src/c_abi.rs).
Its stability statement disclaims compatibility across Comet releases, while the
Arrow-only surface removes the host dependency-version match. Its initialization
contract reserves scalar argument bindings as absent in ABI v1. A null pointer
is compliant, not a prototype bug. The revised documents correctly refuse unsupported
constant-dependent typing instead of silently extending that interface.

## Compliance and execution limits

Read the full saved request, repository governance, LAKESAIL, SHEHAB, CLARITY and
WRITING-RULES, and the complete reviewed documents. No context compaction occurred
in this review. No builds, benchmarks, tests, cleanup or external messages were
performed. This report records independent source/document inspection; the
optimized filter run is owned by the lead and is outside this verdict.
