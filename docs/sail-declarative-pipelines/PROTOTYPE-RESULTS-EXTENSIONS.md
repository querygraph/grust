# Prototype results: extensions over the Arrow-only C boundary

What the extensions prototype built so far shows, for the review. Terms as in
DECISION-NOTES-EXTENSIONS.md. The streaming prototypes have their own results
document.

## Current integration qualification

The observations below remain the reported standalone fixture results. They do
not qualify production loading. Inspection of the prototype additionally found
that execution rebuilds argument fields without their original metadata and
returned arrays do not visibly retain the library after the function is dropped.
Comet’s importer relies on process-retained library code for the latter case.
Both contracts need qualification before package integration.

The pinned Comet interface admits pure immutable functions and requires a null
constant-argument pointer during initialization. Those are interface restrictions,
not capabilities established by the fixture. Comet explicitly disclaims ABI
stability across its releases. The current
[scalar proposal](EXTENSIONS-ON-ARROW-C-ABI.md) and
[integration design](EXTENSIONS-STREAMSOURCE-INTEGRATION.md) supply the resulting
requirements; historical statements below about correctness apply only to the
exercised fixture cases.

## P5. Scalar functions from a library over the Arrow-only C kernel

**Question.** Can Sail load a library that exports scalar kernels in the
shape Apache Sedona defined and Apache DataFusion Comet adopted, with the
version probe and discovery symbol Comet uses, and run those kernels as
DataFusion scalar functions, without any DataFusion type crossing the
boundary? (Decision E1.)

**What was built.** A crate, `sail-c-udf`, with three parts: the C layout of
the kernel, the kernel instance and the kernel list, as records of function
pointers with a private data pointer and a release function; a loader that
opens a library, refuses it unless its version probe returns the supported
version, calls the discovery function and takes each kernel out of the list;
and an adapter that presents a kernel as a DataFusion scalar function,
creating an instance per evaluation, asking it for the return type from the
argument types, handing it the argument arrays through the Arrow C Data
Interface, and importing the result array. The layout, symbol names,
ownership rules and import sequence are restated from Comet's code with
attribution; Comet's exporter is not included. A second crate,
`sail-c-udf-fixture`, is a library that fills those records by hand, with no
SDK, for two kernels: `add_one_c`, and `sub_c` whose argument order is
observable.

**What it showed.** Three tests pass. The fixture loads through the probe and
discovery and lists its two functions by name. Through DataFusion's frame
API over a three-row batch, `add_one_c` gives 2, 6 and null, and `sub_c`
gives opposite signs when its arguments are swapped, so nulls and argument
order cross the boundary intact. A kernel error (`sub_c` with one argument)
reaches the query as an error naming the function and the kernel's own
message. A library without the version probe is refused by name. Clippy
with warnings as errors and the formatter are clean. The crate depends on
Arrow, DataFusion's expression crate and the loading library only; nothing
the integration branch added.

**Ownership, as exercised.** The host owns its argument arrays until the
kernel's execute takes them, leaving a released placeholder in each slot;
the kernel writes the result array for the host to own; the kernel list's
buffer is freed by the library after the host has moved each kernel out.
The library handle lives as long as any imported function, so a function
cannot outlive its code.

**What it changes in the decision notes.** Nothing in E1's recommendation;
it confirms that the boundary can be implemented from the layout alone. The
P5 specification now says the fixture is Sail-owned and the crate applies to
upstream `main` as is.

**What it leaves out.** Loading Comet's own test library and Sedona's
functions. Those independently compiled binaries remain unverified; the
handwritten fixture establishes a narrower result. The hook that lets a package declare such a library beside the
`datafusion-ffi` channel in the session's extension loader. Panic containment
on the kernel's side is the exporter's job (Comet's SDK does it); the host
side has nothing to contain. Spark SQL end to end, which follows the hook.

## What P5 establishes and what it does not

It establishes that the Arrow-only scalar boundary is small enough to carry
in Sail without a dependency on either project's crate, that the import
sequence is correct against a library written to the layout alone, and that
errors and nulls survive the crossing. It does not establish that Comet's or
Sedona's libraries load unchanged, which needs their binaries, nor anything
about the relation boundary, which is P6.
