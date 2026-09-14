# Ostracod 0.18.0

Status: released, registry-verified and delivered.

This lockstep release packages shared execution cancellation, controlled Arrow
streams, prepared Cypher admission, exact snapshot statistics and borrowed native
Arrow graph serialization/input-size admission. Automatic routing and full
execution-budget mapping remain active work. The isolated LanceDB write-memory
and cancellation changes are excluded from this release.

Source/tag: `28d24712a031c81b5324670323a65c325b6c534a`, `v0.18.0`.
All eight native gates passed on Capitola: formatting, build, workspace tests,
warnings-denied Clippy, rustdoc, workspace packaging, attribution and quick
integration. Tests: 1,627 passed, zero failed, 49 ignored across 100 summaries.
Ignored or unavailable live coverage is not claimed as passed; raw logs retain
its boundary.

All 24 clean-source package archives were independently reproduced byte for
byte. All 20 publishable crates uploaded in dependency order, with the facade
last. Outside-workspace `cargo info` and registry archive hashes verified every
published package against native qualification.

The book rebuild passed its EPUB, layout and artifact-contract validators:
54 pages, stamp `0.18.0-99af0afd`, artifact commit `8bbff93`. Cover and body
were visually inspected and rendered text includes the new admission/control
sections. TextPack `0.18.0-28d247` was delivered through the canonical wrapper.
FirstPair book deployment completed at
`https://firstpair-pdh1nhs5k-fromcafe.vercel.app`, aliased to `firstpair.org`.
Catalog/build/smoke/live verification passed. PDF, EPUB and TextPack iCloud
copies are regular files and byte-identical to their source artifacts.
FirstPair metadata commit `1a009db` is pushed; unrelated catalog/upload entries
are unchanged. `delivery-logs.tar.gz` and `delivery-check.json` retain evidence.

The JSON receipts and `qualification-logs.tar.gz` retain commands, outcomes,
source identity, hashes and publication evidence. Existing benchmark pins are
preserved; this release establishes no automatic-routing threshold or general
performance claim.
