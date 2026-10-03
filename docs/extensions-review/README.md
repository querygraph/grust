# Building the two review guides

For a new design review, start at the versioned
[SAIL-EXTENSIONS-REVIEW-REQUEST.md](https://github.com/querygraph/sail/blob/sail-extensions/docs/development/extensions/SAIL-EXTENSIONS-REVIEW-REQUEST.md).
The editions described below remain reference books for their original source
pin; current review targets and the separately tested loader candidate are
identified by that entrypoint.

These source-owned configs use the central FirstPair builder. They do not
change or publish the Grust book, its catalog identity or library deployment.
The review target is Sail `bd8ce9ae8839477e2c08a0475ab7900b115c5366`;
the document edition is 1.0. No runtime qualification is performed here.

From the repository root, build both guides:

```bash
bash docs/extensions-review/build.sh
```

Use `--main` or `--host` to build one. The script delegates to
`~/src/firstpair/publishing/scripts/build-library-book.sh --repo-root … --config …`.
Set `FIRSTPAIR_ROOT` only when that central checkout lives elsewhere. See
[the repository contract](../../FIRSTPAIR.md) for FirstPair ownership and
publishing rules. A build is local and does not publish anything.

The source hooks require Python 3.12 with its working standard-library XML
parser. No Python packages are needed by those hooks. This explicit interpreter
also avoids a known incompatible system Python/Expat installation on the
authoring machine; the initial failed attempt is retained in the build evidence.

The main guide assembles the short introduction, overview, all eight modules
and complete sample listings. Its companion assembles the host comparison and
historical patch listings. The resulting `dist/` directories each contain the
standalone Markdown, PDF, EPUB, HTML, assembly and validation receipts; source
bundles supplied by the author are preserved. Code remains byte-identical to
the pinned manifest. The PDF uses 8.4-point code and muted per-listing line
numbers for citation; wrapped continuations receive no additional number.
For extracted examples and patches these are listing lines, not original
repository-file line numbers. The PDF adds invisible line-break opportunities
for long tokens; the Markdown and EPUB retain the original code bytes.

All within-book chapter and printed-source links become internal anchors.
Cross-book Markdown references target the `work/extensions-review-guide`
branch in Grust. Provenance links to a different Sail revision remain external;
they never silently point to the prototype's patch instead.

`assemble.py` rejects missing chapters, unknown local links and unclosed fences.
`verify.py` checks chapter order, both main overview tables, code languages and
manifest bytes; artifact checks validate EPUB ZIP/XML, local links, wrapping
CSS and every printed code block, then search extracted PDF text for every
nontrivial code line. The central builder also runs its standard package checks.
These checks complement, but cannot replace, visual PDF review for clipped
lines, overlapping text, table layout and page breaks.

For a content-only check after assembly:

```bash
python3.12 docs/extensions-review/verify.py
python3.12 docs/extensions-review/verify.py --book-root docs/extensions-host-review
```

Add `--artifacts` to check rendered outputs. Before delivery, render selected
pages with `pdftoppm`, including both overview tables and the start, middle and
end of long code listings. Inspect every page as a contact sheet and inspect
any suspicious page at readable resolution. Retain visual QA separately from
the automated verification receipt; neither is a benchmark execution verdict.
