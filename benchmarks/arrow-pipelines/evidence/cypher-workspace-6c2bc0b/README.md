# Cypher bridge workspace integration gate

Clean source `6c2bc0b791ee3dd1eace513be6c749e5cb64c642` on Capitola.
Both native commands exited zero, using four nice jobs:

```sh
nice -n 10 cargo test --locked --workspace --all-features -j 4
nice -n 10 cargo clippy --locked --workspace --all-features --all-targets -j 4 -- -D warnings
```

Across 99 test-result summaries: **1,597 passed, 0 failed, 49 ignored**.
Ignored tests remain unrun, including external-service cases. Test output retains
Ladybug duplicate-ZSTD-symbol linker messages and LanceDB large-unwind-section
warnings. The workspace Clippy command passed with warnings denied. This gate
predates the facade feature-forwarding change and does not replace the required
release package, book, registry, benchmark or live-service qualification.
