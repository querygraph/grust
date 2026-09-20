# Timing flakes in the LSQB runner's process tests

Status: **worked around in CI, not fixed.** Recorded 2026-09-20.

`benchmarks/lsqb` tests its observation-worker supervision by spawning `/bin/sh`
workers and asserting how the coordinator reacts within wall-clock windows:
50 ms to reap after `SIGKILL`, 10 ms of `SIGTERM` grace, 500 ms to become
`READY`. On a quiet machine they pass every time. On a starved one a process can
be descheduled for longer than the window, and the test reports a supervision
failure that did not happen.

## What was observed

All on GitHub-hosted runners, on commits that did not touch the runner:

| date | test | message |
| --- | --- | --- |
| 2026-09-20 | `cleanup_tests::hung_cleanup_cannot_hold_the_coordinator_indefinitely` | failed once, passed on the next run of the same code; message not captured |
| 2026-09-20 | the same | `observation worker could not be reaped after SIGKILL` |
| 2026-09-20, same run | `plan_tests::legacy_worker_is_supported_but_cannot_supply_a_new_matrix_plan` | `observation worker did not become READY within the configured timeout` |
| 2026-09-20, same run | `plan_tests::ready_execution_plan_survives_hard_timeout_without_a_result_record` | the same |

Three failing in one run, on a documentation-only commit, is a starved runner,
not three defects.

## Reproduction

Not on macOS, even with every core saturated, and not in a Linux container
limited to one CPU: 0 failures in 27 runs. In a Linux container limited to
**0.4 CPU** (`docker run --cpus=0.4`), running the compiled test binary: 1 of 12
runs failed with the tests in parallel and 2 of 12 with `--test-threads=1`, among
them `tests::escaped_pipe_holder_fails_recovery_within_the_reader_bound`
(`pipes remained open` not reported). So serialising the tests is **not** a fix;
the CFS quota stalls a process for up to a period whatever else is running.

## What CI does

The `Graph benchmark tests` step makes up to three attempts and warns on each
failed one. A real defect fails all three. This keeps a red build meaningful;
it does not make the tests right.

## The fix that belongs in the harness

Owner: whoever owns `benchmarks/lsqb`. Separate what the tests prove from how
fast the host is:

- Give the tests windows an order of magnitude above scheduler noise (seconds,
  not tens of milliseconds) wherever the assertion is "this bounded wait ends",
  and keep the tight production defaults out of the tests.
- Where a test asserts an upper bound on elapsed time
  (`started.elapsed() < 2 s`), keep the bound generous for the same reason.
- `cleanup_tests.rs` now prints the error it saw, so the next failure names its
  cause. Do the same in `plan_tests.rs`, which still `unwrap()`s.

When that is done, remove the retry loop from the workflow and this file.
