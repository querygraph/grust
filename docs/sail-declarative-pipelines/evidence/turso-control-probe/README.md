# Turso control-store qualification probe

Throwaway probe for finding 3 of `CONTROL-STORE-REVIEW.md`. It is not product
code. Run 2026-10-31T20:45:57Z on Capitola (macOS), release build, rustc 1.98.1,
`turso` 0.7.2 with default features off, on a shared loaded machine (load
average 16 to 32), Sail base `2d4174d0c`.

Build inside the workspace: add `turso` and `tokio` to a crate, copy
`turso_probe.rs` to its `examples/`, run the example with an empty directory.

Scenarios, on file-backed databases in `journal_mode=mvcc` with `BEGIN
CONCURRENT`:

| Scenario             | Interleaving                                                       | Result                                                 |
| -------------------- | ------------------------------------------------------------------ | ------------------------------------------------------ |
| A                    | Ratifier reads guard, takeover commits, ratifier mutates guard     | `Write-write conflict`; head 0, receipts 0             |
| B                    | Ratifier mutates guard, takeover runs against the open transaction | Takeover gets `Write-write conflict`; ratifier commits |
| C (negative control) | As A, but the ratifier only reads the guard                        | Commits under the stale epoch; head 1, receipts 1      |
| D                    | Racing workers with tokens read outside the transaction            | See below                                              |
| E                    | Writer killed with SIGKILL, 25 rounds, reopened each time          | See below                                              |

Scenario C is the design's "pre-commit control-table read" and shows the probe
can detect the failure. It is why the guard row must be mutated, not read.

Scenario D checks every receipt against the epoch in force at its revision.

| Workers | Acked | Receipts | Head  | Takeovers | Fenced | Retries | Stale receipts | Sequence gaps |
| ------- | ----- | -------- | ----- | --------- | ------ | ------- | -------------- | ------------- |
| 2       | 700   | 700      | 700   | 80        | 20     | 46      | 0              | 0             |
| 8       | 2752  | 2752     | 2752  | 80        | 368    | 1683    | 0              | 0             |
| 32      | 10390 | 10390    | 10390 | 80        | 2330   | 39750   | 0              | 0             |

Scenario E: final revision 14381, no round lost an acknowledged commit, no
round left guard, head and receipts disagreeing. `journal_mode` read back as
`mvcc` and `synchronous` as 2.

## What this does not show

- SIGKILL is process death. Power loss and fsync honesty were not tested.
- One host, one filesystem, one process at a time on a database file. Sharing
  a file between live processes was not tested, and the design's deployment is
  one authority service.
- The workload is one guard row. Multi-target contention was not measured, and
  no timing here is a performance result.
- Restore, fork and incarnation rotation were not exercised.

Adding the dependency adds 82 packages to the Sail lockfile. Lockfile churn
outside additions is limited to `linux-raw-sys` and `litemap` entries.
