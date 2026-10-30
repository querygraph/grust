# Corrected dictionary gate dependency provenance

The dictionary proposal's Arrow58.4.0 citation was stale. The first follow-up inspected an ignored implementation-worktree Cargo.lock and incorrectly called its59.3.2 resolution the actual native gate dependency. Both earlier files remain unchanged as historical records.

The native detached gate at5937e8a8 uses Arrow59.2.0. Its Cargo.lock SHA256 is29dd0ca91217b64ca2d56f25db1993a889ceb20961233fa2c60009339a06338e. The retained dictionary .crate includes exactly the same lock and VCS pin. Sail's tracked lock at vendor43fe0dc8, the current Sail worktree and Sail gate are identical (SHA25692c572736928f7708fe3749254e08f6ebcf60eba5a7b6615cfb444d2f98cf572), also Arrow59.2.0. The implementation worktree59.3.2/58.4.1 lock is separately marked non-gated.

receipt.json preserves exact paths, hashes, dependency chains and actual59.2.0 API excerpts. Those API checks confirm the original count/offset/key-validation claims. This is a provenance correction, not new runtime evidence; no builds or tests were run.
