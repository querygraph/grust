# Standalone Comet scalar adapter design review

Reviewed at 2026-11-05T23:27:05.746355+00:00.
Implementation base: `2c9fa84994d317aade0d1c69faa9a378c780127d` in detached worktree
`/Users/alexy/src/sail/tmp/comet-scalar-20261105-2c9fa8499`.

## Design verdict

The selected increment is coherent and follows committed decisions E1, E3 and E4.
A standalone adapter can establish the binary call, metadata and ownership contracts
without simultaneously changing package discovery, worker lookup or the existing
DataFusion-FFI route. Those integrations remain necessary later; this increment
does not redefine the completed product as a local scalar fixture.

Process-retained library code is the simplest initial ownership mechanism matching
the existing host policy. A result can outlive its UDF, plan or session, so retaining
code only in the UDF is insufficient. Retaining code does not justify retaining
session state or funded memory leases. Tests need to distinguish those resources.

Comet's pinned contract requires trusted pure immutable functions and reserves the
constant-argument pointer as null. Making native-library admission explicitly unsafe
states the real trust boundary. A numeric probe cannot validate arbitrary callbacks,
prove purity or make an incompatible/malformed Arrow export safe.

Preserving exact argument Fields during execution repairs a concrete discrepancy
with planning, which already receives names, nullability and metadata. Checking
execution initialization against the planned return Field makes disagreement a
query error before interpreting output using a different declared schema. It does
not replace the trusted kernel's obligation to export valid Arrow arrays.

## Conditions for the implementation review

- Apply the unsafe trust contract to every public entry point that accepts or loads
  callback records, including direct UDF construction if it remains public.
- Retain library handles for callback lifetime. Do not turn retention into a
  path-based lookup that silently selects older code after a file changes; package
  content identity and worker admission are separate integration work.
- Keep code retention independent of per-call kernel instance release and result
  release. Error paths and partially initialized records must release their owned
  resources while callbacks remain callable.
- Compare full argument/return Fields rather than only Arrow data types. Preserve
  nullability and extension metadata through both planning and execution.
- Report the handwritten fixture as an internal utility contract check. SDK-built
  Comet interoperability, package loading, cluster execution, marker isolation and
  durable replay require their own evidence.

No architectural blocker was found in this bounded design. Final source readiness
remains conditional on inspection of the completed cumulative patch and executed
checks; this initial verdict does not approve code that has not yet been reviewed.

## Documents and compliance

- `DECISION-NOTES-EXTENSIONS.md` SHA-256 `7b7af5d7ffe5ffb7f4da2366f0fe83025c7b6fd3d61be5247dda65c737efdeb7`
- `EXTENSIONS-ON-ARROW-C-ABI.md` SHA-256 `d47d62b93c8a1136c31fb043d4b49ba9851e04c94c537e8b81d26921c4878d34`
- `EXTENSIONS-STREAMSOURCE-INTEGRATION.md` SHA-256 `900d5168cc7122ccd6c5cf00a5efa1e3ba6e74ce4ec46261a3ede450a15205fa`

Read the full saved request, user clarification “from Comet”, repository AGENTS,
LAKESAIL, SHEHAB, CLARITY and WRITING-RULES. Their complete text was read in this
reviewer's current context. No context compaction occurred afterward. Read the
complete E1/E3/E4 notes and companion scalar/integration designs before assessing
the initial copied prototype source. No builds, tests, source edits, cleanup,
remote actions or runtime claims were performed by this reviewer.

## HUMAN-REVIEW.md compendium review

Reviewed 2026-11-06T00:22:38.765954+00:00. Document
SHA-256 `f1b9e7836840e3c6c72191f502e8ecbbd196f0542973352ef2ba2939f864f23b`, 1632 words.
Read the complete new user steering saved in REQUEST.txt before this review.

The compendium supplies the requested bird's-eye scope: continuous declarative
pipelines, ordered change capture, existing Extensions, the Comet scalar route
and measured performance advances. It explains durability from concrete failure
cases, identifies Sail's existing execution and ownership seams, preserves both
extension routes and distinguishes inspected/proposed behavior from qualified
implementation. Its dependency section explains why expression isolation, stable
identity, preparation and fencing constrain later code without turning document
order into an approval sequence. Maintainability and human review are explicit.

Three precision findings were sent to the lead:

- Identify the existing extension host as integration-branch reference code rather
  than implying it is already on the upstream-based foundation.
- State the default change-capture conflict horizon as the prepared interval and
  current durable versions; exhaustive superseded-history checking requires its
  own retention and resource policy.
- Explicitly include immutable saved output or a proven identical replay path in
  the preparation paragraph, so recovery does not appear to rely on positions
  and effect identities alone.

