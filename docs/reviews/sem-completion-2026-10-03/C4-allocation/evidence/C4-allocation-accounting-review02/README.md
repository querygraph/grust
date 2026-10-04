# C4 allocation clock and counter boundary

This source-only supplement qualifies the preserved owner02 audit without changing its frozen files or the ongoing root-owned run.

The Rust probe calls `phase.finish(name, acc.size(), ...)`. Rust evaluates these arguments before the finish method snapshots elapsed time and the System counters. Each reported phase therefore measures the accumulator operation **plus the reported-size and output-size sampling**, including any allocations that sampling makes. These are exploratory standalone control clocks, not a pure update kernel or graph query.

For the exact grouped DF55 factory, the final `size()` is a cached sum (`first_last.rs:739` and `first_last/state.rs:360`). Its body does not scan all groups or traverse buffer contents, and contains no apparent temporary allocation. Ordering scalar extraction and per-winner size bookkeeping occur during updates. Source inspection alone does not explain the observed 43.9-second improving update or assign it to the final size call.

The 240 GB reported accumulator estimate repeatedly counts shared buffers held by ordering slices; live requested System bytes, cumulative requested bytes, reported estimates, and lifetime RSS stay separate. The original 100,000-group ordered process timed out before its final checks, so its whole control remains unqualified.
