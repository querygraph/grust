# StreamSource participation: Research evidence

Recommendation: lower supported streaming plans to Sail's flow-aware nodes after
configured analysis and before the general relational optimizer. Use the public
analyzer extension point; preserve actual source occurrences and their control
streams. A remembered streaming flag or a refusal after source deletion cannot
recover the lost participation.

## Scope and source pins

Source inspected at detached commit `327572240365e2507f348ee92bc009cbfc67abe9`, tree
`bb8699fdfbc4ca88fa6c0e816e189af80e560efd`, in
`/Users/alexy/src/sail/tmp/streamsource-participation-20261105-327572240`.
Upstream comparison base stays `b52144955b629314a000b1fe49eeea97fa3d0c5c`.
There were no tracked source edits when inspected; untracked review logs were present.
No builds, tests, source changes, dependency changes or rebases were performed by
this role. Runtime counterexamples below are proposed tests, unless explicitly
identified as existing source behavior. Spark parity is not established here.

DataFusion sources are version 55.2.0 under the local Cargo registry. Each primary
file in the hash appendix was verified byte-for-byte against its cached crate
archive, and each archive checksum matched this worktree's Cargo.lock. References
below use paths relative to the named crate. Sail references use paths below
`crates/`. No additional repository research was needed: the question is a concrete
ordering and extension-contract issue in the pinned engine, not a new optimization
algorithm for which DuckDB, Polars or a paper supplies the missing mechanism.

## Why the existing ordering loses participation

`sail-plan/src/lib.rs:31–61` resolves and executes logical commands, calls
`SessionState::optimize`, then detects TableScan-backed stream providers and applies
the streaming rewrite. `datafusion/src/execution/session_state.rs:689–765` confirms
that optimize performs both configured analysis and optimization. The batch optimizer
therefore sees the source before Sail gives control rows their semantics.

`datafusion-optimizer/src/eliminate_filter.rs:57–79` replaces a literal false or
NULL filter and its entire input with EmptyRelation. `eliminate_limit.rs:57–83`
similarly eliminates a zero fetch. The default rule sequence contains expression
simplification before these eliminations, then empty-relation propagation. These
rules are correct for data-only relational output. They do not promise to retain
source activity when the output has zero data rows.

The decisive fixture is an actual source emitting data, a checkpoint marker, then
more data under WHERE false. The intended output has no data and still carries the
marker, with the source polled. Checking a boolean classification or a plan name
alone would not establish that property. A union whose false branch has its own
source must retain that branch's participation too; successful output from another
branch must not hide its disappearance.

## Smallest coherent integration

