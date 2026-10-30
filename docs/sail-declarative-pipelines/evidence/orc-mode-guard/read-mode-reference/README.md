# ORC read-mode source reference

This is a pinned Spark 4.2.1 source and installed ORC class audit, not a new Spark runtime observation. No mode probe, Spark session, service, Rust build or gate was run. Spark source pin is 617618396087429b5627a86ce933bb0f5d6645cb; exact source/class/archive hashes and excerpts are retained in source-audit.json.

The effective provider choice comes from SQLConf `spark.sql.orc.impl`, whose allowed values are exact `native`/`hive` and default is `native`. DataSource provider lookup consults that session setting. An operation option with the same spelling is not a provider selector.

SessionState.newHadoopConf clones the base Hadoop configuration and overlays every explicitly set SQLConf entry unchanged. newHadoopConfWithOptions then overlays operation options except path/paths. Therefore exact session `orc.force.positional.evolution` does reach Hadoop; uppercase session variants and runtime `spark.hadoop.orc.force.positional.evolution` remain distinct keys. This audit does not equate RuntimeConfig with initial SparkConf/Hadoop startup configuration.

For Spark's selected default V1 route (the pinned useV1SourceList includes ORC), DataSource passes CaseInsensitiveMap options to inference and HadoopFsRelation. That map's iterator exposes lowercased keys; operation forced-position keys are consequently case-insensitive. V2 OrcScanBuilder instead obtains asCaseSensitiveMap before creating Hadoop configuration, a retained source distinction. This unit does not claim V2 key-casing parity or implement an alternate V2 execution path.

Installed OrcConf bytecode uses the exact same `orc.force.positional.evolution` string for attribute and Hive alias, default false. It obtains the value through Hadoop Configuration.get and invokes Java Boolean.parseBoolean: untrimmed case-insensitive true enables forcing; other text is false. OrcUtils.requestedColumnIds ORs that flag with its automatic all-_col detection; guarding explicit forcing must not reject or change the already qualified automatic legacy mapping.

B2 therefore retains an immutable session implementation/forced-mode snapshot, overlays recognized read/table options only for the forced flag, and rejects Hive/invalid implementation or effective forced-position true only at the ORC read boundary. Unrelated workloads may store these values. False overrides disable a true session flag. Invalid implementation is diagnosed at read time in Sail; no global RuntimeConfig transaction/validation change is claimed. Existing variable substitution limitations are outside this unit.
