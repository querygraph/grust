"""Read already emitted registration lines; no SQL or data warmup action."""
import re

AVAILABLE = re.compile(r"worker (\d+) is available at ")
DATA_JOB = re.compile(r"job (\d+) execution plan")


def registered_ids(log: str) -> set[int]:
    if DATA_JOB.search(log):
        raise ValueError("a dataset job ran before the declared worker readiness boundary")
    return {int(match.group(1)) for match in AVAILABLE.finditer(log)}
