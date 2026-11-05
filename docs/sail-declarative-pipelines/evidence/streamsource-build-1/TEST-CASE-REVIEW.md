# Test case review

No must-fix source or test-coverage defect found in the reviewed snapshot. This
is a review verdict, not a completed build or release gate. Validation of the
latest filter polling path and exception response still needs the final pinned
candidate receipts.

## Reviewed candidate

- Sail baseline: `b52144955b629314a000b1fe49eeea97fa3d0c5c`.
- Cumulative artifact: `review-logs/cumulative-four-design-notes.patch` in
  `/Users/alexy/src/sail/tmp/streamsource-build-20261105-b52144955`.
- Verified SHA-256:
  `6782613a31c5278296421622c5a5fcea918603506a70de62c0f77671fa0f3376`.
- Read the complete 19-file patch, surrounding query and service code, and the
  four preceding design notes. Reviewed event fidelity, filter marker isolation,
  query and console failure propagation, and the exception response correction.

Read the saved full request and AGENTS.md, LAKESAIL.md, SHEHAB.md,
WRITING-RULES.md and CLARITY.md, including the required reread after context
compaction. The saved request was checked again for this final review. The
review made no source edits and ran no builds or tests. Earlier assigned work
authored the two fidelity test modules and added the run-end child-length
assertions before this snapshot was frozen.

## Discriminating coverage

The fidelity tests use the actual encoder and decoder. They preserve positive
row counts with no payload columns, retractions, all four marker kinds, schema
metadata and nested field metadata. Every contiguous slice of a ten-row mixed
batch is checked with both empty and nonempty payload schemas. Expectations
derive from source events, without assuming original data-batch boundaries
survive encoding.

The Arrow matrix covers every applicable type family, rather than every possible
parameter combination. Separate tests prevent an early decimal failure from
masking zero-column, metadata or run-end failures. Checks include exact types,
full Arrow validation, all decimal widths, positive and negative scales, nested
decimals, dictionary key widths and run-end index widths. Run-end children must
contain zero physical entries at length zero and one at positive lengths,
including the Int16 boundary. Length 65537 specifically detects positive wrap
from an unchecked Int16 cast. Physical null counts retain the existing contract;
logical nulls in Null, union and run-end arrays are not falsely rejected.

Filter tests use strict casts and a predicate that rejects any marker row.
They distinguish scalar true, false and null results, verify single evaluation
of data runs, preserve retractions and marker order across slices and batches,
and expose an earlier marker before a later data error. Data-only and empty
batch controls cover the direct polling path. Lifetime assertions establish
release of the iterator's held input; they do not establish that downstream
Arrow slices release every shared buffer.

Failure tests verify that later input remains unpolled, the first cause survives,
input is dropped before terminal publication on error, exhaustion and explicit
stop, and waiters observe stopped status with the same cause. Manager failure
priority, individual failure retention after reset, and successful completion
have separate cases. The atomic state removes the partial-publication state
demonstrated by the retained counterexamples without requiring a timing race.

Protocol tests pair the server response builder with actual PySpark protobuf
and client decoding. Delimiter-free, colon-containing, Unicode, multiline and
empty causes distinguish complete message preservation from prefix stripping.
Absent and recorded error conditions are tested separately. Mocked transport
tests qualify the client boundary; the live failing-query regression qualifies
server integration once run against the final executable.

## Evidence inspected

The following logs are under the source worktree's `review-logs` directory.
Counts refer to their original candidates, not automatically to this snapshot.

