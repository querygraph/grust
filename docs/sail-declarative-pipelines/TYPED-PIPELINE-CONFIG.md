# Typed pipeline configuration for Sail

Pipeline configuration should reject mistakes before a job starts or a table
changes. YAML can remain convenient for small projects while an optional typed
language makes larger configurations easier to reuse safely. Use one versioned
Sail configuration model for both, with the same validation at execution admission.

Dhall, a typed configuration language, is a useful optional authoring frontend.
Compile it to ordinary data outside the server. Do not require a new
configuration evaluator inside Sail's streaming runtime.

## Fit with the configuration Sail already has

Three different configuration surfaces need separate treatment:

| Surface | Existing behavior | Proposed change |
| --- | --- | --- |
| Pipeline project file | The Spark 4.2.1 client loads YAML for project metadata, source-file globs and string-valued Spark settings | Introduce a Sail-owned, versioned project model and strict loader |
| Sail application configuration | Rust structures consume compiled defaults plus `SAIL_` environment overrides | Reuse typed decoding patterns; do not replace application configuration as part of pipeline authoring |
| Data-source option definitions | Repository YAML generates Rust option structures and parsers at build time | Reuse the option registry for connector validation; this YAML is not the user's project file |

Project YAML does not describe the entire computation. Python and SQL source
files register graph definitions, and source options can arrive through those
APIs. Validation must cover those entry points too; validating one project file
cannot make an untyped API safe.

## Intentional differences from Spark

