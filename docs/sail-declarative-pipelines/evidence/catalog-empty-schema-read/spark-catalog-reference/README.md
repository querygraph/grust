# Spark 4.2.1 catalog schema reference

One finite Spark Connect run observed six generic catalog cases (ORC/Parquet/JSON × omitted/explicit schema) plus an existing-table `CREATE TABLE IF NOT EXISTS` guard containing a fresh-name negative control. All seven top-level cases succeeded. The negative control intentionally failed with `UNABLE_TO_INFER_SCHEMA`; its complete condition, exception, traceback, and Spark log are retained. This is not a Sail run or a pytest run.

The first six cases mirror the root's same-binary Sail control retained at `source/sail-catalog-control.py`. `run.py` uses retained inputs instead of deleting a temporary directory, starts one owned Spark Connect JVM, and adds configuration, source/JAR hashes, and cleanup receipts. No product code or frozen public gate/test source changed.

Observed table contracts:

- ORC and Parquet, with omitted schema or explicit `(id INT)`, produce nullable `id INT` and rows `[[3], [1]]`.
- JSON with omitted schema produces nullable `id BIGINT`; explicit `(id INT)` produces nullable `id INT`. Both return `[[3], [1]]`.
- All three input files remain byte-identical. Exact direct-reader schemas, table schemas, rows, and `DESCRIBE TABLE` results are retained per case.
- An existing ORC table accepts `CREATE TABLE IF NOT EXISTS ... LOCATION <missing path>` with the original schema, rows, and `DESCRIBE EXTENDED` unchanged; the missing path remains absent. A fresh table name at the same path fails with `UNABLE_TO_INFER_SCHEMA` and is not published.

The runtime observation does not count every filesystem call. The pinned `CreateDataSourceTableCommand.run` source at lines 49–63 returns for an existing table before data-source relation creation at lines 65–86; lines 99–126 store the resolved schema and then publish the table. That source supports the command's inference-before-publication and existing-table early-return ordering. It does not turn this local probe into a measurement of all metadata I/O or a general catalog durability claim.

The run used installed PySpark/Spark 4.2.1 and PyArrow 26.0.0, Java 20.0.2+9-78, UTC/en-US, `local[1]`, and 512m driver memory. `spark.sql.orc.impl=native`, ANSI=true, and the actual V1-source list and other settings are in `results.json`. Runtime JAR hashes are recorded separately from the local Spark source pin `617618396087429b5627a86ce933bb0f5d6645cb`; no claim is made that the installed JARs were built from that checkout. The full pinned Scala source is retained with its exact Git blob and SHA256 and was compared against the Git object during finalization.

The owned Python PID was 75247 and JVM PID 75290. The JVM exited 0, the exec session 8891 ended 0, and both PIDs were independently absent. No other process was stopped. The full log preserves Connect startup warnings about attempts to reapply immutable startup settings and the expected negative-control failure. There were no retries or hidden initial failures.

The invocation was `PYTHONDONTWRITEBYTECODE=1 JAVA_HOME=/Library/Java/JavaVirtualMachines/jdk-20.jdk/Contents/Home JAVA_TOOL_OPTIONS='-Duser.timezone=UTC -Dsun.timezone.ids.oldmapping=false -Duser.language=en -Duser.country=US' /Users/alexy/src/sail-pipelines-proposal/.venv/bin/python /tmp/sail-sdp-orc-catalog-reference/run.py > /tmp/sail-sdp-orc-catalog-reference/probe.log 2>&1`, from this packet directory. The script has a 600-second bound and cleans only its owned gateway.

`MANIFEST.json` inventories all retained files except itself. Only empty scratch/warehouse directories are omitted; no nonempty evidence file is excluded. `validate_evidence.py` is offline and read-only. Do not rerun `run.py` or `finalize_evidence.py` in this frozen packet.
