# Projection composition: independent design review

Reviewed 2026-11-06T06:54:14.565671+00:00. This is a before-code/source-derived design assessment,
not an implementation, runtime or readiness verdict.

## Scope and compliance

Read the complete saved request and continuing full objective, grust-sdp AGENTS,
LAKESAIL, SHEHAB, CLARITY and WRITING-RULES. Confirmed source starts at detached
`6e4da8d33ba1bf4073fcb853123f81860ef18151` in
`/Users/alexy/src/sail/tmp/projection-composition-20261105-6e4da8d3`; upstream
base is `b52144955b629314a000b1fe49eeea97fa3d0c5c`. The before-code snapshot
names published documents `cac6ef0046e72e5daba7093b1a903adcb73ea89f`, plan SHA-256
`70f66f814b30d865258e5350c1c3cd4ed4eb58a4bf0fe7206a419da2d2d16bb3` and
implementation_started false. Read the full 296-word PROJECTION-COMPOSITION.md.
No nested source AGENTS/CLAUDE instructions were found in this worktree.

The full SDP, both Extensions routes, performance, enforced fencing and typed
configuration/optional Dhall objective remains active. This increment repairs
computation rather than redefining the full goal around projection optimization.
No builds, runtime tests, source edits, remote actions or cleanup were performed.
Only this assigned report is written.

## Required semantics and actual source

Each projection binds its column references to its immediate child's output.
Repeated text `v + 1 AS v` therefore composes additions, rather than proving that
the two projections are interchangeable. Inspected pinned DataFusion 55.2
OptimizeProjections production code. merge_consecutive_projections_one_level
compares the two expression vectors and, when equal, directly substitutes the
previous projection's input. That shortcut drops one dependent computation.
The ordinary fallback instead resolves each referenced column against the previous
projection's schema and substitutes that projected expression. Removing the
shortcut is the narrow source-derived correction to test.

Normal composition already contains work-sharing safeguards for nontrivial
expressions referred to more than once, alias/metadata handling, name preservation
and schema reconstruction. Keep those policies rather than substituting a small
arithmetic-specific optimizer. The defect is not limited to addition or Int64:
expression-text equality does not establish binding equivalence for other admitted
expressions or types either.

## Ownership and alternatives

Recommend ownership of the rule and its necessary private helpers, shared by both
normal optimization and mandatory streaming preparation. The faulty function is
private inside a recursive rule that creates and revisits projections internally.
A wrapper around the public root entry cannot reliably intercept all such pairs.
Renaming visible aliases around it introduces another naming/metadata mechanism
and misses internally created pairs. Disabling the rule loses existing column
pruning; postprocessing cannot reconstruct discarded computation. A preliminary
custom projection composer duplicates the exact binding, volatility, alias and
conditional policies already present in the dependency.

The proposed inherited production scope, approximately 1,142 lines, is justified
by private integration boundaries rather than new algorithmic complexity. Do not
judge it as a new thousand-line optimizer implementation. Preserve the original
file/module organization as practical, use public dependency APIs where available,
and own only the needed private code. Retain exact original copies, pinned
attribution/license and an independently reproducible comparison. Do not fold
unrelated cleanup or inferred dependency improvements into the ownership diff.

The private required-index traversal is part of the actual scope. It follows
correlated subquery outer_ref_columns while deliberately excluding internal
subquery schema columns. Replacing it with a simple column_refs collection would
change pruning semantics. Keep it verbatim except imports/visibility necessary for
the copy. NamePreserver is publicly re-exported and need not be reimplemented.

Preserve recursion protection explicitly. Upstream gates optimize_projections with
its crate feature, and Sail currently enables DataFusion recursive_protection.
The copied Sail module does not inherit that crate's cfg; retaining the same
annotation text without defining/enabling its feature would silently disable the
guard. Use the locked recursive implementation explicitly at the copied recursive
entry. Preserve all public behavior beyond the shortcut correction.

