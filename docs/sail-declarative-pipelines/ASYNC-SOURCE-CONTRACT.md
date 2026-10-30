# Async bounded source contract: typed errors, ownership, uncertain outcomes (proposal)

Status: proposal for Codex's decision, the CF-0056 follow-up. No Sail edit;
the move-only extraction (`33a883091`) is the base. Pinned Iggy
`153fdf466`, sail-iggy `5816b9b`, Sail base `779cb136d`, Fable head
`798cd35c9`. Evidence this draws on: `evidence/fable-iggy-harness`
(scenarios s1–s5 and the pinned `consumer_group_membership` and
`message_cleanup` groups) and `BOUNDED-PLAN-ADMISSION-DESIGN.md` §6.

## 1. What CF-0056 asked for, and what the current contract lacks

`sail-common-datafusion::streaming::bounded` today: `describe` is
infallible; `earliest`, `frontier`, `plan_end` and `scan` return
`ScanError`, whose five variants are all deterministic refusals of the
request (`RetentionGap`, `IncarnationMismatch`, `NonContiguous`,
`UnknownPartition`, `ForeignCursor`), every method is synchronous, and the
only implementation is the in-memory `DeterministicSource`. An adapter over a
network broker has nowhere to put a connection refused, an authentication
failure, a timeout, a cancelled call or a corrupt message, and CF-0056 is
right that the pinned sail-iggy reader shows the failure mode: every SDK
error there becomes `exec_datafusion_err!("failed to poll Iggy messages:
{e}")` text (`formats/iggy/reader.rs:165, 203–223`), which loses the
`IggyError` value and its code.

## 2. Error model

Two types, so the deterministic set keeps `Clone + PartialEq + Eq` and its
exact messages (unchanged, including the tests at `bounded.rs:196`), while
the operational set carries a preserved cause.

```rust
/// Unchanged: a deterministic refusal of the request; no partial rows.
pub enum ScanError { RetentionGap{..}, IncarnationMismatch{..}, NonContiguous{..}, UnknownPartition{..}, ForeignCursor{..} }

pub type Cause = Box<dyn std::error::Error + Send + Sync + 'static>;

/// Why a source call did not return its value. `Debug + Display +
/// std::error::Error`, with `source()` returning `cause` where present.
pub enum SourceError {
    /// The request itself cannot be served; `ScanError` as today.
    Refused(ScanError),
    /// The source could not be reached, did not answer within the caller's
    /// deadline, or closed the connection. Reads have no effect, so the
    /// request is known not to have executed and may be retried with the
    /// same intent.
    Unavailable { partition: Option<PartitionId>, cause: Cause },
    /// Authentication or authorization failed; operator action, not retry.
    Denied { cause: Cause },
    /// The named stream, topic or equivalent container does not exist. Not
    /// `UnknownPartition`: that variant is reserved for a partition missing
    /// from a container that `describe` did find.
    NotFound { object: String, cause: Cause },
    /// The source returned bytes the adapter could not decode as a message.
    /// Fails closed; not retryable.
    Corrupt { partition: PartitionId, cause: Cause },
    /// The owning scope cancelled the call before it completed.
    Cancelled,
    /// The adapter's own invariant failed.
    Internal { cause: Cause },
}

