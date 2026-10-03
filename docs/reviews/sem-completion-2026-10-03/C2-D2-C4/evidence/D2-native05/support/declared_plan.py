"""Inspect actual executed join subtrees; no filename/layout inference."""
import re

import probe_models as m


class JoinProof(m.Model):
    job_id: int
    sort_merge_join_observed: bool
    join_input_hash_exchanges: int
    join_runtime_sorts: int
    join_stage_partitions: int
    declared_checkpoint_reuse: bool


def inspect(raw: str, action: str, partitions: int) -> JoinProof:
    plans = list(re.finditer(r"job (\d+) execution plan\n(.*?)(?=^\[|\Z)", raw,
                           re.MULTILINE | re.DOTALL))
    if len(plans) != 1:
        raise ValueError("exactly one executed workload plan required")
    job_id = int(plans[0].group(1))
    lines = plans[0].group(2).splitlines()
    joins = [index for index, line in enumerate(lines)
             if re.search(r"\bSortMergeJoin(?:Exec)?:", line)]
    if len(joins) != 1 or any("HashJoinExec:" in line for line in lines):
        raise ValueError("actual single sort-merge join required")
    index = joins[0]
    indent = len(lines[index]) - len(lines[index].lstrip())
    subtree = []
    for line in lines[index + 1:]:
        if not line.strip() or len(line) - len(line.lstrip()) <= indent:
            break
        subtree.append(line)
    if not subtree or any("CoalescePartitionsExec" in line for line in subtree):
        raise ValueError("join input subtree absent or collected to one partition")
    exchanges = [line for line in subtree if "RepartitionExec:" in line]
    if any("partitioning=Hash(" not in line for line in exchanges):
        raise ValueError("unexpected join input exchange kind")
    if action.startswith("round-path-path-"):
        expected = 2
    elif action.startswith("round-checkpoint-path-"):
        expected = 1
    elif action.startswith("round-checkpoint-checkpoint-"):
        expected = 0
    else:
        raise ValueError("unrecognized round contrast")
    if len(exchanges) != expected:
        raise ValueError(f"actual join input hash exchanges {len(exchanges)} != {expected}")
    graph = re.search(rf"job {job_id} job graph\s*\n(.*?)(?=^\[|\Z)", raw,
                      re.MULTILINE | re.DOTALL)
    if graph is None:
        raise ValueError("actual job graph missing")
    stages = re.split(r"=== stage \d+ ===", graph.group(1))
    selected = [stage for stage in stages if re.search(r"\bSortMergeJoin(?:Exec)?:", stage)]
    if len(selected) != 1 or "placement=Worker" not in selected[0]:
        raise ValueError("actual worker join stage missing")
    count = re.search(r"^partitions=(\d+)$", selected[0], re.MULTILINE)
    if count is None or int(count.group(1)) != partitions:
        raise ValueError("actual join stage partition count differs")
    return JoinProof(job_id=job_id, sort_merge_join_observed=True,
        join_input_hash_exchanges=len(exchanges),
        join_runtime_sorts=sum("SortExec:" in line for line in subtree),
        join_stage_partitions=partitions, declared_checkpoint_reuse=expected == 0)