The existing project parser rejects unexpected top-level fields and requires
string-valued Spark settings. It does not enforce all annotated field types.
Focused parser execution accepted `name: 12`, `storage: false`, duplicate
names and unknown nested library fields. A duplicate name kept its last value.
Supplying both `database` and `schema` silently selected `database`.
These are reasons to strengthen the loader, not requirements to preserve for
Spark compatibility. The [reference parser](https://github.com/apache/spark/blob/617618396087429b5627a86ce933bb0f5d6645cb/python/pyspark/pipelines/cli.py#L151)
also shows that Python type annotations alone do not enforce the input contract.

The existing bounded pipeline implementation copies Spark's settings merge:
graph inputs can overwrite settings in binding order, and a successful analysis
can be repeated under merged settings. Resolve settings and their scope before
dependent planning instead. A view's settings should not silently replace its
consumer's settings. If a setting must agree across an execution boundary,
declare and validate that constraint. Dependency discovery may still be needed;
it should not silently redefine configuration or reevaluate effectful definitions.

Also reject an unknown data parse mode rather than silently making parsing
permissive. A misspelled failure policy must fail before data processing. The
loader experiment establishes the project-file weaknesses; the merge and
parse-mode findings come from source inspection. The stricter replacements
remain proposed behavior.

## One strict model, several authoring formats

Define versioned Rust data types for the admitted pipeline settings and derive
the external schema where practical. Use explicit variants for different run
modes and source kinds rather than loosely related flags. Keep client-only
file discovery separate from the execution settings the server must validate.
Both are parts of the versioned contract, with one definition of each field.

The loader should enforce these rules:

- Reject duplicate keys before converting a document into a map. Reject unknown
  fields at every defined level and collisions between aliases, including
  `database` and `schema`.
- Require exact scalar types and bounded numeric ranges. Make duration and byte
  units explicit. Distinguish an omitted value, a default and an explicit null.
- Define a restricted YAML scalar policy so words such as `on` do not silently
  become booleans. Reject unsupported tags, merge keys and excessive nesting;
  either reject aliases or limit their expansion explicitly.
- Resolve documented override layers deterministically. Reject conflicting
  values within one layer and report where each effective value came from.
- Validate cross-field constraints before effects, including source replay
  capability, checkpoint requirements and a target's enforced writer fence.

Strict Rust deserialization can reject unknown fields, but it does not supply
all these checks automatically. A generated JSON Schema improves editor
feedback and client validation; the server remains authoritative. Schema
defaults are annotations, so Sail must implement default application explicitly.
[Serde attributes](https://serde.rs/container-attrs.html) and
[JSON Schema defaults](https://json-schema.org/understanding-json-schema/reference/annotations)
describe those distinct responsibilities.

## Close the source-option escape hatch

A typed `Map<String, String>` guarantees only the types of its entries. It
does not detect a misspelled option or an unsupported recovery mode.

Sail's generated option parser converts recognized strings to Rust types, but
unrecognized keys can be ignored and later recognized entries overwrite earlier
ones. The inspected generic parse-mode parser even falls back to permissive
behavior for an unknown value to match Spark. A typo in a requested failure
policy must instead fail configuration admission. These are inspected code
paths, not new execution results. The
[option generator](https://github.com/lakehq/sail/blob/85c6cca01cd521dd778bc200c987a34edf141de1/crates/sail-build-scripts/src/data_source/options.rs#L388)
and [parse-mode handling](https://github.com/lakehq/sail/blob/85c6cca01cd521dd778bc200c987a34edf141de1/crates/sail-data-source/src/options/parsers.rs#L8)
show the relevant behavior.

Each admitted connector should declare its keys, types, aliases, defaults,
applicable operations and semantic checks. Normalize recognized aliases once,
then reject collisions and unknown keys. Extensions may register their own
versioned option schema. An explicitly opaque settings namespace must be
identified as unvalidated and must not carry durability, deletion or ownership
controls. The same checks apply to options supplied through Python or SQL.

## Optional Dhall authoring

Dhall provides typed records, alternatives, functions and imports. Shared
constructors can make invalid combinations harder to express while avoiding
copying large YAML files. Its official tools can
[export JSON or YAML](https://docs.dhall-lang.org/howtos/How-to-integrate-Dhall.html).

The proposed path is to check a Dhall document against the released pipeline
type, normalize it, export JSON, then run Sail's ordinary strict and semantic
validation. Checking against an inferred Dhall type is insufficient: that type
must be the one Sail expects. Numeric bounds and connector capabilities still
need validation after export.

Prefer a pinned external compiler initially. The
[Rust implementation](https://github.com/Nadrieril/dhall-rust)
states that it is unmaintained and implements only part of the language.
Embedding it would add a maintenance and conformance obligation unrelated to
stream execution. An external compiler keeps Dhall optional for YAML users.

Offer a no-evaluation deployment mode that accepts only normalized JSON or
strict YAML. For Dhall builds, pin the compiler and schema, use an explicit
import policy, and support offline compilation from approved dependencies.
Dhall can import files, environment variables and remote content. Semantic
hashes stabilize imported values, but do not replace an access policy or make
missing dependencies available. Its termination guarantee is not a practical
resource bound; impose time, memory and output-size limits on compilation.
These limits follow from its documented
[evaluation and import model](https://docs.dhall-lang.org/discussions/Safety-guarantees.html).

Keep secrets as references resolved through the normal credential mechanism,
not expanded values in the rendered artifact. Preserve source names and field
locations through validation. Where generated output loses an original Dhall
location, report the normalized field path and compiler provenance honestly.

## Alternatives and recommendation

| Approach | Benefit | Cost or limit |
| --- | --- | --- |
| Strict YAML or JSON plus Rust model and generated JSON Schema | Smallest change; catches structural mistakes and supplies editor assistance | No reusable typed functions; semantic checks still belong to Sail |
| Optional Dhall compilation into that model | Typed construction and reusable configuration functions | Compiler distribution, import policy and generated-type maintenance |
| Optional CUE configuration language | Combines structural and value constraints; can validate existing YAML | Another tool and constraint model to maintain consistently with Sail |

CUE supports YAML validation with closed definitions and exports concrete
JSON. Its ordinary package scope is open, so merely adding a schema does not
automatically reject extra fields. It is a reasonable alternative if reusable
constraints are more valuable than Dhall's typed functions.
[CUE validation](https://cuelang.org/docs/concept/how-cue-enables-data-validation/)
and [export](https://cuelang.org/docs/reference/command/cue-export/) document
those capabilities. Adopt one optional authoring frontend initially, not two
independent definitions of pipeline correctness.

Implement the strict model and connector admission first, and demonstrate an
optional Dhall frontend against it. Generate structural schemas from the
canonical model where possible. Pin schema versions and test any separately
maintained Dhall or CUE representation against the same acceptance corpus.
Reject unsupported versions rather than silently applying changed defaults.

Render the effective configuration deterministically, recording its schema
version, explicit defaults and override provenance. Snapshot the expanded
source-file list in deterministic order. A digest can bind this configuration
and its relevant code identity to a recovery contract; it cannot prove that
the source remains replayable or the target actually enforces fencing.
Those facts require admission checks and the storage protocol itself.

The decisive experiment is format equivalence: YAML, JSON and Dhall inputs
with the same meaning produce the same accepted model, while duplicate keys,
typos, alias conflicts, wrong types and invalid combinations fail precisely.
Test changed defaults, unavailable imports, compiler limits and direct API
bypasses. No Dhall or CUE integration has yet been executed in Sail.

Use the strict model as the authoritative pipeline contract, with Dhall as the
first optional authoring frontend and execution admission shared by every input
path. Choose the schema-generation mechanism, compiler packaging and import
policy by testing this contract, rather than maintaining a second definition
of correctness.
