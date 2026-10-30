# ORC writer checkpoint

This checkpoint follows the completed ordinary reader and the batch acceptance
work. It targets Spark **4.2.1**. The [source audit](evidence/orc-writer-checkpoint/README.md)
pins Sail `f6f132819`, native ORC `133c0c5ea` and Spark `617618396`.
The earlier [ORC design](ORC-SOURCE-DESIGN.md) remains the parent contract.
This document freezes the dependency boundary and first implementation unit;
the cancellation ownership and accounting interfaces below still need resolution
before the asynchronous sink is implemented. No writer runtime is qualified here.

## Preserve Sail's execution and publication boundaries

The format factory produces an `OrcWriteFormat`; its sink produces a normal
DataFusion file-sink execution plan using `ListingSinkInput`. Reuse `FileSink`
partition demultiplexing, path naming and `FileSinkConfig`. Keep existing Sail
listing overwrite/delete barriers and JobService scheduling. LakeCat requires no
ORC-specific interface. General catalog behavior stays in Sail.

One native `ArrowWriter` owns one output file across every batch assigned to that
file. Close it once, write its footer once, and complete the object upload before
returning success. The file suffix is `.orc`; compression is internal ORC block
compression. Independent ORC buffers must never be concatenated per input batch.
Retain the existing write row-count contract inside execution; CTAS already
suppresses that internal result through a barrier.

The initial path must support the original `RANGE(3).write.format("orc")`
fixture, followed by no-USING CTAS and the direct materialized view assertion.
Streaming output `b` remains an acceptance obligation for the later generic
streaming implementation. Supporting a primitive writer does not qualify all
nested, decimal, timestamp, TIME or interval writer semantics.

## Current native API findings

`ArrowWriterBuilder::try_build` constructs the compressor, writes `ORC` magic,
then constructs stripe encoders. Unsupported Arrow types reach `unimplemented!`
in encoder construction; footer schema serialization has a separate unsupported
match. A rejected schema can therefore leave bytes before panicking.
`batch_size=0` reaches `step_by(0)` during writing. Schema equality is checked on
each batch, which should remain a required invariant.

Both encoder and footer paths support flat signed integer widths, floats,
Date32, strings/binary (normal and large offsets), booleans, timestamps without
a timezone and timestamps with the exact `UTC` timezone. This is a source-derived
physical type inventory, not a Spark semantic qualification. In particular,
Sail must validate field metadata as well as Arrow storage types: a long-backed
logical interval must not silently become an ordinary ORC LONG, and unknown
extension semantics must not disappear. Timestamp/NTZ/calendar attributes need
their own paired Spark evidence before admission.

Native stripes flush only after an encoded slice exceeds an estimated memory
threshold. A large single value or slice can exceed that target. Encoded buffers,
compression scratch space and accumulated stripe-directory entries also consume
memory. Reducing row batch size or bounding a channel's message count does not
establish a byte limit. Reader resource caps do not bound this writer.

## First unit: native builder rejection before output

Add a pure physical-schema admission check to `ArrowWriterBuilder::try_build`,
before constructing encoders or writing magic. Its allowed physical types must
agree with both encoder construction and footer serialization. Unsupported
nested/decimal/unsigned/non-UTC timestamp cases return a typed error with field
context. This unit does not extend native type support or claim Spark parity for
all admitted physical types. Reject a zero encoding batch size before output.

Acceptance must use an instrumented `Write` implementation to prove zero write
calls for rejected schemas and configurations, including an unsupported later
field after an otherwise valid field. Check unsupported nested types, decimal,
non-UTC timestamps and zero batch size without relying on panic catching as the
success criterion. Preserve successful primitive multi-batch and empty-file
round trips. Gate the native commit separately, then vendor its exact portable
package into Sail in another commit. Public `StripeWriter::new` is a separate
low-level infallible API; builder validation alone does not make every native
writer entry point panic-free.

