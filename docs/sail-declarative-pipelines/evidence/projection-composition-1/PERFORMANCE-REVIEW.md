# Projection composition: initial performance review

Read the complete worktree `review-logs/request.txt`, the saved before-code plan,
`PROJECTION-COMPOSITION.md`, repository `AGENTS.md`, `LAKESAIL.md`, `SHEHAB.md`,
`CLARITY.md`, `WRITING-RULES.md` and source development instructions. Inspected the
initial owned DataFusion 55.2 rule, helpers and both registration sites in detached
worktree `/Users/alexy/src/sail/tmp/projection-composition-20261105-6e4da8d3`,
starting at `6e4da8d33ba1bf4073fcb853123f81860ef18151`. The unchanged owned control
is still building. This is an initial design/cost review, not a fixed-source or
completed-gate verdict. No builds or tracked source edits were performed here.

## Required optimizations and risks

The owned rule must preserve source column pruning, ordinary projection collapse
and the compute-once guard for nontrivial child expressions referenced repeatedly.
Removing that guard could duplicate expensive native or immutable work. Existing
CSE still matters after composition, and volatility/conditional controls must show
that pruning and substitution do not introduce otherwise unnecessary evaluation.
Correctly evaluating successive dependent additions takes precedence over a faster
stock result that discarded an addition.

The equal-expression shortcut can avoid substitution for legitimate identity and
constant cases. Removing it sends these cases through ordinary usage counting,
alias preservation and expression transformation. That increases planning work
in some shapes. In particular, an outer literal has no column substitution, so
the general `new_exprs.transformed` result may be false. Subsequent required-column
pruning may still remove the unused child work; do not assert either a regression
or neutrality without inspecting the final plan and executing a valid control.

Deep projection chains should remain collapsed in one rule invocation where
composition is legal. Check resulting projection counts, source projections and
expression growth in addition to elapsed time. The nontrivial-usage guard bounds
an important source of repeated-expression expansion. Metadata, aliases and
qualifiers must remain semantically correct; dropping them to retain the shortcut
would be an invalid cost reduction.

Owning this rule and its private helpers adds maintenance responsibility, not a
new execution framework. The initial upstream copy and narrowly retained diff
are appropriate evidence. Explicit recursion protection preserves a production
property that would otherwise be lost by copying out of DataFusion's feature
configuration. No new global registry, per-row lock or streaming scheduler is
justified by this repair.

## Prepared equivalent-output comparison

Prepared the opt-in source
`review-logs/performance/projection_composition_cost_probe_v1.rs` outside product
source. It has not been compiled or executed. The implementation owner should
stage it as an ignored `sail-session` integration probe after the cold control,
pin the cumulative tree/lock/probe hashes and verify unchanged source afterward.

Six cells compare stock and owned public rules in the same process and dependency
lock: identity, constant and unique-alias arithmetic chains, each at depths two
and thirty-two. The fixture has a selected Int64 value column and an unused
Int64 column. The same-alias arithmetic stock failure is deliberately excluded
from timing because its output is incorrect; it remains a separate correctness
counterexample.

Before timing, direct analyzed, stock-rule and owned-rule execution must all match
the independent four-row oracle and output schemas. The probe prints complete
raw/rewritten/physical plans, resulting projection counts and projected source
column indices. These structural observations catch pruning/composition loss that
identical final values alone would miss.

Timing covers only one rule invocation on a cloned analyzed plan. Context/input
construction, analysis, physical planning and execution stay outside timing.
Each sample aggregates thirty-two invocations; seven paired samples alternate
order after warmups. Keep every cell and sample, including any slowdown, and
record the actual compiler/profile and host conditions. An invalid output means
that cell has no qualified timing result; never weaken its oracle.

This bounded diagnostic isolates the rule change. It does not measure the full
compiler, CSE interaction under every optimizer sequence, source input/output,
native-kernel runtime, memory peaks or production throughput. Existing mixed-marker
filter/projection costs and short-stream startup overhead remain separate open
limits. Shared-host ratios establish no broad improvement or readiness. Final
cost/source review follows the corrected immutable candidate and actual evidence.

## Executed six-cell comparison and regression finding

Read the complete `composition-cost-v1.log`, receipt and summary. All six cells
passed direct/stock/owned exact-value and schema checks before timing. Each final
plan contained one projection and identical source column indices. Constant
chains requested an empty source projection while preserving four output rows.
The measurement source was unchanged. Independently recomputed all six medians
from the 42 raw paired samples.

| Expression | Depth | Median owned/stock ratio | Pair range |
| --- | ---: | ---: | ---: |
| Identity | 2 | 0.6420 | 0.5372–0.6528 |
| Identity | 32 | 4.1700 | 3.7198–4.5835 |
| Constant | 2 | 0.8478 | 0.8350–0.8589 |
| Constant | 32 | 6.6603 | 5.7937–6.8437 |
| Unique-alias arithmetic | 2 | 0.2273 | 0.2198–0.2322 |
| Unique-alias arithmetic | 32 | 0.0846 | 0.0782–0.0859 |

