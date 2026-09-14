# LanceDB integration qualification

Current-main integration `a6bc05a` passed native adapter tests and
warnings-denied all-target Clippy on Capitola using four nice Cargo jobs.
Commands: `cargo test --locked -p grust-lancedb` and
`cargo clippy --locked -p grust-lancedb --all-targets -- -D warnings`.
Raw logs retain ignored coverage. This is not full workspace/release
qualification or a performance result. Benchmark pins remain unchanged.
