# Operation-local owned ObjectStore facade

Sail `bebabdb9e7ef7d072ea39f9ec9ac536af86a3f50` adds OwnedObjectStore in
sail-execution. It wraps an immutable provider handle and the existing resource
scope; no new scope or global cached-store owner is created. PUT/copy/rename and
one requested deletion use retained completed-value mutation supervisors.
Multipart creation registers the existing whole-lifetime supervisor before provider
invocation; the returned MultipartUpload contains only a command handle. Read,
range/list and provider-specific rename behavior delegate to the underlying store.
No dependencies, registry installation, runner, planning or session changes.

Error conversion preserves caller-visible AlreadyExists/Precondition and other
ordinary condition variants where the representation allows it, with the original
retained typed error tree as source. Noncloneable path/join errors and multi-cause
failures use Generic with the original typed tree; source-free variants preserve
their metadata. Uncertain/interrupted completion retains its nonretryable policy
marker instead of being projected into an ordinary condition. No blanket unknown
marker is invented for normally returned provider errors.

## Actual behavior and controls

All214 execution library tests, formatting and strict all-target/all-feature
Clippy pass. All12 facade tests pass optimized under ten busy workers, each joined;
exact source/log/binary hashes were checked before conditional advancement.

- Actual RemoteCheckpointWriteExec/ParquetSink tests cover sequential and parallel
  serialization: hold provider completion, abandon the writer, cancel the owner,
  observe drainage pending, release completion, observe a valid published Parquet
  object and clean drainage, then explicitly delete through the raw provider.
  A sibling scope writes independently; the parent's cached provider stays intact.
- Bypass controlaa4f2794fa583308ab3f62a4fb866455896afef3 changes ONLY multipart
  delegation in the facade. Both identical writer tests fail “owner completed
  before held multipart completion.” The earlier6613e2cf2 control is retained too.
- Actual InMemory conditional create/update/copy/rename preserve provider condition
  variants and paths, original typed errors and unchanged data. Control
  15694dcb90bc09ea805ccaa5d45b009266760740 changes ONLY the error projection;
  the identical condition test fails on the lost condition variant.
- Held creation/abandoned handles join abort. Lost PUT/copy/rename/delete observers
  retain completion; deletion reads only one location and does not prefetch.
  Sealed/unpolled mutations do not invoke the provider. Part order/capacity and
  actual-published lost-completion response classification are exercised.
- LocalFileSystem covers PUT/multipart/read/ranges/list/copy/rename/delete.
  DynamicObjectStoreRegistry supplies its actual runtime wrapper on a separate
  I/O runtime and retains the same cached handle. Private runtime APIs stay private.
  Prior nested-wrapper component evidence is not a new nested-facade verdict.

## Capacity experiment and retained development failures

The initial writer envelope used one-byte chunks and one admitted part. Upstream
object_store::WriteMultipart.write/put synchronously submits every chunk in one
call; BufWriter checks nominal concurrency before that call, not per chunk. Probe
`dee4ecdfa9ca87d0582e6eeb046e2824816a91a8` captures both actual writer outcomes
as typed AtCapacity errors before reaching the completion barrier (exit101).
The successful two-row fixtures explicitly use256-byte chunks/eight admitted parts.
That is a fixture envelope, not a general production limit. A separate actual
writer regression preserves the one-byte/one-part refusal and confirms joined
abort with no published object for both serialization modes. The bound is part
count, not bytes; routing must account for synchronous bursts and memory.

Development receipts retain the initial private/duplicate fixture declarations
7a2d367f7, private fixture field31d1acf1a, private runtime import718c46201, wrong
memory authority and capacity868b5e157 (209 pass/3 fail), superseded successful
50b2f5c34 (213 pass), and Arc/Box match-pattern compile failurec103d30c6. The shared
multipart fixture source is unchanged; only its cfg(test) module declaration and
import moved to avoid duplicate compilation. An initial qualification-script
comparison overlooked rustfmt moving that import; the comparison now checks the
exact declaration replacement and single identical import independently.

## Remaining design and qualification

The facade is not installed in production. Latest public CLI gate remains exactly
47c473e6b (300 selected public/67 upstream), not this later unused-facade tree.
Operation registry routing, pre-planning admission/owner transfer, writer child-task
joins, provider-internal/runtime-loss behavior and session/cluster teardown remain
open. Returned PUT/copy/rename/delete provider errors need enclosing effect-protocol
visibility/replay classification; observing their future is not provider durability.

Known conditional rejections are currently retained as failed mutation reports,
as the tests assert. A transaction that handles a conflict and later succeeds is
not qualified by this component. Production integration needs an explicit outcome
policy; do not infer clean drainage or resumable cleanup from the observer error.
Failed settlement still lacks a retained raw recovery identity in some paths.
Do not install this using the fixture's hard-coded eight-part limit or describe
it as the complete session barrier. Full Spark SDP, successful ORC writing,
streaming/Iggy and CDC acceptance remain incomplete.

SHA256.json covers archived files other than itself. Scripts/receipts preserve
historical absolute paths and advancement-time binary hashes; use fresh source-
pinned outputs when reproducing. No public tests were rerun for an unused facade.
