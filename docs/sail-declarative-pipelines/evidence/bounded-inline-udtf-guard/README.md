# Refuse unowned dynamic inline Python schema analysis

Sail7b008daa1112e4e3737ae074731e3f3b3fd0f1cf on0e23b2613 imports
Fable d1f2fd565 binding source/tests byte-identically. The inline Python UDTF
return_type=None path now returns typed UnsupportedRead before walking arguments
or entering PlanResolver. Declared schemas retain argument/subquery classification;
a new static-schema argument with an unbound streaming read remains rejected.
No Python payload deserialized or executed by these probes.

[Original review](../fable-inline-udtf-binding-review/README.md) preserves dynamic
admission failure with static control1pass/1fail and initial Fields compile error.
Independent ab016afa0f2c1fe4f06e4a1213fcfb4d53b7bc6b appends the original
8907014d7 helper and assertions verbatim in a nested test module against d1:
2pass/0fail, production unchanged. Actual root candidate passes fmt/strict all-
target/all-feature Clippy,134 common-datafusion+117 Connect libraries (251 total).
Qualifier checks source/test blobs, original fixture text/hash, raw receipts and
counts before conditional advancement. No concurrency mechanism change; no extra
optimized/public CLI verdict. Latest public CLI remains7723dc4de.

This is a temporary unowned-helper exclusion, not complete Spark UDTF support.
Owned dynamic Python schema analysis and its cancellation/join outcomes remain
required under the preparation design. No worker/context API, staging authority,
broker/durable effect/CDC or public caller activation. SHA256.json covers all
packet files except itself; replay to fresh outputs.
