"""Arithmetic behind the size and cost tables of README.md. Pure Python, no Sail.

    python estimates.py > estimates.out

Assumptions, each stated where used:
  |E| = 16 |V| (the Graph500 edge factor), stored in both directions: 2|E| = 32 |V| edge rows.
  Bytes per row: the Parquet sizes measured on cit-Patents (raw/bench-cit-Patents-*.jsonl, file layouts).
"""
import math

SIZES = {"1e6": 1e6, "1e8": 1e8, "1e9": 1e9}
EDGE_FACTOR = 16
B_VK = 26.6      # id, key, x, y; measured 100.5 MB / 3,774,768 rows (vk-sorted, random layout)
B_EK = 14.5      # src_key, dst_key, src, dst sorted by src_key; measured 480.6 MB / 33.04 M rows
B_LEVEL = 64     # cell, mass, sx, sy, xmin, xmax, ymin, ymax as i64/f64 in memory (Arrow)
B_PE = 24        # src_cell, dst_cell, w as i64 in memory (Arrow, measured 28 B per mapped row with dst_level)
B_PE_STORED = 2.3  # PE_l sorted by src_cell, Parquet: measured 1.8 to 2.3 B/row (raw/file-layouts.json)


def gib(x):
    return f"{x / 2**30:,.2f} GiB" if x >= 2**30 else f"{x / 2**20:,.1f} MiB"


def h(title):
    print(f"\n## {title}\n")


h("1. Rows per level and the full level table (uniform worst case: every cell non-empty)")
print("| |V| | levels with 4^l < |V| | rows in levels 0..L* | L* (mean mass >= 16) | bytes, 64 B/row | all levels 0..31 (|V| per level below L*) |")
print("|---|---|---|---|---|---|")
for name, v in SIZES.items():
    lstar = math.floor(math.log(v / 16, 4))
    rows = sum(min(4 ** l, v) for l in range(lstar + 1))
    full = sum(min(4 ** l, v) for l in range(32))
    print(f"| {name} | 0..{math.floor(math.log(v, 4))} | {rows:,.0f} | {lstar} | {gib(rows * B_LEVEL)} | {full:,.0f} rows, {gib(full * B_LEVEL)} |")

h("2. The adaptive head: cells whose parent holds more than T vertices")
print("Uniform layout: internal cells (mass > T) number about (4/3) |V| / T' with T' in [T, 4T);")
print("their children are 4 times that. Upper bound used here: (16/3) |V| / T. Skewed layouts add at most")
print("|V| / T internal cells per extra level of depth.")
print()
print("| |V| | T = 1e3 | T = 1e4 | T = 1e5 | bytes at T = 1e4, 64 B/row |")
print("|---|---|---|---|---|")
for name, v in SIZES.items():
    cells = [16 / 3 * v / t for t in (1e3, 1e4, 1e5)]
    print(f"| {name} | {cells[0]:,.0f} | {cells[1]:,.0f} | {cells[2]:,.0f} | {gib(cells[1] * B_LEVEL)} |")
print("\nCheck against cit-Patents (|V| = 3,774,768), measured adaptive-tree-cells: random 5,509 / 1,365 / 85;"
      " hierarchical 10,156 / 1,177 / 129. Bound: "
      + " / ".join(f"{16 / 3 * 3774768 / t:,.0f}" for t in (1e3, 1e4, 1e5)))

h("3. Pseudo-edge rows per level, random layout (no locality): 16^l (1 - exp(-2|E| / 16^l))")
print("Expected distinct ordered cell pairs when 2|E| directed edge rows fall uniformly on 16^l pairs.")
print()
m = 33037845  # measured ek rows of cit-Patents (both directions, self loops dropped)
print("Check against cit-Patents (2|E| = 33,037,845 rows), measured pe-rows, random layout:")
measured = {2: 256, 4: 65536, 6: 14412661, 8: 32900343, 10: 33036666, 12: 33037845}
for l, got in measured.items():
    pred = 16 ** l * (1 - math.exp(-m / 16 ** l))
    print(f"  level {l:2d}: predicted {pred:14,.0f}  measured {got:14,}")