## Discriminating evidence still required

First wire the unchanged owned copy into both rule lists and reproduce the stock
wrong-answer oracle. Only then remove the shortcut and rerun the identical oracle.
This separates adaptation mistakes from the actual correction. Registration
controls should prove there is exactly one owned rule in the ordinary configured
position and the same owned type in streaming preparation, with no stock rule
running first. Preserve direct analyzed execution as an independent oracle.

Require identity projections, same-alias dependent chains of multiple lengths,
qualified sources, nested schemas/metadata, subqueries and actual source-column
pruning. Compare full output fields and schemas, not only row values. Retain
volatile evaluation counters, deterministic work-sharing controls and conditional
functions that fail if an unused branch is evaluated. Deep graphs need a real
recursion-protection stress control. Both batch and streaming paths must execute
the repaired graph with exact original expected results; prior wrong results
must never become an expected compatibility outcome.

One specific source-derived metadata risk was sent to the lead: the deleted
shortcut uses try_new_with_schema with the outer schema, while the normal
transformed composition path uses Projection::try_new over the previous input.
Construct equal-expression identity projections with distinct outer field/schema
metadata and qualifiers and compare stock versus owned behavior. The general rule
may already lose some metadata later; distinguish an introduced regression from
an existing limitation before adding a second correction.

Measure retained pruning and unchanged-result planning/execution costs rather than
reusing timing cells whose output was wrong. The existing shallow streaming startup
cost and mixed-marker execution cost remain separate open limitations. This fix
should establish the previously failed same-alias query before it can qualify any
performance comparison that includes that query.

The plan's statement about Spark 4.2.1 is source evidence reported by the lead.
The instructed /Users/alexy/src/sail/opt/spark source location is absent here; an
actual source location was requested for independent inspection. No executed JVM
parity is claimed. The required dependent-computation property is independently
supported by the direct graph semantics and inspected DataFusion substitution.

## Initial verdict

The narrow ownership approach is coherent and simpler than wrapping or disabling
the faulty rule. It corrects the dependency at its actual semantic boundary while
preserving pruning and one implementation across compilation paths. Endorse the
design for the authorized local reference increment, conditional on the unchanged-
copy failure, minimal corrected ownership diff, metadata/conditional/volatile
controls and cumulative qualification. No implementation verdict is issued yet.


## Frozen candidate: schema-preserving composition and guarded shortcut

Reviewed 2026-11-06T08:09:05.948492+00:00. Reconfirmed the full saved request and governance; read
the amended published plan and retained schema/performance plans written before
their dependent changes. This section supersedes blanket shortcut-removal advice
above while preserving its original evidence and reasoning.

Independently verified parent `6e4da8d33ba1bf4073fcb853123f81860ef18151`, tree
`a4801a8e6fb2d10d041d07aef9fc9ec1b7ff2bb6`, all 85 cumulative file hashes,
exact cumulative path coverage and all 11 increment paths. Regenerated staged
binary patches match retained final-v1 patches:

- Increment SHA-256 `72d0cd710862bc0b4676f357e8c451813f365dfeb27f87fc3daf2dd03db82a0e`.
- Cumulative SHA-256 `8898a1d1a5b0ae74c3189b022ae7f9c7947675cdde78ef0ff1eb5a29bb322b2f`
  against `b52144955b629314a000b1fe49eeea97fa3d0c5c`.

The final correction stays within the existing rule and compilation architecture.
One owned implementation replaces the normal configured rule in its existing
position and serves mandatory streaming preparation. Private required-index
traversal remains unchanged, including correlated outer references. The already
locked recursive implementation now explicitly protects the copied recursive
entry, independently of DataFusion's crate-feature cfg.

