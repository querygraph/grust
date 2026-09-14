# Shared inline property-map qualification

Clean source `d8f2adc` on Capitola, four nice jobs. Both commands exited zero:

```sh
nice -n 10 cargo test -p grust-datafusion --all-features -j 4
nice -n 10 cargo clippy -p grust-datafusion --all-features --all-targets -j 4 -- -D warnings
```

30 tests passed, zero failed or ignored. The parsed relationship differential
test now checks 13 queries against portable columns/rows. Added cases cover
parameterized edge maps, endpoint maps with colliding property names, incoming
patterns, explicit null and missing properties. Existing node-map tests cover
shared compiler extraction. Correlated maps, broader patterns, automatic routing,
full policy integration and performance are not established by these results.
