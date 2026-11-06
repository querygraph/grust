# Fold positional identity projections without comparing computations

Projection optimization must preserve computations and their declared output fields. A
guarded-equality repair preserves additions and metadata but needs binding proofs. Its
optimized deep, wide identity fixture takes about 1.40 times stock planning time.
Comparing computations before proving identity adds redundant work.

An outer projection that selects every child output once, in the same position, changes
no values. Require equal widths and bare column expressions whose qualifier and name
exactly match each child field. Then reuse the child's expressions and original input,
retaining the complete outer declared schema. Computed, volatile and conditional child
expressions remain unchanged and execute exactly once. Zero-column projections retain
their row-count behavior. Borrow through consecutive identity projections and
reconstruct once, avoiding repeated child-expression cloning. Keep the replacement input
alive while releasing uniquely owned skipped projections iteratively.

Fusing equality and binding checks saves a traversal but still compares computations
that an identity output does not need to inspect. Caching proofs introduces state and
invalidation rules. An early positional identity fold directly applies the ordinary
identity law and needs neither cache nor expression substitution.

Use this narrow fold to avoid repeated binding checks after expression equality. Keep
aliases and literals under the existing guarded route. Continue ordinary substitution
for computed outputs. Keep full-schema equality when removing a projection entirely.
Reordered or partial selections must not use this shortcut.

Verify computed, volatile and guarded child execution, outer metadata and dependency
guarantees, empty outputs, width mismatches and reordered columns. Re-run every correct
timing cell, including nonidentity cases, and retain the original failing safety
controls. Does the identity law remove redundant planning work while preserving all
original oracles? Correctness checks and measured costs must settle it.
