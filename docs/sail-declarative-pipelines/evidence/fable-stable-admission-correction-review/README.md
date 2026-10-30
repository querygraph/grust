# Stable-clock correction: unchanged independent replay

Fable8f953dbf02fea36565ae032a4c3087eaf39e0f61 makes non-Immutable scalar,
aggregate and window signatures non-replayable without name-based exceptions.
Original ca2038b94 fixtures (helper, two independent clocks and immutable control)
are appended verbatim inside a nested test module: test-only81de92a016efce45cbb575e14004dd9b495bdda5.
Production prefix before cfg(test) is identical to8f. Original panic/assertions are
unchanged; this narrow cargo test replay is not a strict-lint verdict. The peer's
own lint-clean fixtures replace panic with Err and add evidence assertions.

Detached replay command cargo +1.98.1 test -p sail-spark-connect --lib --locked
pipelines::streaming::admission::tests::codex_replay exits0:3pass/0fail. Same original
clock checks failed before correction; immutable control passes both. Aggregate/
window branches are source-covered, not independently exercised by this packet.
No whole-root integration/backend/staging/effect verdict. Initial failures stay
in the separate fable-stable-admission-review packet. Root imports binding and
corrected admission in separate units with actual combined-parent gates.
SHA256.json covers packet files except itself; replay to fresh outputs.
