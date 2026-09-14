# Brine 0.20.0 release evidence

Status: all eight release gates passed; crates.io publication is in progress.

Frozen crate source: `90dee05d1e7f3881d5a86a3f8ce5d80e2a7eeed4`.
Native eight-gate qualification passed on Capitola with four nice Cargo jobs;
receipt directory `/tmp/grust-brine-release/20260914T215330Z`.

Book delivery completed through the canonical FirstPair publisher, including
live verification. Book version `0.20.0-fa1cbbaa`, artifact commit `87db972`;
FirstPair delivery commit `845b4c0`. TextPack `0.20.0-90dee0` identifies the
frozen crate source. Exact regular iCloud PDF, EPUB and TextPack bytes and
unchanged unrelated catalog entries are verified in `delivery-check.json`.
Raw build, dry-run and delivery logs are retained in `delivery-logs.tar.gz`.

Automatic Cypher routing, full operator accounting and new performance
qualification remain active engineering work. This delivery does not establish
their completion, nor does it change any running benchmark source pin.

Workspace tests: 1,663 passed, zero failed, 49 ignored across 100 summaries.
All 24 native archives match independently reproduced local archives byte for
byte, with clean frozen-source VCS metadata. Full native package verification
and quick local integration passed; no unavailable external-service suite is
claimed. Publication verification and the release tag remain pending.