## Per-file execution and upload lifecycle

Proposed lifecycle:

`Validated -> UploadOpen -> Encoding -> FooterWritten -> UploadCompleted`.

Any failure before upload completion enters `Aborting`, then `Failed`. The row
count becomes successful only after the footer and upload completion succeed.
A failure after one file completed may leave that completed file, as with the
existing listing-write contract; this does not create table-wide atomicity or
streaming exactly-once publication.

Encoding runs on a blocking worker. Its synchronous `Write` adapter transfers
bounded chunks to the asynchronous uploader, with byte reservations retained
until upload consumption releases them. The queue must propagate consumer loss
as an I/O error, unblock a producer on cancellation and preserve the first
encoding/upload failure as the primary error. Cleanup failures are additional
context rather than a replacement cause. All files from one demux task must be
joined or cancelled and cleaned before the sink reports terminal completion.

Retain the concrete upload/abort handle. DataFusion55.2's `ObjectWriterBuilder`
explicitly drops `AbortableWrite`; calling that builder alone cannot satisfy
abort-on-failure. Do not buffer the final file in a Vec to bridge synchronous and
asynchronous interfaces. Do not use Text's stateless batch serializer for ORC.

The following interface choices remain prerequisites for the sink implementation:

- Identify the existing worker/JobService owner that can await asynchronous abort
  after cancellation. A dropped future cannot itself await cleanup; aborting a
  cleanup task is not proof of cleanup. Define shutdown and worker-loss limits.
- Define reservations for native column buffers, compression scratch, queued
  chunks and footer directories, including one oversized input value and many
  small stripes. A stripe target remains a tuning option, not a memory guarantee.
- Decide how a blocking encoder observes cancellation while uploading is blocked,
  and how all admitted writer tasks are supervised under high file fan-out.

These choices need a worked cancellation trace and fault-injected test before
claiming bounded/cancellable production writes. Cloud process-crash cleanup is a
separate provider guarantee; local cooperative abort tests cannot establish it.

## Options, codecs and review units

Resolve generated ORC write options through the existing option layers. Preserve
Spark compression precedence: `compression`, `orc.compress`, then session
`spark.sql.orc.compression.codec`; default ZSTD. Qualify exact codec aliases and
invalid-option behavior against pinned `OrcOptions.scala` before implementing
parsing. Capture session defaults in immutable configuration snapshots, as with
reader options; workers use the captured configuration.

| Unit | Scope | Required evidence |
| --- | --- | --- |
| W0 | Native builder admission and zero-batch rejection | Zero output on rejection; supported primitive/empty/multi-batch controls |
| W1 | Mechanical native vendor update | Exact package, patches, license and Sail library gates |
| W2 | Resolve ownership/accounting choices above | Worked success/cancellation/failure traces with named owners and reservations |
| W3 | Generated write options and semantic schema admission | Layer precedence, unsupported logical metadata, immutable defaults, Spark option cases |
| W4 | Stateful sink and abortable transport | Multi-batch single-footer files, backpressure, failure at each transition, cancellation, memory admission |
| W5 | Worker sink codec and physical planning | Encode/decode and execute reconstructed sinks; multiple partitions/files; no duplicate ownership |
| W6 | Registry write activation | Spark4.2.1 reads Sail output and Sail reads Spark output; empty/append/overwrite/partition cases; original writer-to-CTAS-to-MV assertions |
| W7 | Broader type parity | Nested/decimal/timestamp/TIME/interval semantics and unsupported-mode errors in separate commits |

W0/W1 are settled preparation work for Sol. W2 remains substantive design work;
its resolution must precede W4. Each unit is a separate human-reviewable commit
with detached source gates. Writing remains explicitly unsupported until the
activated path meets its stated contract. Keep unsupported upstream assertions in
the coverage inventory. No full SDP, streaming/Iggy or CDC completion follows
from this checkpoint.
