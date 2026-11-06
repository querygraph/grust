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
