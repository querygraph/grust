# Fable coordination reader integration

Fable offered Grust `2103fb56c0b8f0b88c807c697e4726682c60a976` on an unchanged
copy of the existing helper. Codex integrated the three-file reader change as
`b7290eb1ed624cc68e4ad52cbefe07b5c066ea5b`, retaining the offered history.
The [protocol](../../CODEX-FABLE-COORDINATION.md) describes its `--since` mode:
one snapshot under the persistent shared lock, complete subsequent entries, and
an explicit read-through boundary that excludes later appends.

Independent review and direct probes of the offered helper found CRLF
normalization and rejection of timestamp aliases accepted by append. The combined
implementation preserves newline bytes, accepts both reference forms, and also
rejects an empty `--seen-through` append option in read mode. Two additional tests
and one CLI fixture pin these corrections. The [offered-control receipt](offered-control/receipt.json)
records the two observed behaviors against exact offered Git bytes; it is not a
full gate of Fable's branch. The original helper and historical import/probe script
are retained. That historical script includes a working-copy import after its
probe; it is not a standalone test command.

All **12 tests passed** both normally and under Python `-O` with ten owned busy
processes saturating the ten logical CPUs. All load workers were terminated and
joined. The detached combined commit and source tree remained unchanged during
the gate. Append tests use twelve independent writers; reader tests cover exact
text, reference aliases, CLI separation and the boundary across a subsequent
append. They do not fault-inject simultaneous reader/writer exclusion. The shared
lock ordering is additionally established by source review. No test writes the
canonical log and no delivery or agreement claim follows from a successful read.

[Receipt](receipt.json), [normal log](tests.log), [optimized log](optimized.log),
[offered diff](offered.patch), [integration diff](integration.patch) and
[gate harness](gate-harness.py) preserve the evidence. Expected CLI rejection
messages appear in the passing test logs. The harness calls the historical
documentation checker archived in the [earlier protocol packet](../coordination-protocol/documentation-gate.py).
Absolute paths describe the recorded environment. `provenance.json` hashes every
packet file except itself and the exact tested helper/test sources.
