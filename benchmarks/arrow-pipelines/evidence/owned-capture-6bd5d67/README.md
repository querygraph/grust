# Owned Arrow capture qualification

Safe owner `2d2fcac` passed all-feature grust-arrow tests and all-target Clippy.
Ordinal capture `c5a1aa3`, cleanup `c03fbb6`, and combined policy `6bd5d67`
passed all-feature grust-datafusion tests and all-target Clippy. Runs used
locked dependencies, four nice Cargo jobs on Capitola. Raw logs retain outcomes.
These checks establish the tested buffer lifetimes and admission boundaries,
not full query-budget mapping, automatic routing or measured throughput.
