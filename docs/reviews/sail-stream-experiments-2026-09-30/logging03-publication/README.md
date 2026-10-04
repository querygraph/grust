# Lossless logging03 publication package

Recorded UTC: 2026-10-01T01:47:18.064345+00:00. This is local packaging of closed diagnostic evidence, not a workload, result-data scan or new performance result. The original `logging03-compact` tree remains unchanged and is not needed in the published snapshot.

The 413,644,800-byte original `diagnostics.tar` is retained as one deterministic gzip file, **13,848,616 bytes** (the largest package file), SHA-256 `2643372903532e7c1ff7b3f206aa7e5b176fef2a2b547ddc6947c1052d4fa83b`. It decodes to original SHA-256 `7726a29a1cef3d34b5611887f5bce53c225f3f13c2d683c69566723996b4d282`. No second compressed server-log copy is included. Gzip uses empty filename, timestamp zero and compression level 9; a second streaming compression to a hash-only sink reproduced identical bytes with the recorded zlib version.

[manifest.json](manifest.json) binds the complete original 14-file tree (827,378,117 bytes, including tar and its extracted files), the four regular flat archive members, copied metadata/support and the current restoration helper. [metadata/result.json](metadata/result.json) is the runner result. [The closed review](support/logging03-closed-review/README.md) keeps the producer certificate, physical-value verification and shared-host comparison limits separate. Recovery, wrapper record, host closure and collection checks are retained under `support/`; no original failure was discarded. The large server log and sampler JSONL are inside the archive, exactly as captured.

Restoration requires Python's standard library, no package installation or network. Choose a **new**, disjoint output path whose parent exists and a **new** receipt outside both package and output:

```sh
python3 rehydrate.py --package /absolute/path/to/logging03-publication \
  --output /absolute/path/to/new-logging03-raw \
  --receipt /absolute/path/to/new-restoration-receipt.json
```

The helper hashes every package payload, checks a pinned decompression-size limit and original tar hash, rejects duplicate/non-flat/non-regular/symlink/traversal archive entries, and verifies every restored file against the original inventory. It uses exclusive writes, admits original-tree size plus 256 MiB free disk, and retains partial output on failure. Exact manifest bytes are pinned before parsing and rechecked at completion. This is trusted collected-evidence restoration, not an adversarial concurrent-filesystem sandbox. Outputs include the original tar plus its extracted diagnostic files, requiring about 827 MB before reserve.

[controls02-receipt.json](controls02-receipt.json) records 11 small private controls, including changed manifest during restoration, altered gzip/raw hash, missing metadata, archive symlink/traversal/duplicate, insufficient disk and no-overwrite cases. [rehydration02-receipt.json](rehydration02-receipt.json) records actual complete fresh-path restoration with the final helper. [determinism-receipt.json](determinism-receipt.json) records byte-identical second compression.

The successful first packaging and restoration receipts are historical: [packaging-receipt.json](packaging-receipt.json), [rehydration-receipt.json](rehydration-receipt.json). A subsequent review added the manifest-drift guard. [helper-refresh.json](helper-refresh.json) records the narrow change; the exact old helper/manifest/test remain under `attempt01/`. The compressed bytes and original inputs did not change. The original successful run is not relabelled a failure.

The packaging scan decoded and checked all archive member text plus copied support, 30 text files in total, for five explicit credential-pattern families; no matches were found. It does not prove absence of every type of sensitive information. No raw evidence was rewritten, deleted, staged or transmitted. The diagnostic archive contains no result Parquet payload, so restoration makes no physical-value or independently recomputed shortest-path claim.
