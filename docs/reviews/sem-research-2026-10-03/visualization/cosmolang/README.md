# Cosmolang 0.1 schema package

[Protocol](../COSMOLANG.md) · [Hierarchy/prediction](../COSMOLANG-HIERARCHY.md).
This is a draft portable contract, not a running service or SDK implementation.
Schema identity uses `urn:querygraph:cosmolang:0.1:<name>`; register the included
schemas by `$id`. No remote schema fetch is required. JSON Schema draft 2020-12.

| File                                                                                      | Boundary                                                                      |
| ----------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| `request.schema.json`                                                                     | Envelope, handshake/session revision and command alternatives                 |
| `navigation.schema.json`                                                                  | Session, complete camera poses, view/frontier and installation commands       |
| `graph.schema.json`                                                                       | Follow, spatial/vector nearest, property/degree filtering and WCC             |
| `work.schema.json`                                                                        | Layout providers and job observation/cancellation                             |
| `common.schema.json`, `camera.schema.json`, `predicate.schema.json`, `budget.schema.json` | Shared identities/context, 2D/3D camera, typed predicates and resource limits |
| `response.schema.json`, `event.schema.json`                                               | Ready/accepted/refused/error and sequenced events                             |
| `manifest.schema.json`                                                                    | Two Arrow resources, quality/provenance, counts and applied budgets           |
| `examples/`                                                                               | Twenty-three illustrative requests and six responses/manifest/event objects   |
| `validate_examples.py`                                                                    | Offline schema checks, cross-field example checks and rejection controls      |

Run with the dependency versions recorded in `requirements.lock.txt`:

```sh
python3 -m venv /tmp/cosmolang-check
/tmp/cosmolang-check/bin/pip install -r requirements.lock.txt
/tmp/cosmolang-check/bin/python validate_examples.py
```

Examples are independent templates, not a browser transcript or measured
provider results. Zero digests are placeholders; resource URIs are illustrative.
The 3D example specifies the desired protocol capability; the current adapter
has not qualified complete programmatic 3D pose control. Embedding ANN is a
proposed index adapter. Accepted or ready examples do not prove a provider can
execute those graph sizes.

Schemas check structural metadata. The gateway still needs context/catalog and
capability resolution; finite numbers; signed Int64 source-ID parsing; camera
clip/basis validity; predicate operator/type compatibility; request byte/depth
caps; domain/selection handles; budget clamping and actual runtime metering.
The checker covers selected cross-field constraints only, not those live checks.
A manifest’s logical complete quotient can use truncated display edges, with
unknown omitted count as `null`, never fabricated zero.

Bulk tables have separate schemas: points `id Utf8`, view-local `idx UInt32`,
`kind Utf8`, `x/y Float32`, optional `z Float32`, exact source mass as UInt64 or
lossless decimal string and requested small attributes; links use source/target
IDs and matching UInt32 indices, declared display weight and exact aggregate
count fields. Every returned endpoint is present in the same view. The receiver
checks actual Arrow layout, counts/bytes and endpoint/index consistency before
installation. This package contains no Arrow payload or GPU integration test.

Graph-result resources resolve to metadata naming their `result_contract`: domain,
input scope, algorithm/index version and exact/ANN/sample/partial status. Nearest
rows contain source IDs, rank, score and metric; WCC rows contain source ID and
versioned component ID. Requested sampling carries a seed in result provenance.
These are separate Arrow products, not fields merged into one mixed-schema stream.

C0 qualification is recorded in [VALIDATION.md](VALIDATION.md). Later C1–C5
acceptance is defined in the hierarchy proposal. No Rust target/cache rebuild
or VM is needed for this documentation/schema gate.
