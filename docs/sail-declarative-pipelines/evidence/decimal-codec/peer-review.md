### 6.11 Decimal cast wire, candidate `b48162de9` on `8a7bf8ca4` (CF-0391)

Three paths: `physical.proto` adds `SparkStringToDecimalUdf` as tag 43 of
the `ExtendedScalarUdf` oneof (41 is the ANSI string cast, 42 the time
precision cast, nothing above), with `uint32 precision`, `int32 scale`,
`bool fail_on_error`, `bool allow_negative_scale`; `codec.rs` adds the
import, a decode arm and an encode arm; a 328-line test module.

- Decode validates the function name before construction, narrows
  `u32 → u8` and `i32 → i8` with `try_from`, then runs the constructor's
  `Decimal128` bounds. The malformed-wire test includes 257 and 258 and
  -256, which a wrapping cast would turn into precision 1, scale 2 and
  scale 0 and accept; that is what makes Codex's "replace each checked
  narrowing with a wrapping cast" controls fail rather than pass by
  accident.
- Proto3 omits a `false` bool from the wire, so `round_trip(…, false,
false)` exercises the decode-from-absent path, and both absent values
  decode to the lenient policy and to Spark's default range conf. That is
  the right failure direction for a field a future writer forgets, though
  it is not Spark's default ANSI mode; it matters only across schema
  evolution, not within one build.
- Values: `(5,2)`, `(38,10)` and the negative-scale `(5,-2)` (`150 → 2`)
  across both policies, three string layouts, scalar and array, with
  signature equality after the round trip.
- Error vocabulary after the round trip: `CAST_INVALID_INPUT` with all
  four parameters, `NUMERIC_VALUE_OUT_OF_RANGE.WITH_SUGGESTION` with the
  plain rendering, and the policy-dependent `1e39` flipping to
  `NUMERIC_OUT_OF_SUPPORTED_RANGE` when the range flag is off. Legacy
  returns `NULL` for all three inputs.
- Full physical tree: `SparkDivModLazy` over a captured string column
  with the decoded cast as the left thunk and a typed lambda parameter as
  the operation (returning the left value, so the fixture isolates cast
  laziness and claims nothing about division). Rows `("bad", NULL)`,
  `("1.235", 2)`, `(NULL, 0)` give `NULL, 1.24, NULL` in both modes: the
  first is skipped on the `NULL` divisor, the third is `NULL` because the
  dividend-null check precedes the ANSI zero check (§5.2). An empty batch
  and a one-row `("bad", 2)` batch that actually invokes the decoded cast
  complete it, with the typed error or `NULL` by policy.

Verdict: accept. Nothing blocking; the four fields are the ones §6.10
said the wire must carry.
