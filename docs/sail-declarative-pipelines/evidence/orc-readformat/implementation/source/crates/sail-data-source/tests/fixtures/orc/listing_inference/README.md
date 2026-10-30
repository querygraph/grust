# ORC listing-inference fixtures

These three small ORCs were written by PyArrow 26.0.0 and read back by PyArrow
with exact schema and value equality. They contain a STRUCT with `Value`,
`value`, or both children. `reference.json` records the writer version,
generator hash, file hashes, schemas and readback values. They are foreign ORCs,
not Spark-written or newly Spark-read fixtures.

The files replace unsupported native-writer STRUCT construction in the listing
tests. The tests retain the separately qualified Spark 4.2.1 merge contract:
root case sensitivity controls root merging, matched nested structs merge with
exact case, and final duplicate-name validation recursively uses the read's case
policy. These bytes supply the schema shapes; they do not establish that contract
by themselves.

To regenerate, copy `generate.py` to an empty directory and run it with PyArrow
26.0.0. The generator refuses to replace an existing ORC and starts no JVM.
