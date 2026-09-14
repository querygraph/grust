# Arrow conversion qualification and retained failure

Source `6544dc410cf57addd06e2ba2057762ba713e953c`, Capitola.
Arrow 55/58/59 tests: 82 passed, zero failed/ignored; warnings-denied Clippy
passed. Optimized profile build and Clippy also passed.

The unchanged end-to-end profile passed all six trials at each of 0, 1, 3, 4,
17 and 100,000 nodes. At one million nodes, all three indexed trials passed;
one DataFusion trial returned memory exhaustion under the unchanged 256 MiB
tracked pool with spill disabled, and the other two passed. All 42 trial
outcomes and the failing process exit are retained. No successful-only speedup
summary is justified. A [paired run](../cypher-conversion-paired) of the original and modified
source-pinned binaries passed 36 checks without increasing the limit. The
original failure remains unresolved.

The optimization remains unreleased. This failure does not prove its cause;
semantic correctness tests do not establish stable resource-envelope behavior.
