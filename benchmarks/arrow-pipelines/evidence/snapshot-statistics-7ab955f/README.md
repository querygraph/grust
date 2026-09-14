# Exact snapshot statistics qualification

Source `7ab955f`, Capitola, four nice Cargo jobs. Locked DataFusion all-feature
tests: **47 passed, zero failed, zero ignored**. Warnings-denied all-target
Clippy passed. Raw logs are in `qualification-logs.tar.gz`.

Tests retain empty schema-only tables, multiple sliced edge batches, isolates,
parallel relationships with duplicate external IDs, snapshot cloning and session
catalog replacement. Counts remain exact and the added ordinal payload is eight
logical bytes per edge. Lookup performs no provider scan or graph export.

These are captured row/batch counts, not selectivity, join-size, parallelism,
serialized-input-size or whole-process-memory estimates. This is unreleased
routing preparation; automatic selection and complete policy admission remain
outstanding. No benchmark performance claim or source-pin change is made.
