# Native C4 allocator owner revision 02

Source preparation only. The original owner01, run01, Rust source freeze and failed attempt remain preserved. No Cargo command, allocator binary or live cleanup was run by this preparation.

## Change and launch

`probe_seconds` now defaults to 600, permits 10 through 1800, and the fresh `run02-plan.template.json` selects 900 seconds per probe. Its campaign cap remains 14,400 seconds. Six probes can therefore use at most 5,400 seconds in that template; the campaign cap also bounds all preceding gates. The partially observed original gives no upper bound on the unfinished merge, so 900 seconds is a prospective timeout, not a guaranteed completion time.

The step checker reports which step budget expired. Forced cleanup records the known direct child's actual return code and completed wait, plus observed group absence and cleanup errors. `forced_cleanup=true` stays true and cannot qualify a positive result. If cleanup itself fails, those failed observations stay in the step and the original timeout remains the owner error. The launcher also records actual direct-owner wait/return code/group absence after forced cleanup; every failure remains failed.

Before root launches a fresh physical result directory, root must independently close the old attempt: actual outer wait, absence of every recorded owned group, unchanged admitted source/config/helpers and the exact lock owner token. Only then may root remove the old attempt's own retained locks. This source preparation does not provide that closure or remove locks.

The template reuses the same frozen Rust source, tools, ownership helpers, and the old attempt's private target/cache. Root may reuse those only after proving that attempt closed, or substitute a separately admitted fresh target/cache and seed manifest. Root creates the fresh `C4-allocation-run02` directory and chooses the final configuration. Helpers are pinned to this revision; the Rust source is unchanged.

Use the original isolated bootstrap with the first search path changed to this directory and the second still `C2-observer-build01`; launch `wait_allocator.py --plan FINAL_PLAN`. Root owns launch, actual waits and final independent review. Source-only controls contain mocked processes and synthetic counters.

## Reported memory size

`review/audit01.json` and the pinned source excerpts explain the partial original observation. At 100,000 groups, `first_update` reported 240,122,269,952 accumulator bytes, while the System allocator meter separately observed 164,733,758 live requested bytes and the process lifetime peak RSS was 199,094,272 bytes. Cumulative allocation requests for that phase were 622,458,304 bytes, a different quantity again.

DF55's ordered grouped accumulator stores one ordering vector per group. A struct ordering scalar is a one-row Arrow slice sharing its original buffers. `ScalarValue.size()` counts the referenced full buffers for every scalar, and the ordering-size sum counts them repeatedly. The value state compacts its stored payload; ordering keys are not compacted by that path. Arrow slices do not copy the underlying buffers. This explains the huge accounting estimate by source inspection; it does not establish physical allocation of 240 GB.

The standalone control uses the same complete three-field value and ordering key. Its requested System allocation counts, live requested bytes, reported accumulator size, Arrow output bytes and per-process lifetime RSS stay separate. It is not a graph query, native Sail pool measurement, MiMalloc measurement, physical-memory sum, or OS memory-envelope proof. The 100,000-group ordered control timed out before its final semantic marker, so that full control is unqualified.
