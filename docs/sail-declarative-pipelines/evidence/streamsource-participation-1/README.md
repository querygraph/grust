# Source-participation qualification evidence

These records qualify a local compiler boundary that retains executable streaming
sources before data pruning. They do not establish integrated recovery or production
readiness. The self-contained result is
[Preserve streaming sources before data pruning](../../STREAMSOURCE-PARTICIPATION-RESULTS.md).

Local source commit: `6e4da8d33ba1bf4073fcb853123f81860ef18151`.
Tree: `f71f8c5c97b08baa0c7f0f914ea7a2e24d150622`.
Parent: `327572240365e2507f348ee92bc009cbfc67abe9`.
Cumulative review base: upstream `b52144955`.
Observed newer upstream `5411f8433` was inspected separately.

| Evidence | What it establishes |
| --- | --- |
| `qualification-summary.json`, `immutable-qualification.json` | Exact source identity, commands, artifact hashes, 2,091 Rust passes and the limits of the verdict |
| `public-tests.json` | Fresh server version 4.2.1 and all 38 selected public tests passed |
| `source-snapshot-final.json` | All 77 cumulative file hashes, 24 increment paths and both patch digests |
| Seven specialist review reports | Independent source checks, findings and exact final pins; these are local reviews, not maintainer design agreement |
| `CONTROL-OUTCOMES.json` and control receipts | Failing bypass/previous-implementation controls, exact restoration and counted expression work |
| `compiler-ownership.json` | DataFusion 55.2 provenance, initial exact copy and retained comparison digest |
| `planning-summary.json` | Every valid timing cell and sample, host limits and material short-plan startup cost |
| Same-alias diagnostic receipts | Wrong optimized results kept distinct from valid timing comparisons |
| Before-code plan snapshots and `REQUEST.txt` | Design scope and constraints recorded before dependent implementation |
| Source-preservation receipts | Original worktrees and the product environment retained |

Planning measurements name their earlier tree in the receipts. Final lint/comment
changes preserve executable behavior, as the final source reviews verify. Timings
remain shared-host debug diagnostics, not throughput or production latency results.
The same-alias optimizer error and mixed-marker execution fragmentation remain open.

Raw patches, binaries, failed logs and executable probes remain under the local
source worktree's `review-logs/`. Failed fixture, native-link, lint, documentation
and stale-probe-build outcomes are retained separately; they are never counted as
passing queries. No source push or upstream publication is part of this evidence.
