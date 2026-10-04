#!/usr/bin/env python3
"""Assemble the review without rewriting any fenced code bytes."""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TARGET = "bd8ce9ae8839477e2c08a0475ab7900b115c5366"
MODULES = [
    "01-discovery", "02-functions", "03-relations", "04-commands",
    "05-placement", "06-memory", "07-lifecycle", "08-compatibility",
]
SOURCES = [ROOT / "docs/EXTENSIONS-ONE-PAGER.md", HERE / "overview.md"] + [
    HERE / "modules" / f"{name}.md" for name in MODULES
] + [HERE / "code-listings.md"]
READER = "markdown-smart"


def configure(book_root):
    global HERE, ROOT, SOURCES
    HERE = Path(book_root).resolve()
    ROOT = HERE.parents[1]
    if HERE.name == "extensions-host-review":
        SOURCES = [HERE / "manuscript.md", HERE / "host-code-listings.md"]
    elif HERE.name != "extensions-review":
        raise ValueError(f"unknown review layout: {HERE}")
    return HERE, SOURCES


def chapter_prefix(path, index):
    if HERE.name == "extensions-host-review":
        return "host-overview" if index == 0 else "host-code-listings"
    return ("introduction" if index == 0 else
            "module-" + path.stem if path.parent.name == "modules" else path.stem)


def stem():
    return "sail-extensions-host-review" if HERE.name == "extensions-host-review" else "sail-extensions-review"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pandoc_ast(text):
    return json.loads(subprocess.check_output(
        ["pandoc", "--from", READER, "--to", "json"], input=text.encode()
    ))


def nodes(value, kind):
    if isinstance(value, dict):
        if value.get("t") == kind:
            yield value["c"]
        for child in value.values():
            yield from nodes(child, kind)
    elif isinstance(value, list):
        for child in value:
            yield from nodes(child, kind)


def outside_fences(lines):
    fence = None
    for line in lines:
        match = re.match(r"^\s{0,3}(`{3,}|~{3,})(.*)$", line)
        if match:
            token, rest = match.groups()
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence) and not rest.strip():
                fence = None
            yield line, False
        else:
            yield line, fence is None
    if fence is not None:
        raise ValueError("unclosed code fence")


def load_manifest():
    manifest = json.loads((HERE / "code/manifest.json").read_text())
    assert manifest["schema_version"] == 1
    assert manifest["repository"] == "querygraph/sail"
    assert manifest["source_commit"] == TARGET
    ids = set()
    for row in manifest["files"]:
        assert row["id"] not in ids, "duplicate listing id"
        ids.add(row["id"])
        path = HERE / row["local_path"]
        assert not path.is_symlink() and path.resolve().is_relative_to(HERE)
        data = path.read_bytes()
        assert sha(data) == row["sha256"] and len(data) == row["bytes"], path
        assert len(data.splitlines()) == row["lines"], path
        data.decode("utf-8")
        assert type(row["printed"]) is bool
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--book-root", type=Path, default=HERE)
    args = parser.parse_args()
    configure(args.book_root)
    manifest = load_manifest()
    documents, anchors, headings = {}, {}, {}
    for index, path in enumerate(SOURCES):
        text = path.read_text()
        assert "\r" not in text, f"noncanonical newline in {path}"
        parsed = pandoc_ast(text)
        hs = list(nodes(parsed, "Header"))
        assert hs and hs[0][0] == 1, f"missing chapter title: {path}"
        prefix = chapter_prefix(path, index)
        ids = {}
        for n, (_, attributes, _) in enumerate(hs):
            old = attributes[0]
            new = prefix if n == 0 else f"{prefix}--{old}"
            assert old not in ids, f"duplicate heading id in {path}: {old}"
            ids[old] = new
            anchors[(path, old)] = new
        anchors[(path, "")] = prefix
        headings[path] = ids
        documents[path] = (text, hs)

    # Printed source links point to the appendix, not to a network checkout.
    listing_anchors = {}
    appendix = SOURCES[-1]
    for row in manifest["files"]:
        if row["printed"]:
            assert (appendix, row["id"]) in anchors, f"missing listing heading {row['id']}"
            listing_anchors[row["source_path"]] = anchors[(appendix, row["id"])]
            listing_anchors[row["local_path"]] = anchors[(appendix, row["id"])]

    def target(current, value):
        url = urlsplit(value)
        decoded = unquote(url.path)
        if not url.scheme or (TARGET in decoded and HERE.name == "extensions-review"):
            for source, anchor in listing_anchors.items():
                if decoded == source or decoded.endswith("/" + source):
                    return "#" + anchor
        if url.scheme or url.netloc:
            return value
        file = (current.parent / decoded).resolve() if decoded else current
        key = (file, unquote(url.fragment))
        if key not in anchors:
            # Companion chapters remain external to this EPUB, with an explicit
            # review-branch destination, never a broken relative file URL.
            cross_book = (file.is_relative_to(ROOT / "docs/extensions-host-review")
                          if HERE.name == "extensions-review" else
                          file.is_relative_to(ROOT / "docs/extensions-review")
                          or file == ROOT / "docs/EXTENSIONS-ONE-PAGER.md")
            if cross_book and file.suffix == ".md" and file.is_file():
                return ("https://github.com/querygraph/grust/blob/work/extensions-review-guide/"
                        + str(file.relative_to(ROOT))
                        + ("#" + url.fragment if url.fragment else ""))
            raise ValueError(f"unresolved book link in {current.relative_to(ROOT)}: {value}")
        return "#" + anchors[key]

    chunks = []
    for path, (text, hs) in documents.items():
        heading_index = 0
        output = []
        for line, ordinary in outside_fences(text.splitlines(keepends=True)):
            if ordinary and re.match(r"^#{1,6}\s", line):
                old = hs[heading_index][1][0]
                heading_index += 1
                # Authored headings may provide an explicit id, but no other attributes.
                line = re.sub(r"\s+\{#[^}]+\}\s*$", "", line.rstrip())
                line = line.rstrip() + " {#" + headings[path][old] + "}\n"
            if ordinary:
                line = re.sub(
                    r"(?<!!)\[([^\]\n]+)\]\(([^\s)]+)\)",
                    lambda m: f"[{m[1]}]({target(path, m[2])})", line,
                )
            output.append(line)
        assert heading_index == len(hs), f"unsupported heading syntax: {path}"
        chunks.append("".join(output).rstrip() + "\n")
    manuscript = "\n\n".join(chunks)
    dist = HERE / "dist"
    dist.mkdir(exist_ok=True)
    output = dist / f"{stem()}.md"
    output.write_text(manuscript)
    receipt = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "review_target": TARGET,
        "manuscript_sha256": sha(output.read_bytes()),
        "sources": [{"path": str(p.relative_to(ROOT)), "sha256": sha(p.read_bytes())}
                    for p in SOURCES],
        "manifest_sha256": sha((HERE / "code/manifest.json").read_bytes()),
        "chapter_anchors": [anchors[(p, "")] for p in SOURCES],
        "printed_listings": sum(r["printed"] for r in manifest["files"]),
        "source_links_remapped": listing_anchors,
    }
    (dist / "assembly.json").write_text(json.dumps(receipt, indent=2) + "\n")
    subprocess.run([sys.executable, str(Path(__file__).with_name("verify.py")),
                    "--book-root", str(HERE)], check=True)


if __name__ == "__main__":
    main()
