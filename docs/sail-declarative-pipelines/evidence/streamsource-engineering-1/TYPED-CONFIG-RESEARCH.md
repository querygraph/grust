# Typed pipeline configuration research

Recommendation: one versioned Sail model owns effective pipeline configuration
and execution admission. Strict YAML and JSON are ordinary input formats; Dhall
is an optional external authoring compiler into that model. Check graph and
connector settings arriving through Python or SQL as well. A typed project file
alone cannot protect the execution boundary.

This report combines local source inspection, one focused execution of the
existing PySpark project parser, and primary documentation research. It does not
establish a working Sail typed loader or Dhall integration. No Spark session,
Sail server, Rust build, Dhall compiler or CUE compiler was run. No dependencies
were installed and no source worktree was changed. The prompt and governing
instructions were read, including after compaction.

## Source identity and inspected scope

The source checkouts were clean when verified. Paths below are relative to the
named checkout; full identities and file hashes are recorded at the end.

| Name | Local checkout | Commit |
| --- | --- | --- |
| Upstream Sail | `/Users/alexy/src/sail/tmp/streamsource-review-20261105-85c6cca01` | `85c6cca01cd521dd778bc200c987a34edf141de1` |
| Pipeline runtime | `/Users/alexy/src/sail-pipelines-proposal` | `99dc47788941daf28eec847527949a4cadafdbd2` |
| Spark 4.2.1 | `/Users/alexy/src/spark-sdp-4.2.1` | `617618396087429b5627a86ce933bb0f5d6645cb` |

### The project file belongs to the client

The runtime example documents `spark-pipelines run --spec pipeline.yaml` in
`examples/declarative-pipelines/README.md:78–82`. The project parser is Spark's
`python/pyspark/pipelines/cli.py`, not Sail's application YAML loader. Inspection
of upstream Sail crates and Python sources did not locate a separate
`PipelineSpec` or `spark-pipelines` project parser.

In the pinned Spark parser:

- Lines 58–118 define dataclasses and validate library-glob syntax. Type
  annotations do not enforce project scalar values at runtime.
- Lines 151–191 load `yaml.safe_load`, reject unexpected top-level fields,
  require `name` and `storage` presence, choose `database` over `schema`, and
  extract nested library `glob.include` without rejecting extra nested fields.
- Lines 194–217 require configuration keys and values to be strings, without
  validating those settings against a semantic registry.
- Lines 231–272 discover and execute Python files or register SQL. The glob
  iteration is not explicitly sorted. This is source inspection, not a claim
  that a particular filesystem returned a different order.
- Lines 317–351 apply configuration to session construction and graph creation;
  storage is a separate run parameter. Source-file discovery belongs to the
  client, while execution settings need authoritative server validation.

