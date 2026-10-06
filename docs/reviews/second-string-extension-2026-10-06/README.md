# Second String Sail extension: progress and qualification

Progress report for Sem, observed October 6, 2026. See the
[full Sem research and PR status](SEM-STATUS.md) for the earlier graph work.

## Implemented

The independent extension wheel implements all sixteen default functions from
[Spark Second String](https://github.com/SemyonSinchenko/spark-second-string/tree/a35db39fa8e9b65db2d201a45b86d11a6ca34b98):
six token similarities, seven character similarities, and three phonetic encoders.
Ten additional native entry points preserve configurable Scala DSL parameters.
The client provides typed Spark Connect helpers; the server executes Rust through
DataFusion Arrow FFI. The package has no Sail crate dependency.

Source is staged on `querygraph/sail` branch `work/second-string-extension`, based
on `sail-extensions` at `a20d660d9f`. It has not yet been published as a release.

## Observed checks

- Native optimized build completed on Morrobay macOS x86-64.
- Forty-one Rust tests pass, including all **7,296 answers from the compiled Scala
  source** through the foreign Arrow FFI route. Numeric comparisons use absolute
  tolerance `1e-12`; phonetic strings must match exactly.
- Fifty-six client tests pass. Typed client and oracle generation scripts pass
  Ruff and strict mypy.
- A separate source review found no material correctness or licensing issue.

The oracle covers default and configurable functions, Java whitespace behavior,
UTF-16 indexing, supplementary characters, empty and whitespace-only strings,
and phonetic normalization. Null propagation, slices, scalar broadcasts and
Utf8/LargeUtf8/Utf8View inputs are tested in the native FFI harness.

## Qualification in progress

The release wheel is building. Next are live Spark Connect checks in local mode
and with two separate Sail worker processes, including the complete Scala oracle
after repartitioning. Final formatting, Clippy and source gates precede the fork
commit and draft PR.

This is a correctness port. We have not measured a performance comparison with
Spark Second String, qualified Linux binaries, or declared the extension ABI
stable. The test host is the existing native release Sail executable built from
`9f0aa7d2a5`, with the matching API 1 / DataFusion 55.1.0 / Arrow 59.3.0 tuple.
It is distinct from the extension source commit.
