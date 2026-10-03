"""Footer facts of every table the benchmark wrote: files, row groups, bytes, whether each file is sorted
by its key, and the key span of a row group as a fraction of the table's key range.

    python file_layouts.py > raw/file-layouts.json

It replaces the "layout-vk-*" records of the bench-*.jsonl files written before the fix of
2026-10-03 12:12, which read the statistics of column 0 (`id`) instead of `key`.
"""
import glob, json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import numpy as np, pyarrow.parquet as pq
from vizserver import SCRATCH

KEYS = {"vk": "key", "ek": "src_key", "levels": "cell", "pe": "src_cell"}
out = {}
for table in sorted(glob.glob(str(SCRATCH / "*" / "*" / "*"))) + sorted(glob.glob(str(SCRATCH / "*" / "*" / "*" / "level=*"))):
    path = pathlib.Path(table)
    files = sorted(path.glob("*.parquet"))
    kind = next((k for k in KEYS if path.name.startswith(k) or path.parent.name.startswith(k)), None)
    if not files or kind is None:
        continue
    column, ranges, sorted_files, rows = KEYS[kind], [], 0, 0
    for f in files:
        pf = pq.ParquetFile(f)
        md = pf.metadata
        rows += md.num_rows
        index = md.schema.to_arrow_schema().get_field_index(column)
        for g in range(md.num_row_groups):
            st = md.row_group(g).column(index).statistics
            ranges.append((st.min, st.max))
        values = pf.read(columns=[column])[column].to_numpy()
        sorted_files += bool((np.diff(values) >= 0).all())
    total = (max(r[1] for r in ranges) - min(r[0] for r in ranges)) or 1
    spans = sorted((r[1] - r[0]) / total for r in ranges)
    out[str(path.relative_to(SCRATCH))] = {
        "rows": rows, "files": len(files), "files_sorted_by_key": sorted_files, "row_groups": len(ranges),
        "bytes": sum(f.stat().st_size for f in files), "bytes_per_row": round(sum(f.stat().st_size for f in files) / max(rows, 1), 2),
        "row_group_key_span_median": round(spans[len(spans) // 2], 6), "row_group_key_span_max": round(spans[-1], 6)}
print(json.dumps(out, indent=1))
