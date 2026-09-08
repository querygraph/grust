# Resident-index and PostgreSQL read review

Base: `29fd384`; isolated branch `perf/resident-index-build`.
Companion benchmark branch: `review/adapter-reliability`, based on `9ee4d47`.
These are implementation candidates and small diagnostics, not a publication
cohort. Existing benchmark processes, source checkouts, and reports were not
modified. The harness still uses its original published/pinned dependencies.

## Changes

- Sparse `TypedGraphIndex` construction sorts its existing temporary triples
  in place for both directions, retaining physical edge slots. It no longer
  allocates a second relation-sized sort vector per direction. Grouping borrows
  label keys from the immutable graph, cloning each distinct output key once.
  Public APIs, dense/sparse selection, query semantics, and snapshot ownership
  stay the same.
- PostgreSQL node/edge reads use `query_raw` and decode each row as it arrives.
  Decoding borrows identifier and property text from the protocol row until
  owned graph values have been constructed. This removes temporary owned text
  copies and an eagerly collected `Vec<Row>`. The result is still a complete
  owned `Vec<Node>` or `Vec<Edge>`; this is not a streaming public API and does
  not make the resident graph memory-bounded.
- New live regression coverage checks thousands of rows with Unicode,
  escaping, nulls, arrays, and large properties; server errors after a valid
  prefix; decoding failures with unread wire messages; empty results; and a
  successful query after a dropped stream. The original transaction,
  differential Cypher, and snapshot-invalidation suites also pass.

## Evidence and limits

Raw outputs are in `../review-evidence/`. Earlier experiments and failed test
attempts remain there; later outputs do not overwrite them.

| Diagnostic | Before | Candidate | Interpretation |
|---|---:|---:|---|
| Sparse index build: cumulative requested allocation, bytes | 94,705,040 | 70,701,124 | About 25% less allocator traffic; not a peak-RSS claim |
| Sparse index build: median client CPU ticks | 47 | 47 | No demonstrated CPU improvement |
| Dense index build: median client CPU ticks | 43 | 43 | No demonstrated CPU improvement |
| PostgreSQL read/decode: median client CPU ticks | 39 | 34 | About 13% less client CPU in this synthetic diagnostic |
| PostgreSQL read/decode: median client peak RSS, KiB | 237,344 | 229,788 | About 3% less process peak RSS, not an SF0.3 capacity result |

The index diagnostic builds 100,000 vertices and 1,000,000 physical edges with
either 128 sparse types or one dense type. All edge identities, endpoint
directions, labels, and cardinalities are checked after construction. The
allocator measures requested bytes, excluding allocator overhead; retained
graph data is outside the index-build allocation boundary. Three paired
before/after runs alternate order. `index-paired.json` contains each result.
Sparse peak requested allocation changed little because the retained index
dominates this fixture. This optimization does not explain or solve the
earlier multi-GiB setup failures.

The PostgreSQL diagnostic reads 100,000 generated relationship rows with a
1,024-byte string property, using fresh test processes and the same optimized
binary. Its buffered path preserves the original collection and decoding
algorithm; its streamed path uses the candidate adapter. Every returned
identity, endpoint, label, and property is checked. There are three paired
runs, with order reversed in the middle pair, in
`postgres-release-{0,1,2}-{buffered,streamed}.log`.

CPU ticks are process user plus system time; this host reports 100 ticks per
second. The PostgreSQL release runs record one-minute host load of 3.40–3.61;
the index records carry their own load values. Wall times on this shared host
are upper bounds: inspect client CPU and recorded load alongside them. Server
CPU was not measured in this decoder diagnostic, so it supports no claim about
total system CPU, query throughput, or a comparison between database engines.
Initial debug-profile PostgreSQL attempts did not show a CPU improvement and
remain in `postgres-*.log`; they are not mixed into the release-profile rows.

The disposable PostgreSQL instance used cached image
`sha256:1c59e2c3c818eaa0f0628f695b36e7c9e362d6b219b36a54a32df645cbd7e1af`,
one CPU, one GiB, no swap allowance beyond that memory budget, a private
database, and host port 25439. That small diagnostic server budget is not the
proposed resource envelope for a performance matrix.

## Validation

- 201 default-feature tests/doc tests across `grust-core`, `grust-memory`,
  `grust-postgres-core`, and `grust-turso`: pass (`final-regressions.log`).
- After the additional borrowed-text decoding change, PostgreSQL's 21 offline
  tests and eight live regression tests pass (`postgres-borrowed-unit-tests-fixed.log`
  and `postgres-final-regressions.log`). The earlier diagnostic compilation
  error and the sandbox connection failure are retained in separate logs.
- Release diagnostics: six successful fresh-process runs. They are diagnostics,
  not six independent workload correctness suites.
- Modified Rust files pass rustfmt; both worktrees pass `git diff --check`.
- The companion harness's 24 default-feature tests pass (one existing test
  ignored). It now gates A8 errors/timeouts, prevents a pass with missing oracle
  coverage, and preserves a failing headline when another operation is refused.

No full workspace/all-feature release check, packaging gate, or publication
was performed. No dependency pin was advanced. The release runbook (`PUBLISH.md`)
requires a separate explicit release request for publishing crates and book
artifacts; these branches are a source handoff, not a released version.

## Before another long run

Retain the 6 GiB rows as capacity observations. Select a performance envelope
from actual setup peaks plus headroom, with equivalent total client/server
accounting. A 16 GiB SF0.3 canary is a candidate to evaluate, not a guaranteed
fit or a universal default. Run short correctness and setup checks for every
admitted backend, freeze the chosen envelope, and then measure selective reads,
expansion, aggregation, returned rows, mutation, and recovery separately.

The larger remaining opportunity is graph/index ownership and setup peak
memory, especially repeated durable read-back and simultaneously retained
representations. Profile those on one cell before redesigning the builder.
Offline launcher fixtures, owned process termination, actual cancellation,
complete expected-cell accounting, and corrected open-loop arrivals should
precede another broad matrix. The companion review has source references and
backend-specific cases for each of these follow-ups.
