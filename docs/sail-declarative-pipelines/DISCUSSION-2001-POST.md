# Draft: post for Sail discussion #2001

Status: draft 2026-11-04, for the owner to post under their own account in
week 1 of the upstream series (plan X0). Links were checked on 2026-11-03.

---

## A bounded native extension contract on DataFusion's FFI: a proof of concept, and three questions

Earlier in this thread the position was that Sail's extension API should not be a Rust trait but an FFI built on DataFusion's, so that Sail and an extension release on their own schedules, that Python packages are the natural distribution and discovery mechanism (PyPI and entry points, with `PyCapsule` as the bridge), and that an end-to-end proof of concept would be welcome. We built one, qualified it, and are preparing it for upstream as a short series of PRs. This post is the contract we'd like to discuss before the code PRs open.

**What it is.** Two independently packaged native extensions run inside Sail without being Sail dependencies: SedonaDB scalar functions executing on workers, and Nutmeg stateful graph relations executing on the driver. Each is a wheel built against `datafusion-ffi`, discovered through a Python entry point, and bound at session start. The host side is small and bounded:

- **Discovery and trusted registration.** The host loads declared packages, rejects collisions and known incompatibilities before binding, and resolves matching scalar implementations on workers by identity rather than by re-shipping code.
- **Bounded relation dispatch.** A Spark Connect `extension` relation (the `RelationPlugin` path asked about in #2002) is dispatched to the registered package with ordinary child plans and pure planning. The foreign region stays opaque to host optimization.
- **Driver placement.** Driver-local stateful regions stay on the driver; automatic replay of those regions is disabled, and an unacknowledged mutation is reported as indeterminate rather than retried.
- **Host-funded memory.** A versioned, opaque, prepaid quota lease crosses the boundary through a 169-line C ABI; the session manager owns the admission pool and injects it into its sessions and in-process workers. Rust ownership and allocator layouts never cross.

**Compatibility is declared, not compiled.** The loader compares the extension's declared API, DataFusion and Arrow versions with the host's (derived from `Cargo.lock` at build time), not the Sail commit or the Rust compiler. We ran unchanged wheels against hosts built with Rust 1.97.1 and 1.98.1, an upstream advance, and an FFI-only dependency move, and against three revisions of the current tree: 1,294 integration passes on the original matrix, 609 on the merged tree, plus refusal and lease-boundary probes that must fail before binding. That is evidence of reuse within a measured matrix, not an ABI promise. The next step we'd propose is an explicit compatibility-version negotiation backed by unchanged-wheel CI, rather than relaxing version checks.

**What it is not.** It does not add optimizer rules, physical planner extensions or command plugins from outside the workspace; those are the extension points inventoried in #1810 and in this thread, and this contract leaves them open. It does not claim foreign-service propagation, sorted or co-partitioned input requirements, driver-only scalar scheduling, indexed spatial joins, or distributed native CSR iteration. Native allocations are non-spillable and participating reservations are not a process RSS cap.

**Three decisions we'd like from you before the code PRs:**

1. Is this experimental compatibility policy (declared versions, measured matrix, negotiation as the next step) and the bounded relation interface acceptable as the first extension contract?
2. Is the session manager the right default admission domain for native memory, with equal configuration never implying shared ownership?
3. What graceful-shutdown policy should apply to a noncooperative native owner: wait with a bound, abandon with a reported failure, or refuse to report the session deleted?

**Where to read more.** The design record for this and the related pipelines work is open as a draft docs PR, lakehq/sail#2930 (section 15 is the extensions contract). The full design review, the ABI experiments with their receipts, and the proposed host responsibilities are on the branch:

- design review: https://github.com/querygraph/sail/blob/work/spark-declarative-pipelines/docs/development/extensions/design-review.md
- ABI review and evidence: https://github.com/querygraph/sail/blob/work/spark-declarative-pipelines/docs/development/extensions/abi-review.md
- the request in full: https://github.com/querygraph/sail/blob/work/spark-declarative-pipelines/docs/development/extensions/maintainer-request.md
- the PR plan (track X): https://github.com/querygraph/grust/blob/work/sail-declarative-pipelines/docs/sail-declarative-pipelines/UPSTREAM-PR-SERIES.md

The PRs would come in this order: the memory-lease C ABI crate, the session-owned loader and admission pool, Connect relation dispatch, driver placement and codec, worker-resolved scalar functions, then the documentation. The example wheels and their matrix harness would live in a separate repository, since they pin exact engine versions and carry their own workspaces. Field-metadata rules for geometry are a separate review decision and are not implied by agreement to the loader contract.
