# Reviewing the Sail extensions

Start every new extension review at the versioned
[SAIL-EXTENSIONS-REVIEW-REQUEST.md](https://github.com/querygraph/sail/blob/sail-extensions/docs/development/extensions/SAIL-EXTENSIONS-REVIEW-REQUEST.md), beside Sail's design review.
It replaces the earlier branch-review invitation and is the authoritative
entrypoint for Sedona scalars, stateful relations and loader compatibility.

The entrypoint identifies the historical prototype and the separately tested
static-preflight candidate by exact commit. Choose a review track there, follow
its clone and tutorial instructions, and include the request version and the
commit from `git rev-parse HEAD` with your comments. A candidate implementation
and a successful test run do not decide adoption or an upstream submission.

The Sedona track covers registration and compatibility, names, geometry fields,
native owner lifetime and worker identity. Bounded relation dispatch, native
resource admission, driver placement and mutation retry are additional questions
for stateful extensions. Native libraries remain trusted code.

## Earlier reference editions

The [one-page brief](EXTENSIONS-ONE-PAGER.md),
[decision maps](extensions-review/overview.md), and
[host comparison](extensions-host-review/manuscript.md) describe their pinned
`bd8ce9ae8` prototype. Their assembled EPUB/PDF editions and earlier source
captures remain historical references. They do not acquire the new loader's
pre-import guarantee or its runtime results through this navigation update.

The broader graph work remains mapped in [GRAPH-NUTS.md](GRAPH-NUTS.md).
Use the canonical review request to choose the relevant scope before following
those additional materials.

Navigation updated 2026-10-03T21:34:23.494615+00:00; review-request edition 1.0.0.
