# LakeCat Agent Guidance

## FirstPair Book Delivery

`FIRSTPAIR.md` is the required contract for this repository's unified book
build and FirstPair library deployment. Read and maintain it before changing or
delivering the book; it owns the catalog slug, shelf, and all source-side
handoff guidance. The shared implementation and authoritative operational rules
live in `~/src/firstpair`. Do not duplicate that deployment procedure here.

LakeCat is the Rust Iceberg-compatible catalog foundation for QueryGraph. Keep
the catalog boundary thin: identity, tenancy, Iceberg REST compatibility,
metadata-pointer state, policy gates, and integration events belong here.

## Repo Boundaries

- Push Iceberg format, manifest, scan-planning, pruning, delete handling,
  metadata-as-data, and engine work into Sail whenever it can be reusable. LakeCat
  should prefer Sail APIs and generated Iceberg REST models over local
  reimplementation. LakeCat consumes Sail as a Cargo **git dependency on the
  `lakecat` branch of `github.com/querygraph/sail`** (develop locally in a Sail
  checkout, then push that branch and `cargo update` the locked rev — see
  `CLAUDE.md`).
- Push graph schema, graph taxonomy, projection logic, graph stores, traversal,
  and graph query behavior into Grust (`/Users/alexy/src/grust`). LakeCat should
  keep only catalog-facing graph sink/projection boundaries and call Grust APIs.
- Push governance, policy composition, capabilities, TypeDID envelopes, secure
  agents, and authorization semantics into TypeSec (`/Users/alexy/src/typesec`).
  LakeCat should ask TypeSec for decisions/proofs and persist receipts.
- Treat QueryGraph (`/Users/alexy/src/querygraph`) as the end-to-end integration
  target. LakeCat changes should naturally support QueryGraph bootstrap,
  Croissant/CDIF/OSI/ODRL/OpenLineage projection, and the QGLake acceptance flow.

## Compatibility Rules

- Do not fork Iceberg semantics or make standard clients depend on non-standard
  endpoints for normal table access.
- Keep Iceberg metadata pristine. Business semantics, policy, graph, lineage,
  and agent state should be derived control-plane or graph data, not required
  custom Iceberg metadata.
- For v4 work, prefer typed Sail support when available. JSON passthrough is an
  explicit compatibility bridge, not the long-term implementation.
- Raw credential vending must be a deliberate, audited exception. Governed
  Sail-planned reads are the default path for agents and untrusted principals.

## Implementation Priorities

- Treat `DESIGN.md` as the living design and review-plan surface. The archived
  `docs/completed/OPUS*.md` files are historical audit inputs, not active
  instructions.
- Use the existing trait seams (`CatalogStore`, `SailCatalogEngine`,
  `GovernanceEngine`, `CatalogGraphSink`, `LineageSink`) and keep defaults safe
  for embedded tests.
- Prefer pushing reusable fixes upstream to sibling repos, then depending on
  them from LakeCat. For example, manifest-metric decoding belongs in Sail; a
  reusable catalog graph taxonomy belongs in Grust.
- When LakeCat needs durable graph projection over a Turso store, use Grust's
  `grust-turso` backend through `grust-turso-local`. Keep graph persistence,
  traversal, and Cypher-over-Turso behavior in Grust; LakeCat should only
  configure the sink, emit catalog graph events, and prove the Grust-owned
  projection boundary.
- Keep feature gates honest. Default-feature tests should pass, and real
  integrations should be wired through explicit features such as `sail-local`,
  `typesec-local`, `grust-local`, `grust-turso-local`, and `qglake-fixture`.
- Keep `lakecat-cli qglake-fixture` as an explicit feature because it depends
  on Sail's local Iceberg fixture writer. Replay, handoff verification,
  management, policy, and storage-profile CLI commands should remain available
  in the default CLI build.
- Side effects to graph and lineage should move toward a transactional outbox so
  catalog state changes are not lost or blocked by external sinks.
- Prefer the Rust `turso` crate for LakeCat's durable local catalog spine. Keep
  the store contract portable, but do not reintroduce SQLx/SQLite unless the user
  explicitly asks for that backend.
- Check in after each logical unit of work. Before committing, add or update
  `CHANGELOG.md` with a concise description of that unit, then stage only the
  files that belong to the unit.

## Verification

- **Toolchain: stable only. Do NOT run `cargo +nightly`** (including
  `cargo +nightly fmt`). LakeCat builds, formats, and lints on the stable
  toolchain; never invoke the nightly toolchain. If a sibling repo's CI requires
  nightly formatting (e.g. Sail), let that repo's CI handle it rather than
  running nightly locally.
- For LakeCat changes, prefer:
  - `cargo fmt -p lakecat-sail -p lakecat-service -p lakecat-api -- --check`
  - `cargo fmt -p lakecat-cli -- --check` when CLI behavior or fixtures change
  - `cargo test -p lakecat-cli --features qglake-fixture qglake_fixture -- --test-threads=1`
    when QGLake fixture generation, handoff scripts, or fixture feature gates
    change
  - `cargo test -p lakecat-store --features turso-local`
  - `cargo test -p lakecat-service --features turso-local`
  - `cargo test -p lakecat-service --all-features`
  - `cargo test --workspace --all-features`
  - `docs/book/build.sh` when user-facing workflows, public behavior,
    acceptance evidence, or architecture guidance changes
  - `scripts/check-local-dependency-contract.sh` when dependency contracts,
    sibling APIs, CI policy, or QueryGraph handoff/import evidence changes
  - `git diff --check`
- When a change touches Sail, Grust, TypeSec, or QueryGraph, run the focused
  tests in that sibling repo as well and report each repo separately.