This is an unoptimized same-tree rule-only comparison on the shared macOS host.
Load averages were 7.90 before and 7.81 afterward. CPU isolation and steal
measurement were unavailable. It provides diagnostic ratios, not production
throughput or a broad improvement claim. The larger deep identity/constant cost
is consistent across all pairs and is material. Faster other cells do not cancel
that regression. Matching final node counts does not mean equal planning work.

An optimized-profile repeat is useful for final magnitude, but it is not necessary
to recognize the structural extra work from sending legitimate equal identity and
literal chains through general expression composition. A narrow correction is
justified before readiness. Preserve the original measured candidate and all
cells; do not substitute the incorrect same-alias stock result as a timing oracle.

## A narrowly proven shortcut

A safe shortcut can require equal full expression lists and then prove every
position independently. After stripping only top-level aliases, accept a literal
or a column resolving to that same position in the immediate child's schema.
Use qualifier-aware resolution. Mixed literal/positional-identity lists may
qualify. Keep the exact outer schema, qualifiers and metadata during reconstruction.

This establishes either constant recomputation or positional passthrough; it does
not equate arbitrary equal expression text with the same computation. A swapped
alias resolves to another child slot and must fail the proof. Arithmetic, casts,
functions, conditionals and volatile expressions do not qualify. They retain
general composition and the existing nontrivial repeated-use guard/CSE behavior.

| Discriminating control | Required observation |
| --- | --- |
| Equal positional identity, shallow/deep | Exact rows/schema; one resulting projection and matching source pruning |
| Equal literals, including null, shallow/deep | Four rows survive empty source projection; literal metadata remains exact |
| Mixed identity and literal positions | Only same-slot columns qualify; values and field order stay exact |
| Equal swapped aliases with two distinct columns | Two swaps restore original values; shortcut cannot discard a swap |
| Equal dependent arithmetic | Both additions remain; original wrong-stock counterexample still fails on control |
| Qualified columns and explicit outer metadata | Resolution uses the immediate child and preserves the declared outer schema |
| Repeated nontrivial immutable child work | Compute-once behavior is retained rather than duplicated |
| Volatile and conditionally unreachable functions | Required invocation counts and guards remain unchanged; no shortcut admission |

The shortcut adds a small proof and preserves the general path for every case
outside that proof. A narrower safe optimization is preferable to reintroducing
the faulty broad equality condition or disabling projection optimization.
`DFSchema::index_of_column` scans fields, so resolving every position independently
can cost quadratic work in projection width. Check one modest wide identity
control before claiming a generally cheap shortcut; do not add a caching framework
without evidence. The final performance comparison must retain all six cells
and source-pruning counters with corrected, frozen source. No source edits,
builds or execution were performed by this reviewer.

## Added qualified wide-identity controls

Prepared `review-logs/performance/projection_composition_cost_probe_v2.rs`
separately, retaining the original six cells and their exact expected values.
It adds two identity cells at width sixty-four and depths two/thirty-two. The
source has sixty-five columns, with the final column unused, so scan pruning
remains observable. Every column contains distinct four-row values to expose
reordering rather than merely checking row count.

The builder receives explicit `source.cN` references. Before timing, the probe
prints each analyzed projection's actual first expression/child field and counts
all exact positional qualifier/name matches. It asserts all sixty-four matches
at every level. This verifies normalization rather than assuming a qualified
string produced the desired expression. Direct/stock/owned outputs and schemas
must all match the independent sixty-four-column oracle. All original samples,
plans and pruning/projection counts remain in the output.

The proposed sufficient shortcut proof can compare columns directly with the
immediate child's qualified field at the same position, in linear width, avoiding
repeated schema-index searches. Partial or unmatched qualifiers can conservatively
fall back to normal composition. This trades shortcut coverage for a simpler
proof and predictable cost without weakening correctness. Equal literal positions
remain independently safe; swapped aliases and computed/conditional expressions
still fail admission. The new probe has not been compiled or run here.

## Executed safe-shortcut comparison

Read `composition-cost-v2.log`, its source-hash receipt and summary. The log
records a finished unoptimized build and one passing eight-cell probe. All direct,
stock and owned oracles, schemas, source-pruning and resulting projection counts
passed before timing. The wide cases report actual fully qualified positional
matches for all sixty-four expressions at each level. Source was unchanged during
measurement. Independently recomputed the eight medians from all 56 paired samples.
The measured owned rule has SHA-256
`57848cce9adc8e64484fa823c8337d4e8301a7b74984ed22d3cfcb3122bf72b7`.

