# Fold positional identity projections without comparing computations

Projection optimization must preserve computations and their declared output fields.
Sail's owned rule repairs discarded additions and metadata, but equal-list shortcuts
now require a binding proof. An optimized deep, wide identity fixture takes about
1.40 times the stock rule's planning time. The extra checks need investigation.

An outer projection that selects every child output once, in the same position,
changes no values. Require equal widths and bare column expressions whose qualifier
and name exactly match each child field. Then reuse the child's expressions and
original input, retaining the complete outer declared schema. Computed, volatile
and conditional child expressions remain unchanged and execute exactly once.
Zero-column projections retain their row-count behavior.

Fusing equality and binding checks saves a traversal but still compares computations
that an identity output does not need to inspect. Caching proofs introduces state
and invalidation rules. An early positional identity fold directly applies the
ordinary identity law and needs neither cache nor expression substitution.

Recommend this narrow fold if isolated diagnostics attribute material cost to
repeated binding checks after expression equality. Keep aliases and literals under
the existing guarded route. Continue ordinary substitution for computed outputs.
Never weaken schema equality or allow reordered or partial selections through
this shortcut.

Verify computed, volatile and guarded child execution, outer metadata and dependency
guarantees, empty outputs, width mismatches and reordered columns. Re-run every
correct timing cell, including nonidentity cases, and retain the original failing
safety controls. Does the identity law remove redundant planning work while preserving
all original oracles? Correctness checks and measured costs must settle it.
