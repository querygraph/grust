# LanceDB write-memory branch review

Reviewed source: `0176718` on `origin/lancedb-write-memory`, 2026-09-14.
The cancellation finding is reproduced by an isolated deterministic native test
on Capitola; this is not full adapter qualification. Do not integrate this queue
until cancellation handoff is covered by a deterministic regression.

## Blocking: cancellation during leadership handoff can strand the queue

In `write_queue.rs`, `Lead::drop` sends `Turn::Lead(rows)` to a waiting caller
and returns while `state.leading` remains true. The receiving caller constructs
its new `Lead` guard only after its `turn.await` finishes. A successful oneshot
send means the receiver was alive at send time; it does not mean the receiver
will be polled again.

Reproduction schedule:

1. Poll writer A until its apply future is pending; A holds the leadership guard.
2. Poll writer B until it waits on its reply receiver.
3. Drop A. Its guard sends `Turn::Lead` to B and keeps `leading = true`.
4. Drop B before polling B again. The delivered rows are dropped, but no guard
   exists in the message or B's future to hand leadership on or clear the flag.
5. Submit writer C. It sees `leading = true`, queues, and waits indefinitely:
   no surviving caller owns leadership.

Use manually polled futures and a pending apply future to make this test
schedule deterministic; a timeout alone is not a sufficient regression oracle.
Also cover a third already-waiting writer when B is cancelled after handoff.

Leadership ownership needs to travel in the delivered message, or a separate
queue worker must own it independently of caller polling. Any fix must account
for the mutex: dropping an ownership token while holding the same queue lock
must not recursively acquire that lock. Preserve explicit uncertain-durability
errors when an in-flight write is cancelled.

## Qualification and maintenance gaps

The new tests cover concurrent successful writes and duplicate keys, but not
leader cancellation, follower cancellation, key-validation failure or apply
failure. Exercise those outcomes before release. Move the inline test module to
a separate test source file to follow the QueryGraph Rust guide.

The branch also introduces fixed session-cache budgets, merge-key indexes and
periodic compaction. Their measured memory/runtime claims need retained raw
receipts and workload boundaries before inclusion in release evidence. This
review neither disproves those improvements nor qualifies them.

## Retained deterministic reproduction

[lancedb-0176718-reproducer](lancedb-0176718-reproducer/) retains the original
queue implementation (its existing tests removed, wrapped in a module for
visibility), the manually polled cancellation regression, executed manifest,
resolved lock and failing log. Run used `cargo test --offline -j 4` with nice 10
on Capitola; exit 101, one failed test, zero passed. The manifest's absolute
Grust core path records that native checkout and must be adjusted elsewhere.
Its offline resolution used futures 0.3.34 and Grust core 0.16.0. No LanceDB
service or adapter build is needed to demonstrate this queue-state defect.
Warnings in the isolated harness are unused/dead-code warnings, retained in the
log. This is intentional failing evidence, not a passing workspace test suite.