Schema preservation belongs in this increment. Unchanged stock and owned controls
both lose declared output qualifiers and field/schema metadata, a demonstrated
pre-existing defect in the promised projection contract. Final composition retains
the original outer DFSchemaRef. Column pruning selects the original qualified
FieldRefs and schema metadata, projects functional dependencies to the retained
indices and validates them through with_functional_dependencies. When no fields
are removed, retaining the existing schema avoids unnecessary reconstruction.
Projection elimination requires both identity expressions and complete schema
equality, including functional dependencies, metadata, types and nullability.
There is no new cast, schema-type override or nullability normalization policy.

Blanket shortcut removal preserved values but introduced observed deep-plan cost.
The final equal-list guard has a direct semantic proof. After top-level aliases,
each expression must be a literal or exactly match the qualifier/name of its
same-position child output. With equal expression lists, a literal is independent
of its child, while such a column reads the same original child expression at
that ordinal. Replacing the two layers with that expression over the grandchild
therefore preserves values. Exact qualified-field comparison is conservative and
linear in output width; it avoids repeated schema-index searches. Reorders,
cross-position references, arithmetic, functions and conditionals use ordinary
composition. Keeping the original outer schema preserves the declared interface
on the safe fast path too. This is smaller than separate literal/identity bypass
mechanisms or a second projection optimizer.

Read the full owned-source comparison. Full dependency originals, production
prefix, RequiredIndices and private index walker match the pinned local dependency
byte for byte. Both helper comparisons reproduce exactly. The main comparison
reproduces after selecting its documented production prefix and trimming trailing
whitespace; its comparison hash covers production, while the candidate manifest
separately covers the whole file including its test-module declaration. Behavioral
deltas are the guarded shortcut and schema retention/pruning/elimination. Other
changes are imports, explicit recursion protection, attribution/license, scoped
lint expectations for inherited code and formatting.

Inspected controls and receipts: the unchanged owned implementation reproduces
both arithmetic failures while identities/direct/filter controls remain correct.
Replacing only the guarded predicate with broad equality fails the two new
positional controls; exact restoration passes both. The selected test log records
163 passes with one pre-existing skip. Strict affected Clippy and Rustdoc finish
successfully. These are inspected lead-run receipts; this reviewer ran no tests.

Controls cover reordered/composite dependency remapping, removed determinants,
empty output and stable repeat optimization. Physical metadata/layout controls
exercise every Arrow type family and empty/nonempty batches through the owned
rule plus physical planner. Full batch/streaming compiler controls independently
compare original analyzed values and exercise volatile counts, shared child
outputs, conditional evaluation and marker preservation. Registration controls
prove exactly one corrected rule in each rule list. Do not expand the component
metadata controls into a claim about every other optimizer's handling of arbitrary
explicit schemas.

Independently inspected retained Spark source at
`617618396087429b5627a86ce933bb0f5d6645cb` and verified its four recorded file
hashes. CollapseProject uses producer alias bindings, conditional deterministic/
usage checks and alias-name/metadata preservation. That supports dependent
composition; no JVM differential execution is claimed.

Eight valid debug cost cells preserve final projection counts and scan pruning.
The original deep identity/constant regressions are repaired, but width-64,
depth-32 qualified identity retains a median 1.439 owned/stock ratio, with all
samples slower. Treat that as material pending the optimized repeat, rather than
as noise or an acceptable production envelope. Public cases, optimized cost and
the immutable cumulative gate remain pending. Earlier shallow-streaming startup,
mixed-marker execution, recovery/fencing, native integration and typed-config
obligations remain outside this correction.

Exact-source design verdict: no demonstrated source-level architectural blocker.
The final implementation is a coherent repair of values and declared schemas,
with a proven conservative shortcut and one maintained rule. This is conditional
local source-design acceptance, not global readiness or a performance waiver.
Only this assigned report was appended; no source edits, builds, runtime tests,
remote actions or cleanup were performed.


## Frozen v2: borrowed positional-identity chain

