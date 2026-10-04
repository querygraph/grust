#!/usr/bin/env python3
"""Content/package checks. Visual PDF inspection remains a separate required gate."""
import argparse
import json
import re
import subprocess
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

from assemble import HERE, SOURCES, chapter_prefix, configure, load_manifest, nodes, pandoc_ast, sha, stem


def normalized(value):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value).replace("\u200b", ""))


def verify_content():
    dist = HERE / "dist"
    text = (dist / f"{stem()}.md").read_text()
    parsed = pandoc_ast(text)
    headers = list(nodes(parsed, "Header"))
    ids = [h[1][0] for h in headers]
    assert len(ids) == len(set(ids)), "duplicate assembled anchor"
    top = [h[1][0] for h in headers if h[0] == 1]
    expected = [chapter_prefix(p, i) for i, p in enumerate(SOURCES)]
    assert top == expected, (top, expected)
    for _, _, (url, _) in nodes(parsed, "Link"):
        target = urlsplit(url)
        if not target.scheme:
            assert not target.path and unquote(target.fragment) in ids, f"broken internal link: {url}"
        else:
            assert target.scheme in ("https", "http", "mailto"), url
    overview = pandoc_ast((HERE / ("manuscript.md" if HERE.name == "extensions-host-review" else "overview.md")).read_text())
    if HERE.name == "extensions-review":
        assert len(list(nodes(overview, "Table"))) >= 2, "both overview tables must survive parsing"
    manifest = load_manifest()
    codes = list(nodes(parsed, "CodeBlock"))
    assert all(attrs[1] for attrs, _ in codes), "code fence without a language"
    for row in manifest["files"]:
        if not row["printed"]:
            continue
        body = (HERE / row["local_path"]).read_text().removesuffix("\n")
        matches = [code for attrs, code in codes if code == body and row["language"] in attrs[1]]
        assert matches, f"listing is not complete and byte-equivalent: {row['id']}"
    assembly = json.loads((dist / "assembly.json").read_text())
    assert assembly["manuscript_sha256"] == sha(text.encode())
    for row, source in zip(assembly["sources"], SOURCES, strict=True):
        assert row["sha256"] == sha(source.read_bytes()), f"source changed: {source}"
    assert assembly["manifest_sha256"] == sha((HERE / "code/manifest.json").read_bytes())
    return {"chapters": len(top), "headings": len(ids), "code_blocks": len(codes),
            "printed_listings": assembly["printed_listings"], "overview_tables": len(list(nodes(overview, "Table")))}


def verify_epub(path, manifest):
    with zipfile.ZipFile(path) as book:
        assert book.testzip() is None
        assert book.namelist()[0] == "mimetype"
        assert book.read("mimetype") == b"application/epub+zip"
        assert len(book.namelist()) == len(set(book.namelist()))
        docs = {}
        for name in book.namelist():
            assert not name.startswith("/") and ".." not in PurePosixPath(name).parts
            if name.endswith((".xml", ".opf", ".ncx", ".xhtml")):
                docs[name] = ET.fromstring(book.read(name))
        nav = [root for root in docs.values() if any(e.tag.endswith("}nav") for e in root.iter())]
        assert nav, "EPUB lacks navigation document"
        links = 0
        for name, root in docs.items():
            for elem in root.iter():
                url = elem.attrib.get("href", elem.attrib.get("src"))
                if not url or urlsplit(url).scheme:
                    continue
                split = urlsplit(url)
                import posixpath
                file = posixpath.normpath(posixpath.join(posixpath.dirname(name), unquote(split.path))) if split.path else name
                assert file in book.namelist(), (name, url)
                if split.fragment and file in docs:
                    assert unquote(split.fragment) in {e.attrib.get("id") for e in docs[file].iter()}, (name, url)
                links += 1
        css = "\n".join(book.read(n).decode() for n in book.namelist() if n.endswith(".css"))
        for required in ("pre-wrap", "overflow-wrap: anywhere", "break-inside: auto", "code span.kw"):
            assert required in css, f"missing EPUB code treatment: {required}"
        pres = ["".join(e.itertext()).removesuffix("\n") for root in docs.values()
                for e in root.iter() if e.tag.endswith("}pre")]
        for row in manifest["files"]:
            if row["printed"]:
                expected = (HERE / row["local_path"]).read_text().removesuffix("\n")
                assert expected in pres, f"EPUB listing differs: {row['id']}"
        return {"zip_members": len(book.namelist()), "xml_documents": len(docs), "local_links": links}


def verify_pdf(path, manifest):
    text = subprocess.check_output(["pdftotext", "-layout", str(path), "-"], text=True)
    compact = normalized(text)
    missing = []
    for row in manifest["files"]:
        if row["printed"]:
            for number, line in enumerate((HERE / row["local_path"]).read_text().splitlines(), 1):
                token = normalized(line)
                if len(token) > 4 and token not in compact:
                    missing.append([row["id"], number, line[:100]])
    assert not missing, f"PDF code text missing/truncated: {missing[:12]} ({len(missing)} total)"
    info = subprocess.check_output(["pdfinfo", str(path)], text=True)
    pages = int(re.search(r"^Pages:\s+(\d+)", info, re.M)[1])
    assert pages > 0 and "Sail Extensions" in text
    return {"pages": pages, "code_lines_missing": len(missing), "visual_review": "required_separately"}


def main():
    global HERE, SOURCES
    parser = argparse.ArgumentParser()
    parser.add_argument("--book-root", type=Path, default=HERE)
    parser.add_argument("--artifacts", action="store_true")
    args = parser.parse_args()
    HERE, SOURCES = configure(args.book_root)
    result = {"generated_at": datetime.now(timezone.utc).isoformat(), "content": verify_content()}
    if args.artifacts:
        manifest = load_manifest()
        dist = HERE / "dist"
        result["epub"] = verify_epub(dist / f"{stem()}.epub", manifest)
        result["pdf"] = verify_pdf(dist / f"{stem()}.pdf", manifest)
        result["artifacts"] = {p.name: sha(p.read_bytes()) for p in [
            dist / f"{stem()}.pdf", dist / f"{stem()}.epub",
            dist / f"{stem()}.md",
        ]}
        (dist / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
