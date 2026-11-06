# Projection composition: Research evidence

Owning the projection rule and its private helpers is the smallest coherent way
to correct the demonstrated rule-level failure while retaining column pruning.
The exact shortcut-removal mechanism still requires an unchanged-copy control and
a corrected-copy run. This report records source inspection and inspected prior
execution receipts, not a new execution or a final candidate review.

## Scope and verified starting state

Source worktree: `/Users/alexy/src/sail/tmp/projection-composition-20261105-6e4da8d3`.
Starting HEAD is `6e4da8d33ba1bf4073fcb853123f81860ef18151`; upstream comparison
base remains `b52144955b629314a000b1fe49eeea97fa3d0c5c`. The new upstream main was
inspected separately, with no rebase. The before-code plan matches its receipt:
SHA-256 `70f66f814b30d865258e5350c1c3cd4ed4eb58a4bf0fe7206a419da2d2d16bb3`.

I read the full saved request and plan, AGENTS.md, LAKESAIL.md, SHEHAB.md,
CLARITY.md, WRITING-RULES.md and applicable Sail source instructions. The full
SDP, Extensions, performance, configuration and fencing objective remains active.
This role performed no builds, runtime tests, source edits, commits or remote
mutations. Only this assigned evidence file was written.

## Demonstrated failure and the narrower mechanism hypothesis

The prior worktree's `review-logs/performance/projection-alias-rule-v1.log` and JSON
receipt record execution at the starting HEAD, exit 101, with source unchanged.
The executed probe matches SHA-256
`8ae4fbabcd340186fbe6dc7219a6d4197c7b4c356f599d1eac25a2695c5406d8`;
the log is `57c152c968a0d51b85f8abdb8b3cb897f2f1c44426c7ade0265be52a77028db3`.
Both arithmetic cases retain [3,4,5,6] after analysis and filter pushdown, then
produce [2,3,4,5] after the public OptimizeProjections rule. Both identity controls
retain [1,2,3,4] at every stage. The probe uses fresh contexts and excludes the full
logical optimizer, common-expression sharing and streaming lowering.

DataFusion 55.2 `optimize_projections/mod.rs:559–568` returns one projection whenever
its expression vector equals its child's. Identical `v + 1 AS v` expressions read
different intermediate bindings; textual equality does not make composition
idempotent. The ordinary substitution path at 593–638 resolves the parent's column
against the child expression, and `rewrite_expr` at 695–724 performs that replacement.
Deleting only the equality shortcut is therefore a precise, refutable candidate.
The isolated execution attributes the failure to the public rule, not yet to that
individual branch. An owned unchanged copy must reproduce it before the branch
removal is judged.

The fallback's existing usage-count/placement check at 575–585 is not a general
proof about volatile or conditional evaluation scope. Test those properties against
both unchanged and corrected copies, including non-equal expression controls, so an
inherited fallback issue is not mislabelled as introduced by this change.

## Exact ownership boundary

All cited DataFusion files were compared byte-for-byte with the cached 55.2.0 crate.

| Implementation to own | Lines including comments and license |
| --- | ---: |
| `optimize_projections/mod.rs:1–888`, before its test module | 888 |
| Private `optimize_projections/required_indices.rs` | 220 |
| Private `utils.rs:57–90`, referenced-index entry point and recursive visitor | 34 |
| Total production source before import/attribution adaptation | 1,142 |

The main file's remaining 1,577 lines are tests requiring private `crate::test`
helpers and a snapshot macro. They are separate from production ownership.
`NamePreserver` is already public through `datafusion_expr::expr_rewriter`; other
expression, schema, optimizer and traversal dependencies remain public imports.
The small private referenced-index walker includes correlated outer references
and all four subquery expression forms; replacing it with a plain column scan would
weaken the copied behavior.

Retain exact initial extracts, Apache licensing, version-pinned CREDIT and raw
comparisons. Keep the final semantic change narrow. Replace the stock rule at its
existing position in `sail-logical-optimizer::default_optimizer_rules`, and use the
same implementation in `streaming_preparation_rules`. `sail-session` delegates to
the first list and only removes a different rule. Neither a second optimizer
framework nor a vendored crate is needed.