| Receipt | Observed result |
| --- | --- |
| `baseline-existing-tests.stdout.log` | 62 existing common-datafusion tests passed |
| `fidelity-negative-control.stdout.log` | 13 new tests failed; two new controls and all 62 existing tests passed |
| `fidelity-fixed-tests.stdout.log` | 77 tests passed after fidelity repairs |
| `filter-negative-control.stdout.log` | Five of the original six filter regressions failed; the data-only control passed |
| `failure-console-negative-control.stdout.log` | Both source and formatting error controls failed against the old sink |
| `failure-query-negative-control-2.stdout.log` | Four failure-management regressions failed; normal completion passed |
| `terminal-publication-negative-control.stdout.log` | Both partial-publication counterexamples failed the initial two-channel repair |
| `three-increment-tests.stdout.log` | 77, 97, 21 and 34 affected crate tests passed, totaling 229, before the latest polling and protocol changes |
| `protocol-negative-control-pytest.log` and its receipt | Nine actual-client fixtures passed; the live query reached an IndexError in `query.exception()` against the executable with the old response format |

The protocol negative control is an executed failure, not a successful live
integration result. The three new Rust response tests and the latest direct
filter polling path need the final coordinated test run. Final public execution
must use the newly built executable, with its source and binary identity recorded.

## Remaining limits

These tests do not qualify streaming projection, asynchronous expressions,
optimizer or worker codec isolation, task-panic supervision, distributed recovery,
fencing, durable completion or performance. Manager waits retain their existing
snapshot semantics. The focused terminal-state checks do not claim a saturated
multicore concurrency qualification. The Arrow fixtures do not validate arbitrary
malformed schemas. Those boundaries match the reviewed increments and do not
justify additional speculative tests in this patch.

## Final delta review

No must-fix finding in the final cumulative patch
`review-logs/cumulative-final.patch`, verified SHA-256
`bda65fdba075378f3088a2b00681fdf63f57b9d9a66722ec78c8e1f688220163`.
The baseline remains `b52144955b629314a000b1fe49eeea97fa3d0c5c`.
Compared the complete patch sections with the preceding reviewed snapshot:
both contain 19 files, and only console writer, its tests and streaming query
status construction changed. The matching delta artifact has SHA-256
`73baa58870461a4b5143a97d24145a5dc86d896e51338a5e42da7075499587f1`.

Formatting and rendering now finish before taking stdout's lock. The write
helper therefore accepts prepared text. Its failure test still injects separate
header and body write failures, and its successful-output assertion now uses
independent literal bytes. This adapts the fixture to the narrowed helper
without weakening either assertion. Formatting failure remains covered through
the actual console sink with an invalid timezone and a check that later input
was not consumed. Active-query listing retains one state borrow while selecting
and constructing status; stopped queries are rejected before allocating status
strings. The terminal-state assertions remain applicable.

The previously pending coordinated receipts are now available and inspected:

- `precommit/receipt.json` binds the preceding `6782613a...` patch to successful
  format, strict Clippy, 232 affected Rust tests, a fresh CLI build and 19 public
  tests. The public set includes the live corrected exception response.
- `precommit-cost-fix/receipt.json` binds the final `bda65fdb...` patch to
  successful format, strict Clippy, the two affected crate suites totaling
  134 tests, a fresh CLI build and the same 19 public tests. Every step records
  that the candidate remained unchanged. Its executable SHA-256 is
  `6d236fdb26ca14dc892ee84f882d8db9db2d81793aded534d8f3b39c13e18112`.

These receipts resolve the earlier focused-validation gaps for their named
patches. They remain precommit qualification, not a verdict on a later immutable
commit or the complete workspace gate. No source edits or test execution were
performed during this delta review; the preceding scope limits still apply.

## Immutable source confirmation

Verified worktree HEAD `2c9fa84994d317aade0d1c69faa9a378c780127d` and tree
`5d67cdc81cdd9ba7eb18a74eda17d84b9e5d30c7`. Its binary diff against
`b52144955b629314a000b1fe49eeea97fa3d0c5c` hashes to
`bda65fdba075378f3088a2b00681fdf63f57b9d9a66722ec78c8e1f688220163`,
exactly matching the reviewed cumulative patch. Tracked source is clean.
The no-must-fix review verdict therefore applies to this immutable source pin.
This confirmation used read-only Git checks and adds no build or test execution
claim; the workspace gate has its own receipt.
