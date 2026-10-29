# Spark ORC logical-type reference archive

This directory preserves the existing local reference collection from
`/tmp/sail-sdp-orc-bridge-reference`. No Spark or native reader was rerun while
archiving it. It is reference evidence, **not Sail runtime qualification**, full
ORC conformance, or a benchmark.

- [provenance.json](provenance.json) records source pins, archive checks, scope,
  original path mapping, and hashes of the archive indexes.
- [files.json](files.json) maps every retained original file to its portable
  relative path and records its byte count and SHA-256 hash. Copied files are
  byte-for-byte originals; their embedded absolute paths have not been rewritten.
- [expected.json](expected.json) retains the 11 case reports over 10 ORC
  fixtures. The foreign CHAR/VARCHAR fixture is read under both timestamp defaults.
- [outcomes.json](outcomes.json) indexes the original per-stage outcomes without
  changing failures into passes. The original [validation.json](validation.json)
  records a successful collection-specific assertion check, not 11 all-pass cases.
- [source-evidence.json](source-evidence.json) preserves the original excerpts
  and observations. [source-validation.json](source-validation.json) compares
  every excerpt with its pinned Git object and records blob IDs and hashes.
- [exclusions.json](exclusions.json) records omitted Hadoop checksum sidecars,
  generated `_SUCCESS` markers, and the empty `spark-local` directory. These
  are not fixture contents or inputs to the retained assertions.

The initial TIME-disabled rejection, SQL syntax error, map-key JSON serialization
failure, and PySpark year-month interval collection/Arrow conversion failures are
retained. Source values and file-read values remain separate, including the
recorded negative-LTZ discrepancy. Native microsecond decoding was not executed
by this reference collection; its expected submicrosecond failure is source-only.

All paths under the original collection root map to the same relative path here.
The original scripts keep their historical absolute paths, package environment,
and native executable path. They are archival inputs, not a relocation-ready
runtime harness. Reproducing their runtime results requires explicitly selecting
and recording the replacement runtime and paths; this archive does not attest
the build identity of the original installed jars or native executable.

Run the read-only integrity verifier with the standard library and Git:

```sh
python3 verify_archive.py \
  --spark-repo /path/to/spark-checkout \
  --orc-repo /path/to/orc-rust-checkout
```

It checks archived file hashes, the original fixture manifest, and the source
excerpts against the recorded commits. It does not import PySpark, compile code,
read ORC through an engine, or execute the archived collection scripts.
