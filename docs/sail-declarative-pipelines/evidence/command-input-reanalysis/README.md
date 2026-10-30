# Per-command input resolution

Sail `f72120882917d0a1ee2a257598387e7fc9d73cb7` onf0ac removes execution's
run-wide provider-plan map. Each selected table command resolves its own upstream
map: graph-local temporary and persisted views are traversed through their flow
definitions; tables stop the closure and are read after upstream writes under the
consuming command's PlanConfig. The map is dropped after that command. Native
GraphScope qualification/renaming and materialize-tables/views/unsupported-mode
phase order stay intact. An unused target provider is no longer read after a write
merely to cache it. No recomputation of committed-table producer definitions.

Three tests use the real resolver and memory catalog with mock provider factories,
no scans: separate commands create fresh shared-view providers and release each
map's Weak leases without touching unrelated inputs; table boundaries stop upstream
recomputation and apply consuming-command read_case_sensitive; a graph persisted
view resolves its defining flow under its captured namespace/config without a
published catalog view. This is plan-map/mock evidence; it does not audit SDK tasks,
session/factory caches or arbitrary provider cleanup. Owned-store/session/cluster
activation and version/replay identity remain separate.

Two independent unchanged-test controls each2pass/1fail:0659b4678 traverses behind
a table (map size2 vs1);0aa532454 uses session config for table reads (false vs
commandtrue). Control warnings from the intentional unused parameter are retained;
these are test controls, not strict-Clippy acceptance candidates.

Sail `163b2fb52f9ba2961cd0338046d4d2f4cf91f686` onf721 removes obsolete
Selection.required, with_dependencies and its StartRun calculation. Refresh/reset
validation and runs are unchanged; no execution read that state afterf721. No new
tests added just for the dead-state cleanup. Both exact detached candidates pass
fmt/strict all-target/all-feature Clippy/146 Connect libraries. No positive source
gate failures or new scheduling/concurrency mechanism/stress claim.

Fresh combined CLI on163b passes300 selected public+67 upstream Python executions,
client/server4.2.1, rebuilt binary/source/identities pinned, owned server exit0/no
remaining listener. Raw receipts/XML/logs under public/. Replay the existing
[frozen harness](../local-runner-ownership/public-harness/README.md) with the full
commit and a fresh output path. This is not original Scala-suite acceptance.

View bodies deliberately keep their existing flow config; upstream→consumer
configuration fusion/read-order handling is still pending. Table-read command
config is qualified here; full Spark SQLConf semantics are not. Fablefea89cc0
review bounds the cache-lifetime claim and requests no source change. C5 later work
must preserve this loop and not restore obsolete selection state.
SHA256.json covers all packet files except itself. Historical absolute paths name
advancement-time inputs; do not overwrite retained controls or result directories.
