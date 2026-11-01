# Flow progress and failure containment

Sail `35e8d4fb3` (parent `c8594db27`) emits flow lifecycle events and contains flow failures, from the Spark run in `gates/events.py` and `events.json`. It ports PipelineRefreshFunctionalSuite's 9 tests through the public client, plus 4 from the measured sequences.

Native 125 + 430, fmt, strict Clippy. Frozen 300 + 67. Pipelines directory 603 of 603 on Sail. `test_refresh_functional.py` 13 of 13 on Spark 4.2.1, read from the terminal on the preceding candidate, which differs from this one only by one removed assertion. On the `c8594db27` binary, 5 of 13 fail.

Measured and matched: PLANNING for batch flows only; retries from `spark.sql.pipelines.maxFlowRetryAttempts`, default 2; readers of a failed flow are skipped through views; independent flows complete; the flow's error is the run's error; a dry run reports only its end.

Not matched: Spark runs flows concurrently, so event interleaving differs; Sail runs them one at a time. There is no retry backoff, and Spark's non-retryable classification is not applied, so every failure retries. The failed-event `Error:` text is Sail's own error text. Persisted-view flows report nothing. AutoCDC runs report nothing beyond the run's end.
