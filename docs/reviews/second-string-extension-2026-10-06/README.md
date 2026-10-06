# Second String: native Sail qualification

The native port passes the complete compiled Scala oracle in local mode and
with two separate Sail worker processes. The final detached source gate passes at the published source commit, including
all forty-one release Rust tests.

- Final source: `f31c33ae01e574b146853ace4a901a3876cf5417`, branch `work/second-string-extension`.
- Pull request: [https://github.com/querygraph/sail/pull/34](https://github.com/querygraph/sail/pull/34).
- Earlier graph work: [Sem research and PR status](SEM-STATUS.md).

## Implemented scope

The reference is Sem's
[Spark Second String at a35db39fa8e9b65db2d201a45b86d11a6ca34b98](https://github.com/SemyonSinchenko/spark-second-string/tree/a35db39fa8e9b65db2d201a45b86d11a6ca34b98).
The independent extension implements all sixteen defaults: six token
similarities, seven matrix/character similarities and three phonetic encoders.
Ten additional native function names expose the configurable Scala parameters.

Typed Python helpers build Spark Connect expressions. Rust executes through
DataFusion's Arrow FFI; the extension has no Sail crate dependency or JVM
runtime requirement. Changes are confined to the new
`examples/extensions/second-string` package and its parent README; no host
implementation changes are required.

## Observed checks

| Check                      | Result                                                                              |
| -------------------------- | ----------------------------------------------------------------------------------- |
| Compiled Scala reference   | 7,296 default and configurable cases retained as the oracle                         |
| Native Rust suite          | 41 tests pass, including all oracle cases through foreign Arrow FFI                 |
| Native local Sail          | 112 tests pass: 56 client tests and 56 live tests, including all 7,296 oracle cases |
| Native two-worker Sail     | The same 112 tests pass, including the complete oracle after repartitioning         |
| Typed Python source        | Ruff and strict mypy pass                                                           |
| Final detached source gate | Passed at the exact published source commit                                         |

Numeric oracle comparisons use absolute tolerance `1e-12`; phonetic strings
must match exactly. Coverage includes null propagation, empty and whitespace
strings, array slices, scalar broadcasts, and Utf8/LargeUtf8/Utf8View inputs.
It preserves Java whitespace and UTF-16 indexing, including supplementary
characters and Monge–Elkan's Java UTF-8 replacement of isolated surrogates.
Double Metaphone uses the primary code with maximum length four.

## Runtime and wheel identity

The compatibility tuple is **extension API 1, DataFusion 55.1.0 and
Arrow 59.3.0**, pinned in the extension's Cargo dependencies. Native checks
use the existing optimized macOS x86-64 Sail host, compiled from
`9f0aa7d2a50f1258544d37c05dd19b3ff3d915b3` with Rust 1.97.1.
The extension is separately built with Rust 1.98.1 and Python 3.12.6.

[host-receipt.json](evidence/host-receipt.json) records the full host command,
source and binary SHA256
`ee80ac3cf9d028639561f3cf32435985192719d629807fcf6a368324fa84946e`.
[wheel-receipt.json](evidence/wheel-receipt.json) identifies the release wheel
in Apo's `wheels04` directory: 3,600,818 bytes, SHA256
`bea2a1dc5db37bd2c3f5da41721969866944ab0c00d6cf23eb3285ae306f6156`.
Host, extension and Scala source identities are distinct. The qualification wheel
was built before final source formatting; the published source also passes the
complete native foreign-FFI oracle. Wheel and source gates are recorded separately.

## Preserved failed attempts

Earlier failures remain in the [attempt index](evidence/attempts.json) and
their original XML records. They are not replaced by the passing runs.

| Attempt                             | Failure and correction                                                                                                                    |
| ----------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| [local01](evidence/local01.xml)     | Casts hid option literals from validation; option handling was corrected.                                                                 |
| [local02](evidence/local02.xml)     | The BIGINT refusal fixture had the wrong expectation; the fixture was corrected.                                                          |
| [local03](evidence/local03.xml)     | Initial type validation rejected a decimal prefix literal; literal validation was corrected.                                              |
| [local04](evidence/local04.xml)     | Implicit decimal coercion hid the original literal; custom coercion now preserves option literal types.                                   |
| [process01](evidence/process01.xml) | The streaming plan required 36 task slots against 16 configured; the passing run uses 32 slots per worker and two CPU threads per worker. |

The development passes are `local05` and `process02`; the final published-head
passes are [local](evidence/gate-local.xml) and [process workers](evidence/gate-process.xml). The index retains every
attempt's original counts and outcomes. The slot correction changes declared
execution capacity, not the functions or oracle expectations.

## License and qualification limits

The package is Apache-2.0 licensed and retains attribution to Sem's source
and Apache Commons Codec 1.21.0. The Scala source and JDK are used to generate
the reference answers; they are not required by the native runtime.

This report establishes the disclosed native correctness checks. It contains
no speed comparison, Linux binary qualification or stable extension ABI claim.
[Published-head gate verdict](evidence/published-head-verdict.json) and
[gate log](evidence/published-head-gates.log) retain the exact source result.
