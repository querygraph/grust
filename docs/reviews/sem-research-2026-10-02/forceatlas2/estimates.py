"""Back-of-envelope arithmetic for the ForceAtlas2-on-Sail paper study.

Nothing here touches Sail. Part 1 counts quadtree cells on synthetic point
sets (numpy only). Parts 2 to 5 are closed-form size and row estimates.
Run: python3 estimates.py
"""

from __future__ import annotations

import math

import numpy as np

SIZES = (10**6, 10**7, 10**8, 10**9)
MIB = 1024.0 * 1024.0
GIB = 1024.0 * MIB


def human(b: float) -> str:
    if b >= GIB:
        return f"{b / GIB:.1f} GiB"
    return f"{b / MIB:.1f} MiB"


# ---------------------------------------------------------------- part 1
def morton(ix: np.ndarray, iy: np.ndarray, bits: int) -> np.ndarray:
    """Interleave two `bits`-bit integers into one key (x in even bits)."""
    key = np.zeros(ix.shape, dtype=np.uint64)
    for b in range(bits):
        key |= ((ix >> np.uint64(b)) & np.uint64(1)) << np.uint64(2 * b)
        key |= ((iy >> np.uint64(b)) & np.uint64(1)) << np.uint64(2 * b + 1)
    return key


def count_cells(x: np.ndarray, y: np.ndarray, bucket: int, bits: int) -> dict:
    """Region quadtree over the bounding square, split while a cell holds > bucket points.

    Depth is capped at `bits`. Returns internal cells, non-empty leaves, the
    4-slot materialised total (internal * 4 + 1), the compressed-tree internal
    count (internal cells with at least two non-empty children) and the depth.
    """
    lo = min(x.min(), y.min())
    hi = max(x.max(), y.max())
    scale = (2**bits - 1) / (hi - lo)
    ix = ((x - lo) * scale).astype(np.uint64)
    iy = ((y - lo) * scale).astype(np.uint64)
    key = np.sort(morton(ix, iy, bits))
    internal = 0
    compressed_internal = 0
    leaves = 0
    depth = 0
    # A cell at level l is the key prefix of 2*l bits.
    parent_internal = None  # prefixes (level l-1) that are internal
    for level in range(0, bits + 1):
        prefix = key >> np.uint64(2 * (bits - level))
        cells, counts = np.unique(prefix, return_counts=True)
        if level == 0:
            alive = np.ones(cells.shape, dtype=bool)
        else:
            alive = np.isin(cells >> np.uint64(2), parent_internal)
        cells, counts = cells[alive], counts[alive]
        if cells.size == 0:
            break
        split = (counts > bucket) & (level < bits)
        internal += int(split.sum())
        leaves += int((~split).sum())
        if split.any():
            depth = level + 1
        if level > 0:
            # children per internal parent, for the compressed count
            _, kids = np.unique(cells >> np.uint64(2), return_counts=True)
            compressed_internal += int((kids >= 2).sum())
        parent_internal = cells[split]
    return {
        "internal": internal,
        "leaves": leaves,
        "slots": 4 * internal + 1,
        "compressed_internal": compressed_internal,
        "depth": depth,
    }


def point_sets(n: int, rng: np.random.Generator) -> dict:
    out = {}
    out["uniform"] = (rng.random(n), rng.random(n))
    # Clustered: 200 Gaussian blobs, Zipf-like sizes, widths over two decades.
    k = 200
    weights = 1.0 / np.arange(1, k + 1)
    weights /= weights.sum()
    which = rng.choice(k, size=n, p=weights)
    cx, cy = rng.random(k), rng.random(k)
    sigma = 10 ** rng.uniform(-4, -2, size=k)
    out["clustered"] = (cx[which] + rng.normal(size=n) * sigma[which],
                        cy[which] + rng.normal(size=n) * sigma[which])
    # Core plus halo: log-normal radius, a dense centre with a sparse periphery.
    r = np.exp(rng.normal(-4.0, 2.0, size=n))
    phi = rng.uniform(0, 2 * math.pi, size=n)
    out["core-halo"] = (r * np.cos(phi), r * np.sin(phi))
    return out


def part1() -> None:
    print("== Part 1. Quadtree cells per point (simulation, numpy) ==")
    print("n, distribution, bucket, depth cap, internal/n, leaves/n, 4-slot cells/n, "
          "compressed nodes/n, depth")
    rng = np.random.default_rng(20261002)
    for n in (10**5, 10**6):
        sets = point_sets(n, rng)
        for name, (x, y) in sets.items():
            for bucket in (1, 16):
                for bits in (16, 26):
                    c = count_cells(x, y, bucket, bits)
                    compressed = (c["compressed_internal"] + c["leaves"]) / n
                    print(f"{n:>8}, {name:<9}, {bucket:>2}, {bits}, "
                          f"{c['internal'] / n:.3f}, {c['leaves'] / n:.3f}, "
                          f"{c['slots'] / n:.3f}, {compressed:.3f}, {c['depth']}")
    print()


