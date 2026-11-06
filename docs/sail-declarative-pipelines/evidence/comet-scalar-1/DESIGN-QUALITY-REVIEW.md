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