impl SourceError {
    /// `true` only for `Unavailable`: the one class a control loop may
    /// retry with the identical intent.
    pub fn retryable(&self) -> bool;
}
```

`plan_end` keeps `Result<Cursor, ScanError>`: it is pure arithmetic over
values already fetched and never touches the network.

Uncertain outcomes. Every method on `BoundedSource` is a read, so no call can
have taken effect without returning; a timeout on a read is `Unavailable`,
not uncertain. The one effect in the Iggy design is the advisory position
store (`store_consumer_position`), and the harness shows its outcome is
genuinely uncertain: a store issued with the broker down returned success in
0.66 s and was replayed by the SDK after restart (s5). That effect is not on
`BoundedSource`. It is proposed as a separate trait so that no read path can
confuse the two:

```rust
#[async_trait]
pub trait PositionStore: Send + Sync + fmt::Debug {
    /// Records a position the adapter may use as a retention hint. The
    /// outcome is `Accepted` unless the adapter read the position back from
    /// the source; a client-side success is never `Confirmed` on its own.
    async fn store(&self, partition: &PartitionId, incarnation: &Incarnation, cursor: &Cursor)
        -> Result<StoreOutcome, StoreError>;
}
pub enum StoreOutcome { Confirmed, Accepted }
pub enum StoreError {
    /// The incarnation the position was captured under is gone (Iggy 87,
    /// `HistoryUnavailable`): drop the position, never retry it.
    Stale { partition: PartitionId, expected: Incarnation, cause: Cause },
    /// The request may or may not have reached the source.
    Uncertain { cause: Cause },
    Denied { cause: Cause },
    Unavailable { cause: Cause },
    Cancelled,
}
```

SDP's own progress record is the authority either way (design review §5.8;
harness consequence 3); `PositionStore` only lets an adapter keep retention
from deleting behind a run. It can be deferred to the adapter unit without
changing anything above.

## 3. Asynchrony and ownership

```rust
#[async_trait]
pub trait BoundedSource: Send + Sync + fmt::Debug {
    fn schema(&self) -> SchemaRef;
    async fn describe(&self) -> Result<SourceDescriptor, SourceError>;
    async fn earliest(&self, partition: &PartitionId) -> Result<Cursor, SourceError>;
    async fn frontier(&self, partition: &PartitionId) -> Result<Cursor, SourceError>;
    fn plan_end(&self, partition: &PartitionId, start: &Cursor, frontier: &Cursor, max_rows: usize)
        -> Result<Cursor, ScanError>;
    async fn scan(&self, range: &Range) -> Result<Arc<dyn TableProvider>, SourceError>;
}
```

`async_trait` is already a `sail-common-datafusion` dependency
(`streaming/source.rs` uses it for `StreamSource::scan`); no new edge.

Ownership rules, which the adapter unit will be held to:

1. **Every adapter call runs inside a task spawned through the attempt's
   `TaskResourceScope::spawn`** (`task_resources.rs:93–121`), which hands
   the task the scope's cancellation receiver; the task selects on that
   receiver and the SDK future, returns its value over a oneshot, and
   resolves to `SourceError::Cancelled` when the receiver fires first. The
   caller awaits the oneshot, never the SDK future, so cancellation latches
   on the owned task and `drain` joins it. Codex's mutation-supervisor
   additions (CF-0079) are not needed for reads; whether `PositionStore`
   should use `spawn_mutation` is Codex's call when that trait lands.
2. **The caller owns the deadline.** The task wraps the SDK call in
   `tokio::time::timeout(deadline)`; expiry is `Unavailable` with a
   timeout cause. The Iggy adapter configures the SDK with bounded
   reconnection (`TcpClientReconnectionConfig::max_retries: Some(n)`,
   `tcp_client_reconnection_config.rs:22–33`), because the SDK default is
   unlimited retries and the harness saw a read hang past 5 s on a dead
   node (s5).
3. **`scan` materialises its range inside the owned task** and returns a
   `MemTable`-backed provider: `plan_end` already bounds the range to
   `max_rows`, the first-offset and incarnation checks run before any row is
   kept (harness consequences 1–2), and no SDK future outlives the task or
   runs during DataFusion execution. The memory envelope is
   `max_rows × message size` per partition per batch, set by the caller
   through `max_rows`. A streaming provider that polls during execution is
   a later option with its own ownership design, not this unit.
4. **No Iggy type crosses the seam**: `Cause` is the SDK error boxed as
   `std::error::Error`; the control model reads `SourceError` only.

## 4. Iggy mapping, from the pinned SDK (`core/common/src/error/iggy_error.rs`)

| `IggyError` (code)                                                                                                                                                                                                                                                                                            | `SourceError`                                                                                                                                                                                         |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Disconnected` 8, `CannotEstablishConnection` 9, `StaleClient` 30, `TcpError` 31, `QuicError` 32, `HttpError` 36, `NotConnected` 61, `ClientShutdown` 63, `ConnectionClosed` 206, `EmptyResponse` 304, `BackgroundSendTimeout` 4052, `BackgroundWorkerDisconnected` 4054, `TaskTimeout` 12001, caller timeout | `Unavailable`                                                                                                                                                                                         |
| `Unauthenticated` 40, `Unauthorized` 41, `InvalidCredentials` 42                                                                                                                                                                                                                                              | `Denied`                                                                                                                                                                                              |
| `StreamIdNotFound` 1009, `StreamNameNotFound` 1010, `TopicIdNotFound` 2010, `TopicNameNotFound` 2011, `ResourceNotFound` 20                                                                                                                                                                                   | `NotFound`                                                                                                                                                                                            |
| `PartitionNotFound` 3007 after a successful `describe` of the topic                                                                                                                                                                                                                                           | `Refused(UnknownPartition)`                                                                                                                                                                           |
| `CannotReadMessage*` 4011–4026                                                                                                                                                                                                                                                                                | `Corrupt`                                                                                                                                                                                             |
| `InvalidOffset` 4100, `SegmentNotFound` 4000 on a range inside a captured frontier                                                                                                                                                                                                                            | re-`describe`; incarnation changed → `Refused(IncarnationMismatch)`; else `Refused(RetentionGap)` from the first retained offset; re-describe failed → `Unavailable` with the original error as cause |
| `HistoryUnavailable` 87 (seen on `store` with a stale context, s3)                                                                                                                                                                                                                                            | `StoreError::Stale`; on a read, `Internal` (not observed on reads)                                                                                                                                    |
| `ConsumerOffsetNotFound` 3021                                                                                                                                                                                                                                                                                 | not an error: no stored position                                                                                                                                                                      |
| first polled offset ≠ `start`                                                                                                                                                                                                                                                                                 | `Refused(RetentionGap)`; the broker raises nothing (s2)                                                                                                                                               |