| Expression | Depth | Median owned/stock ratio | Pair range |
| --- | ---: | ---: | ---: |
| Identity | 2 | 0.4997 | 0.4495–0.5125 |
| Identity | 32 | 0.6877 | 0.6122–0.7254 |
| Constant | 2 | 0.6172 | 0.5394–0.6439 |
| Constant | 32 | 0.8862 | 0.8446–0.8913 |
| Unique-alias arithmetic | 2 | 0.2348 | 0.2287–0.2427 |
| Unique-alias arithmetic | 32 | 0.0843 | 0.0839–0.0852 |
| Qualified width-64 identity | 2 | 1.0598 | 1.0162–1.0778 |
| Qualified width-64 identity | 32 | 1.4392 | 1.4221–1.4615 |

The first six cells retain one projection and identical source columns. Constant
cells still prune source payload to zero columns while preserving rows. Both
wide identity cells eliminate all projection nodes and request the same first
sixty-four source columns. Thus the remaining wide cost is planning work rather
than a measured loss of source pruning or extra runtime projections.

The measured fix admits equal lists only when each alias-stripped expression is
a literal or exactly matches its same-position child qualifier/name. This uses
a linear zip, not repeated schema searches. Swapped/partially qualified/computed
expressions conservatively use general composition. The proof's comparisons add
work, particularly across deep wide chains; no actual cache or broader framework
is justified by this measurement.

The earlier deep single-column identity/constant regressions are corrected in
this experiment. The wide depth-thirty-two median remains about 44 percent slower
and every pair is above 1.42. It is meaningful and must remain visible. Faster
other cells do not offset it. The depth-two wide cell also has consistent smaller
overhead. Final costs must be attributed to the receipt's exact source hashes,
not an unchecked later mechanical-preflight candidate.

This run used an unoptimized profile on the shared macOS machine. One-minute
load averages were 24.22 before and 28.77 afterward; CPU isolation and steal
measurement were unavailable. It establishes diagnostic ratios, not production
compiler throughput or a general speedup. Keeping the correctness repair as a
local reference is reasonable with the wide-planning limitation explicit. Before
performance readiness or a decision about its production magnitude, repeat the
same eight cells using optimized code generation on frozen source. If material
cost remains, investigate a cheaper sufficient proof while preserving all binding,
swapped-alias, metadata, volatile and conditional controls. Do not remove the proof
or add speculative caching simply to match the unsafe shortcut's cost.

Unrelated streaming mixed-marker and short-stream-startup costs remain open.
Mechanical preflight and final cumulative source review are still pending.
No source edits, builds or measurements were performed by this reviewer.

## Frozen source inspection while optimized qualification runs

Reread the saved request and current self-contained composition plan. Independently
verified every file hash in the final snapshot: 85 cumulative files, 11 increment
paths, staged tree `a4801a8e6fb2d10d041d07aef9fc9ec1b7ff2bb6`, increment SHA-256
`72d0cd710862bc0b4676f357e8c451813f365dfeb27f87fc3daf2dd03db82a0e`, and cumulative
SHA-256 `8898a1d1a5b0ae74c3189b022ae7f9c7947675cdde78ef0ff1eb5a29bb322b2f`.

Reviewed the pinned upstream comparison for the owned rule and both helpers,
registration changes, corrected composition path and schema/pruning changes.
The production delta retains the nontrivial repeated-use guard and the existing
CSE path. It adds no per-row lock, persistent cache or execution scheduler.
The exact positional qualifier/name proof borrows through aliases and scans
once across the expression list; it has no per-column schema lookup or new
name-resolution map. Literal/identity admission remains narrower than arbitrary
equal expression text, so swaps, functions and dependent arithmetic take normal
substitution.

The rule now preserves the outer schema for composition and retains original
qualified fields/metadata when pruning. Functional dependencies are projected to
the retained indices. When no output fields are removed, it reuses the schema
reference rather than reconstructing every field. Identity elimination additionally
requires full schema equality. Those correctness checks add planning work but do
not change ordinary row-evaluation behavior or remove source pruning. They are
possible contributors to the debug wide-chain cost; no isolated cost attribution
has been established.

Inspected the added controls for repeated immutable outputs, volatile calls,
conditional evaluation, swapped aliases, metadata/qualifiers, subquery scope,
empty outputs and Arrow type families. The physical execution checks are necessary
because retaining a schema alone does not prove that expressions still produce
that schema. The implementation owner's reported 51 public PySpark checks are
broader evidence than these source observations, but this reviewer ran no tests.

At inspection, the optimized runner processes 56910 and 56922 were confirmed live
and compiling dependencies. The command uses release opt-level 3 with LTO disabled,
16 codegen units and four build jobs. It runs the same eight-cell probe; it is
not the workspace's production LTO profile. The terminal receipt was not yet
available. The debug width-64 depth-thirty-two cost remains material and recorded;
no final performance disposition or improvement claim is made before the optimized
run completes. Full immutable qualification is also pending. Governing-file
compliance remains confirmed; no source edits or builds were performed here.

## Terminal optimized result: wide-chain regression confirmed

