# Corrected admission imported after read binding

Saild0db483082a6891ccac1683dcaa8c425da6eb0f3, parent2d3f9d499,
imports corrected Fable8f953dbf02fea36565ae032a4c3087eaf39e0f61 admission.
Production prefix identical; inline tests extracted to admission_tests.rs, dedented
with one rustfmt using() declaration rewrap. No assertion/expression change. Binding
blob is now identical to peer (both temporary test-only field expectations removed).
Only the admission module declaration is added. Fable co-authorship retained.

The visitor verifies actual provider identity and scans/joins/subqueries before
classifying the bounded subset. Non-Immutable scalar/aggregate/window signatures
mark content non-replayable, including Stable clocks; no name-only clock exception.
The separate independent correction packet preserves the original failing fixtures
and their unchanged3pass replay. This import includes14 peer admission cases.
Aggregate/window signature branches have source coverage here; peer follow-up
b32e4b678 adds four dedicated fixtures but is not included in this root commit.

Exact root-parent fmt/strict all-target/all-feature Clippy plus134 common-datafusion
and110 Connect library tests pass (244 total). The qualifier checks production/test
source, explicit formatting delta, restored binding blob, module declaration,
receipt hashes and co-authorship before conditional advancement. Initial77f6fd50d
extraction-format failure is retained. No concurrency mechanism, public caller,
broker, durable effect/CDC or public CLI activation; latest CLI remains7723dc4de.
Lowering, error chain and new fixtures are separate pending imports. Mixed modes,
multi-leaf views, staging/reconstruction, source authenticity and full original
Spark4.2.1 acceptance remain open. SHA256.json covers all packet files except itself.
Historical helper paths/receipts are not replay destinations.
