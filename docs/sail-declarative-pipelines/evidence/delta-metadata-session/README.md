# Delta planning metadata receives selected Session

Sail `63b660ac0a474ace71976ccef4a7b448a651b69b`, parent `1a80c0a95`,
routes Delta path feature metadata and existing catalog constraint metadata through
the selected Session. Native generated-column analyzer remains authoritative and
unchanged. No dependency/public caller/real Delta SDK or effect activation.

Four actual append-command tests use a Delta-named metadata probe and project the
existing input to its id field. Path feature inference admits one GET; catalog
write metadata plus constraint inference admits two. Both check selected owner/
task-context identity, captured config7/store bytes against parent9, and legacy
no-scope behavior. The writer callback returns a sentinel before implementation/
physical planning. Counts prove completion inside the scope: these callers can
otherwise skip inference failures, so merely reaching the writer is insufficient.

Exact detached fmt/strict all-target/all-feature Clippy and67 plan libraries pass;
four optimized cases pass under ten joined CPU-load workers. Independent path
bypass d9dfdc101 and catalog bypass01e65581c each fail only the corresponding scoped
test while the other scoped and two legacy cases pass (3pass/1fail), unchanged
fixtures. Qualification checks source/log/binary hashes, worker exits, exact two
routes and both controls before conditional advancement.

Initial02058e9e4 failed all four fixtures before the writer because the input a/b
schema did not match probe id. Projection corrected that;286c25b56 then passed path
but revealed two catalog reads rather than the assumed one. Final counter and
scope-admission assertions reflect both reads; byte/scope/config assertions are
unchanged. Both failed candidates/raw logs retained. Latest public CLI remains
09d2f0cb8, no fresh CLI verdict here. Analyzer/capture/transfer and all remaining
session/cluster/provider effects/full original Spark SDP acceptance remain open.
SHA256.json covers all files except itself; historical paths are not destinations.