Read the completed `composition-cost-optimized-v2.json`, complete log and parsed
summary. The release build finished with optimized code generation and the probe
passed. Source was unchanged, and the same probe hash identifies all eight
equivalent-output cells. Independently recomputed all medians from the 56 raw
paired samples. Exact output/schema/pruning checks passed before timing.

| Expression | Depth | Median owned/stock ratio | Pair range |
| --- | ---: | ---: | ---: |
| Identity | 2 | 0.4811 | 0.4732–0.4836 |
| Identity | 32 | 0.5913 | 0.5720–0.6027 |
| Constant | 2 | 0.6488 | 0.6358–0.6600 |
| Constant | 32 | 0.7623 | 0.7524–0.7703 |
| Unique-alias arithmetic | 2 | 0.1775 | 0.1752–0.1802 |
| Unique-alias arithmetic | 32 | 0.0538 | 0.0529–0.0541 |
| Qualified width-64 identity | 2 | 1.0546 | 1.0293–1.0767 |
| Qualified width-64 identity | 32 | 1.4048 | 1.2470–1.4356 |

The command used opt-level 3, LTO disabled, 16 codegen units and four build jobs.
It is an optimized diagnostic profile, not the workspace's production LTO profile.
The shared macOS host's one-minute load average was 13.91 before the build/run
and 13.07 afterward. CPU isolation and steal measurement remained unavailable.
No absolute throughput or broad improvement is claimed.

The deep wide regression persists after optimization: every paired ratio exceeds
1.24, with a median around 1.40. It is material and blocks performance/upstream
readiness for the current candidate. Faster single-column cases cannot cancel
that result. The original debug 1.439 result remains retained; the optimized run
confirms the concern instead of providing grounds to dismiss it as debug overhead
or shared-host noise. Correctness qualification can preserve a local reference
without labeling its performance acceptable. Further focused investigation is
justified before deciding the repair is complete.

The smallest discriminating next experiment is two diagnostic source variants,
each retaining all other owned-rule behavior. One removes only the full-schema
condition on identity removal. The other restores only the broad equal-expression
shortcut. Compare stock, current and both variants in one optimized binary with
rotating execution order on the verified width-64 depth-two/depth-thirty-two plans,
plus one single-column identity control. Exact data, schema and source-pruning
oracles must pass before timing. Those identity fixtures satisfy the intended
properties; the variants remain unsafe general policies and must never be offered
as fixes. Wrong same-alias arithmetic remains excluded from timing.

If either variant isolates most of the cost, investigate a cheaper sufficient
proof that preserves the corresponding original failure controls. Only add a
combined ablation if interaction remains unclear. A broad cache/framework or
general profiler run is unnecessary before this bounded experiment. No production
source change is justified merely by disabling a correctness guard. Full immutable
qualification is still pending. No builds, source edits or measurements were
performed by this reviewer.

## Completed optimized ablation identifies the expensive proof

Prepared the 269-word standalone diagnostic plan before generating the probe,
variant copies and reversible runner under `review-logs/performance`. Preparation
made no product-source changes or builds. The implementation owner reviewed and
executed the harness. Read the complete terminal evidence in
`composition-ablation-v1/runs/20261106T083820.714872Z/`.

The run compiled and passed, with all four implementations matching direct exact
values, schemas, source pruning and final projection counts before timing. The
wide fixtures checked actual normalized qualifier/name bindings at each level.
Independently recomputed the medians from all 84 samples, covering three cells,
four implementations and seven rotating-order repetitions. Each sample contains
32 rule rewrites on a cloned analyzed plan.

| Identity fixture | Current/stock | No full-schema removal guard/stock | Broad equal-expression shortcut/stock |
| --- | ---: | ---: | ---: |
| Width 64, depth 2 | 1.0707, range 1.0551–1.4818 | 1.0459, range 0.9535–1.4270 | 1.0092, range 0.9274–1.3805 |
| Width 64, depth 32 | 1.3902, range 1.3497–1.4297 | 1.3803, range 1.3241–1.4218 | 0.9965, range 0.9529–1.0320 |
| Single column, depth 32 | 0.5918, range 0.5696–0.5990 | 0.5879, range 0.5709–0.6039 | 0.5429, range 0.5266–0.5532 |

The stock/stock reference is one by definition; its raw observations remain in
the complete sample record. Both diagnostic variants retain all other current
code, helper behavior and explicit recursion protection. Removing the full-schema
identity-removal check barely changes the deep-wide cost. Removing the additional
binding proof after expression-list equality removes most of it on these fixtures.
This localizes the dominant cost sufficiently to justify a narrower identity-fold
design; it does not justify adopting either unsafe ablation as a general fix.

A bare positional outer projection can be proven to pass through its child's
outputs directly, independent of whether the child's expressions equal the
parent's. Folding that passthrough while preserving its complete declared outer
schema avoids first comparing entire expression lists and then repeating a
binding proof. The new first-principles plan must constrain that proof, and the
implementation needs original arithmetic, schema, swap, volatility and conditional
controls plus the same eight-cell optimized comparison. No improvement is inferred
before that new source is measured.

