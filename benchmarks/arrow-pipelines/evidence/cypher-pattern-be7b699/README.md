# Parsed directed relationship qualification

Clean source `be7b699` on Capitola. Both commands exited zero, four nice jobs:

```sh
nice -n 10 cargo test -p grust-datafusion --all-features -j 4
nice -n 10 cargo clippy -p grust-datafusion --all-features --all-targets -j 4 -- -D warnings
```

30 tests passed, zero failed or ignored. Eight parsed directed relationship
queries compare exact columns/rows with the portable executor: incoming/outgoing,
node labels, relationship type alternatives, identity predicates, count/grouping,
DISTINCT, ordering/pagination, empty matches and null WHERE. Existing node-scan
regressions qualify extraction of shared RETURN planning. This does not establish
broader pattern support, automatic routing, full policy parity or performance.
