# Iggy adapter union

Sail `be39bbb08` merges the peer's `a8229598c` (CF-0580) with root `0643d6477`. It qualifies the union, not Iggy behavior.

fmt, strict Clippy and library tests across 14 crates, now including sail-session, sail-iggy-bounded, sail-data-source and sail-object-store. Frozen 300 + 67. Pipelines directory plus ORC tests 767 passed, 13 skipped, 4 strict expected failures. Delta Python suite: 875 outcomes, 0 changed from `dea8e10fb`, with the same 12 failed and 12 errors.

The merge carries two fixes to defects from my units, found by the peer. A view over `readStream.format(...)` completed with zero rows; it is now refused. `registered_orc_source_rejects_writing` in sail-session had failed since `4f37aef98`, because my gate did not run that crate; the gate list here does.

The broker scenarios are not library tests and were not run here; the peer reports 7 passing on its branch.
