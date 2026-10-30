# Independent C2 lowercase context review

Exact Sail helper and tables at `f4537586b6c79d60ebc56a183d9744948d812576`
were compiled in an isolated minimal crate against icu_casemap2.3.0 and regex1.13.1,
matching Sail's locked versions. The production helper sources were unmodified.
This is an independent component probe, not a full Sail build or CDC runtime test.

**1,332 of 39,215 generated strings differ from Oracle JDK17.0.8 ROOT lowercase.**
The input set takes all suffixes of length zero through five over A, 1, dot,
apostrophe, underscore, combining acute and ZWJ, constructs `AΣ + suffix` and
`A + suffix + Σ`, and removes duplicate strings while retaining order.

For codepoints `[0041,0031,0301,002E,03A3]`, the Rust helper ends in final sigma
U+03C2, whereas Java ends in ordinary sigma U+03C3. Apostrophe/underscore in place
of the dot and ZWJ in place of combining acute provide further counterexamples.
The one-neighbour-derived classes do not capture these composed word contexts.
The pinned JDK boundary/state rules need investigation. Named examples alone are
insufficient targets for a correction.

The complete cases, raw outputs and every mismatch are preserved, including
all passing comparisons. Java calls String.toLowerCase(Locale.ROOT); no Spark
classes are involved. These findings leave Fable's exhaustive one-scalar result
and its 201 designed-context successes intact. The new generated set is bounded;
it does not prove complete context coverage or public CDC reachability. C2 remains
unintegrated pending correction. No Fable worktree was modified.

The historical harness [run_probe.py](run_probe.py) expects a fresh absolute output
directory. Sources, Cargo lock, compiler log, commands and tool/binary hashes are
archived. `provenance.json` hashes all packet files except itself. This packet
records mismatches intentionally; a verifier passing means the evidence is intact,
not that the proposed implementation has passed parity.
