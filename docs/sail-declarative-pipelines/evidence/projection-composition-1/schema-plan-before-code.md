# Preserve computation and schemas when combining projections

Projection optimization must preserve values and the declared output schema. Two
successive projections computing `v + 1 AS v` must add twice. Equal expression text
reads different input scopes. Isolated DataFusion 55.2 and unchanged Sail-owned
copies instead drop an addition. A separate control shows both copies losing
explicit output qualifiers, field metadata and schema metadata during reconstruction.

Disabling the rule sacrifices column pruning. Renaming aliases around it adds
scoping machinery without controlling internally created projection pairs.
Postprocessing cannot recover discarded computation or metadata.

Recommend owning the existing rule and private helpers inside Sail's logical
optimizer. This carries about 1,142 upstream production lines without replacing
the optimizer framework. Use the same implementation in ordinary optimization
and streaming preparation. Remove the equal-expression shortcut and retain ordinary
child-output substitution.

Preserve the declared outer schema when composing unchanged output positions.
When pruning columns, select its original qualified fields and metadata, remapping
column-dependency guarantees to their retained indices. Remove an identity projection
only when its complete output schema matches its input. Do not introduce casts,
new nullability policy or arbitrary type substitution.

Copy pinned upstream source exactly before adaptation, retaining attribution and
comparison evidence. Preserve recursion protection explicitly using the already
locked version. The copy must reproduce both failures.

The correction must pass original arithmetic and schema oracles, identity and
pruning controls, dependency remapping, subqueries and both registration paths.
Execute resulting physical plans too: schema construction alone checks only column
count. Preserve volatile evaluation counts and conditional guards. Measure valid
old/new plans without timing incorrect results as equivalent work.

Spark 4.2.1 source confirms dependent composition and alias metadata preservation;
JVM parity was not executed. Does this owned rule preserve the complete projection
contract? Controlled failures, exact comparisons and regression checks must settle it.