The ablation profile is opt-level 3, LTO disabled, sixteen codegen units and four
build jobs. Shared-host one-minute load averages were 8.89 before and 11.14
afterward; CPU isolation and steal measurement were unavailable. This supports
diagnostic ratios only. The prior complete eight-cell optimized results remain
retained, including the material wide-chain regression of the current source.

Independently verified every preserved executed Rust artifact hash and the exact
original registry backup. The terminal receipt reports successful restoration of
all original candidate files, index tree and HEAD, with no restoration failures.
Temporary modules and the probe were moved into the run evidence. This measures
diagnostic copies added temporarily beside the frozen candidate, not weakened
production semantics.

The runner file was updated during the owner's execution-start window. Its final
file modification time is 08:38:30 UTC, after the receipt's 08:38:20 UTC start.
Preserved the exact earlier runner bytes by reversing recorded edits and matching
their previously printed SHA-256 `c8c3bb444c7e77df1d29ebf37efa767c33d5733f280c7cbbd276a227f3eb03c4`.
Those reconstructed bytes, a diff to the later `70607992...` revision and explicit
timeline are under `revision-evidence/`. They are not a captured process image.
The current runner file hash alone does not establish which Python revision was
loaded; executed Rust hashes, successful test and exact restoration are separately
verified and remain the measurement evidence. No restart or repeated result was
invented to hide that bookkeeping boundary.

This candidate's material wide-chain cost remains unresolved pending the narrower
fold and final source review. No production/upstream performance readiness is
claimed. No builds or tracked source changes were performed by this reviewer.

## Prepared near-identity controls for the narrower fold

Prepared a separate before-probe plan, `projection_composition_cost_probe_v3.rs`
and `parse_composition_cost_v3.py` under `review-logs/performance`, without building
or changing product source. All eight previous cells and their independent value
oracles remain. Two additional width-64 cells at depths two/thirty-two preserve
sixty-three qualified identity columns and increment only the final column under
unique aliases. A sixty-fifth unused source column keeps pruning observable.

The new oracle adds depth only to the final column's distinct source values.
The probe verifies actual first-sixty-three qualified positional bindings at
every analyzed level and records the last computed expression. This catches
late identity-proof failure and its possible extra planning cost while keeping
the stock result semantically valid. Direct, stock and owned values/schemas still
must match before timing. The parser requires all ten cells, seventy samples,
seven distinct repetitions and thirty-two invocations per sample.

A borrowed walk through consecutive bare identity projections can avoid rebuilding
or cloning child expression lists at every level. Each skipped projection must
pass the full-width, same-order, exact qualifier/name test against its immediate
child. Stop at the first computed, partial, reordered or mismatched projection.
Reconstruct once using the surviving child expressions/input and original outer
schema. An optional final equality comparison can reuse the owned outer vector;
it should not reintroduce per-level equality scans. These are source-level cost
and algebra observations, not an executed verdict on the new implementation.
New frozen source and the complete ten-cell measurement remain pending.

## Borrowed identity-chain measurement resolves the wide regression

Read the terminal `composition-cost-bare-chain-v1` log, receipt and summary.
The optimized build and ten-cell test passed, with unchanged measured source.
The owned module hash `229371de9c2971646b79cb8954817744cdb7adbe2859cd5942806440bac4e342`
matches the inspected current production body. Independently recomputed all ten
medians from seventy paired samples.

Compared probe v4 directly with prepared v3. Its only changes add assertions for
known final projection counts and source column selections, including constant
zero-column scans. All independent direct/stock/owned value and schema oracles
remain unchanged. The near-identity cells also verify actual first-sixty-three
qualified positional bindings and the final computed expression before timing.

| Expression | Depth | Median owned/stock ratio | Pair range |
| --- | ---: | ---: | ---: |
| Identity | 2 | 0.4918 | 0.4826–0.4963 |
| Identity | 32 | 0.6420 | 0.6354–0.6498 |
| Constant | 2 | 0.6515 | 0.6464–0.6588 |
| Constant | 32 | 0.8368 | 0.8276–0.8472 |
| Unique-alias arithmetic | 2 | 0.1782 | 0.1629–0.2115 |
| Unique-alias arithmetic | 32 | 0.0540 | 0.0526–0.0560 |
| Qualified width-64 identity | 2 | 1.0269 | 1.0235–1.0505 |
| Qualified width-64 identity | 32 | 0.9104 | 0.8797–0.9824 |
| Width-64 near identity | 2 | 0.4099 | 0.4088–0.4174 |
| Width-64 near identity | 32 | 0.2631 | 0.2606–0.2667 |

The formerly material wide deep-chain regression is resolved on these measured
equivalent-output cases: every final deep-wide ratio is below 0.983. Preserve
the prior 1.4048 result and ablation evidence rather than relabeling them. The
new near-identity cells show no late-proof-failure regression against stock in
this experiment. The shallow wide median retains a small 2.7-percent overhead,
with a maximum paired ratio around 1.05. It remains visible; additional speculative
tuning merely to force that cell below one is not justified by this evidence.

