# Isopod 0.17.0 release evidence

Released 2026-09-14. Tag `v0.17.0` identifies qualified crate source
`044f4e9043b970b14ddf2e75c12b99eecfa1fd12`.

This lockstep release adds explicit Arrow/DataFusion 55 Cypher execution and
exact portable Int64 ordering. Automatic routing and the broader engineering
goal remain active. The pending `lancedb-write-memory` branch is excluded:
its cancellation defect is reproduced in the retained review. This session
changed no strain benchmark pins.

## Qualification and registry

Final native qualification on Capitola used four nice Cargo jobs and passed
formatting, workspace all-feature build, tests, warnings-denied all-target
Clippy, warnings-denied rustdoc, `cargo package --workspace --allow-dirty`,
package attribution and the quick integration profile. Tests: **1,599 passed,
zero failed, 49 ignored** across 100 result summaries. The quick integration
profile covers local Ladybug, LanceDB and CocoIndex; no external-service suite
is claimed. Native linker warnings and ignored tests remain in the raw logs.

All 24 workspace crate archives have clean source provenance. Independent
publication-checkout packaging produced byte-identical archives. All 20
publishable crates were uploaded in dependency order, with Cypher before
DataFusion and the facade last. Each version was then queried with `cargo info`
from outside the workspace, and each registry archive matched its qualified
SHA-256. The four private members were packaged and qualified, not published.

`status.json`, `archive-audit.json`, `package-comparison.json`,
`publish-status.json` and `registry-verification.json` retain the machine-readable
proof. `qualification-logs.tar.gz` preserves both the final gate and the earlier
successful intermediate gate at `cb2fb77`; only the corrected final source
qualifies the published archives. Focused scan/path profiles remain separately
source-pinned under `benchmarks/arrow-pipelines/evidence` and do not establish
automatic routing thresholds or backend/resource-policy parity.

## Book and TextPack delivery

The unified builder produced and validated the 53-page book, EPUB, MOBI, HTML
and chapter readers. Cover and typed-Cypher body pages were visually inspected.
Book version `0.17.0-bc1f0d28` derives from the pushed documentation handoff;
artifact commit is `8ff6474`. The TextPack retains source provenance
`e044f26d8fbd3b2b9b2d50e413b839005cfed452`, version `0.17.0-e044f2`.
These documentation commits descend from the qualified crate source; they do
not replace the release tag's archive provenance.

FirstPair's mandatory dry-run and clean/pushed preflight passed. Its publisher
uploaded the book, checked the catalog and hosted readers, built and smoke-tested
the site, deployed production, and verified the live Grust entry. FirstPair
metadata commit `3395a02` changes Grust only. The canonical delivery wrappers
copied the versioned PDF, EPUB and TextPack to iCloud; all three match the source
bytes. `delivery-check.json` and `delivery-logs.tar.gz` retain the checks.

The public book is available at [FirstPair](https://firstpair.org/book/grust),
with [PDF](https://firstpair.org/grust/pdf/),
[EPUB](https://firstpair.org/grust/epub/) and
[hosted reader](https://firstpair.org/read/grust/).
