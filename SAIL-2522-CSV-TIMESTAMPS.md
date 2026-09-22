# Sail: CSV `inferSchema` and timestamps, and lakehq/sail#2522

A briefing to read before commenting on
[lakehq/sail#2522](https://github.com/lakehq/sail/pull/2522) or raising it with
the Sail team. Every claim has a source and a way to check it again; the
[verification table](#what-is-verified-and-by-whom) says who checked what. It sits
beside [`GRUST-SAIL.md`](GRUST-SAIL.md), which covers the Sail changes Grust itself
needs. This one is a finding from the Citi Bike showcase that asks nothing of
Grust.

Status as of 2026-09-22. Sail main `f1cf1729`; #2522 open at head `260f3bb7`,
last updated 2026-09-14. **Nothing has been posted or filed.**

## In one paragraph

On Sail main, `spark.read.csv(..., inferSchema=True)` fails on a timestamp column
unless its values happen to carry exactly four to six fractional digits. The
error is `cast Timestamp(Second, None) to Spark data type`, with `Millisecond` or
`Nanosecond` in place of `Second` depending on the input. An open PR from an
external contributor, #2522, already fixes the second and millisecond cases. It
is titled for Parquet, but it changes schema inference for CSV too. The one CSV
case it leaves failing is seven to nine fractional digits. There the PR's author
chose, on purpose and with a stated reason, not to widen nanoseconds. That reason
comes from Spark's *Parquet* behaviour. For *CSV*, Spark infers a timestamp and
truncates to microseconds. So the useful contribution is a short comment on #2522,
not a new issue or PR.

## How it fails

Three steps, each checked in the code:

1. **arrow-csv chooses the unit from the number of fractional digits**
   (`arrow-csv` 59, `src/reader/mod.rs:191-195`): none gives `Second`, one to three
   give `Millisecond`, four to six `Microsecond`, seven to nine `Nanosecond`. The
   `Second` pattern also accepts a trailing `Z` or `+02:00` and still records no
   timezone.
2. **Sail passes the inferred type through unchanged.** `CsvReadFormat::infer_schema`
   (`crates/sail-data-source/src/formats/csv/read.rs:45`) merges the per-file schemas
   as inferred.
3. **Sail maps only microsecond timestamps to Spark types.**
   `crates/sail-spark-connect/src/proto/data_type_arrow.rs:171-175` returns an error
   for `Timestamp(Second | Millisecond | Nanosecond, _)`, with or without a
   timezone. The message is built at line 134. `Timestamp(Microsecond, Some(_))` maps
   to Spark `timestamp`, and `Timestamp(Microsecond, None)` to `timestamp_ntz`.

So a column fails or succeeds according to how many fractional digits its values
happen to have. That is why the Citi Bike data behaves two ways: the Kaggle file
the Neo4j tutorial uses has `start_time` values like `2018-05-31 23:59:59` (no
fraction, so `Second`, so it fails), while Citi Bike's own raw file has four
fractional digits and reads fine.

## Reproduction

Ten seconds against any Sail Spark Connect server:

```python
open("/tmp/t.csv", "w").write("t\n2018-05-01 00:00:05\n")
spark.read.option("header", True).option("inferSchema", True).csv("/tmp/t.csv").printSchema()
```

On Sail main this raises `cast Timestamp(Second, None) to Spark data type`. With
#2522 it prints a timestamp column.

Each row below is a CSV of header `t` and one value. Columns: Sail main
`f1cf1729`; Sail built from #2522's head `260f3bb7`; classic Spark 4.0.1.

| value | Sail main | Sail + #2522 | Spark 4.0.1 |
| --- | --- | --- | --- |
| `2018-05-01 00:00:05` | fails, `Second` | `timestamp_ntz` | `timestamp` |
| `2018-05-01T00:00:05` | fails, `Second` | `timestamp_ntz` | `timestamp` |
| `…05.5`, `…05.584` | fails, `Millisecond` | `timestamp_ntz` | `timestamp` |
| `…05.5840`, `…05.584000` | `timestamp_ntz` | `timestamp_ntz` | `timestamp` |
| `…05.5840000`, `…05.584000000` | fails, `Nanosecond` | **still fails, `Nanosecond`** | `timestamp` |
| `…05Z`, `…05+02:00` | fails, `Second` | `timestamp_ntz`, offset converted to UTC and dropped | `timestamp` |
| `…05.584000+02:00` | `timestamp_ntz` | `timestamp_ntz` | `timestamp` |
| `2018-05-01` | `date` | `date` | `date` |
| `2018-05-01 00:00` | `string` | `string` | `timestamp` |

## What #2522 does

[#2522](https://github.com/lakehq/sail/pull/2522), "fix: read Parquet files with
second and millisecond timestamps", by james-willis, an external contributor. It
adds `try_merge_normalized` in `crates/sail-data-source/src/listing/utils.rs`, which
widens `Timestamp(Second | Millisecond, tz)` to `Microsecond` in an inferred
schema. It is called from the CSV reader (`formats/csv/read.rs:100`) as well as
the Parquet, JSON, Avro and Arrow readers, so **the PR changes CSV inference even
though its title names only Parquet.**

It leaves nanoseconds alone deliberately. Its code comment, verbatim:

> Nanoseconds are left alone so that they are still reported rather than silently
> truncated, which matches Spark: its Parquet reader accepts `MILLIS` and `MICROS`
> but not `NANOS` (SPARK-40819).

That is a principled choice and should be treated as one, not as an oversight.

Related upstream issues: #2519 (open) is the same error on the Parquet read path;
#2518 (closed) is the same error on the write path. No issue or PR mentions CSV
`inferSchema`.

## Why CSV is different

- **[SPARK-40819](https://issues.apache.org/jira/browse/SPARK-40819) concerns Parquet
  only.** It is about Parquet `INT64 (TIMESTAMP(NANOS,true))`, which began throwing
  "Illegal Parquet type" in Spark 3.2, fixed in 3.2.4, 3.3.2 and 3.4.0. It says
  nothing about CSV or text sources.
- **Spark's CSV reader truncates nanoseconds.** On classic Spark 4.0.1, reading a
  CSV with `inferSchema=True`:

  | value | inferred type | stored fraction |
  | --- | --- | --- |
  | `2018-05-01 00:00:05.123456789` | `timestamp` | `.123456` |
  | `2018-05-01 00:00:05.123456500` | `timestamp` | `.123456` |

  `.123456789` becomes `.123456` rather than `.123457`, and the half-way value also
  goes down, so this is truncation, not rounding.

So "match Spark" means different things for the two formats. For Parquet
nanoseconds it means report them, which is #2522's position. For CSV it means read
them and truncate.

## What stays different from Spark even with #2522

Not part of the comment, but you should be able to answer if asked.

- **Timezone flavour.** Where Sail reads these values it infers `timestamp_ntz`
  (no timezone); Spark infers `timestamp` (session local time). This predates #2522
  and affects microsecond values that already work. **So the unit matches Spark
  and the timezone flavour does not.**
- **Minute precision.** `2018-05-01 00:00` stays a `string` in Sail; Spark infers
  `timestamp`.

Each would be its own issue, if anyone wants it raised.

## Options

| Option | For | Against |
| --- | --- | --- |
| Ask in team Slack first | Lightest touch; the team decides the route before anything public | none |
| Comment on #2522 | Puts the CSV finding where the review happens | Adds a question to an external contributor's PR in public |
| Wait for #2522 to merge, then send a small PR for CSV nanoseconds | Doesn't widen someone else's scope | The gap stays documented nowhere until then |
| Do nothing | The showcase works around it with an explicit schema | Every CSV user with a plain timestamp column hits this |

Current plan: ask in team Slack, then comment on #2522 if the team agrees.

## Drafts

**Team Slack**:

> Heads up: CSV `inferSchema` fails on any timestamp without 4–6 fractional digits
> (e.g. `2018-05-01 00:00:05` → `cast Timestamp(Second, None)`). #2522 fixes second/ms
> but CSV nanoseconds still fail — worth widening there too?

**Comment on #2522**:

> Thanks for this — it also fixes CSV `inferSchema`, which today fails on any
> timestamp without 4–6 fractional digits (`2018-05-01 00:00:05` →
> `cast Timestamp(Second, None) to Spark data type`); with `260f3bb7` those now read.
> One CSV case remains: 7–9 fractional digits still fail with
> `Timestamp(Nanosecond, None)`. Leaving nanoseconds alone makes sense for Parquet
> (SPARK-40819 is Parquet-specific), but for CSV Spark itself infers `timestamp` and
> truncates — on 4.0.1, `…05.123456789` reads as `…05.123456`. Would widening
> nanoseconds for CSV fit in this PR, or would you prefer a follow-up?

## What is verified, and by whom

"Agent" means a Claude Code subagent working on the `grust` host; "Claude" means
the coordinating session, which checked it directly. Nothing here has yet been
checked by you.

| Claim | Checked by | How to check again |
| --- | --- | --- |
| The bug is live on current Sail main | agent, on `f1cf1729`, which is current main | the reproduction above |
| #2522 fixes second and millisecond for CSV | agent, built `260f3bb7` and ran it | build #2522, run the reproduction |
| Seven to nine fractional digits still fail with #2522 | agent, same build | the table's nanosecond row |
| arrow-csv picks the unit from the fractional digits | agent, `arrow-csv` 59 `reader/mod.rs:191-195` | read the source |
| `data_type_arrow.rs:171-175` rejects non-microsecond units; the message is at line 134 | **Claude**, read at `f1cf1729` | `git show f1cf1729:crates/sail-spark-connect/src/proto/data_type_arrow.rs` |
| CSV inference passes the type through; #2522 calls `try_merge_normalized` at `read.rs:100` | **Claude**, read on both commits | `git show pr-2522:crates/sail-data-source/src/formats/csv/read.rs` |
| #2522's head is `260f3bb7`, open, last updated 2026-09-14 | **Claude** | `gh pr view 2522 --repo lakehq/sail` |
| #2522's stated reason for leaving nanoseconds (quoted above) | **Claude**, read in the PR's diff | `gh pr diff 2522 --repo lakehq/sail` |
| SPARK-40819 is Parquet-only | **Claude**, read the JIRA | the link above |
| Spark 4.0.1 infers `timestamp` for CSV and truncates nanoseconds | **Claude**, ran classic Spark 4.0.1 on JDK 17 | the script below |
| Spark 4.2 classic behaves the same | **not checked** | run the script with `pyspark==4.2.*` |

### Before posting

The comment says "with `260f3bb7` those now read". That rests on an agent's build,
not yours. Run the reproduction against a Sail server built from #2522 yourself
before posting it.

### Spark truncation check

Requires JDK 17 and `uv`:

```python
# spark_nanos.py — run with:
#   JAVA_HOME=$(/usr/libexec/java_home -v 17) \
#     uv run --no-project --with pyspark==4.0.1 python spark_nanos.py
from pyspark.sql import SparkSession
spark = SparkSession.builder.master("local[1]").config("spark.ui.enabled", "false").getOrCreate()
for value in ["2018-05-01 00:00:05.123456789", "2018-05-01 00:00:05.123456500"]:
    open("/tmp/n.csv", "w").write(f"t\n{value}\n")
    df = spark.read.option("header", True).option("inferSchema", True).csv("/tmp/n.csv")
    micros = df.selectExpr("unix_micros(t) % 1000000 AS us").first()["us"]
    print(value, df.schema["t"].dataType.simpleString(), f"{micros:06d}")
```

Expected output: `timestamp` and `123456` for both values.