Source inspection matches the measured repair. The rule borrows through full-width
bare positional identities, checking each against its immediate child. It stops
before computed/reordered/partial boundaries and reconstructs once with the
surviving expressions/input and original outer schema. Final expression equality
only reuses an owned vector; it no longer admits skipping an arbitrary computation.
This avoids per-level vector rebuilding without a cache or a weaker binding rule.

The profile is opt-level 3, LTO disabled and sixteen codegen units. Shared-host
load averages were 15.79 before and 13.21 afterward; CPU isolation and steal
measurement were unavailable. These are diagnostic rule-planning ratios, not
production latency, full-compiler performance or runtime throughput. Faster
single-column results do not become a broad improvement claim. Metadata-rich
schemas and complete compiler workloads are covered by separate correctness
and gate evidence, not this limited timing matrix.

Freezing the candidate for final cumulative review and qualification is reasonable.
The executed matrix no longer identifies a material regression needing another
cost-specific repair. The implementation owner's reported affected tests precede
the additional prefix-selection control, which must be included in the final gate.
New source pins and full immutable qualification remain pending. Existing mixed-
marker and startup costs remain separate open limits. No builds, source edits
or measurements were performed by this reviewer.

## Final v2 source and cost verdict

Reread the saved request, repository instructions, `LAKESAIL.md`, `SHEHAB.md`,
`CLARITY.md`, `WRITING-RULES.md`, source development instructions and the
before-code identity-fold and borrowed-chain plans. This review complies with
the assigned read-only source scope. Independently verified the complete final
snapshot against current file contents and the Git index:

- Parent: `6e4da8d33ba1bf4073fcb853123f81860ef18151`.
- Upstream base: `b52144955b629314a000b1fe49eeea97fa3d0c5c`.
- Final tree: `1935edac69836542b67aa5ca25f5d794c14ee2b4`.
- Increment patch SHA-256:
  `42199c5a97525b898e516db90d415ecfed8f6098415ec3f58383dcadabb56101`.
- Cumulative patch SHA-256:
  `3dd8b8f09be9506f0fce1b3f4f611817d7567e47b4788c8a6b90eae0e5269bee`.
- All eighty-five cumulative file hashes and eleven increment paths match.
  No tracked unstaged changes were present.

Compared the complete final tree with the previously reviewed frozen tree
`a4801a8e6fb2d10d041d07aef9fc9ec1b7ff2bb6`. Only the owned projection rule and
its two test files changed. All eighty-two other cumulative paths, including
the existing Comet boundary, streaming operators, observability, participation
compiler and source wrappers, are byte-identical. Their earlier findings and
limitations therefore remain applicable; this increment does not repair the
known mixed-marker runtime or short-stream planning costs.

Inspected the final upstream comparison for the rule and its two helpers,
registration in both optimization paths, recursion protection, declared-schema
preservation and dependency remapping. The new production delta is the borrowed
positional-identity chain described above. Its proof remains linear in the fields
examined at each skipped boundary. It allocates no cache or per-level replacement
expression vector, clones at most the surviving expression vector, and retains
the complete outer declared schema. It does not change expression evaluation,
marker scheduling, native callback lifetime or execution locks. The ordinary
substitution and repeated-use computation guard remain for nonidentities.

The additional logical test covers full, reordered, prefix, suffix and empty
selections over thirty-two identities, with outer metadata and functional
dependencies. The execution test checks volatile and conditional child work
in ordinary and encoded-stream execution using exact invocation and row counts.
These assertions are substantive safeguards for the shortcut, not timing
thresholds. Their presence is verified; final execution qualification remains
the implementation owner's pending gate.

The terminal ten-cell measurement receipt lists exactly the final eleven
increment file hashes, including the production module hash recorded above.
Thus its measured production code is the frozen v2 code, rather than a nearby
unqualified revision. Preserve all ten cells, prior failed controls, the initial
deep regressions and the three-way ablation. The final deep-wide median is
0.9104 against stock, replacing the earlier material 1.4048 regression on that
same correct-output case. The shallow-wide median remains 1.0269. This small
residual does not justify another speculative repair or block the local reference
candidate on the measured evidence. No material introduced performance blocker
remains demonstrated for this increment's tested scope.

Read the strict mechanical preflight receipt for this exact tree: nightly format,
workspace all-target/all-feature Clippy and the affected strict Rustdoc checks
passed before freezing. The earlier affected-test and preliminary public-test
results do not replace the final immutable full gate. The cost verdict permits
that gate to proceed; it does not assert production readiness, general planning
improvement or completion of the broader SDP and Extensions work. Shared-host
and diagnostic-profile limits in the ten-cell assessment continue to apply.

## Final v3 ownership and performance review

