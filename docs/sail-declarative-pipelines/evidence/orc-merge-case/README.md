# ORC schema merge and duplicate validation reference

[The frozen Spark 4.2.1 packet](reference/README.md) retains 16 file-read cases,
eight direct JVM merge diagnostics and eight independently checked PyArrow ORCs.
Thirteen reads succeed; three case-insensitive nested merge cases fail schema
analysis with COLUMN_ALREADY_EXISTS. All failures are retained.

Root name merging and nested merging have different case policies. Outer merge
uses session sensitivity, while matched nested types reset to case-sensitive
merging. A separate recursively case-aware duplicate check rejects the resulting
nested Value/value fields in a case-insensitive file relation. Direct JVM merges
expose that intermediate schema without claiming the file relation succeeded.

mergeSchema=false succeeds in the tested root/struct/list/map-value cases. The
observed file enumeration chose lowercase first; this is not evidence for a
lexical ordering guarantee. Unicode, map-key and broader type conversion remain
outside this reference. It informs the pending Sail inference implementation;
no Sail runtime or SDP acceptance count changes.
