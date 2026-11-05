# Comet C ABI extension integration: source research

The next extension increment should qualify a Comet-compatible scalar adapter,
then connect it to the existing package admission and function registry. The
existing relation and native-memory contracts remain useful, but neither the
old extension host nor the C scalar prototype is integrated into the newly
tested StreamSource foundation. Do not transfer their previous test results to
that combined design.

## Scope and provenance

Read the complete saved build-2 request, including “from Comet,” its preceding
build request, repository AGENTS.md and LAKESAIL.md, SHEHAB.md, CLARITY.md and
WRITING-RULES.md. Reviewed EXTENSIONS-ON-ARROW-C-ABI.md, the extension decision
notes and reported prototype results. This report uses source inspection only:
no builds, execution experiments, source edits or compatibility runs. Existing
prototype pass counts remain reported historical results.

| Source | Inspected pin and state |
| --- | --- |
| Existing Sail extension host | `/Users/alexy/src/sail-pipelines-proposal`, `99dc47788941daf28eec847527949a4cadafdbd2`; clean tracked source |
| Separate C scalar prototype | `/Users/alexy/src/sail-proto-p5`, `ef7286ca28222d9f25b719aacda6baea2876a0de`; clean tracked source |
| New streaming foundation | `2c9fa84994d317aade0d1c69faa9a378c780127d`; its Git tree lacks `sail-c-udf`, `sail-session/src/extensions` and `sail-native-resource-ffi` |
| Comet SDK and importer | Official Apache source at `0f7f8e45399847715093b3d3affdfa97614b39dc`, the pin already credited by the prototype |
| SedonaDB extension interface | `/Users/alexy/src/sedona-db-extension-poc`, `0a1993d9be8bcf52150593ad08fc6a3412d50f29`; inspected `c/sedona-extension` matches HEAD. Four unrelated tracked files have existing modifications, preserved |

Fetched origin for the local Sail repository and additional Sedona repository.
Comet was read from official pinned raw GitHub source and browser pages; no
Comet checkout or executable was created. These are pinned contract assessments,
not claims about the newest release. P5 and the new foundation share ancestor
`0ba425c0331aee4dd4e9a280c6a793926fd0876e`; P5 is not already part of that foundation.

## Existing implementation worth retaining

The old Sail host discovers Python entry points in `pysail.extensions` only when
`SAIL_EXPERIMENTAL_EXTENSIONS=1`. It validates manifests before reading native
capsules, handles aliases and built-in-name collisions, and binds session owners.
The manifest currently requires exact DataFusion and Arrow library versions
plus Sail API version 1. Build-time values come from Cargo.lock. These are
implemented compatibility guards, not a stable C ABI promise.
Sources: `crates/sail-session/src/extensions/mod.rs:175–330`,
`manifest.rs:6–78`, and `crates/sail-session/build.rs:18–38`.

Scalars arrive through `FFI_ScalarUDF`; relations export child `FFI_ExecutionPlan`
objects and import `FFI_TableProvider`. Distributed relations require driver
placement and use the existing driver registry. Scalar codec identities name
package/configuration identity and function, with an explicit refusal when the
worker has not loaded the matching identity. The process registry retains
native scalars; package retention separately protects code callbacks.
Sources: `extensions/mod.rs:79–166,219–228,261–321`,
`crates/sail-common-datafusion/src/native_scalar.rs:14–125`, and
`crates/sail-execution/src/proto/codec.rs:3666`.

The native memory lease is already a separate C record with version, size,
quota, opaque owner and retain/release callbacks. The host prepays a non-spillable
reservation and tracks final owner release. This accounts participating
allocations rather than all process memory. It should not be redesigned merely
because scalar import changes.
Sources: `crates/sail-native-resource-ffi/src/lib.rs:10–120` and
`crates/sail-common-datafusion/src/native_resource.rs:21–53,106–140`.

The existing Sedona example is an independently built DataFusion-FFI extension,
not a Comet library. Its adapter captures immutable default Sedona options;
host SET propagation is excluded. This existing working channel needs its
current version guards while another channel is introduced.
Sources: `examples/extensions/sedona/Cargo.toml:16–26`,
`src/lib.rs:17–73,92–161`.

## Exact Comet contract and corrections to the proposal