Reread the saved request and governing instructions, including the before-code
`PROJECTION-CHAIN-OWNERSHIP.md`. Independently verified final tree
`21849a5803fcad439c651087885c101046ee2921`, all eighty-five cumulative file
hashes and eleven increment paths. The increment patch SHA-256 is
`437725b92d01339d336f055b234f5c720447358d42dacadcbb347155fb7db3bd`.
The cumulative patch SHA-256 is
`e8cfb314bd6fe1e8887b21d63ca98c4bca33c71f497a33e699b3a4156e0c6e6e`.
Parent and upstream base are unchanged from v2. No tracked unstaged differences
were present. Only the owned rule and its logical tests differ from v2; the
other eighty-three cumulative files retain their previous reviewed contents.

The ownership change addresses a real omission in the shared-plan timing
fixtures. Borrowing across identities avoided repeated clones, but dropping
a uniquely owned removed chain still recursively destroyed its input pointers.
The retained lifecycle control records baseline success and the v2 candidate's
stack overflow after entering rewrite at depth 8192 on an explicit one-MiB
thread stack. That earlier failure remains evidence against v2, regardless
of its passing shared-plan timings.

The final implementation first establishes replacement expressions and clones
the retained input pointer. It then unwraps uniquely owned skipped projection
nodes iteratively, moving each input onward before releasing its frame. Pointer
identity stops before the retained tail. Failed unwrapping stops at sharing,
where another owner keeps the subtree live. This adds linear release work in
the number of removed unique nodes with constant auxiliary state. It allocates
no traversal cache, clones no per-level expression vector and adds no locks or
per-row execution work. Each node must eventually be destroyed anyway. The
important change is bounded projection-chain destruction depth, not avoidance
of that necessary work. Arbitrary deep expression destructors and arbitrary
unrelated subtrees are outside this narrow guarantee.

Inspected the added fixed-stack test. It verifies unique ownership rather than
cloning away the failure, covers depths 8192 and 16384 with unique and shared
tails, and checks exact schemas and the original empty leaf. It verifies the
shared subtree stays intact and later consumes it through the rule, preventing
fixture teardown from hiding recursive destruction. The original standalone
control was rerun without changing its probe or runner: both baseline and final
candidate complete both depths and join successfully. Verified preserved probe
hash `228e0d58d9cce8fd48763db48c7b5d7db6f41d8b86b10ff8d840c49e88a2c866`,
runner hash `94d0392c28cc3a9b38fde197f2f495599b4f48d3115f1ecc9c00a9559f5cf10e`,
log hashes and restoration receipt in the `identity-drop-v2` run. The source
restoration claim also agrees with the independently verified final tree.

The final optimized ten-cell measurement uses the unchanged v4 probe, retaining
all value, schema, projection-count and scan-column oracles. Its receipt matches
all eleven final increment file hashes and reports unchanged source. Independently
recomputed the following from all seventy raw log samples, with seven paired
samples and thirty-two rewrites per sample in every cell:

| Expression | Depth | Median owned/stock ratio | Pair range |
| --- | ---: | ---: | ---: |
| Identity | 2 | 0.4854 | 0.4792–0.4919 |
| Identity | 32 | 0.6389 | 0.6227–0.6487 |
| Constant | 2 | 0.6549 | 0.6193–0.6720 |
| Constant | 32 | 0.8251 | 0.8145–0.8365 |
| Unique-alias arithmetic | 2 | 0.1789 | 0.1751–0.1878 |
| Unique-alias arithmetic | 32 | 0.0540 | 0.0508–0.0559 |
| Qualified width-64 identity | 2 | 1.0239 | 1.0088–1.1287 |
| Qualified width-64 identity | 32 | 0.9244 | 0.9218–0.9384 |
| Width-64 near identity | 2 | 0.4130 | 0.4089–0.4173 |
| Width-64 near identity | 32 | 0.2620 | 0.2612–0.2636 |

The earlier material deep-wide regression remains resolved on the measured
correct-output cases. The shallow-wide median retains 2.4-percent overhead,
including a paired maximum of 1.1287; preserve the entire range rather than
discarding that sample. Faster cells do not cancel slower cells. The small
median residual does not justify a further speculative change or block the
local correctness-reference candidate on this evidence.

These are shared-host rule-planning ratios on the same ten-CPU Mac. Load was
18.74 before and 12.55 afterward; steal is unavailable on macOS. The diagnostic
uses optimization level three, LTO disabled and sixteen codegen units. The log
contains the optimized build completion and passing selected test. Analysis,
physical planning and execution remain outside the timed region. Shared plan
clones mean these cells do not quantify uniquely owned deep-chain release
throughput. Its safety is established separately by the structural proof and
fixed-stack controls, without a new speed claim.

The exact-tree mechanical receipt records passing nightly formatting, strict
workspace all-target/all-feature Clippy and affected strict Rustdoc before
freezing. The implementation owner reports 166 affected tests passed and one
pre-existing skip; the immutable full gate and final public qualification remain
pending. No additional material performance blocker is demonstrated for this
increment's inspected and measured scope. Existing mixed-marker and startup
limits remain open. This is a source and bounded cost verdict, not general
production or upstream readiness. This reviewer performed no builds or source
edits and inspected executions performed by the implementation owner.