Reviewed 2026-11-06T08:58:43.608120+00:00. Reconfirmed saved request/governance and read the complete
PROJECTION-IDENTITY-FOLD.md plus its retained before-code chain plan. Parent stays
`6e4da8d33ba1bf4073fcb853123f81860ef18151`. Independently verified tree
`1935edac69836542b67aa5ca25f5d794c14ee2b4`, all 85 cumulative file hashes,
exact cumulative path coverage and all 11 increment paths. Regenerated staged
binary patches and retained final-v2 patches match:

- Increment SHA-256 `42199c5a97525b898e516db90d415ecfed8f6098415ec3f58383dcadabb56101`.
- Cumulative SHA-256 `3dd8b8f09be9506f0fce1b3f4f611817d7567e47b4788c8a6b90eae0e5269bee`
  against `b52144955b629314a000b1fe49eeea97fa3d0c5c`.

Read the entire v1-to-v2 source delta: 21 production lines and two focused tests.
The new branch proves that the outer expressions are bare positional identities
using the existing exact qualifier/name check. It then borrows through consecutive
identity projections, checking each retained projection against its own immediate
input. It stops at the first nonidentity projection or nonprojection input and
retains a projection at the leaf boundary. Reconstruction uses the surviving
projection's unchanged expressions/input and the original outer schema. Equality
at the end only chooses whether to reuse the original owned vector or clone the
surviving vector once; it never admits skipping a computation.

This is the ordinary identity law across a chain. It neither duplicates computed,
volatile or conditional child expressions nor substitutes them into additional
consumer positions. It retains outer qualifiers, fields, metadata and functional
dependencies. Empty projections preserve positive row counts and metadata. Existing
safe literal/equal-list and general composition paths remain available. Partial
selection and reorder cases fail this branch's width/position proof and use normal
composition. The change is simpler than caches, proof invalidation or per-level
expression-vector cloning, and complements rather than weakens the schema repair.

Inspected new controls: a 32-level chain over a computed child preserves exact
expressions, outer metadata/dependencies, repeat optimization, reorder, prefix and
nonprefix partial selection, and empty output. Actual batch/streaming execution
compares direct and compiled values with counted volatile and guarded immutable
child calls. Counts remain one call over four or two selected rows respectively;
markers continue through the shared execution helper.

Verified all final ownership comparisons independently. Full exact dependency
originals remain unchanged. The main v2 comparison now explicitly labels its
normalized production-prefix hash scope, with the whole-file hash separately
recorded; both original/owned trailing whitespace are normalized for comparison.
Both helper comparisons remain exact. The only additional behavioral delta is the
proven borrowed identity chain; schema/FD logic, recursion protection and the
correlated required-index visitor are unchanged.

The mechanical-v3 receipt names this exact tree and passes nightly workspace
formatting, workspace all-target/all-feature strict Clippy and strict affected-crate
Rust documentation. The inspected selected-test log records 165 passes and one
pre-existing skip before the final partial-selection branch was added. That final
branch is therefore still execution-pending despite compilation/lint passing.
Do not call the full frozen candidate test-qualified from the earlier count.

Inspected the ten-cell optimized shared-host cost summary. Deep width-64 identity
now measures 0.9104 owned/stock instead of the predecessor's 1.4048; shallow width-64
identity remains 1.0269. Both wide near-identity cells and all other measured cells
remain retained. This removes the demonstrated material deep-wide slowdown in the
measured envelope without hiding the smaller shallow cost. It does not establish
general planning complexity, production latency or throughput. Performance's
independent verdict, full immutable gate and public-v2 qualification remain pending.

Exact-source design verdict: no new architectural blocker. The borrowed chain is
a small coherent application of a proved law, with one reconstruction and complete
outer-schema retention. Earlier cumulative design findings carry forward, including
recovery/fencing/native integration/typed configuration and existing mixed-marker
and compiler-startup limitations. This is local source-design review, not global
readiness. No source edits, builds or tests were performed; only this report was
appended. A minor plan wording clarification was sent separately: full-schema
equality is required when removing a projection entirely; composition may retain
a distinct outer schema unchanged.


