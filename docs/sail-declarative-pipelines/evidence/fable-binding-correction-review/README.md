# Independent replay after the binding correction

Immutable Fable correction `41f09ec470aa0415d23f5ecd0e0acdf792fb9987` remains
unintegrated. The same two named scalar-subquery/EXISTS counterexamples from the
[original failing probe](../fable-binding-expression-review/README.md) now pass:
exact cargo command returns0,2 passed/0 failed, with clean unchanged HEAD before
and after. This closes those validator-boundary failures only. No provider/RPC,
complete CTE/alias, admission or overall streaming verdict follows. CF-0151 sends
the scoped result to Fable; join orientation, multiple range-bearing subqueries,
provider/static provenance and canonical binding aliases remain separate review.

The root gate was restored to2e7beda82 after this terminal replay; root product is
unchanged by it. Source/log/receipt are retained, including the normal linker
unwind-size warning. SHA256.json covers packet files except itself. Replay into
fresh outputs; run.py retains historical absolute paths.