# ---------------------------------------------------------------- part 2
def part2() -> None:
    print("== Part 2. Bytes: tree versus position table ==")
    # Compact cell: centre of mass 2 x f32, mass f32, size f32, first child u32,
    # child mask / leaf count u32 (padded) = 24 B. Wide: f64 fields, u64 index = 48 B.
    cell32, cell64 = 24, 48
    body32, body64 = 12, 24  # x, y, mass
    # State row for the iteration: id i64, x, y, mass, previous force (2 values).
    state32 = 8 + 5 * 4
    state64 = 8 + 5 * 8
    cases = {
        "bucket 1: 0.72 internal cells per point (measured in part 1)": 0.72,
        "bucket 1: 1.0 internal cells per point (bound for a compressed tree)": 1.0,
        "bucket 16: 0.05 internal cells per point (measured in part 1)": 0.05,
    }
    print(f"cell = {cell32} B (f32) or {cell64} B (f64); body = {body32}/{body64} B; "
          f"state row = {state32}/{state64} B")
    for label, per_point in cases.items():
        print(label)
        for n in SIZES:
            cells = per_point * n
            t32 = cells * cell32 + n * body32
            t64 = cells * cell64 + n * body64
            print(f"  |V|={n:.0e}: cells {cells:.2e}; cells+bodies f32 {human(t32)}, "
                  f"f64 {human(t64)}; cells only f32 {human(cells * cell32)}; "
                  f"state table f32 {human(n * state32)}, f64 {human(n * state64)}")
    print("Truncated pyramid (levels 0..L, dense upper bound (4^(L+1)-1)/3 cells, 24 B each):")
    for level in (6, 8, 10, 11, 12):
        cells = (4 ** (level + 1) - 1) // 3
        print(f"  L={level}: {cells:,} cells, {human(cells * cell32)}")
    print()


# ---------------------------------------------------------------- part 3
def part3() -> None:
    print("== Part 3. Reviewer's architecture: bytes moved per iteration ==")
    limit = 128 * MIB
    print("collect up = |V| x 12 B (x, y, mass as f32); "
          "tree down per consumer = cells x 24 B + |V| x 12 B, 0.72 cells per point")
    for n in SIZES:
        up = n * 12
        down = 0.72 * n * 24 + n * 12
        print(f"  |V|={n:.0e}: up {human(up)}; down per consumer {human(down)}; "
              f"x8 workers {human(8 * down)}; x64 tasks {human(64 * down)}; "
              f"fits one 128 MiB message: {'yes' if down <= limit else 'no'}")
    per_vertex = 0.72 * 24 + 12
    print(f"largest |V| whose full tree fits one 128 MiB message: {limit / per_vertex:.2e} "
          f"(at {per_vertex:.1f} B per vertex); positions only (12 B): {limit / 12:.2e}")
    print("coarse grid at level L (dense upper bound 4^L cells x 24 B):")
    for level in (6, 8, 10, 11):
        print(f"  L={level}: {4**level:,} cells, {human(4**level * 24)}")
    print()


# ---------------------------------------------------------------- part 4
def part4() -> None:
    print("== Part 4. Interactions per vertex and rows per iteration ==")
    # Annulus model, uniform density: at each level the accepted cells of side s lie
    # between distance s/theta and 2s/theta, an area of 3*pi*s^2/theta^2.
    # Cells nearer than s/theta are opened: pi*s^2/theta^2, so a level-synchronous
    # relational traversal materialises accepted + opened = 4*pi/theta^2 rows per level.
    for theta in (1.2, 0.5):
        per_level = 3 * math.pi / theta**2
        opened = math.pi / theta**2
        print(f"Barnes-Hut annulus model, theta={theta}: {per_level:.1f} accepted and "
              f"{opened:.1f} opened cells per level")
        for n in SIZES:
            levels = math.log(n, 4)
            print(f"  |V|={n:.0e}: {levels:.1f} levels, about {per_level * levels:.0f} "
                  f"cell interactions per vertex; as join rows {(per_level + opened) * levels:.0f}")
    edge_factor = 16  # edges per vertex, Graph500 convention; messages go both ways
    attraction = 2 * edge_factor
    print(f"attraction rows per vertex = 2|E|/|V| = {attraction} at |E| = {edge_factor}|V|")
    for bucket in (16, 64):
        print(f"relational multilevel grid, leaf bucket {bucket}:")
        for n in SIZES:
            levels = max(0.0, math.log(n / bucket, 4) - 1)  # levels 2..leaf
            far_point_cell = 27 * levels          # vertex joins each interaction-list cell
            near = 9 * bucket                     # upper bound: 3x3 full leaf cells
            cells = (4 / 3) * n / bucket
            far_cell_cell = 27 * cells / n        # cells join their interaction lists
            ancestors = levels                    # vertex joins its own ancestors
            print(f"  |V|={n:.0e}: levels {levels:.1f}; point-cell far {far_point_cell:.0f}, "
                  f"near {near} rows per vertex, total {far_point_cell + near:.0f} "
                  f"({(far_point_cell + near) / attraction:.1f}x attraction); "
                  f"cell-cell variant {far_cell_cell + ancestors + near:.0f} rows per vertex "
                  f"({(far_cell_cell + ancestors + near) / attraction:.1f}x)")
    print("sampling: M negatives per vertex per iteration = M rows per vertex; "
          "M=5 is 5/32 of the attraction rows")
    print()


# ---------------------------------------------------------------- part 5
def part5() -> None:
    print("== Part 5. Attraction shuffle versus tree traffic, bytes per iteration ==")
    edge_factor = 16
    msg = 8 + 8  # destination id i64 + force 2 x f32
    for n in SIZES:
        shuffle = 2 * edge_factor * n * msg
        tree = 0.72 * n * 24 + n * 12
        print(f"  |V|={n:.0e}: attraction messages {human(shuffle)}; "
              f"tree to one consumer {human(tree)} ({tree / shuffle:.1%}); "
              f"collect {human(12 * n)} ({12 * n / shuffle:.1%})")
    print()


if __name__ == "__main__":
    part1()
    part2()
    part3()
    part4()
    part5()
