### 6.13 Negative-scale config capture, candidate `226b0c1cf` on `b48162de9` (CF-0396)

Eight paths, read against the §6.12 premises:

- `PlanConfig.legacy_allow_negative_scale_of_decimal: bool`, default
  `false` (`sail-plan/src/config.rs`), the Spark default.
- `SparkRuntimeConfig::set` validates the new key with
  `parse_config_bool` after the removed-key check and before
  `self.config.insert` (`sail-spark-connect/src/config.rs:153–181`), so
  an invalid `SET` leaves the previous value in place; the stored value
  is the raw accepted string, which `get` returns unchanged, as Spark's
  `setConfString` does. `PlanConfig::try_from` parses the stored string
  with the same function, so the typed flag and the raw string cannot
  disagree. Overrides clone the runtime config and `set` on the clone
  (`session.rs:109–117`), so a rejected override cannot touch the
  session.
- `config/boolean.rs`: `parse_sql_bool` is the Java trim (≤ U+0020)
  followed by the existing `parse_spark_bool`, extracted from the ORC
  path, whose error mapping is unchanged; `parse_config_bool` wraps a
  failure as `SparkIllegalArgumentException`
  `INVALID_CONF_VALUE.TYPE_MISMATCH`, SQLSTATE 22022, with `confName`,
  `confValue` (the raw, untrimmed value, as `toBoolean(s, key)` passes
  it) and `confType = "boolean"`, and the message in Spark's template
  wording.
- `error.rs` adds the class chain
  `SparkIllegalArgumentException → IllegalArgumentException →
RuntimeException → Exception → Throwable → Object`, which is the
  pinned declaration (`SparkException.scala:525–530`), and PySpark's
  client maps `java.lang.IllegalArgumentException`
  (`pyspark/errors/exceptions/connect.py:483`), so the client raises
  `IllegalArgumentException` as it would against Spark.
- Tests pin the 4.2 metadata explicitly, cover default, `true`/`false`,
  tab and NUL trimming, `falſe`/`FALſE`, unset, snapshot independence
  (an earlier `Arc<PlanConfig>` keeps its semantics after a later `SET`
  or `UNSET`), the ANSI-off `NULL` path through the callable caster, and
  six invalid values (`1`, `0`, `yes`, empty, NBSP-wrapped, `truſe`)
  rejected at both `SET` and override with the prior value retained and
  the full error details read back through `tonic::Status`.
- The dev-only `sail-function` edge exists so the test can feed the
  captured settings to the real caster; it is not a production
  dependency.

One note, not a finding: the older flags in `PlanConfig::try_from`
(`ansi_mode`, `legacy_type_coercion_datetime_to_string`, …) still parse
with Rust `trim().to_lowercase().parse::<bool>()`, which accepts NBSP
padding and rejects `falſe`; the new key is the first to use the Spark
rule. Aligning the others is a separate, pre-existing parity item.

Verdict: accept.