These are narrow clarification edits; the structure and overall design are sound.
The accompanying optimized-performance evidence records both dense and sparse/
grouped cases and supports the document's measured-overhead statement. This
review inspected those retained summaries and did not execute their probes.
No source edits, builds, tests or remote actions were performed.

## Final frozen source review

Reviewed 2026-11-06T00:32:15.056371+00:00. Verified
index tree `d8e9633355f2bac78ab9470e49aceda1992d2388` and all twelve snapshot file hashes. The incremental
diff against `2c9fa84994d317aade0d1c69faa9a378c780127d` has SHA-256
`0561254aaed99782dd50a4901f4c28162f799748cfcdac7dd6f5f6ea08676d64`. The cumulative diff against upstream
`b52144955b629314a000b1fe49eeea97fa3d0c5c` has SHA-256
`59706bb772a2ef606b2bab5657fbe2fe8f18507661110eb0baf53dac50caa376`. No unstaged tracked source changes were present.

Read the complete new adapter, ABI, loader, fixture and three integration-test
modules, crate manifests and lockfile delta. This pass reviews the new twelve-file
increment on the previously qualified foundation parent. It does not independently
rerun or extend the foundation gate.

No must-fix design issue was found in this frozen standalone implementation:

- `load` is unsafe and refuses nonimmutable declarations before opening code. Its
  safety contract names pointer/layout validity, ownership transfers, non-unwinding
  callbacks, factory concurrency and truthful purity. The probe is not presented
  as proof of those obligations. Direct construction is crate-private unsafe.
- Opened handles enter the process registry before probe/discovery callbacks.
  Constructor retention also precedes its callback use. The registry contains
  library handles rather than sessions, kernel instances or memory leases.
  Kernel/list/instance records retain their ordinary release paths.
- Retention compares Arc identity rather than resolving code by filesystem path.
  It does not silently reuse an old implementation when a path changes. Each
  opening is retained, including refused libraries. Admission must therefore be
  bounded by the caller; content identity and admission policy remain package-host
  integration requirements. This is explicit in code and design.
- Planning and invocation pass the actual argument Fields. Execution checks
  argument field count, types and allowed lengths before exporting user arrays.
  The ABI permits length-one scalar broadcast, as confirmed in its pinned source.
  Return compatibility checks exact DataType including nested Fields and metadata,
  while accepting ignored top-level names and safe nullable widening. Output row
  count and nonnullable output are checked after import.
- Per-call instances and borrowed schema exports remain scoped. Error strings are
  copied before releasing their instance. Returned arrays can invoke release code
  after UDF/plan/library-owner drop because the code handle is process-retained.
  Invalid producer pointers remain outside the explicit unsafe contract.

The small code registry is simpler than introducing ownership wrappers around
every exported allocation at this stage. It deliberately trades unloadability for
a straightforward callback-lifetime rule. The full product still requires bounded
package admission and separation of code from existing retained session owners.
There is no new dependency version movement; the lock delta adds the two local
crate entries using already resolved dependencies.

Retained evidence shows thirteen focused tests and two independent pinned Comet
producer probes passing, with strict Clippy reported by the integration owner.
Inspected the independent probe log, including contained initialization/execution
panics. These are inspected execution records, not tests run by this reviewer.
The final immutable gate has not yet completed and is not inferred from those
focused results. Tests require the fixture library to be built first, as their
helper states; this remains a prerequisite for a fresh gate.

The revised HUMAN-REVIEW.md now distinguishes the reference extension host from
the new foundation, states the default conflict horizon and requires saved output
or proven identical replay. Those earlier precision findings are resolved.
The updated standalone plan also explains the DataFusion alias/nullability rule.

Saved REQUEST, current HUMAN-REVIEW and the governing instructions were reread as
applicable; no context compaction occurred during this pass. No source files,
builds, tests, cleanup or remote state were changed by this reviewer.

## Frozen v3 delta review

Reviewed 2026-11-06T00:49:25.928095+00:00. Verified
tree `ad453e21427f3f702a342a033dc6c488ab9a7195`, all fourteen file hashes, incremental SHA-256
`a4a1634ae6c0d087f5735cb911da43be19529fec10145ff4333c947562214224` and cumulative SHA-256
`094bbb2510294c4e705cb0bd1dce41366b6bcb74d12bc25ba372af09d67406a3`.

The new nullary signature delegates actual arity to kernel initialization while
allowing DataFusion to plan zero-argument functions. The fixture and observable
DataFusion test exercise that capability rather than only direct invocation.
The missing-probe check now uses a controlled loadable library instead of relying
on executable-loader platform behavior. The planned-field test requires the
specific agreement error, so a later unrelated error cannot satisfy it.