Recursion protection is a real integration dependency. The upstream recursive
function at line 126 uses `cfg_attr(feature = "recursive_protection", recursive::recursive)`.
Sail enables this feature on DataFusion, not on the receiving Sail crate. Preserve
that protection explicitly when adapting the copy. `recursive` 0.1.1 is already
locked; adding a direct dependency need not change its version. Its inspected
implementation wraps calls with `stacker::maybe_grow`; do not substitute an
unprotected recursion or infer a zero-cost implementation.

## Alternatives and boundaries

The public rule has no switch for the shortcut and no public merge-function hook.
Disabling the rule discards pruning and other projection optimizations. Repairing
its output cannot recover discarded computations. Alias-renaming or selective
pre-merging wrappers must preserve qualification, metadata and subquery scope,
while accounting for pairs formed internally; that is a broader correctness burden
than owning the rule. A future upstream fix could end this ownership, but no
compatible replacement version was established by this investigation.

Spark 4.2.1 source at commit `617618396087429b5627a86ce933bb0f5d6645cb` independently
uses producer/consumer substitution in CollapseProject. Its Optimizer.scala
1234–1300, 1426–1477 and 1529 onward distinguish producer bindings and preserve
names/metadata while applying deterministic/use-count eligibility. This supports
dependent composition, not every detail of the Sail proposal. Read through Git
because the local checkout is sparse; no JVM parity run was performed.

The requested canonical local DuckDB and Polars paths do not exist. Searches under
`/Users/alexy/src` did not locate their projection source checkouts. No engine
behavior or alternative algorithm is inferred from that absence, and no broad
external research or new clone was needed to resolve this concrete ownership choice.

## New upstream main

`5c0381bb3105ab38bf808cbe3e68a3e0aae619e6` follows the separately inspected CASE/IF
change `5411f84330e8172acb22dd477044f42c07fcc2e5`. Its two-file delta fills missing
nullable fields in `resolve_query_to_schema` with typed nulls, preserves target
metadata, and gives a named error for missing nonnullable fields. The accompanying
DataFrame.to tests cover nested types, metadata and zero-column positive-row input.
It does not change projection optimization, dependencies or this failure. Neither
changed path overlaps the current cumulative source delta against the upstream
base. The raw two-commit-endpoint diff SHA-256 is
`62db43545df7c64f597e25bd15579e6eeafbf710130615b68f19f1d15a6e0610`.
This is source inspection, not a merge, test or compatibility verdict.

## Reproduction pins

Registry root: `/Users/alexy/.cargo/registry/src/index.crates.io-1949cf8c6b5b557f`.

| Artifact | SHA-256 |
| --- | --- |
| DataFusion optimizer 55.2.0 crate | `acfb8cea6e05e2e75bae183340cf7d53cccb3db0449e2f1fbc07654d980fd19f` |
| Full projection module | `033142c1aed8a542a0aaa74130d9c7af045aa7583e85c978e3b7cfab06d97541` |
| Exact 888-line production prefix | `9d9195e6cb38e2a24e72e6e9e525a4117a3ad23c6d54b3b103f6baa1f77a6a60` |
| Required-indices module | `a5883edf5409036250e334abc1a81fdca5cf8ce8c7cc1935a3d3bcb3d8bcca9d` |
| Exact 34-line referenced-index helpers | `2b4e07c6556204de7889157fb50aa8f0d9407444f92e8e3c6580ce616d223f40` |
| Full utils.rs | `5be84cefe62b5aba884f494ba9456e6a05f30094c20f215bda8528b1c3e7a2f4` |
| Recursive 0.1.1 crate | `0786a43debb760f491b1bc0269fe5e84155353c67482b9e60d0cfb596054b43e` |
| Recursive src/lib.rs | `9d479f4b662a1233ac542ee150b1d2f1d0ae64dbff500f53a8751e3adfeb9606` |
| Spark Optimizer.scala Git blob | `92ad566793ceac9684e24632515908cbb2f755905e9a17148058968715c982ed` |

