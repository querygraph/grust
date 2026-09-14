# Repeated endpoint qualification

Clean source `370a44d` on Capitola, four nice jobs. Both commands exited zero:

```sh
nice -n 10 cargo test -p grust-datafusion --all-features -j 4
nice -n 10 cargo clippy -p grust-datafusion --all-features --all-targets -j 4 -- -D warnings
```

30 tests passed, zero failed or ignored. The relationship differential test now
checks 22 parsed queries against portable columns/rows. Repeated endpoints cover
incoming/outgoing/undirected self-loops, property/type/label constraints and
conflicting endpoint labels. Name collisions between nodes and relationships
remain rejected. Source inspection confirms one node join for repeated endpoints
and no reverse branch for their undirected form; throughput remains unmeasured.
Automatic routing, broader patterns and complete resource admission are pending.
