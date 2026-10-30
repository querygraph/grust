Recorded: 2026-10-30T00:16:35.588765+00:00

# Native materialized variable-length validation

Base: `bc0c0cef83ba4bb297aaf6941ba0f328a95a2663`.

The draft changes only materialized list/map/string/binary batches and shared allocation/length helpers. Check offset count + 1, offset element bytes and i64 scratch bytes against addressability before PRESENT decoding. Reserve and zero the length scratch only after PRESENT succeeds, preserving malformed-PRESENT error precedence without unnecessary scratch allocation. Scratch and byte-payload reserves use TryReserveError wrapped in native I/O OutOfMemory. Decoded lengths must be nonnegative; their total uses checked i64 addition and the existing Arrow i32 offset bound before child/data allocation. Row count is not capped at i32::MAX. OffsetOverflow variant/fields are unchanged; its display now says array offset total rather than String/Binary bytes.

Eight new tests cover 11 malformed real unsigned RLEv1/RLEv2 encodings per type family, child-decode counters, unread byte payloads, impossible batch-count admission, exact intrinsic boundaries, nested list/null controls, map null/empty controls and string/binary null/empty controls. Test counts and runtime results await root's gates; only source inspection, formatting and diff checks were performed here. The independent architecture reviewer confirmed the revised preflight/PRESENT/allocation ordering and reported no further material source finding; this is not runtime evidence.

Explicitly still outstanding (original exact source anchors in `/tmp/sail-sdp-orc-value-safety-handoff.md`):

- Skip paths retain their previous unchecked arithmetic and string/binary exact-consumption issue. This unit deliberately does not impose a cumulative i32 ceiling on skipped values.
- Dictionary construction still passes the declared entry count to full-batch materialization. It gains these shared intrinsic checks but has no incremental dictionary-length setup; large addressable declarations still need the separate dictionary unit.
- Primitive/PRESENT allocation paths outside these materialized length buffers are not comprehensively changed.
- RLEv2 delta minimum-signed-value and short-run arithmetic issues remain a separate decoder unit.
- This is not a total heap guarantee, allocator redesign, configurable resource policy or arbitrary ORC value-size limit.

No Sail/vendor or Grust files were edited. Root owns detached gates and commit.
