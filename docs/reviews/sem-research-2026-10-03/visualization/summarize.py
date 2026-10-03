"""Print the README timing tables from raw/bench-*.jsonl and raw/flight-*.jsonl.

    python summarize.py > raw/summary.txt
"""
import glob, json, pathlib

here = pathlib.Path(__file__).parent
rows = {}
for f in sorted(glob.glob(str(here / "raw" / "bench-*.jsonl"))) + sorted(glob.glob(str(here / "raw" / "flight-*.jsonl"))):
    for line in open(f):
        r = json.loads(line)
        rows[(r["graph"], r["layout"], r["measure"])] = r


def cell(r):
    if r is None:
        return "n/a"
    if "skipped" in r:
        return "skipped"
    return f"{r['median']:.3f} ({r['min']:.3f} to {r['max']:.3f})"


def out(r):
    res = r.get("result") if r else None
    if isinstance(res, dict) and "rows" in res:
        return f"{res['rows']:,} rows, {res['arrow_bytes'] / 1024:,.0f} KiB"
    if isinstance(res, dict) and "pseudo_edges" in res:
        return f"{res['cells']['rows']:,} cells + {res['pseudo_edges']['rows']:,} pseudo-edges, {(res['cells']['arrow_bytes'] + res['pseudo_edges']['arrow_bytes']) / 2**20:,.1f} MiB"
    if isinstance(res, int):
        return f"{res:,} rows"
    return ""


cases = sorted({(g, l) for g, l, _ in rows})
measures = []
for (g, l, m) in rows:
    if m not in measures and "median" in rows[(g, l, m)] or "skipped" in rows[(g, l, m)]:
        if m not in measures:
            measures.append(m)
print("| measure | " + " | ".join(f"{g} {l}" for g, l in cases) + " |")
print("|---|" + "---|" * len(cases))
for m in measures:
    print(f"| {m} | " + " | ".join(cell(rows.get((g, l, m))) + (f"<br>{out(rows.get((g, l, m)))}" if out(rows.get((g, l, m))) else "")
                                    for g, l in cases) + " |")
print()
for (g, l, m), r in rows.items():
    if "median" not in r and m not in ("start", "done") and "skipped" not in r:
        print(f"{g} {l} {m}: {json.dumps(r.get('result'))}")
