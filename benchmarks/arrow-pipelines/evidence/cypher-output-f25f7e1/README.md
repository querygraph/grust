# Cumulative output-limit qualification

Clean source `f25f7e1` on Capitola, four nice jobs. Both commands exited zero:

```sh
nice -n 10 cargo test --locked -p grust-datafusion --all-features -j 4
nice -n 10 cargo clippy --locked -p grust-datafusion --all-features --all-targets -j 4 -- -D warnings
```

35 tests passed, zero failed or ignored. The output regression verifies multiple
emitted batches, exact JSON-byte acceptance and one-byte-below rejection against
an independent serde_json encoding, cumulative row rejection, UTF-8/escaping/null
values and empty-output metadata accounting. This validates output enforcement;
one decoded batch, candidate work, input/working memory and deadlines still need
separate admission. It does not establish full policy parity or automatic routing.