## 5. Control-model changes in Connect (`pipelines/streaming/intent.rs`)

`RunFrontier::capture` and `next_intent` await `describe`, `frontier` and
`earliest`, so both become `async fn`; `PlanError::Scan(ScanError)` becomes
`PlanError::Source(SourceError)`, with `Refused` keeping today's messages.
`From<SourceError> for SparkError` in `streaming/source.rs`: `Refused` →
`SparkError::invalid` as today; `Unavailable`, `NotFound`, `Denied`,
`Corrupt`, `Internal` → one `SparkException`-class error whose message is
the `Display` chain (`error: cause`), the typed value having been consumed
by the runner's retry decision before conversion; `Cancelled` → the existing
cancellation mapping. The runner's policy, in one place: retry the identical
intent while `retryable()` and the attempt budget allows; otherwise stop the
run with the typed error in the run record. `DeterministicSource` implements
the async methods trivially.

Tests in the contract unit: a `FaultingSource` wrapper over
`DeterministicSource` that returns a chosen `SourceError` on the nth call,
proving `capture`/`next_intent` surface it unchanged and that `Refused`
messages are byte-identical to today's; a cancellation test that spawns a
never-completing `scan` through a `TaskResourceScope`, cancels, and asserts
`Cancelled` plus a clean drain; a deadline test with the window argued from
the fixture (a source that waits on a channel nobody sends to, so the second
event cannot occur), per the working-discipline rule on clock races.

## 6. Scope and boundaries

In this unit: `bounded.rs` (error types, async trait, `PositionStore` if
accepted), `intent.rs` and `source.rs` in Connect, `test_source.rs`, tests.
Not in this unit: any Iggy dependency or feature, any `sail-data-source`
edit, `StreamSource`, unit-4 admission or execution, session or runtime
edits, Codex's `spawn_mutation` path. The Iggy adapter is the unit after
this one, in `sail-data-source` behind an `iggy` feature, and will cite §4
line by line.

## 7. Questions for Codex

- (a) `SourceError` with a boxed cause (no `Clone`/`PartialEq` on the outer
  type; `ScanError` unchanged) versus an `Arc` cause that keeps `Clone`.
- (b) `PositionStore` in this unit, deferred to the adapter unit, or
  dropped.
- (c) `scan` materialising inside the owned task (§3.3) as the contract's
  stated obligation, versus leaving provider ownership to each adapter.
- (d) the async conversion of `capture`/`next_intent` in the same commit as
  the error types, or as a second commit.
- (e) the `SparkException` class for the non-refusal arms of
  `From<SourceError> for SparkError`.
