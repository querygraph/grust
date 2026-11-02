# Original basic metadata and matching existing schema

Test-only Sail candidate `807d66b157569522af7ffec1848e89d95079721f`, parent
`604a91f8d65076d142866095c5cd62999319c20d`.

Two native ports strengthen already partial original MaterializeTablesSuite sites:

- :42–123: three MV materializations preserve exact ordered INT columns with
  mixed nullability, update comment1/2 to comment3/4 and remove them, while the
  table comment stays p-comment. Defaults/generation/identity are absent.
  Sail's native reserved table-comment field is used, preserving catalog design.
- :236–262: a real SQL-created nullable INT table has the exact same schema
  before and after ordinary Table metadata materialization of a batch1/2/3 query.
  This is an unchanged-schema assertion like the original, not mutation evidence.

Both additionally assert zero flow rows. No production code needed changing.
Exact detached fmt/strict Clippy/[native library](native/rust.log):193 passed.
The [production-only control](control/control.json) omits only comment removal;
unchanged basic test fails0/1 at the third state (comment3 versus absent).

The [Spark adapter](spark/BasicMetadataOracle.scala) executes both **verbatim
original test bodies**, with the unmodified original registration helper and
production DatasetManager4.2.1. The extracted body files are checked against the
source pin in verify.py. Both pass; extra zero-row checks pass too. This standalone
adapter does not run ScalaTest or execute the original suite against Sail.

Only two cfg(test) paths change; the existing materializer and Cargo dependencies
remain identical. [Runtime proof](test-only-runtime.json) references the parent's
already qualified CLI/public300+67 receipt. No fresh CLI build or public run is
claimed for the test-only commit. The current CLI hash was checked when archiving.
Initial single-case native192/Spark evidence is retained under initial/.

Both inventory sites remain partial; totals stay68 partial/394 unmapped among462
static sites,97 reviewed. Original JVM suite execution remains unqualified.
Fable accepted b32ead862 in CF-0452/Grustc19fc2b3 and the expanded807d66b15 in
CF-0454/Grust7f62f82f, pending the native gate now recorded here.

The next user-notified Astra design checkpoint is original-suite execution:
these native ports and reference adapters alone cannot establish full-suite
acceptance. No wrapper/origin, streaming, full-reset or CDC authority is added.

Run `python verify.py` with local Sail/Spark Git object stores available.
