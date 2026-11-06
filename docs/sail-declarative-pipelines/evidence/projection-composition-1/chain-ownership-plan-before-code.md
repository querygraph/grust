# Release removed projection chains without recursive destruction

Sail must optimize deeply nested queries without crashing. A projection owns its
input through an Arc, Rust's shared ownership pointer. Removing a long chain must
preserve computations and bound destruction depth as well as optimizer recursion.

Borrowed identity folding proves many pass-through layers before reconstructing
once. If the original chain has one owner, dropping that owner recursively destroys
the skipped layers. The optimizer's recursion guard does not protect generated
destructor calls. A fixed-stack control passes with the previous rule and overflows
during the borrowed rule's rewrite. Shared-plan timing fixtures do not exercise
this ownership condition.

Limiting chain length requires a platform-dependent stack threshold. Increasing the
thread stack only moves the limit. A general custom destructor changes ownership
far beyond projection optimization. Prefer consuming only the proven skipped
projection chain iteratively.

Establish the replacement expressions and keep the surviving input alive first.
Then unwrap uniquely owned projection nodes one at a time, moving their input
onward before each frame is released. Stop at the retained input or shared
ownership. The live replacement tail prevents destruction of an unrelated subtree.
This bounds projection-chain release without a cache or another execution framework.

Verify deep uniquely owned and shared-tail plans on a fixed small stack, with exact
schemas and original leaves. Retain the failing no-release control and rerun all
value, volatility, metadata and planning-cost checks. This contract concerns removed
projection chains, not arbitrary expression destructors. Does explicit ownership
release preserve the identity fold's benefit while eliminating the demonstrated crash?
