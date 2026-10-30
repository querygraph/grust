# Aggregate/window signature fixtures imported

Sail0e23b2613f809604ec72757b56e4fa2f9b922b2a on d0db48308 imports
Fable b32e4b67825f46de91290cd40e3b40fb80b9fbc2 test-only fixtures. The
admission_tests.rs body matches the offered file; only the existing root header
differs. Four cases cover Stable aggregate, aggregate-as-window, WindowUDF, and
an Immutable count control. These use synthetic projections to reach signature
visitor arms; they do not qualify executable aggregate/window support, whose plan
nodes remain rejected. No production source, dependency or activation changes.

Exact actual-parent detached fmt/strict all-target/all-feature Clippy,134 common-
datafusion+114 Connect libraries pass (248 total). Qualifier checked exact source,
receipt/log hashes and counts before conditional advancement. No concurrency
mechanism changed; no additional optimized/public CLI verdict. Latest public CLI
remains7723dc4de. Full original Spark SDP acceptance remains incomplete.
SHA256.json covers packet files except itself; historical paths are not destinations.
