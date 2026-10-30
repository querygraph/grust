"""Generate tiny foreign ORCs for listing inference; no Spark/JVM is started."""

import hashlib
import json
import platform
from pathlib import Path

import pyarrow as pa
import pyarrow.orc as orc

root = Path(__file__).resolve().parent
report = {
    "generator": "pyarrow.orc.write_table",
    "python_version": platform.python_version(),
    "pyarrow_version": pa.__version__,
    "files": [],
}
for filename, names in [
    ("nested_upper.orc", ["Value"]),
    ("nested_lower.orc", ["value"]),
    ("nested_duplicate.orc", ["Value", "value"]),
]:
    path = root / filename
    if path.exists():
        raise FileExistsError(path)
    fields = [pa.field(name, pa.int64(), nullable=True) for name in names]
    children = [pa.array([index + 1], type=pa.int64()) for index in range(len(names))]
    table = pa.table({"s": pa.StructArray.from_arrays(children, fields=fields)})
    orc.write_table(table, path)
    actual = orc.ORCFile(path).read()
    assert actual.equals(table, check_metadata=True), (actual, table)
    report["files"].append({
        "path": filename,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
        "schema": str(actual.schema),
        "rows": actual.to_pylist(),
    })
report["generator_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
(root / "reference.json").write_text(json.dumps(report, indent=2) + "\n")
