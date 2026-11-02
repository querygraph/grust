# State rebuild does not preserve all session registries

Design-only detached Sail candidate `1c1c4abcd4754427067ef30a211c47fa480cf81a`
on `a0a369baada5b3b78d66c11c6694191da72d6fe8`; not integrated into the product
branch. No dependency/feature change. Exact fmt and two native-path tests pass.
The source remains reachable at refs/sdp/design/planning-state-registry-probe.

1. A native Prepare statement registers a one-row plan. Parent and a direct
SessionState clone execute it successfully. Rebuilding the same state through
SessionStateBuilder::new_from_existing, restoring session id and post-build
config, loses the prepared statement: Execute reports it does not exist.
2. A custom config-sensitive scalar UDF returns the create-default-catalog flag
it was bound with. The direct state clone retains the exact UDF Arc. The builder
replaces it using temporary config with that flag false. Restoring config to true
after build leaves the UDF returning false; the parent returns true.

This extends the earlier catalog/config probe. Its post-build restore technique
avoids catalog replacement but is not a general preservation constructor. The
second test is a custom-provider compatibility counterexample, not an observation
that a specific normal Sail built-in currently misbehaves. Native statement
support is tested without enabling DataFusion SQL parsing. The real authoritative
SessionContext remains separate from any proposed per-operation query state.

SessionState fields are private; prepared-plan accessors are pub(crate) in the
pinned dependency. The builder initializes that map empty and exposes no copy
hook for it. A preservation wrapper must therefore avoid that reconstruction or
obtain a qualified dependency seam; do not paper over it by skipping registries.
This experiment selects no runtime mechanism and makes no distributed/SDK claim.
Historical linker unwind-size warning is preserved; tests return0. SHA256.json
covers packet files except itself. Replay into fresh outputs, never overwrite
retained evidence. The runner script retains original absolute paths.