## Frozen v3: explicit release of removed identity chains

Reviewed 2026-11-06T09:18:03.315101+00:00. Reconfirmed the saved full request/governance and read the
253-word PROJECTION-CHAIN-OWNERSHIP.md and retained before-code ownership plan.
The confirmed lifecycle defect supersedes the prior v2 no-blocker assessment until
its correction is verified below; prior evidence is retained rather than relabelled.

Independently verified parent `6e4da8d33ba1bf4073fcb853123f81860ef18151`, tree
`21849a5803fcad439c651087885c101046ee2921`, all 85 cumulative file hashes,
exact cumulative path coverage and all 11 increment paths. Regenerated staged
binary patches and retained final-v3 patches match:

- Increment SHA-256 `437725b92d01339d336f055b234f5c720447358d42dacadcbb347155fb7db3bd`.
- Cumulative SHA-256 `e8cfb314bd6fe1e8887b21d63ca98c4bca33c71f497a33e699b3a4156e0c6e6e`
  against `b52144955b629314a000b1fe49eeea97fa3d0c5c`.

Read the entire v2-to-v3 delta. After the existing binding proof and expression
selection, the implementation clones the retained input into the replacement tail.
It then consumes the original Arc chain iteratively. Pointer equality stops before
the retained tail; Arc::try_unwrap stops at shared ownership. Each uniquely owned
Projection frame moves its input onward before the frame's remaining fields drop.
The live replacement tail prevents unwrapping an unrelated subtree. The semantic
identity proof, selected expression vector and complete outer schema are unchanged.

This is the smallest coherent ownership correction for the demonstrated defect.
The optimizer's recursion annotation cannot protect generated recursive destruction.
A chain-depth threshold or larger stack would move rather than remove the failure.
A general destructor framework would change unrelated ownership. The local release
loop adds neither cached proof state nor another execution abstraction. Its guarantee
is bounded release depth for removed projection chains, not all recursive expression
or schema destructors.

Inspected the permanent fixed-stack test at depths 8,192 and 16,384 with a one-MiB
thread stack. It proves unique root/input counts, a genuinely shared middle tail,
unchanged schema and original empty-relation leaf semantics. It subsequently consumes
the saved shared tail through the rule, so fixture destruction does not conceal a
remaining failure. Existing value, volatility, conditional, metadata, dependency,
partial-selection and Arrow physical-layout controls remain unchanged.

The original standalone probe distinguishes before_rewrite from after_rewrite and
completion. Its prior current variant aborts from stack overflow after before_rewrite
at depth 8,192 while its baseline succeeds. Inspected the repeated run under
performance/identity-drop-v2/runs/20261106T091500.858024Z: the same probe SHA-256
`228e0d58d9cce8fd48763db48c7b5d7db6f41d8b86b10ff8d840c49e88a2c866` and runner
`94d0392c28cc3a9b38fde197f2f495599b4f48d3115f1ecc9c00a9559f5cf10e` now complete
and join both depths for baseline and corrected current. The receipt identifies
this exact tree, verifies same binary and exact restoration, and reports no restoration
failures. This is an inspected external-run receipt, not a test run by this reviewer.

Selected corrected-tests-v6 records 166 passes and one pre-existing skip, now
including the final partial-selection branches and permanent ownership control.
Mechanical-v4 names the exact tree and passes workspace formatting, strict
all-target/all-feature workspace Clippy and strict affected-crate Rustdoc. All
three final-v3 ownership comparisons independently reproduce, including explicitly
labelled normalized production-prefix and whole-file hash scopes; original pinned
sources remain retained unchanged.

