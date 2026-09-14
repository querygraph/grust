# Anonymous pattern qualification

Clean source `a85b530` on Capitola, four nice jobs. Both commands exited zero:

```sh
nice -n 10 cargo test -p grust-datafusion --all-features -j 4
nice -n 10 cargo clippy -p grust-datafusion --all-features --all-targets -j 4 -- -D warnings
```

31 tests passed, zero failed or ignored. The relationship differential test
checks 28 parsed queries against portable columns/rows, adding anonymous nodes,
anonymous edges, abbreviated arrows, undirected patterns, property constraints
and collisions with generated-name stems. Three anonymous node scans separately
check counts with labels, maps and empty matches. These results do not qualify
broader paths, automatic routing, resource-policy parity or throughput.
