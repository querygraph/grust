# Historical Markdown link context

The first ownership documentation snapshot stopped before publication because a
retained, unchanged copy of `RESULTS.md` was checked from its archive directory.
The [unchanged authoritative verifier failure](archived-links-baseline.json) and
[independent audit failure](failed-independent-audit-failure-20261001T010351687857Z.json)
are retained. The old candidate and private publication output remain unchanged.
This is a documentation-integrity correction, not new runtime evidence.

The corrected verifier accepts an explicit manifest `archived_markdown_link_contexts`
entry containing `original_path` and `source_manifest`. Both the archived file
and retained source manifest must belong to the current hashed inventory. The
source manifest's original file row must prove the archive's exact SHA256 and
byte count. Only then does the verifier resolve the archive's links from the
original directory. Every relative target is still checked; no link is skipped
and no historical prose is rewritten.

For this one archive, the retained source row proves SHA256
`7cf7f2e3fb677f3e547db4214de2dd9d48c2db8f4a5463a3234bc002444e7d9a`
and 33,684 bytes. All 68 relative links resolve from the original experiment
directory. The original unmapped check still fails. The [exact context](context.json)
and [frozen control receipt](receipt.json) retain the provenance.

Sixteen tests run against a private frozen verifier copy cover the valid mapping,
missing targets, changed archive/source-manifest bytes, wrong historical hash or
size, wrong original path, unknown paths/fields, malformed mappings, duplicate
rows, traversal and symlink attempts, and unchanged ordinary-document failures.
Generated fixtures stayed in temporary directories. These controls execute the
production parsing/link helpers; they do not run the operational documentation
gate or claim a verdict on a newly prepared snapshot.

The new private tooling permits only this verifier and the new evidence folder
in addition to the earlier authorized scope. It inserts exactly the reviewed
context after fresh root authorization. Shared RESULTS, historical Markdown,
old snapshot bytes, runtime sources and live replay evidence are untouched.
Candidate and exact documentation gates, independent snapshot review and normal
publication guards remain required before delivery.
