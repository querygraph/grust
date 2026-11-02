# JDK ROOT lowercase integration

Sail `cae618d7ff4661cb126333ad109f275b32bcad4b` imports Fable's common utility
from immutable source `71e4a94d910c7afa978eaf1cc98beccb5df92051`.
The production implementation and generated table/oracle bytes are unchanged;
tests moved into their own module. An explicitly supplied unreadable/malformed
external corpus now fails the replay test instead of returning successfully.
No dependency, lockfile, CDC caller or streaming activation is included.

Exact detached candidate: formatting, strict all-target/all-feature Clippy and
all **24 sail-common library tests pass**. The library run supplied the independent
JVM corpus; a separate uncaptured replay reports **68,588 strings, zero mismatches**.
The tests also check every Unicode scalar against the pinned JVM hash, generated
sigma contexts and lookup versus resolver distinctions. Missing/malformed explicit
corpora return test exit101 as expected; these are intentional negative controls,
not unresolved implementation failures. Raw logs and receipts preserve both.

The independent JVM input/output authority is the existing
[corrected C2 packet](../fable-c2-corrected-review/README.md).
`make-corpus.py` converts its cases.json and hex java.stdout into the replay format
(SHA256 `7d861e2652d1dc5925c2a1127e610a7a8e76bfcd54014fd94f2ff77a93726fc2`).
`import-source.py` records the exact extraction; it must not be rerun on the already
integrated checkout. `qualify.py` asserts exact offered production/table/oracle
identity and runs the three replay controls after checking the full gate receipt.
These historical coordinator scripts use absolute worktree and fresh /tmp paths;
inspect/adapt output paths before reproducing, never overwrite retained evidence.

This is common-component qualification. It does not qualify public SDP execution,
all possible string contexts, CDC definitions, durable effects or the original
Spark Scala suite. No concurrency ownership code changed in this unit.

The first documentation gate rejected the intentionally malformed corpus archived
as a .json file, because that gate parses all JSON evidence. Its failure is retained
in initial-doc-gate.log. The unchanged invalid bytes are now malformed-input.txt;
the historical test receipt retains the original runtime path. No assertion or
production source changed in this documentation correction.
