# View read modes and analyzed flow streamingness

Sail 15272ec0a17070b3a9694992cc4a94ba98f572ce (parent 7a32efd2a) implements Spark's view read-mode checks (FlowAnalysis.scala:238-255) and makes flow type validation use analyzed streamingness.

## Measured contract (Spark 4.2.1, 33 cases in spark/observations.json)

The check compares the read mode with the view's analyzed mode, not with a flag on the query. A view is streaming if any input is streaming, including a UNION with a stream and a stream inside a CTE, and streamingness passes through a batch read of a streaming view.

| View | Consumer | Default | Check disabled |
| --- | --- | --- | --- |
| batch | ST, STREAM(v) | INCOMPATIBLE_BATCH_VIEW_READ | BATCH_RELATION_FOR_STREAMING_TABLE |
| batch | ST, v | BATCH_RELATION_FOR_STREAMING_TABLE | same |
| batch | MV, v | accepted | accepted |
| batch | MV, STREAM(v) | INCOMPATIBLE_BATCH_VIEW_READ | accepted |
| streaming | ST, STREAM(v) | accepted | accepted |
| streaming | ST, v | INCOMPATIBLE_STREAMING_VIEW_READ | accepted |
| streaming | MV, v | INCOMPATIBLE_STREAMING_VIEW_READ | STREAMING_RELATION_FOR_MATERIALIZED_VIEW |
| streaming | MV, STREAM(v) | STREAMING_RELATION_FOR_MATERIALIZED_VIEW | same |

Both errors carry SQLSTATE 42000. The session setting also disables the check. An invalid value fails only a flow reading a view, with Scala's text `For input string: "maybe"`. A view's own setting does not exempt the first read of that view, because Spark fuses view settings after the read.

## Qualification of the exact candidate

- fmt, strict Clippy, 125 Plan and 237 Connect library tests, CLI build: gates/library-and-cli.log.
- Frozen 300 selected public and 67 upstream: gates/frozen-public-receipt.json.
- New test_view_read_modes.py: pass on Spark 4.2.1 (exit 0; that run printed no count) and 34 of 34 on Sail. Combined with the streaming-input tests, 92 of 92 on Sail.
- Control: the same tests on the 7a32efd2a binary give 19 failed, 15 passed.

## Known limits

- **First-pass overlay approximation.** The check reads the call's raw flow settings plus base and session. Spark also applies settings from views read earlier in the same call. A flow reading view a (which disables the check) and then a mismatched view b is therefore not matched on the first call. Not measured or covered.
- The dry-run contract is what is qualified. Real execution still classifies pipelines with the syntactic is_streaming_query_plan outside graph.validate, and public streaming execution stays disabled. A check-disabled STREAM read of a batch view may be refused at execution even though Spark would run it as batch.
- Scope tracking counts named reads the resolver actually visits. An unused CTE around a stream was not separately measured against Spark; the frozen CTE cases pass.
- Persisted-view identifiers in these errors were not paired; Spark's temporary view renders as `v`, and Sail quotes its stored output name.
- No inventory promotion or original Scala-suite acceptance is claimed.
