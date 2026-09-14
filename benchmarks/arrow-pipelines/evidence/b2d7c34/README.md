# Shared immutable binding qualification

Clean source b2d7c34, Capitola, 2026-09-14. Source, binary SHA-256, toolchain,
commands, exit statuses and memory boundaries are in `status.json`.

All 54 optimized engine checks passed; Cypher tests passed 868 with zero
failures and two ignored. Warnings-denied Clippy passed. The before-fix source
for this allocation change is d96a7e7, which already has the empty-SUM correction.

On the 20,000-node fixture, median two-hop indexed Cypher time across three
trials changed from 3.995955 s to 2.343132 s. Full-process maximum RSS changed
from 10,498,555,904 to 6,029,000,704 bytes. Node-aggregate medians were 0.024267 s
and 0.023664 s; one-hop medians were 0.310280 s and 0.297260 s.

All trials and first-use observations are retained. These are descriptive
measurements on this fixture, not statistical confidence or universal speed
claims. Process memory includes both engines, all graph representations and
retained allocator state; it is not isolated Cypher RSS. The unchanged DataFusion
working pool is 256 MiB and does not cap Cypher or process RSS.

Candidate rows now share immutable node/edge bindings while maintaining owned
projected values, physical edge slots, order and conservative logical copy
charges. Workspace/package qualification and named release delivery are pending.
