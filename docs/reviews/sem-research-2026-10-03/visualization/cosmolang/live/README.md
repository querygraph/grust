# Cosmolang C1: native Cosmograph exploration slice

C1 implements the first local slice of [Cosmolang 0.1](../../COSMOLANG.md).
This is an experimental service, outside the published Grust workspace.
The source gate runs the actual Cosmograph SDK, Sail host and Nutmeg extension;
it does not replace any of them with a mock. The final receipt belongs to the
exact detached source commit it names.

## Qualification

`cosmolang: PASSED native gateway, MCP and Cosmograph gate at 4d222349b452ddc75e76cf3267acec2f78c73ba3`

The [exact-source receipt](evidence/gate04/receipt.json) records a clean unchanged
detached checkout and the native binary hash. [Seventeen semantic controls](evidence/gate04/semantics.json),
[the MCP client](evidence/gate04/mcp.json), and [four browser controls](evidence/gate04/browser.json)
passed. The [expanded graph screenshot](evidence/gate04/expanded.png) was visually
reviewed. Artifact/source identities are in [artifacts.json](evidence/artifacts.json).
The earlier detached lint failure is preserved separately. Development failures
(memory admission, numeric-only WCC IDs, startup/port errors) remain in the raw
owned archive on Apo; no development failure is counted as a passing gate.

## Implemented boundary

- Browser: `@cosmograph/cosmograph` **2.5.1**, pinned in `package-lock.json`.
  Typed Arrow tables map `id`, `source`, `target`, `x`, `y` into the SDK.
  Camera pan/zoom remain browser local. The prototype is 2D.
- HTTP gateway: schema checked Cosmolang requests, pinned catalog context,
  session revisions, payload-sensitive retries, complete bounded view requests,
  follow edges, hierarchy expansion/collapse, native WCC, session cleanup.
- MCP: the same dispatcher, a stdio transport, `tools/list`, `tools/call`, and
  `resources/read`. Arrow results are resources rather than tool text rows.
  `/mcp` is a local JSON-RPC diagnostic endpoint; it is not advertised as a
  complete Streamable HTTP transport.
- Sail: Parquet reads, endpoint filters and joins, bounded set reachability,
  quotient coordinates and multiplicities. Expansion recomputes incident
  quotient edges; it never drops edges merely because the other endpoint
  remains collapsed. Self loops remain explicit quotient links.
- Nutmeg: an admitted selection receives a local projection ID map, CSR staging,
  the requested supported WCC method, then restoration of source IDs. Opaque
  namespaced IDs remain strings through Arrow, JSON and the browser. A projected
  numeric ID or component label is never confused with a durable source ID.

Official API references: [data updates](https://cosmograph.app/docs-lib/features/data-adding/)
and the installed SDK declarations. The npm package declares **CC-BY-NC-4.0**;
a commercial deployment must use the appropriate Cosmograph licensing arrangement.
The qualification uses a local development browser, not a public deployment.

## Resource and semantic limits

The server policy admits at most 10,000 drawable points, 100,000 quotient links,
and a catalog shard of one million vertices/edges. These are **prototype caps**,
not a claim that this first slice has qualified million-point rendering or
multibillion-node exploration. A supplied flat group membership and supplied
coordinates form a two-level hierarchy; no layout or hierarchy generation is
claimed. Coordinates average within each collapsed group.

Complete results exceeding a cap are refused. There is no silent sampling.
Scan admission uses catalog metadata and a conservative operation multiplier;
no input-validation graph job runs. The input is valid and immutable by contract.
The fixture preparer supplies counts/bytes; a production catalog with snapshot
leases and indexes remains follow-up work. Current follow queries scan Parquet
with endpoint predicates, not a claimed external adjacency index.

The gate uses a 512 MiB Sail managed pool with a 128 MiB Nutmeg reservation,
inside that pool, two workers and native macOS release binaries. This is not an
OS RSS limit: Python, Arrow and browser allocation are separate. The local
artifact store is capped at 64 MiB; a session has 16 views/16 selections/128
completed requests; eight active sessions and 64 lifetime opens are permitted.
Close frees session resources. Deadlines are cooperative publication checks,
not hard process termination guarantees. A hard worker memory/time envelope is
required before exposing the service beyond loopback.

Nearest neighbors, property/degree filtering, predictive prefetch, arbitrary
hierarchy levels, 3D camera synchronization, durable view leases and browser
installation acknowledgements remain unsupported. Unsupported operations
receive a capability refusal. `view.request` returns a resource; the browser
loads it explicitly. There is no false server acknowledgement that it rendered.
The browser fixture is intentionally fixed to the fixture catalog; a production
catalog picker is outside C1.

## Run and qualify

Use Python 3.12, Node and the pinned dependencies. Install the retained native
Nutmeg release wheel into the Python environment. `requirements.lock.txt` pins
its Python dependency environment; the wheel hash/source is recorded separately
in qualification evidence. Keep artifacts outside the checkout.

```sh
python gate.py --sail /path/to/native/release/sail --output /new/evidence/directory
```

The gate requires a clean detached checkout and owns the Sail, gateway and Vite
processes it starts. It uses loopback ports 18765–18767 and refuses occupied
ports. It runs Ruff, mypy, all proposal schema controls, the typed SDK build,
independent HTTP/Arrow semantic controls, a real MCP SDK client and Chrome
browser controls. Chrome uses a software WebGL renderer in the automated gate;
that proves integration and rendered output, not physical GPU throughput.
It preserves failures and source/binary identity checks and stops its processes.

To inspect interactively, prepare the fixture, start the native Sail host with
extensions enabled and the gate's recorded environment, run `server.py`, and
run `npm run dev -- --port 18766` in `browser/`. Open `http://127.0.0.1:18766`.
Select a group to expand it, or follow the source vertex named in the input.

The final gate also covers collapse round trips, refusal of unknown collapses,
layout-frame and 2D camera pins, and selection affinity for hierarchy changes.
[The failed preceding gate](evidence/failed-gate03/semantics.log) is preserved:
its refusal tests shared mutable parameters; each request now copies them.
Earlier passing evidence remains in `evidence/`.
