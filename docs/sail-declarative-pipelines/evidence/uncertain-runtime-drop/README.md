# Runtime-wrapper completion/Drop disposition

Sail `a2cee8f0037af5910deac0f0473e4387caa7c9cf` suppresses the per-upload
Drop abort backstop as soon as complete is first polled, before spawning to the
I/O runtime. A failed/lost completion response does not prove publication absent.
Confirmed explicit abort also disables redundant Drop work. An informed caller
can still abort after failed complete; an upload whose completion was never polled
keeps its existing abandoned-upload cleanup. No descriptor/context marker, registry,
public API, dependency or checkpoint route is added.

The actual retained whole supervisor over RuntimeAwareMultipartUpload exposed the
bug: the provider publishes to InMemory and returns a completion error; the wrapper
leaves finished=false and Drop then calls abort. Detached control23f85f69e fails the
unchanged desired assertion with abort count1. It reaches the first (single-layer)
case before failing; the second loop case is not claimed as separately observed
in that failing run. The fixed source passes both layers and additional distinct-
runtime store construction. Raw provider destruction signals all wrapper ownership/
Drop work ended before counters are checked; no absence-by-sleep assumption.

Exact detached qualification: **38 library tests**, fmt, strict all-target/all-feature
Clippy, and all38 optimized tests under ten joined CPU-load workers pass. Additional
cases cover native store creation through two runtime wrappers on distinct I/O
runtimes, a complete first-polled/dropped before a separate current-thread I/O
runtime starts, explicit abort after uncertainty, and unpolled completion preserving
the legacy abort. Existing concurrent parts, runtime affinity and canceled-complete
characterizations remain passing. The earlier passing candidate27620bc05 is retained
as superseded by stronger tests, not labelled failed.

A fresh exact-commit CLI passes **300 selected public cases and67 upstream Python
executions**, server reports Spark4.2.1, all owned server/listener processes stopped.
Receipts name the exact source and CLI hash. [Frozen public runner](../local-runner-ownership/public-harness/README.md)
reproduces the same selection; these counts are not the full original Scala suite.
The negative control's complete original test prefix equals the fixed test prefix.
Both source dependencies and lockfile are unchanged.

Cost/boundary: failed complete can leave provider multipart parts until an explicit
provider-qualified cleanup or lifecycle policy. Generic Drop cannot safely decide
that abort is appropriate after an uncertain commit. The existing timed abort wait
and open-upload Drop cleanup remain; full disposal recovery/session barriers are
still unqualified. Nested complete tasks can still be detached on runtime loss;
failed drain/unknown classification must retain the namespace. Nothing here turns
an unknown report into confirmed cleanup or selects C0 durability.

[Provider/runtime checkpoint](../../PROVIDER-RUNTIME-OWNERSHIP-DESIGN.md).
Historical qualifier paths and receipts use absolute coordinator and /tmp paths;
inspect/adapt output locations before reproduction and preserve all old results.
