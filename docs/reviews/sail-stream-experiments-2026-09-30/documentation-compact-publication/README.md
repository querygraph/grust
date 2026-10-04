# Compact replay documentation publication

Recorded UTC: 2026-10-01T02:22:32.997203+00:00

Commit `f2b3dedaebc792103d46e5cf1336c52e7c1e79ff` passed its exact documentation gate and was pushed to `work/proposal-v5` and `work/sail-graph-review`. [Delivery](delivery.json), [exact gate](exact-after-receipt.json), and [independent snapshot audit](independent-audit.json) bind the reviewed tree and manifest. Shared activation preserved 463 existing source paths; its receipt is [beside this folder](../documentation-compact-activation.json). This is documentation integrity, not a runtime or cluster gate.

The initial snapshot was rejected after the coordinator ran `git status` without disabling optional index writes. The raw index changed while the staged tree still matched HEAD and all selected sources remained unchanged. [The guard failure](preparation-attempt01/index-refresh-guard-failure.json) is retained. A fresh detached snapshot used unchanged selection and authorization, with [only output-path changes](path-only-delta.patch) to its helpers; guards were not relaxed. The independent auditor's first manifest-schema accessor failure and corrected audit are also retained.

[The collection inventory](collection.json) records every copied source and exact hash. Scripts retain historical operational paths and are evidence, not instructions to rerun publication. This copy contains no dataset or result payloads.
