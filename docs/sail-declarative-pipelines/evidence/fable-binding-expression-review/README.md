# Independent expression-subquery validation counterexamples

Detached review candidate `3e6ca3c34c09911350671b4e55ad7dd613a23cb2`, based on
Fable offer `ebf631edd3b41b288a2c4d899a7a82dd658582e1`. Only two tests are appended
to binding.rs; offered implementation and existing tests are unchanged. The exact
cargo command compiles, runs both tests and returns101 (0 passed,2 failed).
A projection with no input and an unbound scalar-subquery read returns Ok(empty
ReadSet); a bound stream with EXISTS(unbound catalog read) returns Ok containing
only the stream. Both require UnboundCatalogRead before resolution. This confirms
the source review at the actual validator boundary, not physical provider/RPC I/O.

CF-0142 acknowledges the defect and forthcoming correction; CF-0143 sends these
fixtures for exact replay. No correction/integration verdict is implied. Existing
CTE/duplicate-binding requests remain separate review work. Product branch remains
b90c4fbbe; the review gate was restored there after this terminal experiment.
Candidate retained under refs/sdp/reviews/fable-binding-expression. The raw Apple
linker unwind-size warning is preserved; compilation succeeded. SHA256.json covers
packet files except itself. The runner uses original absolute paths; replay into
fresh outputs rather than overwriting evidence.
