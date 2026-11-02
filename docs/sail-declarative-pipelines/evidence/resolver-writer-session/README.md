# Writer and schema planning use the selected Session

Sail `7723dc4de8d3d8d4641b1445a8049345918fecb7` on ddd83d815 routes
create_writer and the three existing write.rs infer_schema/infer_metadata sites
through the selected provider Session. Registry/catalog lookup and native analyzer
state remain authoritative. Procedure/row-level propagation is separate work.

Three tests resolve actual v1 write commands: selected Session writer callback,
legacy authority callback, and an existing empty-schema catalog target that infers
schema then plans its writer. Callbacks perform metadata GETs through the selected
scope/registry/config7 after direct parent config mutation to9 (not SQL/RPC SET).
No physical planning/target publication is executed, and catalog columns remain
empty after resolution. Fallback sees parent store/config9/no new scope.

Exact fmt/strict Clippy/all-target/all-feature,49 plan libraries and49 optimized
tests under ten joined busy workers pass. Writer-bypass59d19856f fails two scoped
tests while fallback passes; schema-bypassc6897c1c1 fails the identical empty-schema
test separately. Source/test blobs/log/binary checks preceded advancement. Initial
012461552 compile failure used nonexistent SinkInfo.paths in the fixture; the
corrected test uses Sail's existing find_path_in_options. No assertion was weakened.

Fresh CLI at the exact final commit passes300 public+67 upstream Python executions,
Spark4.2.1, owned server exit0/no listeners. This is a regression selection, not full
original Scala SDP acceptance. Opt-in lake metadata paths have source/type coverage,
not a new dedicated backend fixture. No public caller/owned registry/effect/CDC or
cluster path is enabled. Earlier catalog I/O, analyzer snapshot semantics, capture/
execution transfer, typed cleanup/primary and provider guarantees remain open.
No dependency change. SHA256.json covers packet files except itself. Historical
paths/hashes identify advancement-time evidence; replay into fresh outputs.
