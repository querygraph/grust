"""Markdown tables from the raw benchmark records.

    python summarize.py raw/bench-local.jsonl [raw/bench-scale-unbounded.jsonl ...]
"""
import collections, json, statistics, sys


def yes(values):
    values = list(values)
    if not values or values[0] is None:
        return ""
    good = sum(bool(v) for v in values)
    return "yes" if good == len(values) else ("no" if good == 0 else f"{good} of {len(values)}")


for path in sys.argv[1:]:
    records = [json.loads(line) for line in open(path)]
    host = next(r for r in records if r["record"] == "host")
    runs = collections.OrderedDict()
    for r in records:
        if r["record"] == "run":
            runs.setdefault(r["case"], []).append(r)
    print(f"\n#### `{path}`\n")
    print("settings:", json.dumps({k: v for k, v in host["settings"].items() if "CHECKPOINT" not in k}),
          "| rows:", host.get("rows", host.get("vertices")), "| edges:", host.get("edges", ""), "\n")
    print("| case | runs | wall s, median | wall s, range | server CPU s, median | exact 0..n-1 | dense follows id order "
          "| files in order | each file in order | same result in every run |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for case, rs in runs.items():
        ok = [r for r in rs if r["ok"]]
        if not ok:
            print(f"| `{case}` | {len(rs)} | failed: {rs[0].get('error')} {rs[0].get('message', '')[:120]} |||||||")
            continue
        wall = [r["wall_seconds"] for r in ok]
        cpu = [r["server_cpu_seconds"] for r in ok]
        exact = [r.get("dense_is_0_to_n_minus_1", r.get("matches_reference")) for r in ok]
        fingerprints = {r.get("fingerprint", r.get("last_offset")) for r in ok}
        failed = f" ({len(rs) - len(ok)} failed)" if len(ok) != len(rs) else ""
        print(f"| `{case}` | {len(ok)}{failed} | {statistics.median(wall):.2f} | {min(wall):.2f} to {max(wall):.2f} "
              f"| {statistics.median(cpu):.2f} | {yes(exact)} | {yes(r.get('dense_follows_id_order') for r in ok)} "
              f"| {yes(r.get('files_sorted') for r in ok)} | {yes(r.get('each_file_sorted') for r in ok)} "
              f"| {'yes' if len(fingerprints) == 1 else 'no: ' + str(len(fingerprints)) + ' results'} |")
