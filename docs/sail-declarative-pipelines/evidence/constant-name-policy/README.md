# Explicit constant-name lowering policy

Recorded 2026-10-31T03:47:22.261826+00:00.

Product commit `f0a232af259fa2bf33c089d5439ffb45fa78061e`, parent `3ffb497d3e5dcbb48c56a5dd06687044ef994508`,
replaces the internal boolean context with `ConstantContext::Ordinary` and
`ConstantContext::Identifier`. Two exhaustive methods separately express function
foldability retention and deferred arithmetic evaluation. Existing catalog
resolution still selects Identifier; bare-catalog execution is not activated.
The enum is confined to the planning crate; no protocol or configuration changes.

Formatting, strict Clippy, 101 plan and 177 Connect library tests passed on the
immutable detached source. A fresh CLI passed 300 selected public tests and 67
upstream Python executions. Focused 14-case arithmetic and 20-case provenance
observations preserve the prior results, including all known incompatibilities;
the provenance harness also runs the four existing parameter tests. No new tests
mirror the enum's implementation. No full original Scala SDP-suite acceptance.

`verify.py` checks source identity, log/artifact hashes, native/public counts,
focused outcome/metadata equivalence and teardown. `runtime-gates.py` preserves
the executed orchestration and absolute temporary output paths; underlying probe
sources remain in the preceding packets. Run the verifier with Python 3.12.