Comet exports `comet_udf_abi_version` and `comet_c_udf_list_v1`; supported ABI
version at this pin is 1. Its SDK explicitly distinguishes freedom from the
host’s DataFusion dependency version from binary compatibility. It supports
SDK-built libraries, publishes no C header, and requires rebuilding for its
release-specific experimental ABI. The DataFusion 53-to-54 example is a source
account in the SDK documentation, not an experiment executed here.
[SDK contract](https://github.com/apache/datafusion-comet/blob/0f7f8e45399847715093b3d3affdfa97614b39dc/native/comet-udf-sdk/src/lib.rs#L26).

The scalar structs use Arrow schemas/arrays and C callbacks. Shared factory
callbacks must support concurrent calls; each evaluation instance is serialized.
In ABI v1 `scalar_args` is reserved and must be absent. Only immutable functions
are admitted; the interface cannot declare volatile behavior. Therefore P5’s
NULL constants and Immutable flag match Comet’s restricted contract, but the
Sail admission policy must state and enforce that restriction. ABI layout can
change even in a patch release; “changes rarely” is not a supported guarantee.
[Layout and restrictions](https://github.com/apache/datafusion-comet/blob/0f7f8e45399847715093b3d3affdfa97614b39dc/native/comet-udf-sdk/src/c_abi.rs#L26).

Comet’s importer explicitly says returned Arrow arrays do not retain the library.
Its process-wide cache deliberately never unloads successfully loaded libraries.
P5 has an Arc on the function and LoadedLibrary, but no such output-lifetime
policy. Dropping both while an output remains can leave a release callback whose
code is unloaded. This is a source-derived safety gap, not an executed crash.
Retain successful libraries for process lifetime, matching the existing host
policy, or prove an owner wrapper for every exported allocation before admission.
[Importer lifetime](https://github.com/apache/datafusion-comet/blob/0f7f8e45399847715093b3d3affdfa97614b39dc/native/core/src/execution/c_udf/imported_c.rs#L85),
[process cache](https://github.com/apache/datafusion-comet/blob/0f7f8e45399847715093b3d3affdfa97614b39dc/native/core/src/execution/c_udf/cache.rs#L18).

P5 preserves argument fields during return-field inference but reconstructs
execution fields with empty names, nullable=true and no metadata. It ignores
`ScalarFunctionArgs.arg_fields`. Planning and execution can therefore disagree
for metadata-sensitive kernels, including spatial extension types. Preserve
actual fields and check returned type/row-count consistency before integrating.
Comet’s own pinned adapter also reconstructs fields; copying it unchanged does
not settle Sail’s stronger metadata requirements. P5’s two arithmetic fixtures
do not exercise this gap. Sources: P5 `crates/sail-c-udf/src/udf.rs:100–133,171–235`;
Comet importer `:187–219,249–281`.

The [Arrow C Data Interface](https://arrow.apache.org/docs/format/CDataInterface.html)
provides stable same-process data exchange and release callbacks. It does not
supply a Comet version negotiation field or cross-process execution protocol.
Do not invent an “Arrow C interface version” equality check from Arrow crate
versions. Define accepted data/layout capabilities separately from the pinned
Comet contract and package identity. Mixed packages still need exact guards for
any DataFusion-FFI scalar or relation they expose; dropping those guards globally
would weaken the current host.

## Sedona relation scope remains separate

Sedona’s header has the same scalar callback layout but permits constant bindings
and a successful, released output schema meaning that one kernel does not apply.
Its header and Python import paths do not export Comet’s discovery symbols.
Matching structs therefore does not prove that Sedona packages load unchanged.
It also defines table providers, execution plans, properties, scans and synchronous
or asynchronous streams. Those establish available building blocks, not a Sail
relation integration or recovery contract.
[Pinned header](https://github.com/apache/sedona-db/blob/0a1993d9be8bcf52150593ad08fc6a3412d50f29/c/sedona-extension/src/sedona_extension.h#L175).

The relation adapters are larger than “two small adapters.” At this pin their
files have 826 and 664 lines before test modules, plus runtime, stream, expression
and utility support. The crate depends on several DataFusion and Sedona crates;
its default feature includes protobuf expression transport. C-shaped records do
not remove semantic coupling in those encoded properties. Choose the admitted
scan/property/stream subset and inspect its dependency closure before deciding
between a crate dependency and attributed source ownership.
Sources: `c/sedona-extension/Cargo.toml:32–62`,
`src/table_provider.rs:578–650,757–825`, `src/execution_plan.rs:593–664`.

The proposed rule that extension relations provide bounded input with host-owned
end-of-data markers is future integration policy. It is not demonstrated by P5
or by the existing DataFusion relation channel. No C ABI source contract supplies
checkpoint participation, replay positions or fencing.

## Next concrete increment

Write a short decision note admitting only trusted, immutable Comet-v1 scalar
libraries at the pinned contract, with process-lifetime code retention and full
Arrow field fidelity. Keep DataFusion-FFI compatibility checks for existing
channels. Compare carrying the small pinned Comet importer/layout with the
current P5 adaptation; retain attribution and the exact comparison diff for
necessary changes. Do not import Sedona’s relation dependency tree in this step.

Then qualify the adapter as one isolated source increment. Reuse P5’s tests but
add metadata-sensitive init/execution, nullability and return-field agreement,
all applicable Arrow families, zero rows, errors, concurrent factory calls,
release counts, and outputs surviving adapter/session teardown. Build the pinned
Comet test library unchanged to provide an independent producer. A hand-written
Sail fixture alone cannot establish Comet SDK compatibility. Exporter panic
containment belongs to that producer and needs its own negative controls.

After that passes, add the narrow package/session registration bridge using the
existing identity, collision, ownership and codec contracts. Demonstrate a real
Spark SQL call and named ABI/missing-symbol refusals. Worker loading and identity
checks require their own multi-process evidence; scalar C pointers never become
a transport format. StreamSource may invoke admitted scalars only on data rows,
after marker isolation is qualified for the relevant operator. Durable extension
relations and change capture remain dependent later increments.

## Inspected-source hashes

Recorded: 2026-11-05T23:18:10.211036+00:00

| Source | SHA-256 |
| --- | --- |
| Sail host manifest | `57a9e054f6a32674292b240103af568397298f5d4cdf1fb90cd391b99d5b1e2e` |
| Sail host registration | `b485bdd83f47a6468f5e2e6deaa8d97863bfb647026fd6cf226105a0b471ce92` |
| Sail native scalar ownership/codec | `227b83b6bb7c0a1b2835deb35e52b00eb67dfd056cd9a72f3f4a1c09bc056128` |
| Sail native memory lease | `35ff30e923b34a6baa9608a2df1ca4ad6585a5681a4a448cc8436ebe06a72afe` |
| P5 ABI | `22c02acac0a56cfdb3d784f685f450fadba78e3f64a0d6470c732f8f72f76c48` |
| P5 loader | `c3f419ea1a970f67af8a11204ed8136a75bea1652b6341f8f8b417c6bfe1c16f` |
| P5 adapter | `c79be82f113949a3cdf1c053c595484c797b5c4632afb180c1f00d8fc5760b13` |
| Sedona header | `90a07a81842eabefcb36c3f152764beac9fd740dc1f1cc839c402a917ae057ef` |
| Sedona crate manifest | `b322be22f91b4548cfc18d1af10a8c83a10dfd19c5675d6a3cd1a1145c7ba896` |
| Sedona table provider adapter | `b93e609cebeb2c9caec32708eb7916f9aa5e5d34887611241e5203fcd3ad781d` |
| Sedona execution adapter | `64b21fd10575f3ede3c450d443e7230c275c7d65f9b4f8703b1bb0305b2485e4` |
| Comet `native/comet-udf-sdk/src/lib.rs` | `c0e71c4d559e7a4b14ebdb9a0571a55f790adefb4da21b4397c159d41a06a1a8` |
| Comet `native/comet-udf-sdk/src/c_abi.rs` | `5998bdb824db455b8d778cd879b82a0d65d2650530e73302e8b9e7b852f1869c` |
| Comet `native/core/src/execution/c_udf/loader.rs` | `1ab7b2f9eb37989c8c55b4033000b301ef0f62ef2c36c23828a1dc29d869ad30` |
| Comet `native/core/src/execution/c_udf/imported_c.rs` | `7216b56a638cfc7b198ef9b80e1c6a64565746eff29a75ec23511f9fa19d38f9` |
| Comet `native/core/src/execution/c_udf/cache.rs` | `855b3e0bb28d685619e39422258234406c562b2843a4b89f358330b57d8d6d68` |
| Comet `native/comet-test-udfs/src/lib.rs` | `ea476f617a4e3ea5b46c35995f17fa94e79485e774f5fdc8318dcb72217dea91` |
