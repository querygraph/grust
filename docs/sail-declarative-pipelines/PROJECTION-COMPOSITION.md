# Preserve computation and schemas when combining projections

Projection optimization must preserve values and the declared output schema. Two
successive projections computing `v + 1 AS v` must add twice. Equal expression text
reads different input scopes. Isolated DataFusion 55.2 and unchanged Sail-owned copies
instead drop an addition. Both copies also lose output qualifiers, field metadata and
schema metadata during reconstruction.

Waiting for a dependency repair delays delivery. Disabling the rule sacrifices column
pruning. Renaming aliases around it adds scoping machinery without controlling
internally created projection pairs. Postprocessing cannot recover discarded computation
or metadata.

Recommend owning the existing rule and private helpers inside Sail's logical optimizer.
About 1,142 existing production lines are carried; the framework stays. Use the same
implementation in ordinary optimization and streaming preparation. Use ordinary
child-output substitution for computed expressions. Borrow bare positional identity
chains and reconstruct once. Release skipped wrappers iteratively. Equal alias/literal
lists still require same-position binding.

Preserve the declared outer schema when composing unchanged output positions. When
pruning columns, select its original qualified fields and metadata, remapping
column-dependency guarantees to their retained indices. Remove an identity projection
only when its complete output schema matches its input. Do not introduce casts, new
nullability policy or arbitrary type substitution.

Retain exact pinned originals, attribution and comparisons. Preserve recursion
protection with the locked version. The unchanged copy must reproduce both failures.

Verify original arithmetic and schema oracles, identity, pruning, dependency remapping,
subqueries and both registrations. Execute resulting physical plans too: schema
construction alone checks only column count. Preserve volatile evaluation counts and
conditional guards. Measure valid old/new plans without timing incorrect results as
equivalent work.

Spark 4.2.1 source confirms dependent composition and alias metadata preservation; JVM
parity was not executed. Does ownership preserve computation, schemas and optimization?
The [identity-fold decision](PROJECTION-IDENTITY-FOLD.md) explains the planning-cost
choice.
