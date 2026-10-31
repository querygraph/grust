# Full-refresh target and auxiliary-state cleanup

Integrated Fable's A1 offer in two human-reviewable commits: a general Sail catalog fix invalidates the directory-listing cache after TRUNCATE, followed by pipeline auxiliary-table identity and full-refresh cleanup. The implementation diffs are identical to offers a0b3cecb2 and bd782c422; their commit messages and Fable coauthor credit are preserved.

DatasetManager materialization now truncates a fully refreshed target, takes its declared schema instead of merging the previous generation, and drops only that target's AutoCDC auxiliary state through Sail's existing catalog/command path. It also drops stale auxiliary state when creating an absent target. `pipelines.reset.allowed=false` downgrades the request to refresh and preserves data/state. Repeating the drop is harmless. Auxiliary identifiers preserve catalog/database and use Spark's reserved table prefix; key names use compact JSON string arrays.

Qualification on the exact combined source: formatting, strict Clippy, 20 catalog and 214 Connect native tests, 300 selected public plus 67 upstream Python tests, and the ten existing analysis-order/no-flow/streamingness regressions. Native full-refresh coverage seeds rows and auxiliary tables, checks preservation when reset is disabled, then checks truncation, schema replacement, selected auxiliary drop, unrelated-state preservation and repeated refresh. The public-execution regression still requires rejection of incremental outputs before catalog effects.

This implements metadata/full-refresh cleanup and auxiliary naming, not CDC writes, checkpoint reset, Iggy durability or complete Spark SDP conformance. Existing public streaming/sink effects remain disabled.
