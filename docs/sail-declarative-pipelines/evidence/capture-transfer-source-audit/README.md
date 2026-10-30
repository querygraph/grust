# Capture transfer source/lifetime audit

Source-pinned facts for CAPTURE-EXECUTION-TRANSFER-DESIGN: current local execution
recaptures authority; DataFusion55.2 state() marks execution start, task_ctx derives
from authority; Delta logical sources retain a log store from factory runtime,
while file-scan data stores come from scan Session; Iceberg Table has StoreContext,
its built scan has metadata/refinements, and scan operations reacquire stores.
Excerpts record full source hashes. This is not live backend/provider lifetime or
cancellation qualification. Do not infer that every retained store is reused for
later data I/O, or that every path reacquires it.

Standalone Rust1.98.1 lifetime-generic consuming trait-object method compiles/runs;
escaping the runner lifetime fails E0597. The receipt pins source and commands.
It proves that language pattern only, not Sail API, async trait, Send/Sync, registry
ownership, caller/cluster/transport or effect semantics. Draft capture API remains
under review. SHA256.json covers all packet files except itself.
