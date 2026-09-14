# Cypher lowering qualification through a039f01

At clean source `a039f01`, Capitola passed all 25 focused DataFusion tests and
all-feature/all-target Clippy with warnings denied. The full Cypher suite at
`956c7dc` passed 869 tests, zero failures, two ignored. The latter source covers
the shared integer-ordering and column-name changes; subsequent production
changes here are confined to the optional DataFusion bridge.

Raw logs retain typed node scan, aggregate, null truth table, parameter,
pagination, identity, provider replacement and reference differential coverage.
This is an unreleased compiler, not automatic routing or resource-policy parity.
The separate optimized scan receipts remain pinned to `771cb89`; subsequent
compiler additions are not retroactively part of those measurements.
