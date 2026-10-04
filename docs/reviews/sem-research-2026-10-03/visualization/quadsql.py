"""Quadtree-as-a-table expressions for PySpark Connect on Sail. Ids and keys are BIGINT (i64).

Contract (see README.md section 2):
  key(v)          = Morton interleave of (qx, qy), qx, qy in [0, 2^LMAX), qx on the even bits.
  cell_l(v)       = key(v) >> 2*(LMAX - l)            # level l, 0 <= l <= LMAX
  children of c   = 4c .. 4c+3 at level l+1
  vertices of c   = key in [c << 2*(LMAX-l), (c+1) << 2*(LMAX-l))
"""
from pyspark.sql.connect import functions as F

LMAX = 31          # 31 bits per axis, a 62-bit key, non-negative in i64
UNIT = 2 ** 53     # hash -> [0, 1) with 53 bits


def unit(col_or_name, seed):
    """A deterministic pseudo-uniform double in [0, 1) from xxhash64(col, seed)."""
    return (F.xxhash64(col_or_name, F.lit(seed)).bitwiseAND(F.lit(UNIT - 1))).cast("double") / F.lit(float(UNIT))


_MASKS = [(16, 0x0000FFFF0000FFFF), (8, 0x00FF00FF00FF00FF), (4, 0x0F0F0F0F0F0F0F0F),
          (2, 0x3333333333333333), (1, 0x5555555555555555)]


def with_key(frame, xmin, ymin, side, lmax=LMAX):
    """Add `key`: quantize (x, y) into a square box of `side` at (xmin, ymin), interleave the bits.

    Done as a chain of projections so that no expression is duplicated."""
    top = 2 ** lmax - 1
    scale = (2 ** lmax) / side
    q = lambda c, lo: F.least(F.greatest(F.floor((F.col(c) - F.lit(lo)) * F.lit(scale)).cast("bigint"),
                                         F.lit(0).cast("bigint")), F.lit(top).cast("bigint"))
    f = frame.withColumn("_a", q("x", xmin)).withColumn("_b", q("y", ymin))
    for shift, mask in _MASKS:
        f = f.withColumn("_a", F.col("_a").bitwiseOR(F.shiftleft("_a", shift)).bitwiseAND(F.lit(mask)))
        f = f.withColumn("_b", F.col("_b").bitwiseOR(F.shiftleft("_b", shift)).bitwiseAND(F.lit(mask)))
    return f.withColumn("key", F.col("_a").bitwiseOR(F.shiftleft("_b", 1))).drop("_a", "_b")


def shift(level, lmax=LMAX):
    return 2 * (lmax - level)


def cell(col_name, level, lmax=LMAX):
    return F.shiftright(F.col(col_name), shift(level, lmax))


def key_range(c, level, lmax=LMAX):
    """[lo, hi) of vertex keys inside cell c of `level`."""
    s = shift(level, lmax)
    return c << s, (c + 1) << s


LEVEL_AGGS = [F.count(F.lit(1)).alias("mass"), F.sum("x").alias("sx"), F.sum("y").alias("sy"),
              F.min("x").alias("xmin"), F.max("x").alias("xmax"), F.min("y").alias("ymin"), F.max("y").alias("ymax")]
ROLLUP_AGGS = [F.sum("mass").alias("mass"), F.sum("sx").alias("sx"), F.sum("sy").alias("sy"),
               F.min("xmin").alias("xmin"), F.max("xmax").alias("xmax"), F.min("ymin").alias("ymin"),
               F.max("ymax").alias("ymax")]
