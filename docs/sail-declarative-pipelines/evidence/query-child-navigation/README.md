# Query child navigation and bounded sampling classification

Three human-reviewable Sail units build on7a50f2875. These are preparatory binding
and admission changes: the thirteen-case configuration comparison still has
3 matches/10 differences. The [next native design](../../NATIVE-INPUT-BINDING-DESIGN.md)
uses ordered graph-view tracing with the existing resolver; provider slots remain
a deferred fallback, not a selected representation.

## Sampling classification

6db005e39bbf07ad6ba9a1e7cae7d9ca8a46d417 inspects sampling expressions in both
ReadNamedTable.sample and QueryNode::TableSample. Hidden unbound batch/streaming
reads and Tail helpers are refused. Literal Percent and Bucket forms retain their
classification. ROWS contents are conservatively inspected, but generic native
ROWS remains unsupported; no execution or hidden-I/O witness is claimed for it.
Two native Percent witnesses show the nested read is reached before foldability
validation at both sites. They exercise a resolver scope, not a scan or SDK.

Exact detached fmt/strict all-target/all-feature Clippy/150 Connect libraries
pass. Restoring the old walk in controld5058ba21, with tests unchanged, gives
1pass/1fail: native witness passes, classification wrongly accepts the hidden read.

## Shared structural navigation

75f63e823fcc0d9a23e3acfaefe73c4429ddc094 adds QueryChild::{Expression,Window,Query}
and QueryPlan.visit_children to sail-common, reused by the bounded binder. It
borrows original children, retains field/list order and repeats, and returns the
first callback error unchanged. Expressions/windows precede query inputs; raw
CTE definitions precede the body, WithRelations references precede root. It
exposes temporal/sample/dynamic-name/UDTF/predicate expressions too. This is
structural navigation, not CTE interpretation, plan-ID expansion, execution or a
general Catalyst-equivalence claim. No DataFusion or other dependency is added.

The binder retains its read/helper/dynamic-Python refusals and CTE keep-last scope.
Five common contract tests cover nested query order, repeated children, original
identity and first-error boundary, CTE/reference structural behavior, modifier
expressions and named windows. One classifier test checks a Filter's unbound
condition read is reported before its unbound body. Existing binding tests remain.

Exact detached fmt/strict Clippy/33 common+151 Connect libraries pass. Source-only
controlf3178c5af swaps Filter input before expression, with unchanged tests:
4pass/1fail; the first-error boundary test detects the prematurely visited input.
Initiald0ea6206a failed the test-only Clippy panic lint. Replaced the panic branch
with an explicit later-input counter and zero assertion; no waiver or relaxed
behavioral assertion. Failed receipt/source/logs remain archived.

## Explicit admission policy

0d0064b6e6106a0f817926ff8a46965017248275 takes Fable's review recommendation and
lists every navigated QueryNode kind in the policy pre-match instead of a default
arm. A future query kind requires both a navigation implementation and an explicit
admission decision. This is a separate small commit, preserving offered history.
Exact fmt/strict Clippy/151 Connect libraries pass. No new tests mirror Rust's
exhaustive-match rule. The common source is unchanged from75f63e823's33-test gate.

Fable reviews e45000ab/CF-0269 cover the first two units; the third implements its
minor policy recommendation. No new concurrency schedule or optimized stress
verdict is claimed. Latest rebuilt public CLI gate remains163b300+67, not these
commits. All raw linker warnings, failed attempt, exact positive gates, controls,
source patches and review snapshots are covered by SHA256.json.