Register a final analyzer rule implemented in sail-plan through
`sail-session/src/optimizer.rs:7–10`. Existing configured rules already resolve
lambda variables, aliases, types, iterator functions and input-file metadata before
this point. Preserve that order. DataFusion's public Analyzer API executes its
configured rules and checks executable invariants at the end. Its public
SessionState optimize method already records analyzer/optimizer steps for Explain.
This is a smaller integration than owning or duplicating SessionState orchestration.
See [the pinned SessionState API](https://docs.rs/datafusion/55.2.0/datafusion/execution/session_state/struct.SessionState.html).

Remove the redundant post-optimizer rewrite once this stage is authoritative.
Keep batch plans on their existing path. A preparation API must handle already
prepared plans without adding a second collector or rewriting encoded control
columns. Existing tests that call rewrite_streaming_plan after state.optimize need
to exercise the new shared preparation boundary, not perform lowering twice.

Canonicalize only what supported streaming lowering actually requires. In particular,
Limit::get_skip_type/get_fetch_type in `datafusion-expr/src/logical_plan/plan.rs:3700–3742`
accept literal Int64 forms and validate negative values. Public ExprSimplifier can
literalize casts/arithmetic in skip/fetch before constructing StreamLimitNode without
running relational elimination over the input. Preserve the existing null semantics.
The AnalyzerRule interface supplies ConfigOptions, not the execution timestamp;
creating a fresh timestamp would change semantics. Time-dependent limit expressions
need a baseline comparison or a deliberate supported-scope decision.

Do not run every structural optimizer as an assumed harmless canonicalizer. Distinct
becomes an aggregate; correlated subqueries can become joins; those operators remain
unsupported by the streaming rewriter. Conversely, do not reject every subquery:
`scalar_subquery_to_join.rs:40–47` says uncorrelated scalar subqueries remain physical
expressions by default. A previously working bounded scalar subquery in a streaming
projection/filter must be tested and retained. Confirm outer references, EXISTS/IN,
subquery settings and constant-subquery cases before deciding which lowering is
required. An unsupported source-containing form needs a named limitation, not silent
conversion into a batch query.

The generic optimizer still traverses extension inputs and expressions. The proposed
boundary is not an opaque optimization barrier. Pinned contracts supporting it are:

- StreamFilterNode and StreamProjectionNode are Extension variants, so ordinary
  Filter/Projection elimination does not match them. Their required-column hooks
  retain every input column, including controls.
- ExtractLeafExpressions only extracts from ordinary Aggregate, Filter, Sort, Limit
  and Join nodes. CommonSubexprEliminate recurses through extensions but does not
  extract their own expressions. See `extract_leaf_expressions.rs:174–190` and
  `common_subexpr_eliminate.rs:561–592`.
- Extension defaults block column predicate pushdown and limit pushdown. This is
  not a blanket block: the filter rule can push a column-free predicate through
  an extension with children. See `push_down_filter.rs:1196–1257`.
- OptimizeUnions may reconstruct/coerce branches, and optimizer traversal can change
  schemas. Final logical and physical tests must show that newly inserted ordinary
  evaluators never receive marker payloads. General optimizer safety is not proven
  merely by choosing an Extension node.

## Source discovery and identity

Ordinary TreeNode traversal visits plan inputs, not expression subquery plans.
Current `is_streaming_plan` uses that traversal. `datafusion-expr/src/logical_plan/tree_node.rs:60–75`
and `apply_with_subqueries` at lines 799–818 provide the distinction and the public
subquery-aware alternative. Discovery must not silently miss a stream inside an
expression or hide it by folding the enclosing expression first.

There is no default InlineTableScan analyzer rule in this DataFusion version.
`LogicalPlanBuilder::scan_with_filters_inner`, in `logical_plan/builder.rs:523–550`,
inlines a provider's logical plan when scan filters are empty and restores alias and
projection. Normal nested views built through that API can expose their sources early.
A raw TableScan with filters is different. ViewTable::scan in
`datafusion-catalog/src/view.rs:105–145` builds filter/projection/limit over the stored
plan and recursively invokes physical planning. Sail's RenameTableProvider returns
None from get_logical_plan. Test builder-created nested views, raw scans and renamed
providers separately; do not assume discovery covers all three from one view test.

`sail-logical-plan/src/streaming/source_wrapper.rs:16–48` currently ignores the
StreamSource object in equality and hashing. Two separately constructed wrappers
with the same schema/arguments can therefore compare equal. DataFusion's
LogicalPlanSignature hashes plans for optimization termination, and other rules use
plan equality. Upstream TableScan equality also ignores the provider but includes
table identity; copying that assumption does not establish occurrence identity for
Sail's sources.

Use a fresh query-local occurrence token when constructing a wrapper, preserved by
clone and with_exprs_and_inputs. Arc<()> is sufficient: Arc::ptr_eq and its allocation
address give process-local equality and hashing without a UUID service or counter.
Keep PartialOrd consistent with equality as well; its current derived implementation
ignores source and schema. Distinct fresh wrappers, even around the same source Arc,
should remain different occurrences; clones should remain equal. Do not serialize
or advertise this token as durable checkpoint identity, and do not add pointer values
to public explain text.

## Alternatives and explicit limits

A source-aware copy of EliminateFilter alone is insufficient: zero limits, empty
propagation, branch rewrites and future rules can also discard inputs. Guarding every
optimizer result with source-count comparisons introduces rollback policy and cannot
by itself prevent unsafe expression movement. Disabling general optimization on all
streaming plans avoids deletion but sacrifices existing folding and canonicalization.
Wrapping only source leaves still allows Filter(false) to erase the wrapper.

Dependency ownership should be reconsidered if a specific public rule must change.
At present the public analyzer hook and existing Sail flow nodes express the needed
semantic boundary without modifying a dependency. No copied engine implementation
is justified merely to choose the ordering. If a concrete rule fails after rewriting,
retain its failing fixture and evaluate ownership of that rule with pinned attribution
and an exact comparison instead of accumulating name-based exclusions.

LIMIT 0 is distinct from a false filter. Immediate cancellation can return zero rows
without opening/polling input, even when its logical source remains represented.
The existing StreamLimitState::step stops after fetch exhaustion and explicitly has
a TODO for checkpoint completion and later markers. Retaining its logical source
does not solve that protocol. Do not describe LIMIT cancellation as durable zero-output
participation. The checkpoint participation test should use an active false-filtered
flow and prove real polling and marker delivery.

## Newly fetched upstream main, kept separate

Commit `5411f84330e8172acb22dd477044f42c07fcc2e5` is a direct child of the existing
base and is titled “fix: resolve CASE and IF to the common type of their branches
(#2955)”. The binary diff has 14 paths and SHA-256
`98f17881bfe69c46b5550c5757277965ad94faa0558e331879d75145098ddb89`.
Inspected its implementation changes and feature assertions; no upstream tests were
run and no integration was attempted.

The change shares CASE result-type/cast handling between resolver and analyzer,
preserves nested nullability/metadata when casting, extends list-view coercion,
adjusts DATE/TIMESTAMP branch preparation and adds SparkIntegerDatePart. Its feature
changes cover CASE/IF numeric, temporal and nested values, nested coalesce, date-part
time zones and one round regression. It changes no optimizer ordering or stream
participation machinery and adds no Cargo.lock dependency changes.

Only `sail-execution/src/proto/codec.rs` overlaps this branch's cumulative path list.
Its nine-line upstream delta adds the integer date-part import, decoder, encoder
recognition and round-trip assertions; the streaming codec changes are different
sections. This is a source-overlap observation, not proof that a merge builds or is
regression-free. The analyzer recommendation retains the configured Sail coercion
rules and therefore avoids forking the area changed upstream. Keep base b52144955
until a separately authorized integration is reviewed and qualified.

## Required next evidence

Use the real production/programmatic preparation path to check false, NULL and
constant-false filters, both union branches, aliases/renames, views, zero-column
projections, marker ordering and source errors after markers. Check positive ordinary
batch controls and configured analyzer execution. Exercise working bounded scalar
subqueries and nonliteral LIMIT/OFFSET against the unchanged parent. Record actual
source scan/poll counters and marker output, not only plan text. Establish wrapper
clone equality and distinct-occurrence inequality. Preserve a control that removes
the new boundary and loses participation.

Confirmed compliance with the saved full request and previously reread AGENTS.md,
LAKESAIL.md, SHEHAB.md, CLARITY.md, WRITING-RULES.md and applicable source instructions.
This is a primary-source assessment with proposed counterexamples; implementation,
final cumulative review and runtime qualification remain pending.

Recorded: 2026-11-06T04:40:57.209584+00:00

## Primary-file hash appendix

All rows are DataFusion 55.2.0 files verified against their locked crate archives.

| Crate and file | SHA-256 |
| --- | --- |
| `datafusion/src/execution/session_state.rs` | `880ea0ac875fd3311a0de5cb509711b8c066b80e627eda9c2f8bb06fc1ee6c9e` |
| `datafusion-optimizer/src/optimizer.rs` | `0957ff8055750880c4134bdf23b7778bf32d50d801900206365a46e5c5076547` |
| `datafusion-optimizer/src/analyzer/mod.rs` | `d028390d06305969f9c007c0a5731a242127bb8dd313a302e0c1f10cb02467e0` |
| `datafusion-optimizer/src/eliminate_filter.rs` | `b18c7250823aa29206fca42426c4e0e9e2c04a792a6de42cf8145aa0ae9036aa` |
| `datafusion-optimizer/src/eliminate_limit.rs` | `e85fcbe2b2b593d2f4e7403524cbe47124dbe156c21dbd33b0a48d1bbbe660e7` |
| `datafusion-optimizer/src/simplify_expressions/simplify_exprs.rs` | `d58af2575cdcdeece79acbe45dd0f63239ec5aa5f1c84614acd882d2ef4b08b0` |
| `datafusion-optimizer/src/plan_signature.rs` | `95d5b216d6c65f0e5581d999851a4462c148b2ae5097e7cb18e432fa998d471f` |
| `datafusion-optimizer/src/scalar_subquery_to_join.rs` | `5a14656101bc84fda246a6b860330eb17e3567a198bc4b3ca9eae197d111a4aa` |
| `datafusion-expr/src/logical_plan/tree_node.rs` | `f2d3749694c12243c124f8e27200f8ab0c1e3803d577842e8b46cec64ee41ab1` |
| `datafusion-expr/src/logical_plan/builder.rs` | `e4880858108c146150f07406f772b736de668d5470295dfe8cb6d1ba60e156a7` |
| `datafusion-expr/src/logical_plan/plan.rs` | `d4e231290a071b2078f4970b1644606758b83a31d03f4c8ddb780a2c5891a898` |
| `datafusion-catalog/src/view.rs` | `4a0409fcf4100ad630f909a3c42d3c62ed7b5d19d4c93d1555462aab443318d5` |


## Before-code scan-pushdown assessment

The analyzer boundary needs a small preparation step if it is to retain the existing
scan projection and filter callbacks. Lowering immediately makes the source wrapper
an opaque leaf and makes flow-node required-column hooks retain every input column.
That protects markers but prevents the ordinary rules from reaching scan options.
The source code supports an audited preparation using public PushDownFilter followed
by OptimizeProjections on an explicitly admitted graph, before flow lowering.
This is a recommendation for validation, not a measured preservation verdict.

Pinned public-rule behavior was inspected directly:

- `push_down_filter.rs:774–850` is a top-down rule. When simplifying its conjunction
  removes a filter, it returns the child, not EmptyRelation. A child with fetch or
  skip prevents filter movement. The production implementation does not construct
  EmptyRelation.
- `push_down_filter.rs:1118–1194` calls the provider with nonvolatile predicates
  excluding scalar subqueries. Exact predicates enter the scan and leave the residual
  filter; Inexact predicates enter both; Unsupported predicates remain outside.
  It validates callback result count and preserves existing scan filters.
- Projection movement respects volatile/non-pushable expressions at lines 1297–1339.
  Union movement retains every branch. These transformations can change expression
  placement, but they run before adding encoded marker rows and the final lowering
  must still convert every resulting data evaluator to its flow-aware equivalent.
- `optimize_projections/mod.rs:275–288` maps required indices through an existing
  scan projection before rebuilding the TableScan. Filter requirements retain columns
  needed by residual predicates; an exact predicate can use a column absent from the
  output projection because scan filters refer to the source schema.
- The same rule is unsafe on arbitrary streaming graphs: lines 190–198 replace a
  global aggregate with no required aggregate expressions by one empty-column row,
  deleting the source. Its recursion also visits uncorrelated expression subqueries
  at lines 491–501. Projection merging/pruning can discard unused expressions.

Establish eligibility before running either pass. Admit only the relational forms
that the existing streaming rewriter can lower: its supported unary nodes, unions,
source/constant leaves and its explicit supported extension/sink forms. A graph with
an unsupported aggregate, window, join, sort, unnest or unknown extension skips this
preparation and reaches the existing named streaming refusal. An unused aggregate
result must not become eligible merely because pruning can remove the aggregate.
Stream-containing expression subqueries must already have been discovered and
classified. Proven bounded expression subqueries retain their separate batch
preparation; pruning those pure batch subqueries does not justify pruning an embedded
stream. Hidden view/provider plans require the discovery handling described above.

Prefer one small shared admission predicate/classification beside the rewriter over
a trial rewrite of a cloned graph followed by another rewrite. A dry run builds
schemas, flow nodes and occurrence tokens twice and couples admission to allocation.
Do not introduce a general plan taxonomy framework: share only the supported-form
classification needed by preparation and rewriting. Keep the named refusal logic
and tests next to that classification so a future supported node cannot silently
bypass the eligibility decision. Eligibility is a restriction on preparation, not
a replacement for real streaming execution or a new reason to reject supported
bounded scalar expressions.

Use the public Optimizer driver for the selected rules, respecting each rule's
apply_order and recursion contract; calling PushDownFilter::rewrite once on the root
is not a whole-plan pass. Do not import the complete default rule list or select it
by subtracting a few dangerous names. Preserve the configured analysis before these
passes and flow lowering immediately afterward. Ordinary batch planning remains
unchanged.

A remaining source-derived counterexample concerns predicate normalization. The
previous complete optimizer runs SimplifyExpressions before PushDownFilter. With
only the two selected rules, a provider may receive a cast/arithmetic expression
where it previously received a folded literal. Later simplification cannot reach
filters stored privately in StreamSourceWrapperNode, whose expressions() is empty.
A provider that accepts `value > 3` but refuses a casted/arithmetic equivalent could
therefore lose pushdown despite receiving the callback. This has not been executed.
Include a normalization-sensitive counting provider. If the difference is confirmed,
reuse the existing expression simplifier on the admitted graph or normalize the
candidate predicates before negotiation; do not claim equivalence from callback
counts alone. Excluding unsupported/source-containing-subquery graphs remains
necessary before any simplification that can discard an expression.

Custom pruning of already lowered nodes would need more new policy: mapping requested
payload indices around the two control fields, retaining predicate-only columns,
rebuilding source projections and qualified schemas, remapping aliases/renamed
providers, negotiating exactness and retaining a data-only residual filter while
preserving all markers. The existing public rules already express these data-plan
operations. Reusing them in a tightly scoped phase has the smaller implementation
and test surface now. If a rule's behavior must change, evaluate owning that exact
pinned implementation; no dependency copy is needed just to call these public rules.

The counting-source fixtures should compare actual scan arguments and execution:

- Wide source, one selected payload field; reordered/repeated selections and aliases.
- Predicate on an unselected column under Exact, Inexact and Unsupported responses.
- Normalization-sensitive constants, volatile predicates and bounded scalar subqueries.
- Constant-only and zero-payload outputs, preserving positive data row counts and markers.
- False/NULL filters and two union occurrences, retaining actual source polls and markers.
- An aggregate-shaped unsupported graph whose unused aggregate could otherwise erase
  its source, retaining a named refusal rather than silently entering batch mode.

These checks establish callback and representation behavior. They do not prove
source implementations honor marker-preserving pushdown; an admitted StreamSource
must filter its data while continuing its promised control protocol. They also do
not settle a new positive-limit pushdown policy or checkpoint completion.

The draft's prepared-statement caution should state the actual product boundary.
The Sail spec CommandNode includes SetVariable and ResetVariable at
`sail-common/src/spec/plan.rs:504–510`. The resolver constructs only those Statement
variants in `sail-plan/src/resolver/command/variable.rs:9–24`; searches of Sail's
resolver/spec/SQL crates found no Prepare entrance. DataFusion's separate direct
prepared-statement API is not an implemented Sail resolver path to expand in this
increment. Describe it as outside the inspected Sail entrance, not as a supported
product path whose implementation this change must supply.

The two additional primary files match the locked DataFusion 55.2.0 archive:

| File in datafusion-optimizer | SHA-256 |
| --- | --- |
| `src/push_down_filter.rs` | `3e269ed167e1a4374f240671178dee46fc7abd4121263b2e3d4162d6b7398b76` |
| `src/optimize_projections/mod.rs` | `033142c1aed8a542a0aaa74130d9c7af045aa7583e85c978e3b7cfab06d97541` |

Read the current first-principles participation plan. This follow-up retains the
saved-request/governance scope and changes only this evidence report. No source
edits, builds, tests or dependency changes were performed; no new runtime result is
claimed.

Recorded: 2026-11-06T04:50:12.902959+00:00


## First-optimizer-rule alternative: required contracts

Moving preparation to the first configured OptimizerRule supplies the real
OptimizerConfig, including query execution time and the shared alias generator.
It therefore allows the existing Sail SimplifyExpressions rule before PushDownFilter
and OptimizeProjections without inventing a timestamp. The same original-source
eligibility and bounded-subquery separation remain necessary. Register it first,
use its own whole-plan traversal, and make later passes no-op once no unprepared
stream source remains. The inner selected optimizer must not contain the preparation
rule itself, or it would recurse rather than prepare. These are viable public APIs;
no global timestamp context is justified.

Two concrete source-derived hazards need resolution before this placement is safe.

First, DataFusion's optimizer checks the root output schema after every rule.
`datafusion-expr/src/logical_plan/invariants.rs:114–123` calls
DFSchema::logically_equivalent_names_and_types, whose implementation at
`datafusion-common/src/dfschema.rs:607–618` compares field qualifiers as well as
names and logical types. StreamCollectorNode currently rebuilds its DFSchema from
Arrow and discards qualifiers. A qualified root streaming scan can therefore fail
this new rule boundary even though its physical payload is unchanged. Preserve the
original qualified payload fields and metadata in the collector, and exercise a
direct qualified-table/programmatic plan. The old post-optimizer rewrite did not
have this invariant check around its result.

Second, optimization is optional policy in DataFusion. `optimizer.rs:612–621` enters
rules only while the pass count is below optimizer.max_passes, so zero passes omit
mandatory lowering entirely. With optimizer.skip_failed_rules enabled, lines 715–727
restore the plan from before a failed rule and continue. A preparation or unsupported
streaming-shape error can then be swallowed; a subsequent false-filter rule can
turn that original graph into EmptyRelation. The OptimizerRule API has no per-rule
non-skippable flag. Defaults are skip_failed_rules=false and max_passes=3 in
`datafusion-common/src/config.rs:1660–1663`, but the semantic guarantee cannot silently
depend on defaults.

If first-rule placement is selected, the smallest explicit contract is a mandatory
pre-optimizer analyzer check for streaming plans that rejects those two incompatible
configurations before optional optimization starts. This introduces named unsupported
streaming configurations and must be described and tested. An error inside the
skippable preparation rule is insufficient. Keeping mandatory analyzer lowering is
the alternative, with the time-dependent simplification limitation already discussed.
Owning a larger optimizer/orchestration layer or creating deferred-plan wrappers
would be more machinery than these choices currently justify.

Pinned `datafusion/src/execution/context/mod.rs:727–756` confirms that direct
DataFusion PREPARE invokes the configured optimizer with no query execution timestamp.
First-rule placement would be reached on that default-pass-count path, unlike a pure
analyzer rule. It does not establish full prepared streaming support: Sail exposes
no Prepare command in its inspected spec/resolver, placeholders and configuration
bypass still need their own contracts, and a missing timestamp must remain missing.

This is a source assessment, not an executed failure claim. No new source code,
build or test execution was performed. Both hazards were sent to the coordinator
before implementation. Their final resolution and final cumulative code remain
subject to independent review.

Recorded: 2026-11-06T04:52:41.496639+00:00


## Mandatory compiler WIP review and entry-point audit

The chosen mandatory Sail compiler phase resolves the first-rule bypass finding
without restricting optional optimizer settings. It calls configured analysis once,
prepares streaming with the actual SessionState OptimizerConfig, then calls the
optional optimizer. Public raw DataFusion planning remains outside this compiler's
contract. The updated self-contained plan and its before-code archive were read;
the archive matches SHA-256
`867532242e21712aafea13a556cfc7047911d242bd25670e34b6839d15483b93`.
This section reviews moving work in progress, not a frozen candidate or gate result.

### Ownership comparison

Independently extracted DataFusion 55.2 SessionState::optimize from the previously
archive-verified source. The exact method is lines 689–765, 77 lines, SHA-256
`8f6848528f15124e06959c267010f8b1c7d677bf45898bc0f89b8c63c408c3da`.
It matches both `review-logs/compiler-ownership/upstream-optimize.rs` and
`initial-verbatim-copy.rs` byte-for-byte. The full upstream file remains SHA-256
`880ea0ac875fd3311a0de5cb509711b8c066b80e627eda9c2f8bb06fc1ee6c9e`.

Generated and inspected an independent dedented-method comparison with WIP
`sail-plan/src/optimizer.rs`, then SHA-256
`cb4facfd032c9f4b82db5dd1323294b2b2888317f3986758791ead96eb8b86c1`.
The changes are the free-function signature, public analyzer/optimizer accessors,
formatting and the two mandatory preparation calls. The original analyzer and
optional-optimizer Explain context/error branches remain. The file carries the
Apache header and a pinned CREDIT URL. This is a justified narrow ownership change
because SessionState::optimize itself exposes no inter-phase hook. A raw-source-to-final
comparison artifact was not yet present during this WIP read; the coordinator was
asked to retain it with the final source receipt. This review did not write source
or ownership artifacts owned by the coordinator.

The ordinary execution path now calls this helper. The existing dedicated Sail
explain path inserts the same preparation function between its configured analyzer
and optimizer while preserving its physical-observer machinery. The collector now
preserves qualified payload fields and schema metadata, resolving the earlier
qualifier-loss finding at source level. SourceOccurrence uses clone-preserved Arc
identity in equality/hash/order. The zero-fetch physical branch returns an empty
stream before executing its child; that is the documented cancellation contract,
not a checkpoint-completion claim.

### Findings sent during the WIP read

The first expression-subquery check omitted SetComparison. Discovery could find a
source inside ANY/ALL, yet simplification could erase the enclosing expression before
lowering. The coordinator replaced the handwritten variant list with public
LogicalPlan::apply_subqueries. Inspected `datafusion-expr/src/logical_plan/tree_node.rs:913–930`:
that method covers Exists, InSubquery, SetComparison and ScalarSubquery. The new
check calls subquery-aware source discovery on each embedded subquery before any
preparation rewrite, including deeper nesting. This closes the omission in inspected
source; a direct logical-plan regression still needs execution evidence.

The initial admission check also allowed every Extension. The documented subset
argument applies to the known streaming rewriter extensions and sinks, not arbitrary
extension pruning hooks. Requested a shared known-extension classification or a
conservative preparation skip for unknown extensions. An unknown node must reach
its intended named refusal before unaudited hooks can optimize away evidence of its
streaming input. Resolution remains to be checked on the frozen patch.

### Eager resolver execution bypasses

Four existing Sail resolver paths execute/collect through bare DataFusion before the
new mandatory compiler receives the final resolved plan:

| Resolver path | Eager operation |
| --- | --- |
| `query/limit.rs:93–96` | Count the input for tail |
| `query/pivoting.rs:227` | Infer distinct pivot values |
| `query/stat.rs:386–389` | Collect crosstab distinct values |
| `query/time_travel.rs:230–233` | Evaluate a scalar time-travel bound |

Each uses ctx.execute_logical_plan(...).collect(). A false-filtered stream may be
removed by DataFusion during that eager execution. The time-travel case can return
only a literal to the outer compiler, leaving no source for later discovery. Tail,
pivot inference and crosstab require currently unimplemented streaming aggregation
or bounded materialization semantics; adding them is outside this increment.
Recommended a shared source-discovery refusal before eager collection while keeping
the existing bounded-input execution path. These are source-derived bypass findings,
not newly executed runtime failures. The frozen patch must close or explicitly bound
them before asserting that all Sail compiler entrances preserve declared sources.

### Raw commands

The inspected Sail spec/resolver produces SetVariable and ResetVariable Statement
nodes, not PREPARE. Other Sail commands use their existing extension ownership path.
No additional SQL command feature is needed for this task.

However, public sail_plan::execute_logical_plan currently forwards arbitrary
LogicalPlan values to SessionContext before optimization. DataFusion's raw
CreateMemoryTable handler calls state.optimize on the input and collects it
(`datafusion/src/execution/context/mod.rs:862–895`); raw PREPARE directly optimizes
and stores its input (`727–756`). A source-bearing raw command can therefore erase
its source before the caller reaches optimize_logical_plan. Recommended refusing
those declared-stream raw command forms before forwarding, keeping bounded commands
and Sail extension commands unchanged. At minimum the exported API must distinguish
this bare DataFusion boundary from the Sail compiler; documentation alone does not
make raw execution preserve participation.

The mandated compiler phase, timestamp reuse and earlier collector repair are
sound at the inspected source level. Open WIP items are extension eligibility,
eager/raw-command entrance handling, final ownership comparison and their concrete
regressions. No builds, tests, source edits, dependency changes, commits or remote
mutations were performed by this role. Saved-request and governing-instruction
compliance is unchanged; final cumulative review is still required.

Recorded: 2026-11-06T05:05:13.326244+00:00


## Frozen participation v1: final Research source review

**Verdict:** no remaining must-fix Research finding in this frozen source candidate.
This is a source and provenance verdict. It does not qualify public execution,
performance, distributed recovery or the full workspace gate.

The reviewed worktree is
`/Users/alexy/src/sail/tmp/streamsource-participation-20261105-327572240`.
I independently regenerated the index tree and both binary diffs, verified every
working-file and staged-blob hash in `review-logs/candidate-snapshot-final.json`,
checked the increment path inventory, and confirmed no unstaged tracked changes.

| Pin | Independently verified value |
| --- | --- |
| HEAD / increment parent | `327572240365e2507f348ee92bc009cbfc67abe9` |
| Frozen index tree | `0eee4fd9d9e34a28f3cea54eb6a2e80843c64bae` |
| Upstream comparison base | `b52144955b629314a000b1fe49eeea97fa3d0c5c` |
| Increment SHA-256 | `6ef125ea78c0b7ad8e86e61d4c14330d0f783ed2b6cd4a6b155c03d3a775f231` |
| Cumulative SHA-256 | `4672c5700077d505a417a6613d9002cbab56f8dc1ccb654ba65379b67d818c83` |
| Cumulative files / increment paths | 77 / 24 |

The cumulative review includes the unchanged foundation, Comet adapter and
projection implementation previously examined in their Research reports. Their
current bytes were included in the 77-file verification. I read all current
participation production changes and their new Rust and public Python tests,
including the interaction with the existing configured optimizers, marker-isolated
projection, source codec boundary and collector. This does not substitute a prior
gate for a gate on the cumulative candidate.

### Compiler ownership and source contracts

The exact 77-line DataFusion 55.2 `SessionState::optimize` extract, its initial
verbatim copy and the cached crate match the earlier pinned source. I independently
reconstructed `compiler-ownership/comparison-final-v1.patch` byte-for-byte from the
upstream method and final Sail method. Its SHA-256 is
`574919cc814c49a6d1341fbb162b42922229edf56fa5fc75c452b063eaf73182`.
The final Sail file is
`cb4facfd032c9f4b82db5dd1323294b2b2888317f3986758791ead96eb8b86c1`.
The changes are the free-function/public-accessor adaptation and preparation calls
between configured analysis and optimization in both branches. The Apache header
and pinned CREDIT are present. The original analyzer/optimizer Explain observers
and error branches remain; newly introduced preparation errors propagate normally.
The earlier missing final-comparison artifact finding is closed.

`optimizer.rs:35–111`, `lib.rs` and `explain.rs:303` place the mandatory phase before
the optional optimizer. `preparation.rs:23–87` uses the actual OptimizerConfig,
direct declared traversals and a bounded three-round preparation loop. Therefore
optional `max_passes=0` and `skip_failed_rules=true` cannot bypass that phase.
The plan correctly distinguishes the public Sail compiler from bare DataFusion
entry points. Already lowered graphs have no raw streaming scans and return
unchanged. This is in-process preparation idempotence, not stable recovery identity.

The final known-extension classifier is shared by admission and lowering, closing
the unaudited-extension-hook finding. Unsupported relational shapes skip the
preparatory rules and reach named refusal before those rules can erase their input.
The public subquery walker covers ScalarSubquery, Exists, InSubquery and
SetComparison, with recursive source discovery before simplification. This closes
the ANY/ALL omission. The raw unexpanded ViewTable case is genuinely exercised by
its TableScan fixture; a separate positive fixture exercises a normally exposed view.

All four eager resolver guards now precede their existing collection calls. The
raw CreateMemoryTable and Prepare guards precede command forwarding. The boundary
tests include bounded positive controls and source counters. These close the six
identified bypasses at source level. They do not establish participation for an
opaque provider that fails to declare its protocol, or add streaming support to
currently unsupported commands and expression-subquery execution topologies.

SourceOccurrence consistently uses clone-preserved Arc pointer identity for Eq,
Hash and ordering. Distinct occurrences retain distinct live allocations, including
repeated reads of one provider. Normal display does not expose addresses. The
collector preserves qualified payload fields and metadata. The zero-fetch branch
returns before child execution or polling, as its counter-based positive/negative
fixture requires. This is cancellation of demand and makes no final-checkpoint claim.

### Common expressions and test boundaries

The fourth preparation rule is DataFusion's public CommonSubexprEliminate, applied
last after projection merging. Its `apply_order` is None because it recurses itself
through nodes and uncorrelated subqueries; the caller respects that contract.
The pinned implementation preserves output schema, excludes volatile nodes and
tracks conditional function arguments, AND/OR and CASE branches. See
`datafusion-optimizer-55.2.0/src/common_subexpr_eliminate.rs:547–605,652–704`.
The source is byte-identical to the cached crate and has SHA-256
`910d062e599a6aa2c09d652f7abb2b5254b6fb5356c6945d09eed4e01f0b93a7`;
the crate SHA-256 is
`acfb8cea6e05e2e75bae183340cf7d53cccb3db0449e2f1fbc07654d980fd19f`.
This reuses dependency semantics rather than inventing a streaming-specific CSE.

The before-code common-expression plan matches its recorded SHA-256
`c6c81da2f9bd8d53a8302e2ece6ae29901d7c03548f6b9870e1d71d504528e2f`.
The current standalone plan accurately explains the observed duplication concern
and the required repair. I inspected the tests comparing old late lowering with
the new compiler: immutable repeated calls and repeated provider occurrences retain
work counts; volatile calls remain separate; conditional tests retain selected
results and reject evaluating the function outside its admitted branch. They check
marker traffic as well as rows. Their source establishes meaningful coverage;
I did not run them and do not infer a general performance envelope from them.

The other fixtures check false/null/constant-false filters, all marker kinds,
source errors, exact/inexact filter residuals, projection requests and materialized
bytes, positive zero-column row counts, source occurrence multiplicity, configuration
bypass and unchanged bounded batch planning. Python assertions use exact multisets
where no ordering contract exists. The first reported public attempt failed during
native-library setup, so it establishes no executed public-query result. The
coordinator reported 217 affected Rust tests passed with one pre-existing ignore;
this role did not execute or independently turn that report into a gate receipt.
Fresh native/public runs, planning measurements and the immutable full gate remain
separate qualification work.

I reread the saved request, AGENTS.md, LAKESAIL.md, SHEHAB.md, CLARITY.md,
WRITING-RULES.md and applicable Sail source instructions after compaction. This
review used pinned local primary source and retained artifacts. No builds, runtime
tests, source changes, dependency changes, commits or remote mutations were performed.
The full SDP, deterministic CDC, fencing, typed configuration and both extension
routes remain outside this increment's completion claim. All WIP Research findings
listed above are now explicitly closed at the source level on this exact tree.

Recorded: 2026-11-06T05:52:05.102796+00:00


## Frozen participation v3: source confirmation and unresolved diagnostic

**Source verdict:** no additional Research defect found in the v1-to-v3 changes.
The prior source conclusions extend to this exact candidate. Readiness remains
unqualified while the planning correctness diagnostic and full gate are open.

I independently verified HEAD remains
`327572240365e2507f348ee92bc009cbfc67abe9`, the index tree is
`c1e9563dec7527ed11c2e2bf5476816229317a93`, all 77 working-file and staged-blob
hashes match `candidate-snapshot-final.json`, the 24 increment paths match Git,
and there are no unstaged tracked changes. Regenerated binary diffs match:

- Increment SHA-256: `cddf405cb8205cfce54b14f97190b135bcd8b843f79724a8ffc90eb0b756694c`.
- Cumulative SHA-256 against `b52144955b629314a000b1fe49eeea97fa3d0c5c`:
  `28c0c0b0400fc61662667d08d878ff629ca4a3b303c4637f6c3c5cbf3437c066`.

The complete tree-to-tree delta has four files. Production changes only move the
Ordering import in source_wrapper.rs. Three fixture files replace expect/expect_err
with fallible test errors; unexpected success, invalid fixtures and poisoned locks
still fail. Assertions, values, counters and refusal messages are retained.
The participation fixture additionally recompiles an already compiled graph through
configured analysis and optimization, checks structural equality and executes that
recompiled plan. This strengthens the earlier preparation-only re-entry check.

The owned compiler is byte-identical to v1. Its SHA-256 remains
`cb4facfd032c9f4b82db5dd1323294b2b2888317f3986758791ead96eb8b86c1`.
I again reconstructed the retained raw upstream-to-Sail method comparison exactly;
its SHA-256 remains
`574919cc814c49a6d1341fbb162b42922229edf56fa5fc75c452b063eaf73182`.
The cumulative implementation, dependency contracts and earlier closed source findings
are otherwise unchanged.

I inspected `participation-public-v3-receipt.json` and its pytest log: the selected
public suite records exit zero and 38 passes, and the server probe reports 4.2.1.
This is inspected execution evidence from the coordinator, not a run by this role
or a JVM Spark parity result. The preparation-bypass receipt records a failed
control, exact source restoration and a successful restored command. Neither receipt
alone is an immutable full-workspace qualification.

The retained `performance/planning-same-alias-v1.json` and log now record a completed
failing diagnostic, with source unchanged. At depth twelve, expected and direct
execution yield [13,14,15,16], while both old and new optimized paths yield [2,3,4,5].
This is an observed discrepancy shared by those two paths in that fixture. It does
not identify the responsible optimizer rule, prove behavior on a separate baseline
commit, or qualify timings from that experiment. Root-cause isolation and the
correctness boundary must remain explicit; source review is not a reason to dismiss
this result. No general performance or readiness verdict is made here.

I reread REQUEST.txt, the literal latest `continue` in
`review-logs/continuation-request.txt`, AGENTS.md, LAKESAIL.md, SHEHAB.md,
CLARITY.md, WRITING-RULES.md and applicable source instructions. I performed no
builds, runtime tests, source edits, commits or remote mutations. The full goal
and the previously stated durable-recovery limits remain unchanged.

Recorded: 2026-11-06T06:04:48.610923+00:00


## Frozen participation v4: final source confirmation

**Verdict:** no additional Research source finding in the v3-to-v4 delta.
This confirms source identity and preserves the earlier review boundaries; it is
not a broad correctness, performance or full-gate readiness verdict.

I independently verified all 77 working-file and staged-blob SHA-256 values,
all 24 increment paths, unchanged HEAD
`327572240365e2507f348ee92bc009cbfc67abe9`, no unstaged tracked changes, and these
regenerated final pins:

- Index tree: `1501e3dcaf84158319a99fd4c3122c2dcb84bfc1`.
- Increment SHA-256: `2bc3f0275441454387ed32baa8764642bf4f35edef299f63dc796b65ed4aea6d`.
- Cumulative SHA-256 against `b52144955b629314a000b1fe49eeea97fa3d0c5c`:
  `e4f922d5c38697aa487fe256d9b1885227bbe506e600500a30be9e9e9b978b1a`.

The complete delta changes only two files. `sail-plan/src/lib.rs` isolates the
intentional raw DataFusion command-type imports under a documented, scoped lint
exception. The boundary fixture uses the same scope for raw-command construction
and exempts its intentional read of DataFusion's in-memory catalog. Production
control flow, test inputs and runtime assertions are unchanged. The exceptions do
not enable general command resolution through DataFusion or weaken the earlier
streaming guards.

The owned optimizer routine remains byte-identical to v1. I again reconstructed
its retained upstream comparison exactly; the file SHA-256 remains
`cb4facfd032c9f4b82db5dd1323294b2b2888317f3986758791ead96eb8b86c1`
and comparison SHA-256 remains
`574919cc814c49a6d1341fbb162b42922229edf56fa5fc75c452b063eaf73182`.
No dependency-ownership assessment changed.

I inspected the latest retained planning receipts and logs without running them.
The unique-alias `planning-v3` probe passes all four direct/old/new output checks.
Its shared-host median new/old planning ratios are 1.007 for shallow batch, 1.003
for depth-twelve batch, 1.660 for shallow streaming and 0.942 for depth-twelve
streaming. These are bounded diagnostic measurements, including the slower cell;
no general performance acceptance is inferred here.

The separate `planning-same-alias-v2` diagnostic still fails for both batch and
streaming at depth twelve: direct output matches [13,14,15,16], while both optimized
paths return [2,3,4,5]. The passing unique-alias probe does not resolve this shared
optimized-result defect. Its exact cause remains unassigned, and neither this
source confirmation nor reported strict affected Clippy success closes it.
The immutable full gate remains a separate pending step.

I reread the saved request, literal continuation and all assigned governance and
source instructions. No builds, runtime tests, source edits, commits or remote
mutations were performed by this role. The full redesign goal remains active.

Recorded: 2026-11-06T06:16:15.632463+00:00


## Frozen participation v5: Rustdoc-only final pin

**Source verdict:** no new Research finding. I independently verified all 77
working-file and staged-blob hashes, 24 increment paths, unchanged parent HEAD,
no unstaged tracked changes, and the regenerated final binary diffs:

- Tree: `f71f8c5c97b08baa0c7f0f914ea7a2e24d150622`.
- Increment SHA-256: `15fd96913eecd7d1d1e64fd1083d12bc34630a13c93802541d2cd14bb73941c7`.
- Cumulative SHA-256 against `b52144955b629314a000b1fe49eeea97fa3d0c5c`:
  `0b71c28974776dedaf643028bf12cc7959a0856b751db223b883393818e3d59a`.

The complete v4-to-v5 delta wraps the CREDIT label in inline-code backticks in
optimizer.rs:33. This prevents Rustdoc treating the label as an intra-doc link;
no executable code or test changes. The final whole-file SHA-256 is
`bd72af6797a2ad3e64a1734d1d0f730648d3ef2d6a9b0c58986984c5c64a6b27`,
matching `compiler-ownership/comparison-final-v2.json`. The executable method is
byte-identical to retained `sail-optimize-method.rs`. I reconstructed the unchanged
upstream-to-Sail method comparison again; its SHA-256 remains
`574919cc814c49a6d1341fbb162b42922229edf56fa5fc75c452b063eaf73182`.

The previously reviewed cumulative implementation and ownership attribution remain
valid on this exact tree. All prior limits remain, including the unresolved shared
same-alias optimized-result defect and the separate performance/full-gate assessment.
Reported strict Rustdoc success is not a run performed by this role. No builds,
runtime tests, source edits, commits or remote mutations were performed. Request
and governance compliance is unchanged from the preceding confirmation.

Recorded: 2026-11-06T06:21:15.848669+00:00