print()
print("| |V| | 2|E| | " + " | ".join(f"l = {l}" for l in (4, 6, 8, 10, 12)) + " |")
print("|---|---|" + "---|" * 5)
for name, v in SIZES.items():
    e2 = 2 * EDGE_FACTOR * v
    cells = [16 ** l * (1 - math.exp(-e2 / 16 ** l)) for l in (4, 6, 8, 10, 12)]
    print(f"| {name} | {e2:,.0f} | " + " | ".join(f"{c:,.3g}" for c in cells) + " |")
print("\nStored bytes of P_l at 2.3 B/row (sorted Parquet, measured): "
      "1e9, l = 6: " + gib(16 ** 6 * B_PE_STORED) + "; l = 8: " + gib(16 ** 8 * B_PE_STORED))

h("4. Precomputing pseudo-edges: which levels")
print("Rule: precompute P_l for the levels where expanding a typical cell on demand would scan more than")
print("R edge rows. A cell at level l holds |V| / 4^l vertices (uniform) and |V| d / 4^l edge rows, d = 32.")
print("L_p = smallest l with 32 |V| / 4^l <= R. Above L_p, read a precomputed P_(l+1) block.")
print()
print("| |V| | R = 1e6 rows | R = 1e7 rows | R = 1e8 rows |")
print("|---|---|---|---|")
for name, v in SIZES.items():
    row = []
    for r in (1e6, 1e7, 1e8):
        lp = max(0, math.ceil(math.log(32 * v / r, 4)))
        stored = sum(min(16 ** l, 32 * v) for l in range(lp + 2))
        row.append(f"L_p = {lp}, P_0..P_{lp + 1} <= {stored:,.3g} rows ({gib(stored * B_PE_STORED)})")
    print(f"| {name} | " + " | ".join(row) + " |")

h("5. Expand one cell at frontier level l: rows read")
print("Precomputed: P_(l+1) rows whose source is one of the 4 children: at most 4 x (cells at level l+1), and")
print("at most the edge rows of the cell. On demand: every edge row of the cell, |V| d / 4^l (uniform).")
print()
print("| |V| | frontier l | cell mass (uniform) | on-demand rows | on-demand bytes at 14.5 B | precomputed rows, bound |")
print("|---|---|---|---|---|---|")
for name, v in SIZES.items():
    for l in (3, 5, 7, 9):
        mass = v / 4 ** l
        rows = 32 * mass
        bound = min(4 * 4 ** (l + 1), rows)
        print(f"| {name} | {l} | {mass:,.0f} | {rows:,.3g} | {gib(rows * B_EK)} | {bound:,.0f} |")

h("6. Build cost, extrapolated linearly in edge rows from graph500-24 (520,759,040 edge rows), laptop seconds")
G500 = 520_759_040
measured = {"EK build, unsorted (2 joins)": 21.87, "EK build, sorted": 52.52, "PE_8 from EK": 73.95,
            "PE_6 from EK": 11.10, "all PE levels by rollup from PE_10": 104.74}
print("| step | graph500-24, s | 1e8 (3.2e9 rows), core-hours | 1e9 (3.2e10 rows), core-hours |")
print("|---|---|---|---|")
for name, sec in measured.items():
    f8, f9 = 3.2e9 / G500, 3.2e10 / G500
    print(f"| {name} | {sec} | {sec * f8 * 10 / 3600:,.1f} | {sec * f9 * 10 / 3600:,.1f} |")
print("\nCore-hours = laptop seconds x 10 cores x row ratio / 3600. Linear scaling is an assumption; a sort is")
print("n log n and a cluster adds shuffle over the network.")
