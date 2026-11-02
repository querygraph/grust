# Attach the already-admitted resource owner

Sail `18bfee751f61c06a1597ead382de72f11ceae4dd` adds ScopedTaskContext.from_resources.
It preserves task/session state while attaching the supplied exact scope; new()
still supplies a fresh scope. An externally admitted task test checks pointer
identity, retained registered work and cancellation independent of the parent.
Exact fmt/strict all-target/all-feature Clippy,125 library and125 optimized tests
under ten busy workers pass. All workers were joined and source/log/binary pins
were qualified before advancement. This helper does not admit jobs or route I/O.
The historical qualifier requires its original detached HEAD/binary and is retained
for inspection rather than blind replay after subsequent builds.

Historical absolute paths and binary hashes identify advancement-time evidence.
Use fresh outputs when replaying. SHA256.json covers all packet files except itself.
