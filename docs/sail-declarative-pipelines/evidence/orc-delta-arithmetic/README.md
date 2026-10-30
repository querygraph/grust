# ORC RLEv2 delta arithmetic

Native `133c0c5ea13578bd6905070dee11f0e66750cd9a` decodes signed first/fixed deltas with wrapping i64
arithmetic, without taking the absolute value of i64::MIN. Packed 64-bit
magnitudes retain their unsigned bit patterns; direction follows the signed
first delta, including Java's additive zero case. Narrow i16/i32 results still
require representability. Invalid variable singleton runs fail before payload
reads or output mutation; fixed singleton compatibility remains unchanged.

Eleven raw-byte tests cover every nonzero encoded width's short-run guard,
extreme magnitudes, wrap boundaries, narrow checks, original I/O errors and
skip/continuation alignment. Two old varying-delta tests now use their intended
input arrays instead of accidentally shadowing them with empty scratch vectors.
The [frozen handoff](reference/HANDOFF.md) and retained Apache ORC sources explain
the selected arithmetic. This is source-backed compatibility; no new Java/C++
runtime oracle was executed. Other integer encodings and allocation paths are
outside this unit.

Formatting, strict Clippy, 368 native tests (eight ignored) and 247
no-default-feature tests pass. Independent source review found no blocker.
Sail `c38ef0b235ce898fad88aa26434645780dd82f8e` vendors the exact package with seventeen patch revisions;
package/source/license/hash checks, formatting, strict Clippy and 201 data-source
tests pass. The native detached gate's retained Cargo.lock equals the packaged
lock and selects Arrow 59.2.0; Sail's unchanged tracked lock selects 59.2.0 too.
No failed gate attempts occurred. These library gates do not qualify a public
ORC format, writer, streaming/CDC runtime or full SDP acceptance.