The rule's public reference is the version-pinned
[DataFusion projection module](https://github.com/apache/datafusion/blob/55.2.0/datafusion/optimizer/src/optimize_projections/mod.rs).
Local archive comparisons above are the evidence actually inspected.

Recorded: 2026-11-06T06:56:27.271277+00:00


## Frozen v1 cumulative source review

**Research verdict: no outstanding source or dependency-ownership defect found in
this candidate. This is not a readiness verdict.** The wide, deep planning cost
remains unresolved, and the full immutable gate is pending.

I reread the saved request, referenced continuation, all governing documents and
applicable Sail instructions after compaction. I also read the original,
schema-preservation and guarded-shortcut plans, verified each retained plan hash,
and read the current outward proposal. This review performed no builds, tests or
source edits.

| Verified boundary | Exact pin |
| --- | --- |
| Starting HEAD | `6e4da8d33ba1bf4073fcb853123f81860ef18151` |
| Frozen index tree | `a4801a8e6fb2d10d041d07aef9fc9ec1b7ff2bb6` |
| Increment patch SHA-256 | `72d0cd710862bc0b4676f357e8c451813f365dfeb27f87fc3daf2dd03db82a0e` |
| Cumulative patch against upstream `b52144955` SHA-256 | `8898a1d1a5b0ae74c3189b022ae7f9c7947675cdde78ef0ff1eb5a29bb322b2f` |

I regenerated both patches from the index, compared retained patches, checked all
85 cumulative file hashes against staged and working bytes, checked all 11
increment paths, and confirmed no unstaged tracked changes. The 74 previously
reviewed cumulative files outside this increment are byte-identical to the
starting commit. Prior foundation, Comet, projection and participation Research
reviews therefore retain their source boundaries. I reviewed the complete new
owned implementation, both integrations and all three new test files, with the
existing compilation and streaming-preparation context.

The original extracts match the cached DataFusion 55.2.0 crate byte-for-byte. I
reconstructed all three `ownership/*comparison-final-v1.patch` files and verified
all source, owned-code and comparison hashes in `comparisons-final-v1.json`.
The main comparison excludes the final test-module declaration and normalizes its
trailing blank line; the snapshot independently pins the whole file. The retained
index walker includes the original trailing blank line, hence 35 retained lines
rather than the earlier 34-line functional boundary. No algorithm was added to
that walker or RequiredIndices. The Apache license and pinned CREDIT remain.

The substantive changes are confined to the equality shortcut and projection
schema retention in `optimize_projections/mod.rs:548–574,644–649,841–898`.
The shortcut requires equal expression lists and restricts each position to a
literal or a column naming that same child output position, after stripping aliases.
Computed expressions, swaps and cross-position dependencies use the original
substitution path. Full declared schema equality is additionally required before
identity elimination. Both ordinary optimization and streaming preparation replace
the stock rule in place with this same implementation. Explicit
`#[recursive::recursive]` retains the enabled upstream recursion protection using
already-locked recursive 0.1.1; this does not claim zero overhead.

The schema adaptation uses public APIs appropriately. DataFusion 55.2
`Projection::try_new_with_schema`, `logical_plan/plan.rs:2476–2496`, checks column
count rather than validating expression-derived types. Its use here retains the
valid declared output for equivalent composition, not an arbitrary type override.
Pruning clones original qualified fields and metadata, and calls
`FunctionalDependencies::project_functional_dependencies`,
`functional_dependencies.rs:292–332`. That helper remaps retained indices,
drops dependencies missing a determinant and preserves dependency mode and
nullability. RequiredIndices supplies sorted, unique indices. The full-schema
comparison includes those dependencies. Physical tests check metadata, actual
values, types, nullability and positive-row zero-column output, which is stronger
than merely constructing a logical schema.

I inspected the retained execution records rather than executing them. The
unchanged-owned arithmetic control fails while direct and identity controls retain
their oracles. `unchanged-metadata-registration-v1.log:160` records identical stock
and unchanged-owned loss of explicit qualifiers and metadata; all three selected
metadata/registration tests failed. The corrected arithmetic probe passes unchanged
oracles. The final guarded-shortcut control changes only the predicate back to
broad equality: two positional tests fail, and both pass after restoration. Its
candidate hash matches the frozen module. These controls establish the targeted
failures; they do not prove every inherited optimizer transformation correct.

`corrected-tests-v3.log` records 163 passing selected Rust tests and one skipped
test. Strict affected Clippy and Rustdoc logs finish successfully. The preliminary
public receipt and log now record 51 passing tests with a server version probe of
4.2.1. These are inspected root-run results, not an independent execution or a
full immutable-gate result. The Arrow matrix covers every type family with finite
parameters and placeholder payloads, not every possible value or layout. Volatile
and conditional tests cover explicit representative evaluation-count contracts;
Spark JVM parity remains unexecuted.

The retained debug diagnostic validates exact output for all eight cells before
comparing rewrite cost. Its wide 64-column, depth-32 identity case records a
1.4392 median owned/stock ratio on this shared host. The optimized repeat is pending
in the evidence inspected here; the slowdown is not dismissed as noise. Earlier
failures and all cost cells remain retained. Neither this review nor these
component results establish completed SDP recovery, target fencing, extension
integration, configuration delivery or general performance readiness.

Recorded: 2026-11-06T08:14:21.734381+00:00


## Frozen v2 review and unique-ownership counterexample

**Research verdict: v2 has a confirmed introduced stack-overflow regression and is
not ready.** The source-derived risk was tested before attributing a runtime failure.
The value/schema argument for the identity fold is sound within its stated binding
conditions, but destruction of its skipped input chain needs correction.

| Verified boundary | Exact pin |
| --- | --- |
| Frozen index tree | `1935edac69836542b67aa5ca25f5d794c14ee2b4` |
| Increment SHA-256 | `42199c5a97525b898e516db90d415ecfed8f6098415ec3f58383dcadabb56101` |
| Cumulative SHA-256 against `b52144955` | `3dd8b8f09be9506f0fce1b3f4f611817d7567e47b4788c8a6b90eae0e5269bee` |

I reread the saved request, governance, applicable source instructions and all
amended plans, including PROJECTION-IDENTITY-FOLD.md and the retained before-code
identity-chain plan. I independently verified all 85 staged/working file hashes,
11 increment paths, both regenerated and retained patches, and all three final
ownership comparisons. Only the rule and its two Rust test files differ from v1.
The raw and normalized source-hash annotations added to comparisons-final-v2.json
accurately distinguish the intact original extract from the comparison prefix.
The recursive attribute, dependency version, registrations and earlier schema
adaptations are unchanged.

The new fold at `optimize_projections/mod.rs:549–567` checks full-width bare columns
against each immediate child's qualified fields, borrows through matching identities,
and reconstructs once with the complete outer schema. It does not admit partial or
reordered selections or duplicate a child computation. Expression equality at the
end chooses which vector to retain; it does not establish identity. The new tests
cover schema/dependencies, selection order, finite-depth computation and guarded or
volatile work. The inspected 165-test pass predates the final prefix-case expansion;
the full frozen test gate and public v2 qualification remain pending.

A distinct lifecycle risk follows from keeping ownership of the original `input`
while borrowing to a deep descendant. Returning can drop the uniquely owned skipped
Arc chain recursively. DataFusion 55.2 LogicalPlan and Projection have no custom
iterative destructor. The optimizer's entry recursion annotation does not add a
per-node guard to that destruction. Default `skip_failed_rules=false` and Sail's
owned preparation path do not require a shared plan that would mask the effect.
This was initially a hypothesis, not a reported cause.

After a written diagnostic plan, Research prepared only evidence-directory artifacts.
The root reviewed and executed two separately filtered tests from the same binary.
Each directly constructs a chain over one qualified-field EmptyRelation, checks
every plan Arc has exactly one owner, moves the plan into the rule without cloning,
and uses an explicit 1 MiB thread stack. The prior rule receives only temporary
module-path adaptation; no behavior is changed. The original leaf and schema are
the result oracle. Retained run:
`review-logs/performance/identity-drop-v1/runs/20261106T090745.131823Z/`.

| Variant | Observed outcome |
| --- | --- |
| Prior v1 rule | Both depths 8,192 and 16,384 returned the expected leaf/schema and joined; exit 0 |
| Frozen v2 rule | Depth 8,192 constructed successfully and passed uniqueness checks, then explicit stack overflow and SIGABRT after `before_rewrite`, before `after_rewrite`; Cargo exit 101 |

The second outcome is runtime execution, not a build failure. The shared executable
SHA-256 is `e9c02632c849382b496856baec296bcf51e36db703ed6dd5a4d16f803c331444`.
The executed probe is `228e0d58d9cce8fd48763db48c7b5d7db6f41d8b86b10ff8d840c49e88a2c866`;
the executed runner is `94d0392c28cc3a9b38fde197f2f495599b4f48d3115f1ecc9c00a9559f5cf10e`.
Its receipt preserves separate processes, phase markers and exact artifacts.
I independently rechecked all 85 source hashes, index and absence of unstaged changes
after restoration. The controlled comparison establishes an introduced rewrite-time
overflow. Recursive destruction is the source explanation; no debugger stack trace
was collected to claim direct frame-level observation.

The optimized ten-cell diagnostic belongs to this frozen source and preserves the
previous cost evidence. It does not supersede the lifecycle counterexample or imply
a general performance/readiness result. Performance qualification remains with its
independent role. This review ran no build or test itself and changed no production
source. The root-run negative control is evidence inspected by Research.

Recorded: 2026-11-06T09:09:30.828786+00:00


## Frozen v3 review: unique-chain fix and shared-retirement contract

The original unique-ownership overflow is corrected in the inspected control.
One source-contract finding remains: use atomic retirement rather than discarding
`Arc::try_unwrap`'s error when another plan owner may retire concurrently.

Verified tree `21849a5803fcad439c651087885c101046ee2921`, increment SHA-256
`437725b92d01339d336f055b234f5c720447358d42dacadcbb347155fb7db3bd`, and cumulative
SHA-256 `e8cfb314bd6fe1e8887b21d63ca98c4bca33c71f497a33e699b3a4156e0c6e6e`.
All 85 file hashes, 11 increment paths, index, working bytes and retained patches
match. Only the main rule and logical tests differ from v2. All three final-v3
ownership comparisons reconstruct exactly, with raw and normalized scopes explicit.
I read the saved request and before-code ownership plan; applicable governance and
source instructions remain the ones reread for this review sequence.

The retained replacement input stops iterative release at the surviving subtree.
The permanent test covers unique ownership and a retained shared midpoint, exact
schema/leaf results, unchanged shared tail and cleanup through a second rewrite.
In `identity-drop-v2/runs/20261106T091500.858024Z`, the original probe `228e0d58…`
and runner `94d0392c…` are byte-identical to the failing control. Baseline and current
now pass both depths using the same executable
`74164ab0a404310bf15629fdd2d0a91150da0759bd7fc7e7a3b689f4bbb62d26`.
I inspected their phase markers, log hashes and restored source/index. This closes
the reproduced single-owner failure, without erasing its original receipt.

The loop still immediately drops an error Arc returned by `try_unwrap`. If another
owner retires between that method's check and the error's destruction, this caller
can become the final owner and recursively drop the chain. The documented remedy
is `Arc::into_inner`, stable since Rust 1.70: it consumes the ownership count and
returns the last value directly. Rust 1.98.1 documents this exact linked-list
retirement hazard and implements the atomic alternative in
[alloc/src/sync.rs](https://github.com/rust-lang/rust/blob/1.98.1/library/alloc/src/sync.rs#L1034-L1204).
This is primary-source API analysis, not a newly executed concurrent Sail failure.
The current shared-tail test deliberately keeps its second owner alive, so it
cannot establish the concurrent-retirement guarantee. Changing the loop pattern
from `Ok`/`try_unwrap` to `Some`/`into_inner` preserves its structure and retained-tail
boundary without extra guards or dependency ownership.

Mechanical-v4 records strict workspace Clippy, nightly formatting and Rustdoc
success on this tree. The final optimized diagnostic retains all ten cells,
including the shallow wide ratio above one. Those records are inspected root-run
evidence, not independent execution or broad readiness. Full immutable and public
v3 qualification remain pending. Research performed no builds or source changes.

Recorded: 2026-11-06T09:19:49.883132+00:00


### Atomic-retirement source closure before final freeze

The current rule uses `Some(Projection(previous)) = Arc::into_inner(discarded)`.
I verified its entire file differs from the archived pre-change source only in
that API/pattern replacement. The main-file SHA-256 is
`ab210de37085fdce9854a09ce0380872749f2be5d2c71d06e95773fbd0920653`.
The retained-tail owner and pointer-equality stop are unchanged; the before-code
atomic-retirement plan hash matches its receipt. This closes the shared-retirement
API-contract finding using the pinned Rust contract above. It does not claim a
newly reproduced concurrent failure or universal safety for destruction by external
owners. No remaining mechanism concern was found within this ownership scope.
Final frozen hashes and the repeated root-run checks are still required.

Recorded: 2026-11-06T09:20:31.649206+00:00


## FINAL V4 Research verdict

**No outstanding Research source, API-contract or ownership-provenance finding
remains for this frozen candidate.** This closes the two lifecycle findings within
the stated projection-chain scope. Full immutable and public qualification remains
pending; this source verdict does not establish completion of the full project.

| Independently verified boundary | Exact pin |
| --- | --- |
| Starting HEAD | `6e4da8d33ba1bf4073fcb853123f81860ef18151` |
| Frozen index tree | `b337dfd145db4773ba1aa019028a8e9c86bbaa67` |
| Increment SHA-256 | `d0be097703b5ce7ba7f1e8400dfd486ee492f9d64f2c91437a8e4f86409cc227` |
| Cumulative SHA-256 against upstream `b52144955` | `01226d1ed79d26afa4cd9e36d1e331b365d3ad4ba93c434fbbc50636262c991c` |

I reread the saved request, governing AGENTS.md, LAKESAIL.md, SHEHAB.md, CLARITY.md,
WRITING-RULES.md and the atomic-retirement before-code plan. The applicable Sail
source instructions were read during this review sequence. The plan hash matches.
I verified all 85 cumulative file hashes against both staged and working bytes,
all 11 increment paths, both regenerated and retained patches, HEAD and index,
and the absence of unstaged tracked changes. V3 to v4 changes exactly one production
line, replacing `Ok`/`try_unwrap` with `Some`/`into_inner`. All other source is
byte-identical to the previously reviewed cumulative candidate.

All three final-v4 comparison patches reconstruct exactly from the retained pinned
DataFusion extracts. Raw-source, normalized-prefix and full-owned-file hashes match
their declared scopes. Licenses, attribution, recursion protection, helper behavior
and both rule-registration points remain as reviewed. The new retirement line uses
the verified Rust 1.98.1 ownership contract while preserving the surviving input
owner and pointer-equality boundary. The shared-retirement finding closes by that
source contract, not by claiming a newly executed concurrent failure or race proof.

The retained follow-up
`identity-drop-v3/runs/20261106T092201.365516Z` targets this exact candidate. Its
probe `228e0d58…` and runner `94d0392c…` are byte-identical to the original failing
control. I verified the executed artifact and log hashes. Both baseline and current
complete depths 8,192 and 16,384 with exact original schema/leaf assertions and
successful thread joins, using the same executable
`a566ea16541d1f4804dc7921a9fd6f005cc2c4c392dc77d24aaac463134467e1`.
The receipt and independently checked working bytes confirm complete restoration.
The original failing run remains retained.

Mechanical-v5 records successful nightly formatting, strict workspace Clippy and
Rustdoc on this tree before freeze. The 166-test result with one skipped test
precedes the final API replacement and is not relabelled as a v4 full-suite run.
The final optimized cost receipt's source hashes match v4 and all ten cells retain
seven samples. Its deep-wide ratio is 0.91687 and shallow-wide ratio is 1.02469;
these are shared-host rule-rewrite diagnostics, not production latency or a general
performance guarantee. The independent Performance role owns that qualification.

This final review prepared no new diagnostic artifacts, executed no tests or builds,
and changed no source. Root-run execution evidence was inspected. Existing finite
Arrow/type/value coverage, external-owner destruction limits, unexecuted Spark JVM
parity and the incomplete broader SDP/Extensions/configuration/fencing goal remain
explicit limitations.

Recorded: 2026-11-06T09:26:52.324703+00:00