Independently compared the copied Comet factory, instance and discovery sections
against the retained pinned upstream SDK source, ignoring formatting whitespace
only. No nonformatting difference was present. Attribution, source pin, Apache
license text and Sail-facing type aliases make the ownership boundary explicit
and reduce the maintenance risk of silently reinterpreting the records.

Read COMET-SCALAR-NULLABILITY.md before reviewing its guard. The guarantee is
explicit: a nonnullable scalar result has no logically null evaluated rows,
including nulls reached through encoded representations. Checking only physical
validity would not establish that guarantee. The new tests exercise nonempty
dictionaries, run ends, both union modes and Null, preserve nullable outputs,
and distinguish unused null children from selected nulls. This is a narrow
property check rather than generic native payload validation.

The logical check runs only for planned nonnullable results. Its cost is material:
Arrow 59.2.0 RunArray::logical_nulls constructs a bitmap by logical row count,
and dictionary/union handling may scan or materialize null information. This
work is not funded through a new host reservation in the standalone adapter.
The preceding note correctly requires the caller to bound work and memory and
does not claim production resource qualification. Production package admission
still needs that bound; ordinary nullable results do not gain this scan.

Suggested one cheap ordering improvement before the final gate: reject a returned
row-count mismatch before computing logical nulls. Length inspection is constant
time, whereas a wrong-length compressed output could otherwise expand a bitmap
before receiving its already-necessary rejection. This does not require a broader
validation policy or change the valid-result contract.

The selected logical guarantee is coherent and its resource tradeoff is disclosed.
No architectural redesign is required by the v3 delta. The integration owner
reports fifteen focused tests and affected strict Clippy passing; final broader
immutable qualification remains pending. This reviewer performed source/document
and hash inspection only, with no builds, tests or source changes. Saved request
and governance compliance remains confirmed.

## Final design closure and source pin

Reviewed 2026-11-06T01:07:25.607967+00:00. Confirmed
final index tree `455101575ecbfbec6f843464ce178e0d09046f51`, all fifteen file hashes, incremental
SHA-256 `7477e67e9b6262e5aec067714c586ef7ac49790e8e6ac7d14116829213bdf325` and cumulative SHA-256
`743a1346feb7ae62a4cded0224b007312b471b09d80d149b2b0bdf5c25c25b30`. Tracked worktree source matched the staged candidate.
The copied Comet record sections still match their pinned upstream text except
formatting whitespace. Final Rustdoc link/CREDIT formatting changes do not change
the ownership or execution contracts.

The returned-length check now precedes logical-null work, closing the preceding
review recommendation. Read the revised first-principles nullability note before
assessing the replacement predicate. The final implementation no longer relies
on Arrow's logical-null bitmap helper: the source-derived single-child union
type-ID issue and compressed-run expansion are both material reasons to change
that dependency boundary.

A small Sail-owned presence predicate is a simpler fit than copying Arrow's full
bitmap implementation for an existence question. It uses public typed accessors
and short-circuits on null presence. Dictionaries inspect selected keys; union
slots follow actual type IDs and offsets; run-end arrays inspect only physical
runs intersecting the slice. Encoded values recurse. Present list/struct parents
remain present even when their children contain nulls. Empty arrays are nonnull
for this result guarantee, and nonempty Null arrays are null.

The source contains no logical-row bitmap construction. A compressed run stays
compressed during the presence check, apart from shared-buffer array slicing.
Dictionary and union traversal can still take work proportional to selected rows
and nested encoding depth. That remaining cost requires caller limits before
production package admission; it is not a measured performance envelope. Nullable
outputs bypass the new predicate entirely. No unbounded auxiliary cache or
per-row result archive was added.

The new nonzero-ID union tests cover direct unions and nesting through dictionaries
and run ends. Valid slices retain unused null children without false rejection.
The million-row run fixture distinguishes logical row count from physical run
count. These tests target the observed failure and resource boundaries rather
than mirroring a bitmap implementation. Inspected the relevant Arrow 59.2 public
run-index and union-offset accessors supporting the slice reasoning.

No unresolved must-fix design finding remains in this final standalone candidate.
The code keeps the original trusted-producer boundary, process-retained callback
code, per-call instance release and metadata/return-field compatibility design.
The parent foundation remains unchanged. Package/worker integration, session/code
owner separation, funded admission and distributed recovery remain required work.

The integration owner reports seventeen focused tests, affected strict Clippy,
two SDK probes and strict Rustdoc passing. This closure is source and evidence
inspection, not execution by this reviewer and not a completed immutable-gate
verdict. No source edits, builds, tests, cleanup or remote actions were performed.
Saved request, Human Review and governance compliance remains confirmed.
