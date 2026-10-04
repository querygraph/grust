"""Bucketed all-edge stepping (delta-star), with a bounded client controller.

Unlike classical light/heavy delta-stepping, every selected vertex relaxes all
outgoing edges. Pending vertices stay server-side. Bucket closure occurs by
reselecting the minimum pending bucket until it is empty. This is deliberately
named delta_star, not classical delta-stepping or Dijkstra.
"""
import math
from pyspark.sql.connect import functions as F

from .algorithms import ConvergenceError


def execute(graph, run, vertices, adjacency, size, source, delta, limit):
    if isinstance(delta, bool) or not isinstance(delta, (int, float)) or not math.isfinite(delta) or delta <= 0:
        raise ValueError("delta must be positive and finite")
    path, state = run.materialize(vertices.where(F.col('id') == source).select(
        'id', F.lit(0.).alias('distance'), F.lit(0).cast('long').alias('hops'), F.col('id').alias('parent')))
    pending_path, pending = path, state
    for step in range(1, limit + 1):
        run.cancellation.check()
        bucket = pending.agg(F.min(F.floor(F.col('distance') / delta))).first()[0]
        if bucket is None:
            result_path, result = run.materialize(vertices.join(state, 'id', 'left'), expected_rows=size)
            return run.finish(result_path, result, algorithm='sssp-delta-star', iterations=step-1, converged=True)
        if not math.isfinite(bucket):
            raise OverflowError('distance/delta bucket overflow; choose a larger delta')
        active = pending.where(F.floor(F.col('distance') / delta) == bucket)
        # Frontier on the left: the partitioned hash join builds on its left input.
        candidates = active.join(adjacency, active.id == adjacency.src).select(
            adjacency.dst.alias('id'), (active.distance + adjacency.weight).alias('distance'),
            (active.hops + 1).alias('hops'), active.id.alias('parent'))
        relaxed = state.unionByName(candidates).groupBy('id').agg(
            F.min(F.struct('distance', 'hops', 'parent')).alias('best')).select('id', 'best.*')
        graph._observe(run, 'sssp-delta-star', step, 'iteration_start', bucket=bucket, plan_of=relaxed)
        if candidates.where(F.col('distance') == float('inf')).limit(1).count():
            raise OverflowError('shortest-path distance overflow')
        next_path, updated = run.materialize(relaxed)
        if updated.where(F.col('distance') == float('inf')).limit(1).count():
            raise OverflowError('shortest-path distance overflow')
        before = state.select('id', F.struct('distance', 'hops', 'parent').alias('before'))
        changed = updated.join(before, 'id', 'left').where(
            F.col('before').isNull() | (F.struct('distance','hops','parent') != F.col('before'))
        ).select('id','distance','hops','parent')
        # Remove processed and superseded records before adding improved labels.
        remaining = pending.join(active.select('id'), 'id', 'left_anti').join(
            changed.select('id'), 'id', 'left_anti')
        next_pending_path, next_pending = run.materialize(remaining.unionByName(changed))
        for obsolete in {path, pending_path}:
            run.remove(obsolete)
        path, state = next_path, updated
        pending_path, pending = next_pending_path, next_pending
        graph._observe(run, 'sssp-delta-star', step, 'iteration_end', bucket=bucket)
    # Certify completion even when the last allowed expansion emptied the queue.
    if pending.limit(1).count():
        raise ConvergenceError(f'sssp-delta-star did not converge in {limit} iterations')
    result_path, result = run.materialize(vertices.join(state, 'id', 'left'), expected_rows=size)
    return run.finish(result_path, result, algorithm='sssp-delta-star', iterations=limit, converged=True)
