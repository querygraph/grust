"""Content identity for installed native wheels and immutable manifest options."""
import hashlib
import json


def identity(entry, manifest):
    digest = hashlib.sha256()
    digest.update(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode())
    files = entry.dist.files
    if not files:
        raise ValueError("native extension needs an installed wheel file manifest")
    count = 0
    for relative in sorted(files, key=str):
        name = str(relative)
        if ".dist-info/" in name or "__pycache__/" in name or name.endswith(".pyc"):
            continue
        path = entry.dist.locate_file(relative)
        if not path.is_file():
            raise ValueError(f"native extension package file missing: {relative}")
        digest.update(name.encode() + b"\0")
        with path.open("rb") as stream:
            digest.update(hashlib.file_digest(stream, "sha256").digest())
        count += 1
    if count == 0:
        raise ValueError("native extension wheel contains no package files")
    return f"{manifest['name']}@{manifest['version']}:{digest.hexdigest()}"
