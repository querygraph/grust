# Expression subquery traversal and wildcard binding

Two small Sail commits on163b2fb52 prepare the ordered input-binding phase from
[the configuration design](../../FLOW-CONFIGURATION-DESIGN.md). No configuration
fusion, public captured execution, streaming/CDC effect path or new admission
policy is activated by this extraction.

## Wildcard gap correction

744b1686734dac6257ed61c816327266c9310047 makes the bounded read classifier inspect
WildcardOptions.replace_columns[*].expression. Previously UnresolvedStar was a
leaf even though native wildcard resolution resolves replacement expressions,
including subqueries. Other wildcard options contain names/patterns, not Expr.
The new tests reject an unbound batch read and a helper-executing Tail hidden in a
replacement; a local bound read remains accepted. A separate native PlanResolver
witness resolves the exact expression and records both outer and nested reads,
so this is not a synthetic expression refused before its subquery is reached.
No scan or external catalog SDK is exercised by that witness.

Exact detached formatting, strict all-target/all-feature Clippy and148 Connect
library tests pass. Unchanged negative controlc88fa1d0c restores the old leaf;
one native witness passes and one classifier test fails (hidden read wrongly
accepted). Only binding.rs changes in the control; test blobs are unchanged.
The initial fdd7ea466 compile failure is retained: a test Mutex poison error
needed explicit conversion to PlanError. Assertions were not weakened.

## Shared pure traversal

7a50f2875f0d0042d923658668cfe2671fc56255 moves expression/window query descent into
sail-common's typed spec, reused by the existing bounded binder. No DataFusion or
other dependency is added. FnMut callbacks borrow the original QueryPlan and
preserve expression/list order, repeated occurrences and the first typed error.
A callback owns the policy for descending into a query; opaque Subquery plan-ID
references are not expanded automatically. Tests cover reference identity (even
for equal plan IDs), repetition, stopping/error identity, wildcard/window/frame
children, and the explicit query/plan-ID boundary. No general Catalyst traversal
order or CTE policy is claimed by the expression helper.

Exact detached formatting, strict all-target/all-feature Clippy and28 common+
148 Connect library tests pass. Independent controlafcd25fa2 reverses expression
list visitation without changing tests:2 pass/2 fail, including original query
pointer identity and the prefix before the callback error. The initial453ff6d80
compile failure is retained: Infallible callback results needed explicit type
annotation in three tests. No behavioral assertion changed.

The latest public CLI regression remains163b2fb52 (300 selected+67 upstream), not
these new commits. No new concurrency scheduling is introduced and no new stress
verdict is claimed. Raw Rust linker warnings are retained in logs. Fable reviewed
unit1 with no change requested (CF-0260); unit2 offered in CF-0261. Source patches,
positive receipts, unchanged-test controls, failed attempts and review snapshots
are retained here, all covered by SHA256.json.
