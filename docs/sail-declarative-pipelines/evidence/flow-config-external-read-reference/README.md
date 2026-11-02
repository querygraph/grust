# External Parquet metadata and private flow configuration

Seven direct Spark4.2.1 pipeline observations plus two ordinary SQL controls test
the proposed external read-point premise for native binding. **They do not
establish that premise.** The metadata behavior here follows the run-session case
setting, whereas flow analysis uses its private setting. This constrains the
[next native design](../../NATIVE-INPUT-BINDING-DESIGN.md); no new bound-input
representation is selected from these results, and no Sail parity is claimed.

A fresh Parquet fixture has two distinct fields, Foo and foo, values1 and2. A
direct SQL read succeeds under session caseSensitive=true, producing upper_value=1
and lower_value=2. The same read under false rejects duplicate column foo.

| Pipeline case | Session base | Flow/view settings | Result |
| --- | --- | --- | --- |
| external read before true view | false | view true | COLUMN_ALREADY_EXISTS |
| true view before external read | false | view true | COLUMN_ALREADY_EXISTS |
| declared true consumer, external before view | false | both true | COLUMN_ALREADY_EXISTS |
| graph true default, external before view | false | both inherit true | COLUMN_ALREADY_EXISTS |
| external read without view | false | none | COLUMN_ALREADY_EXISTS |
| external before false view | true | view false | AMBIGUOUS_REFERENCE |
| false view before external | true | view false | AMBIGUOUS_REFERENCE |

The session-true cases pass metadata validation but fail semantic resolution of
Foo/foo under the private false setting. In the session-false cases, neither a
private true flow nor graph setting permits the file metadata. Reversing relation
order does not change these outcomes. This is a narrow format/setting/phase result,
not a guarantee about arbitrary providers, table functions or helpers.

Attempt01 retained five cases without ordinary SQL/session-true controls; all
failed with duplicate columns, including declared-true and graph-true controls.
It could not support the proposed read-point claim. The final rerun adds the
controls above. Full inputs, errors/events, settings, client jar hashes and source
pin are in observations.json; installed runtime jars are not claimed built from
the local source checkout. The original file URI is retained in SQL/provenance;
exact input files are also archived under input/ for future replay. The Spark
session stops with no15002 listener. verify.py validates all nine observations,
harness identity and teardown; SHA256.json covers every archived file. No original
Scala suite or production Sail configuration-fusion verdict follows from this.