The [pinned Spark parser](https://github.com/apache/spark/blob/617618396087429b5627a86ce933bb0f5d6645cb/python/pyspark/pipelines/cli.py#L151)
supports these distinctions. The experiment below directly checks selected
parser outcomes; it says nothing about whether downstream Spark accepts a
malformed specification or how a job executes it.

### Sail application settings are already typed

Upstream `crates/sail-common/src/config/application.rs:23–83` defines Rust
configuration structures and merges compiled defaults with `SAIL_` environment
overrides through Figment. Nested structures commonly deny unknown fields;
the top-level `AppConfig` does not carry that attribute. Existing aliases can
produce duplicate-field errors when an environment override and a default use
different names for the same field. This is a typed application configuration
surface, not a strict project loader.

`crates/sail-common/src/config/loader.rs:15–40,50–73,94–117` defines the
build-time item format, explicit empty-string/zero conventions, and nested
default assembly. Its final map insertion replaces a repeated leaf. These are
code-derived observations; application loading and duplicate defaults were not
executed. See the [application model](https://github.com/lakehq/sail/blob/85c6cca01cd521dd778bc200c987a34edf141de1/crates/sail-common/src/config/application.rs#L23)
and [default loader](https://github.com/lakehq/sail/blob/85c6cca01cd521dd778bc200c987a34edf141de1/crates/sail-common/src/config/loader.rs#L94).

### Connector option YAML generates Rust code

Upstream `crates/sail-build-scripts/src/data_source/options.rs:16–79` defines
the repository's option metadata. Lines 95–137 read the YAML during the build,
validate key spelling and filter by supported scope. Lines 153–244 generate
typed structures, default parsing and layer merging. This is not the format a
pipeline author submits.

Lines 388–454 generate independent matches over supplied string key/value
pairs. Recognized aliases assign the same field, later entries overwrite
earlier ones, and unmatched keys do not trigger an error in this generated
parser. `crates/sail-data-source/src/formats/rate/options.rs:8–15` applies
option layers in order. `crates/sail-common-datafusion/src/datasource.rs:48–86`
also exposes opaque options, where collecting into a map loses duplicate-key
provenance. These are inspected code paths, not executed parser cases.
See the [generator](https://github.com/lakehq/sail/blob/85c6cca01cd521dd778bc200c987a34edf141de1/crates/sail-build-scripts/src/data_source/options.rs#L388)
and [option layers](https://github.com/lakehq/sail/blob/85c6cca01cd521dd778bc200c987a34edf141de1/crates/sail-common-datafusion/src/datasource.rs#L48).

`crates/sail-data-source/src/options/parsers.rs:8–15` explicitly preserves
Spark's fallback from an unknown parse mode to permissive behavior. Lines
18–57,80–113 include numeric bounds, accepted boolean spellings, optional
strings and positive-integer parsing. Typed conversion therefore already
exists, but it is not equivalent to rejecting every typo or invalid mode.
The [parse-mode fallback](https://github.com/lakehq/sail/blob/85c6cca01cd521dd778bc200c987a34edf141de1/crates/sail-data-source/src/options/parsers.rs#L8)
is a concrete compatibility choice the proposed strict pipeline admission
should replace. Broader data-source API compatibility remains an implementation
scope choice; a pipeline-only wrapper must not allow direct API bypasses.

### Flow configuration also needs deterministic scope

The pipeline runtime's `crates/sail-spark-connect/src/pipelines/config/merge.rs`
is explicitly compatibility-driven. Lines 1–21 describe raw string settings.
Lines 37–50 overwrite them in graph-view binding order. Lines 85–146 merge
distinct used inputs only after a successful first analysis and detect
conflicting raw values. `config/resolve.rs:275–339` calls analysis at line 283,
merges at line 294, and calls analysis again at line 320 when the accepted
configuration changed. These were read, not executed.

`crates/sail-spark-connect/src/config.rs:190–220` validates some recognized
settings while otherwise retaining strings. Adding Dhall before this path
would leave its ordering and semantic issues intact. The design recommendation
is explicit scope and deterministic effective settings before dependent
planning. Do not normalize arbitrary string options as though their semantics
were known; normalize only fields owned by a typed schema. Source dependency
discovery may still be needed, but it should not silently redefine the
consumer's configuration or require reevaluating effectful user definitions.
This is a proposed design change, not a proven replacement planner.

## Focused parser execution

The existing runtime `.venv/bin/python -B` supplied Python 3.12.14,
PyYAML 6.0.3 and PySpark 4.2.1. Installed `pyspark/pipelines/cli.py` and the
pinned Spark source had identical SHA-256 values:
`82ea1cad088a59da34c38d2936ff2edf6216a1aeb8e3c2a15231e27f38451486`.
The script called only YAML loading and `unpack_pipeline_spec`. Bytecode
writing was disabled. System Python lacked PyYAML; no installation was made.

| Input | Observed parser result |
| --- | --- |
| Duplicate `name` | Accepted, last value retained |
| Integer name and boolean storage | Accepted unchanged |
| Extra fields inside a library entry and its glob | Accepted, extras omitted |
| Extra top-level field | Rejected with named unexpected-field error |
| Unquoted boolean Spark setting | Rejected because the value is not a string |
| Quoted boolean Spark setting | Accepted as a string |
| Both `database` and `schema` | Accepted, database selected |
| `name: on` | Accepted as boolean true after YAML conversion |
| Empty document | Rejected with an incidental `TypeError` |

The following Python body was run from the runtime checkout using
`.venv/bin/python -B -` with a quoted shell heredoc. The retained body and stdout
are UTF-8 with LF line endings and one terminal newline; their hashes are in
the generated provenance footer.

```python
import dataclasses, hashlib, json, pathlib, sys
import yaml
from pyspark.pipelines import cli
from datetime import datetime, timezone
reference = pathlib.Path('/Users/alexy/src/spark-sdp-4.2.1/python/pyspark/pipelines/cli.py')
installed = pathlib.Path(cli.__file__)
print(json.dumps({'at':datetime.now(timezone.utc).isoformat(),'python':sys.version.split()[0],'pyyaml':yaml.__version__,'installed_sha256':hashlib.sha256(installed.read_bytes()).hexdigest(),'reference_sha256':hashlib.sha256(reference.read_bytes()).hexdigest()}))
cases = {
'duplicate_name':'name: first\nname: second\nstorage: /tmp/data\n',
'wrong_top_scalar_types':'name: 12\nstorage: false\n',
'unknown_nested_field':'name: ok\nstorage: /tmp/data\nlibraries:\n- glob:\n    include: x.py\n    typo: true\n  typo: true\n',
'unknown_top_field':'name: ok\nstorage: /tmp/data\nstorag: /lost\n',
'conf_boolean':'name: ok\nstorage: /tmp/data\nconfiguration:\n  spark.sql.caseSensitive: true\n',
'conf_quoted_boolean':'name: ok\nstorage: /tmp/data\nconfiguration:\n  spark.sql.caseSensitive: "true"\n',
'database_schema_collision':'name: ok\nstorage: /tmp/data\ndatabase: a\nschema: b\n',
'yaml11_on_name':'name: on\nstorage: /tmp/data\n',
'empty_document':''}
for name, value in cases.items():
    try:
        spec=cli.unpack_pipeline_spec(yaml.safe_load(value))
        print(json.dumps({'case':name,'outcome':'accepted','value':dataclasses.asdict(spec)}))
    except Exception as error:
        print(json.dumps({'case':name,'outcome':'rejected','error_type':type(error).__name__,'message':str(error)}))
```

```jsonl
{"at": "2026-11-05T05:38:13.594713+00:00", "python": "3.12.14", "pyyaml": "6.0.3", "installed_sha256": "82ea1cad088a59da34c38d2936ff2edf6216a1aeb8e3c2a15231e27f38451486", "reference_sha256": "82ea1cad088a59da34c38d2936ff2edf6216a1aeb8e3c2a15231e27f38451486"}
{"case": "duplicate_name", "outcome": "accepted", "value": {"name": "second", "storage": "/tmp/data", "catalog": null, "database": null, "configuration": {}, "libraries": []}}
{"case": "wrong_top_scalar_types", "outcome": "accepted", "value": {"name": 12, "storage": false, "catalog": null, "database": null, "configuration": {}, "libraries": []}}
{"case": "unknown_nested_field", "outcome": "accepted", "value": {"name": "ok", "storage": "/tmp/data", "catalog": null, "database": null, "configuration": {}, "libraries": [{"include": "x.py"}]}}
{"case": "unknown_top_field", "outcome": "rejected", "error_type": "PySparkException", "message": "[PIPELINE_SPEC_UNEXPECTED_FIELD] Pipeline spec field `storag` is unexpected."}
{"case": "conf_boolean", "outcome": "rejected", "error_type": "PySparkTypeError", "message": "[PIPELINE_SPEC_DICT_VALUE_NOT_STRING] For pipeline spec field `configuration`, value for key `spark.sql.caseSensitive` should be a string, got bool."}
{"case": "conf_quoted_boolean", "outcome": "accepted", "value": {"name": "ok", "storage": "/tmp/data", "catalog": null, "database": null, "configuration": {"spark.sql.caseSensitive": "true"}, "libraries": []}}
{"case": "database_schema_collision", "outcome": "accepted", "value": {"name": "ok", "storage": "/tmp/data", "catalog": null, "database": "a", "configuration": {}, "libraries": []}}
{"case": "yaml11_on_name", "outcome": "accepted", "value": {"name": true, "storage": "/tmp/data", "catalog": null, "database": null, "configuration": {}, "libraries": []}}
{"case": "empty_document", "outcome": "rejected", "error_type": "TypeError", "message": "'NoneType' object is not iterable"}
```

## Primary research on optional formats

The following external pages were read for this review. URLs using `latest`
or unpinned documentation describe what was inspected, not immutable package
contracts. Compiler and schema versions must be pinned in any implementation.

| Primary source | Relevant fact and consequence |
| --- | --- |
| [Dhall integration](https://docs.dhall-lang.org/howtos/How-to-integrate-Dhall.html) | Both native bindings and external JSON/YAML compilation are documented. An external compiler preserves an ordinary-data server boundary. |
| [Dhall safety](https://docs.dhall-lang.org/discussions/Safety-guarantees.html) | Imports can use files, HTTP and environment variables. Hashes pin normalized values. Total evaluation can still be impractically expensive. Use import controls and resource limits. |
| [Dhall language tour](https://docs.dhall-lang.org/tutorials/Language-Tour.html) | Integrity hashes identify canonical normalized expressions, not the source text. A rendered configuration digest is a distinct artifact identity. |
| [Dhall JSON/YAML tutorial](https://docs.dhall-lang.org/tutorials/Getting-started_Generate-JSON-or-YAML.html) | Typed records, functions and alternatives can construct exported data. The exported data still needs Sail's semantic admission. |
| [dhall-rust status](https://github.com/Nadrieril/dhall-rust) | The project describes itself as unmaintained and estimates roughly 90 percent language support. This argues against making it a new server dependency by default. |
| [serde_dhall API](https://docs.rs/serde_dhall/latest/serde_dhall/) | The inspected API was 0.13.0 and offers expected-type annotation through `StaticType`. Inferring some valid Dhall type is insufficient when Sail expects a specific type. |
| [Dhall Haskell releases](https://github.com/dhall-lang/dhall-haskell/releases) | The inspected release page listed 1.42.2, dated January 19, 2025, with standard 23.1.0. No release binary was downloaded or executed. Compiler choice remains an integration decision. |
| [CUE validation](https://cuelang.org/docs/concept/how-cue-enables-data-validation/) | CUE validates existing YAML/JSON and reports input locations. Closed definitions matter because package scope is open. Useful alternative for constraint-oriented validation. |
| [CUE export](https://cuelang.org/docs/reference/command/cue-export/) | Export requires concrete values and produces JSON by default. It can serve the same ordinary-data boundary as Dhall. |
| [CUE constraint model](https://cuelang.org/docs/concept/the-logic-of-cue/) | Constraints unify without relying on their order; conflicting values fail. Do not treat this as Sail's existing override-layer semantics. |
| [Serde container attributes](https://serde.rs/container-attrs.html) | Unknown-field rejection is explicit. It does not automatically supply project-specific semantic validation, source spans or a raw duplicate-key policy. |
| [JSON Schema objects](https://json-schema.org/understanding-json-schema/reference/object) | Extra properties require explicit closure. Composition needs care when defining which fields are permitted. |
| [JSON Schema annotations](https://json-schema.org/understanding-json-schema/reference/annotations) | `default` documents a value; validation does not insert it. Sail must own application of defaults. |
| [JSON Schema conditionals](https://json-schema.org/understanding-json-schema/reference/conditionals) | Cross-field conditions can be expressed, but external source availability and enforced writer ownership require runtime admission. |
| [Schemars](https://docs.rs/schemars/latest/schemars/) | The inspected API was 1.2.3 and derives JSON Schema from Rust types. Generation reduces duplicated structure; custom semantic checks still need explicit representation or shared acceptance tests. |

No `dhall`, `dhall-to-json` or `cue` executable was available in the inspected
shell path. Their behavior above is primary-source research, not local
execution. No maintenance commitment, supported release matrix, compiler
performance or diagnostic fidelity has been measured.

## Proposed contract and unresolved validation

The self-contained design is [Typed pipeline configuration](../../TYPED-PIPELINE-CONFIG.md).
It recommends exact scalar types, duplicate/unknown-key rejection, alias
collision detection, bounded values, explicit defaults and override provenance.
Connector registries must cover API-supplied settings; opaque string maps must
not carry durability or ownership controls. A schema checks configuration
shape, not whether a target really rejects a stale writer.

Dhall is proposed as optional authoring into the same canonical model, with a
released expected type, pinned compiler, approved offline imports and bounded
evaluation. Normalized JSON or strict YAML remains usable without evaluation.
Secrets stay references. Source locations should survive where possible;
after compilation, report normalized field paths honestly when original spans
are unavailable. These are requirements, not demonstrated functionality.

Next validation should compare acceptance and normalized output across YAML,
JSON, Dhall and direct APIs, including wrong scalar types, duplicates, unknown
fields, alias collisions, unsupported schemas, changed defaults, unavailable
imports, resource limits and invalid cross-field combinations. Schema
generation and frontend maintenance should be measured against that corpus
before committing to an embedded implementation. No existing prototype proves
these properties.

## Generated provenance

Recorded: 2026-11-05T05:46:01.570813+00:00

Retained experiment body SHA-256: `bec19d937caa03c565552b86641c9b7c7eb659e5676acd749ede37f4d5baf1a6`.

Retained experiment stdout SHA-256: `3808a1f6a55164ed21c34e7218e9e36c0f8eac3bbb4cc0938cd9dd48614a1189`.

Upstream Sail HEAD: `85c6cca01cd521dd778bc200c987a34edf141de1`; status: clean.

| File | SHA-256 |
| --- | --- |
| `crates/sail-common/src/config/application.rs` | `588905332bbfdd48506edb08e1de1a750ea9ce2a8fac10a004423815ff04ea69` |
| `crates/sail-common/src/config/loader.rs` | `6d32562f47eb1ad180a89b054916ef0f828e7969a8f441aabcf00a47f827610d` |
| `crates/sail-build-scripts/src/data_source/options.rs` | `7c197cd13ad5ab62498c46d9576086b38b33b2b9d396b2f4b4ce93345fe79f21` |
| `crates/sail-data-source/src/options/mod.rs` | `a5881fac85a69a659b27e081ef0124bd1c7930fbb2173b33b4e1e0fa7b1c95a3` |
| `crates/sail-data-source/src/options/parsers.rs` | `f0dc387ff34cf4120896cb4ce9818c90ab15cbec49228d96c192ef76d4435bd4` |
| `crates/sail-data-source/src/formats/rate/options.rs` | `764049ca818402d5a52b8a69b14f0a63970b8585f669739beeb9d0088f4d32da` |
| `crates/sail-common-datafusion/src/datasource.rs` | `d4da8eb5217a3ff92c2c9a6a29e01b9841888d774a2364448a6c7fbe84462020` |

Pipeline runtime HEAD: `99dc47788941daf28eec847527949a4cadafdbd2`; status: clean.

| File | SHA-256 |
| --- | --- |
| `examples/declarative-pipelines/README.md` | `d8a827b59f803a373fad73d36d54c71a10b2c68befb1065421edde9c7bbc21b1` |
| `crates/sail-spark-connect/src/pipelines/config/merge.rs` | `f26f3a2ac64cbdaa32ee52a5d728be033bc50d685d9c56e0430a19ddb9a8358e` |
| `crates/sail-spark-connect/src/pipelines/config/resolve.rs` | `075ee9d3600065f00278d1f9e386aae6ea27853aa884b7d42ff4fb7eb501927f` |
| `crates/sail-spark-connect/src/config.rs` | `364360e87aae3cd781b5f68eb9c2b16877db48cb9601e86a2b20f9af7f2e5f6b` |

Spark 4.2.1 HEAD: `617618396087429b5627a86ce933bb0f5d6645cb`; status: clean.

| File | SHA-256 |
| --- | --- |
| `python/pyspark/pipelines/cli.py` | `82ea1cad088a59da34c38d2936ff2edf6216a1aeb8e3c2a15231e27f38451486` |
