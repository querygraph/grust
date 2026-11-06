# Native extensions in recoverable streaming pipelines

Pipelines should be able to call separately packaged native functions and read native
relations without making those packages dependencies of Sail. Preserve the existing
extension host and add the Arrow-only scalar interface used by Apache DataFusion Comet,
a native accelerator for Spark.
A scalar function computes values for input rows; a relation supplies a set of rows and
needs a broader execution contract.

## Preserve what the existing host does

The existing host discovers Python packages, checks manifests, and binds native functions
and relations. Its DataFusion foreign-function interface, or FFI, carries DataFusion
types and checks the host's DataFusion and Arrow versions. Distributed plans identify
functions by package, configuration and name; workers resolve the matching implementation.
Native allocations use C callbacks to request memory against host-controlled limits.

That host exists in the pipeline integration code. Porting it to the streaming foundation
must preserve those behaviors; package integration has not yet been demonstrated.

| Responsibility | What streaming recovery adds |
| --- | --- |
| Package loading and function lookup | Record the selected interface and actual code and configuration so restart resolves the same implementation |
| Native relations | Preserve where they execute, cancellation and cleanup; establish whether their input can be reproduced |
| Memory ownership | Keep allocations accounted for while returned results still reference them |
| Library loading | Separate loaded code lifetime from query, session and function-instance lifetime |

The proposed streaming protocol requires saved intended writes and rejection of new
writes from replaced workers. Extensions join that protocol; they do not introduce
a second checkpoint system.

## Add a second scalar interface explicitly

A binary interface is the calling contract between compiled libraries. Comet's scalar
interface passes Arrow schemas and arrays through C records and callbacks. This reduces
coupling to DataFusion's Rust types. It does not promise compatibility across Comet
releases, including patch releases. Pin the actual interface layout and verify the
producer; a version number or an Arrow-only signature cannot establish arbitrary
library compatibility.

Replacing every existing package would combine a package migration with loader and
execution changes. Keeping only DataFusion FFI retains its version coupling. Recommend
supporting both, with the package explicitly selecting an interface for each exported
function. Resolve names deterministically and report an unavailable implementation
clearly. Mixed packages still need DataFusion and Arrow compatibility checks wherever
they use the existing interface.

The Comet route initially supports trusted functions whose results depend only on their
inputs and which perform no external writes. Declaring a function immutable does not
prove that property or make native pointers safe. Treat native code as trusted code;
manifest and interface checks are not a sandbox. A stateful function falsely declared
immutable could even be evaluated incorrectly during query planning.

The pinned interface reserves its constant-argument pointer and requires null. A function
that needs literal values while determining its result type requires a different,
versioned interface or a clear unsupported-operation error. Execution-time literals can
be expanded into arrays. Preserve complete input and output fields, including nested
metadata, rather than reducing the interface to data types alone.

## Keep cleanup code alive as long as results need it

A returned Arrow array can contain a release callback implemented by its native library.
A client may retain a slice after its query, function and session have ended. Unloading
the library then leaves the eventual cleanup call pointing at code that no longer exists.

The initial adapter keeps loaded library code for the process lifetime. The alternative
is to attach explicit library ownership to every exported allocation, which needs a
larger lifetime and unload protocol. Process retention matches the existing host policy
and Comet importer. Query allocations and function instances should still be released
when no longer needed.

The existing scalar registry retains the whole package owner. Its port must separate
that ownership from session resources; cleanup does not follow automatically from keeping
code loaded. Even a library rejected after opening can consume process-lifetime resources.
Limit repeated loading and identify actual code content. Test reading, slicing and
destroying results after every query and session owner has been dropped.

## Define which native work can recover

Sail's streaming operators carry data and ordered control messages. Native scalar
functions receive only data values; Sail preserves control order and retraction flags.

A finite native relation can participate where the execution graph defines its completion.
Returning Arrow batches does not make it replayable. A live native source needs stable
identity, recoverable positions, retained input and controls reaching its executing task
through `StreamSource`. A finite input used during recovery needs either a reproducible
snapshot or saved output. The scalar interface supplies neither source contract.

Record function identity and normalized configuration with prepared work. Repeating a
deterministic computation needs fixed inputs, code and dependencies. Nondeterministic
computation needs saved, validated output. Functions that mutate an external service need
an explicit retry and effect protocol before durable pipelines can use them; a manifest
cannot prevent duplicate side effects.

## What is demonstrated and what needs a decision

The [standalone adapter results](COMET-SCALAR-RESULTS.md) establish complete argument-field
handling, checks on the immutable declaration and process-retained callback code.
Two probes passed using an independently compiled producer from the pinned Comet development
kit. They do not establish compatibility with other Comet versions, package registration,
Spark SQL calls or worker loading.

Keep the existing DataFusion route as a control during integration. Test both routes
through package loading, duplicate names, mismatched worker code, cancellation, memory
limits and session cleanup. Check metadata, literal expansion, sliced and nested arrays,
nullability, error ownership and result lifetime through those real interfaces. Checking
nulls in dictionary, union and run-end encoded values must not require unbounded expansion.

Do maintainers want the optional Comet scalar interface in the host? Which packages and
pinned producer should define its first integrated acceptance cases? Do those functions
fit trusted, side-effect-free execution with process-lifetime code retention?

A C relation interface is a separate choice. Comet's scalar interface does not define
relation planning, execution properties, asynchronous execution or placement. Preserve
existing relations while actual requirements determine that broader contract. Carrying
a small attributed C interface does not require adopting Comet's or Sedona's entire
dependency graph.
