# Undirected one-hop qualification

Clean source `67be037` on Capitola, four nice jobs. Both commands exited zero:

```sh
nice -n 10 cargo test -p grust-datafusion --all-features -j 4
nice -n 10 cargo clippy -p grust-datafusion --all-features --all-targets -j 4 -- -D warnings
```

30 tests passed, zero failed or ignored. The relationship differential test now
checks 17 parsed queries against exact portable columns/rows. Added undirected
cases cover total multiplicity, grouped endpoint counts, a self-loop with labels
and type filtering, and reversed endpoint property constraints. Parallel edges
remain distinct, and reverse self-loop rows are excluded. This is correctness
evidence; join throughput, automatic routing and policy parity remain unqualified.
