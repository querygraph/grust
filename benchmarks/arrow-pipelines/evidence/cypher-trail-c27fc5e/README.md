# Composable trail qualification

Clean source `c27fc5e` on Capitola, four nice jobs. Both commands exited zero:

```sh
nice -n 10 cargo test --locked -p grust-datafusion --all-features -j 4
nice -n 10 cargo clippy --locked -p grust-datafusion --all-features --all-targets -j 4 -- -D warnings
```

37 tests passed, zero failed or ignored. Two- and three-hop directed compositions
match exhaustive source-edge ordinal tuple oracles, preserving parallel edges
and loops while excluding any reused physical relationship. Cloned snapshots
compose; separately captured snapshots are rejected even for identical tables.
This qualifies the lazy trail operator for these cases, not parsed multi-hop
routing, arbitrary path semantics, resource admission or throughput.
