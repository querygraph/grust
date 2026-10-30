# Read binding imported separately from admission

Sail2d3f9d49970f9df63df9e672bbc3012ccf1a45a6, parent d6d802d22,
imports binding.rs/binding_tests.rs plus minimal GraphScope::new from Fable
d77fc47958641933e84577bfa88e3be5cfbd9471. Analysis/test blobs identical;
binding source differs only by two test-only field dead-code expectations for
StaticBinding.provider and LocalBinding.provider until admission consumes them.
The following admission unit must remove those attributes. Streaming/mod.rs adds
only the binding declaration. No flow/effect/caller is activated.

Initial test-only Clippy failure30c365e25 showed the two fields have no reader in
a binding-only build (the peer originally combined admission with binding).
The narrow expectations keep each human-review unit buildable; no broad allow or
synthetic test added. Initial failure is retained. Actual combined parent then
passes fmt, strict all-target/all-feature Clippy,134 common-datafusion+96 Connect
library tests, including13 binding tests. Exact source/receipt hashes and parent
were checked before conditional advancement. No concurrency mechanism changed;
no new optimized/public CLI verdict is claimed. Latest CLI remains7723dc4de.

Binding validates the pre-resolution bounded subset, walks expression subqueries
and CTE scope, and retains explicit provider identities. Provider authenticity,
mixed read modes/multi-leaf local view support, execution ownership/effects/CDC and
full original Spark4.2.1 SDP acceptance remain open. Later binding/admission source
corrections must preserve original failing evidence. SHA256.json covers every
packet file except itself; historical receipt paths are not replay destinations.