## Final v4 atomic retirement and exact-pin verdict

Reread the saved request and governance, the updated ownership note and the
atomic-retirement plan recorded before this implementation. Independently verified
all eighty-five cumulative file hashes, eleven increment paths, both binary patch
hashes and the Git index tree. No tracked unstaged changes were present.

- Final tree: `b337dfd145db4773ba1aa019028a8e9c86bbaa67`.
- Increment SHA-256:
  `d0be097703b5ce7ba7f1e8400dfd486ee492f9d64f2c91437a8e4f86409cc227`.
- Cumulative SHA-256:
  `01226d1ed79d26afa4cd9e36d1e331b365d3ad4ba93c434fbbc50636262c991c`.
- Parent remains `6e4da8d33ba1bf4073fcb853123f81860ef18151` and upstream base
  remains `b52144955b629314a000b1fe49eeea97fa3d0c5c`.

The complete v3-to-v4 source diff changes one line: discarded owners now use
`Arc::into_inner` and `Some`, replacing `Arc::try_unwrap` and `Ok`. All other
eighty-four cumulative paths are unchanged. The live retained-tail pointer and
pointer-identity termination remain intact.

Checked the pinned [Rust 1.98.1 implementation and API contract](https://github.com/rust-lang/rust/blob/1.98.1/library/alloc/src/sync.rs#L1034-L1204).
Dropping failed `try_unwrap` results can race with another owner and invoke
ordinary destruction. `into_inner` instead atomically retires this reference;
it returns the value when retiring the last owner and otherwise returns no
value, without invoking that value's destructor here. This directly fits the
iterative release loop. No new concurrent crash reproduction is claimed. External
owners' destruction and arbitrary expression destructors remain outside the
guarantee.

The cost model remains linear work in the unique removed nodes with constant
auxiliary state. The standard-library operation is an atomic reference decrement,
not an added mutex or per-row operation. There is no additional traversal, cache
or expression-vector cloning relative to v3. The replacement tail stays alive
before retirement begins, so release does not consume the retained subtree.

Verified the preserved original lifecycle probe and runner hashes in the
`identity-drop-v3` run, including each log hash and both completed/joined depth
markers. Baseline and final candidate pass depths 8192 and 16384 on the explicit
one-MiB stack. The receipt records exact source restoration, which agrees with
the independently verified current tree. These repeat the finite unique-chain
control; they do not establish an arbitrary concurrent destruction envelope.
The prior failing no-release run remains retained.

The final optimized receipt matches all eleven final increment file hashes and
the unchanged v4 timing probe. Independently recomputed every result from the
seventy raw samples. All ten exact value/schema, pruning and projection-count
oracles pass before timing. Seven alternate-order pairs and thirty-two rewrites
per sample remain in every cell:

| Expression | Depth | Median owned/stock ratio | Pair range |
| --- | ---: | ---: | ---: |
| Identity | 2 | 0.4838 | 0.4670–0.4938 |
| Identity | 32 | 0.6413 | 0.6340–0.6507 |
| Constant | 2 | 0.6677 | 0.6571–0.6816 |
| Constant | 32 | 0.8532 | 0.7796–0.8623 |
| Unique-alias arithmetic | 2 | 0.1744 | 0.1698–0.1787 |
| Unique-alias arithmetic | 32 | 0.0528 | 0.0520–0.0551 |
| Qualified width-64 identity | 2 | 1.0247 | 0.9765–1.0282 |
| Qualified width-64 identity | 32 | 0.9169 | 0.9028–0.9492 |
| Width-64 near identity | 2 | 0.4123 | 0.4094–0.4212 |
| Width-64 near identity | 32 | 0.2637 | 0.2618–0.2658 |

The material deep-wide regression remains resolved on the measured cases;
every final pair for that cell is below 0.95. Retain the shallow-wide median
overhead of 2.5 percent and its entire range. It does not justify speculative
tuning or block the local reference candidate on these measurements. Other
faster cells do not erase that residual.

The optimized build completion and passing selected test are present in the log.
The profile remains optimization level three, LTO disabled and sixteen codegen
units on the shared ten-CPU Mac. Load was 16.65 before and 12.96 afterward;
steal is unavailable. These rule-planning ratios include a shared plan clone and
exclude analysis, physical planning and execution. They make no claim about
uniquely owned release throughput, complete compiler latency or production speed.

The exact-tree mechanical preflight records passing strict workspace all-target,
all-feature Clippy, nightly formatting and affected strict Rustdoc before freezing.
No additional material performance blocker is demonstrated within this finite
source and measurement scope. The full immutable gate and final public checks
remain pending. Earlier mixed-marker and startup limitations remain open, and
the broader SDP and Extensions objective remains incomplete. This reviewer
performed no builds or source edits.
