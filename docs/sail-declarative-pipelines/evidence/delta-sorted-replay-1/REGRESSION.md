# Sorted Delta replay: final correctness regression review

**No introduced correctness or functionality regression was identified in the
completed public matrix.** All required comparisons use the frozen candidate's
exact final CLI and native artifacts. Performance assessment and immutable landing
qualification remain separate requirements. The external Delta suite still has
inherited failures, expected failures and skips; this is not an all-tests-pass claim.

| Pin | Value |
| --- | --- |
| Frozen tree | `5181d08ac4b48dca578ea046a0313f572507e30a` |
| Parent | `3f741daad57df4bcc22cecfb7802d458b1ad1d06` |
| Upstream | `b52144955b629314a000b1fe49eeea97fa3d0c5c` |
| Candidate CLI SHA-256 | `99360acacc78671397a4bf0832bf2ae471916f300a0309a1daf9e07ba8c6c114` |
| Candidate native SHA-256 | `54c123351d0a3c0429444b5de39ded41d8ac33404d4ebb81daf3fc54c4957511` |
| Regression audit SHA-256 | `5354730e88f09eed97503b19e2b17219e75f95be36a7397716a23f20b6254f4c` |

The final audit is `regression-preparation/REGRESSION-AUDIT-v1.json`. It retains
1,475 evidence/source/artifact pins and all literal nonpassing reasons. The earlier
`REGRESSION-SOURCE.md` records the source analysis; this review resolves its public
runtime evidence requirements. Its performance and broader integration limits remain.

## Complete comparisons

All nine stages are terminal with complete node/phase records and stopped owned
processes. There were no deselections, collection errors, internal errors, duplicate
nodes or missing phases. Test sources, recorder, client versions, server execution
settings and resolved JVM dependencies compare equally. The client remains PySpark
4.2.1 with PyArrow 26.0.0.

| Artifact | External Delta: 2,185 nodes | Native: 17 nodes | Prior public: 51 nodes |
| --- | --- | --- | --- |
| Upstream | 2,120 pass; 2 fail; 42 xfail; 21 skip | 17 pass | 40 pass; 11 fail |
| Parent | 2,120 pass; 2 fail; 42 xfail; 21 skip | 17 pass | 51 pass |
| Candidate | 2,120 pass; 2 fail; 42 xfail; 21 skip | 17 pass | 51 pass |

This totals 6,759 node executions, not 6,759 distinct tests. Each external run also
retains the same separately recorded concurrency-module collection skip. The exact
inherited nonpassing node/category set agrees with the earlier qualified baseline.
The fifteen new Delta history nodes pass on all three artifacts.

Six comparison reports preserve 99 changed rows: 44 literal reason differences
against each baseline and eleven upstream public failures that pass on the candidate.
Every row has one explicit, pinned resolution; none was erased or relabelled as a
matching result. All parent public/native results and upstream native results match.

## What the differences establish

The 88 inherited reason differences retain their original failure/xfail status.
Independent inspection covered all 232 literal line hunks. They comprise object
addresses, fixture locations and pytest truncation, generated physical-column UUIDs,
one dictionary display-order change, and four INTERSECT operand-pair diagnostics.
Both reported INTERSECT pairs come from unchanged fixture rows and retain the same
unsupported list-comparison error. No successful INTERSECT result is claimed.

The two ordinary failures still stop at JVM-created Parquet-layout assertions before
Sail row checks. Seventeen external skips pass in the native selection. Four skipped
nonnullable nested-field evolution cases and the flaky concurrency module remain
uncovered. No supplementary retained-table read is used to turn failures into passes.

The eleven upstream public improvements cover three zero-column row-count errors,
five source-participation/admission failures, two qualified-field binding failures,
and one missing streaming waiter exception. Exact candidate tests now pass. The two
upstream binding failures occurred before marker-expression evaluation, and the
console failure stopped at its first waiter assertion; those traces do not prove
later behavior independently. Per-node rationale and limits are retained in
`UPSTREAM-PUBLIC-FAILURES-v1.json` and the final audit.

The final batch matrix also passes all 96 executions: parent/candidate, batch sizes
1, 7 and 8,192, fifteen eager/hash/sort history cases and the existing valid
deletion-vector identity test. Artifact bytes, source inventory, forced batch settings,
node identities and terminal cleanup were independently checked. Assertions and
forced Sort/Hash plan checks remain intact.

This review does not establish deep-stack process-abort coverage, distributed recovery,
connector integration or a production performance envelope. It does not authorize
commit, push, remote PR or cleanup. The saved continuation and required governance
were reread; compliance is confirmed. This role ran only read-only evidence comparison
and audit scripts, with no builds, tests, servers, source edits or changed assertions.
