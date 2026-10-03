# Vortex native and Python reader controls

On native Sail9f0aa7d2, unregisteredformat read/write return the observed
'No data source found for: vortex'; the six-row Parquet control passes.
The first registered-reader attempt was not admitted because the source-only
pysail package lacked _native. Its rc2, error and original plan are retained.

The admitted registered Python reader uses the exact4b88c8fb Python adapter
with PySpark4.2 and a separately installed native package. All six full typed
row comparisons pass: all, equality, range, nullpostfilter, stringpostfilter
and projection. The writer returns its observed NOT_IMPLEMENTED error; writer
support is not claimed. Both completed controls have waited naturaldriver0,
requested nativeSIGTERM, no forcedcleanup and closed identity records.

No Rust native Vortex registration or benchmark parity is claimed. All raw
metadata, startup errors, source-gate failures, plans and logs are retained.
Tiny raw outputs/fixture and native binaries remain at their original paths,
with declared hashes in copied receipts/manifest. No payload was read or
rehash performed during packaging. This is a bounded format/correctness
control, not a Vortex performance benchmark or a new oracle run.
