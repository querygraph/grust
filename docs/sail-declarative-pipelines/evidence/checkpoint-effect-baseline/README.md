# Checkpoint publication after caller cancellation

Sail `36525a06f8d6da69a5c968a0630968690602ad71` adds one deterministic
characterization test to the runtime object-store wrapper. Production code and
all dependency manifests remain unchanged.

The test holds a multipart provider's complete operation, cancels and joins its
caller, deletes an existing checkpoint object and confirms its absence, then
releases the provider. The object reappears with the late payload. Provider
lifetime disposal is awaited, and no abort is reported. This uses real InMemory
storage with a controlled multipart fixture; it does not emulate remote storage
failure or prove provider-independent durability.

All **17 library tests pass**, with formatting and strict all-target/all-feature
Clippy. The focused test also passes in an optimized binary under one owned busy
worker per logical CPU; all load workers were terminated and joined. The exact
commit stayed detached and unchanged during both gates. Raw logs, receipts,
source patch and historical harnesses are retained. The initial test-only compile
failure (ObjectStore instead of ObjectStoreExt) and invalidated/interrupted
optimized build are retained separately. The test assertion was unchanged.

The observed behavior preserves an already-admitted commit. A future session
cleanup owner must join that operation before namespace deletion; canceling its
caller is insufficient. This commit does not implement the effect adapter,
session barrier, public ORC writer, streaming or CDC execution. It qualifies no
new original Spark SDP registration. No public runtime behavior changed, so the
public SDP selection was not repeated for this test-only commit.

`provenance.json` hashes every packet file except itself. Historical harnesses
contain absolute paths and expect fresh output directories. They describe the
recorded runs rather than an idempotent command to rerun in place.