The final ten-cell optimized shared-host receipt retains all samples and output
qualification. Deep width-64 identity is 0.9244 owned/stock; shallow width-64 identity
remains 1.02394, including its slower outlying sample. Wide near-identity cells are
0.4130 and 0.2620. These remain one-rule rewrite diagnostics with plan cloning,
not production latency, throughput or whole-compiler cost. Do not generalize their
improvement to earlier mixed-marker or mandatory-compiler startup limitations.

Exact-source design verdict: the identified unique-chain lifecycle blocker is
closed by a local ownership repair and discriminating original controls. No further
source-level architectural blocker was found in this cumulative design review.
Full immutable qualification and final public execution remain pending. Full SDP,
fencing/recovery, both native integration routes and typed configuration/Dhall
remain active obligations. Only this assigned report was appended; no source edits,
builds, runtime tests, remote actions or cleanup were performed.


## Final v4: atomic retirement API and exact pin

Reviewed 2026-11-06T09:26:38.621903+00:00. Reconfirmed saved request/governance and read the updated
ownership plan plus atomic-retirement before-code record. Independently verified
parent `6e4da8d33ba1bf4073fcb853123f81860ef18151`, tree
`b337dfd145db4773ba1aa019028a8e9c86bbaa67`, all 85 cumulative file hashes,
exact cumulative path coverage and all 11 increment paths. Regenerated staged
binary patches match retained final-v4 patches:

- Increment SHA-256 `d0be097703b5ce7ba7f1e8400dfd486ee492f9d64f2c91437a8e4f86409cc227`.
- Cumulative SHA-256 `01226d1ed79d26afa4cd9e36d1e331b365d3ad4ba93c434fbbc50636262c991c`
  against `b52144955b629314a000b1fe49eeea97fa3d0c5c`.

Read the complete v3-to-v4 delta: one pattern/API substitution from try_unwrap/Ok
to into_inner/Some for discarded owners. Rust 1.98.1's pinned implementation and
documentation distinguish discarding a failed unwrap from consuming owners atomically.
The latter returns the final value for iterative handling instead of allowing the
failed-unwrap owner's ordinary destruction to become the last drop. This directly
fits chain retirement. The proof is API/source-derived; no newly reproduced
concurrent failure is claimed. The plan correctly excludes destruction by external
owners and arbitrary recursive expressions. [Pinned Rust source](https://raw.githubusercontent.com/rust-lang/rust/refs/tags/1.98.1/library/alloc/src/sync.rs)

The replacement tail remains live before retirement, pointer equality still stops
before that tail, and shared ownership still terminates the local loop. Binding,
schema/FD preservation, expression selection and recursion protection are unchanged.
All final-v4 ownership comparisons reproduce independently with their stated
normalized production-prefix and complete-file scopes and matching full hashes.

Mechanical-v5 names this exact tree and passes workspace formatting, workspace
strict all-target/all-feature Clippy and strict affected-crate Rustdoc. The original
probe/runner hashes remain unchanged in identity-drop-v3's repeated run; baseline
and current complete and join both fixed-stack depths on this exact candidate,
same binary is verified, and exact source restoration has no failures. The earlier
166-pass selected suite predates this API substitution and is not relabelled a v4
whole-suite pass. The final public and immutable workspace gates remain pending.

The repeated ten-cell optimized diagnostic retains all samples and valid output
oracles: deep-wide identity is 0.9169 owned/stock, shallow-wide 1.0247. Those are
shared-host rule-rewrite ratios, with all earlier cost boundaries unchanged.
No production throughput, latency, integrated recovery or general optimizer
correctness claim follows from them.

Final v4 source-design verdict: no additional architectural blocker. The atomic
retirement API strengthens the narrow ownership fix without another mechanism,
state cache or framework. Previous cumulative findings and full-goal implementation
obligations remain active; this is not global readiness. Only this report was
appended. No source edits, builds, runtime tests, cleanup or remote actions occurred.
