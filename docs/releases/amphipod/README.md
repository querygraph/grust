# Amphipod 0.16.0 qualification

Source and tag: `23d447d7a06cd9249c7fd3ba4ce781806303df6d`, `v0.16.0`.
All 20 public crates were published and verified from outside the workspace.
Registry archives are byte-identical to native-qualified archives; all 24 local
workspace package candidates matched native hashes before publication.

Capitola qualification used at most four nice Cargo jobs. Formatting, workspace
build, 1,565 tests (zero failures, 49 ignored), all-targets/all-features Clippy
with warnings denied, rustdoc with warnings denied, workspace packaging,
attribution and quick local integration passed. Quick integration covers local
Ladybug, LanceDB and CocoIndex; it does not claim external service qualification.
Native test linking emitted a Ladybug linker warning retained in the raw log.

Book validation passed for 51 pages, marker `0.16.0-94c201da`; the new degree
section on PDF page 46 was visually inspected. TextPack marker is
`0.16.0-94c201`. Book deployment completed; `delivery-check.json` verifies byte-identical
versioned PDF, EPUB and TextPack copies and Grust-only catalog changes. The first deployment preflight rejected a stale FirstPair remote
reference; its log is retained. Refreshing the reference allowed preflight.

The compressed logs preserve the executed qualification driver, raw checks,
publication, registry queries, book rendering and inspected page image. Prepared
degree measurements remain under `benchmarks/algorithms/evidence/degree-5d28f02`.
The broader algorithm, Arrow/loading and language compatibility goal remains
active; this release does not establish universal backend performance or GDS
compatibility.
