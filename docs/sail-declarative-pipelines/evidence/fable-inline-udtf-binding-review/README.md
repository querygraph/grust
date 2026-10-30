# Dynamic inline UDTF bypasses bounded pre-resolution helper guard

Source pinned to root0e23b2613f809604ec72757b56e4fa2f9b922b2a. Binding
walks inline UDTF arguments but does not inspect return_type. Sail's resolver calls
PySparkUdtfPayload::analyze for None, which unpickles and invokes Python during
resolution, before post-resolution admission and outside lowerer's unused scope.
ReadType::Udtf is rejected, so this inline QueryNode path bypasses that boundary.

Independent test-only8907014d7c51ca0ffc8fc73f2ef5e526552287e0 changes only
binding_tests.rs. Detached cargo +1.98.1 test -p sail-spark-connect --lib --locked
inline_table_function_ exits101:1pass/1fail. Dynamic schema wrongly returns empty
Ok(ReadSet); static declared-schema classification passes. The probe never calls
the resolver, deserializes empty command bytes or runs Python. Initial48c15d67c
compile failure used Vec instead of spec::Fields; only initializer changed to
Fields::default, assertions preserved. Source excerpts record full-file hashes.

CF-0192 review/CF-0193 ACK/CF-0194 exact failure request a narrow pre-resolution
guard and unchanged regression replay before importing lowerer. Correction pending.
Temporary unowned-helper exclusion is not complete Spark support: owned dynamic
Python schema analysis remains required in the pre-planning ownership phase.
No Python worker/ownership design or permanent feature restriction selected.
SHA256.json covers all packet files except itself; replay into fresh outputs.
