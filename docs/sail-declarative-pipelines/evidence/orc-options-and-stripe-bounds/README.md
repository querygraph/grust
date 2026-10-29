# ORC configured resource limits and checked stripe ranges

Native `2ecec391db` validates both footer-offset additions and footer end at
metadata construction, keeping the existing public accessor infallible. Stripe
construction checks row-count conversion, footer/selected-stream addressability,
and every stream's checked end against declared index+data, including skipped
streams. It allows declared padding and large unselected streams; no arbitrary
stripe cap, exact stream-sum equality or extra file-length request is introduced.
Immutable physical object-extent preflight remains source integration work.

Both metadata constructors and sync/async readers have malformed tiny fixtures
and valid controls. Native formatting, strict Clippy, 320 passing tests (eight
ignored) and 199 no-default-feature library tests passed. Sail vendor commit
`e9e0fe382` passed exact-package/source/license/hash checks and its complete
150-test data-source library gate; its runtime lock is unchanged.

Sail options commit `2c10b2da7` adds generated read options through the existing
YAML/build/ResolveOptions mechanism. Three byte budgets default to 64 MiB and
schema depth to 64 (root STRUCT depth 0). Options and table properties support
snake_case and camelCase aliases; layer order remains Sail's existing policy.
Zero stays zero, invalid/platform-overflowing integers fail, and byte limits are
capped by the local finite pool limit and isize::MAX. Unknown/Infinite pools
retain configured ceilings. Current reservations never change the policy.

Tests exercise actual retained ORC file-tail/stripe reads with default, zero and
tiny budgets, complete depth validation, batch-size preservation, all four keys,
layer precedence and a completely reserved finite pool. The final gate passes
formatting, strict Clippy and 156 data-source tests. The first candidate failed
strict Clippy for one unnecessary mutable local in the test; its exact patch and
logs are retained. Removing only `mut` fixed that compile issue. A second run
passed 154 tests but failed two new assertions that incorrectly expected the word
`limit` in compressed-block budget errors. Those cases/fixtures/budgets remain;
the corrected assertions require the exact native encoded-tail or compressed-block
error messages, with production code unchanged. A subsequent shell path typo
prevented branch advancement after all checks passed; the identical candidate
was gated again with the correct conditional advance command. All failures and
the operational retry are retained.

These are resource/reader foundations. A configured limit is not a total-heap
guarantee. Full source/opener integration, requested-schema adaptation, worker
codec, registry, writer and public Spark SDP qualification remain open. No new
CLI, streaming/Iggy or CDC runtime verdict is claimed.
