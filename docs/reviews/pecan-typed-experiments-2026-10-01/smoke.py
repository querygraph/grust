"""Exact Linux compatibility checks before the timed WCC experiment."""
from __future__ import annotations

import argparse
import json
import signal
import traceback
from pathlib import Path
from typing import Literal

import pyspark_pecan
import runtime
from pydantic import BaseModel, ConfigDict
from pyspark.sql.connect.client.retries import DefaultPolicy
from pyspark.sql.connect.session import SparkSession
from pyspark_pecan import GraphAlgorithms

BINARY = Path('/targets/sail-compact-host-56194b170155/sail-linux-x86_64-56194b170155-release')
BINARY_SHA = '5b7f506c19afd76a28b84c1459397b4ab30ff4cfc761f4195789425b963facec'


class Options(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')
    repo: Path
    controller_sha: str
    harness_repo: Path
    output: Path
    mode: Literal['local', 'process-cluster']


def deadline(_signal: int, _frame: object) -> None:
    raise TimeoutError('Linux compatibility smoke exceeded 120 seconds')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('repo', 'controller-sha', 'harness-repo', 'output', 'mode'):
        parser.add_argument('--'+name, required=True)
    options = Options.model_validate(vars(parser.parse_args()))
    options.output.mkdir(parents=True, exist_ok=False)
    receipt: dict[str, object] = {'outcome': 'error', 'options': options.model_dump(mode='json')}
    cleanup: list[dict[str, str]] = []
    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(120)
    try:
        assert runtime.git(options.repo, 'rev-parse', 'HEAD') == options.controller_sha
        assert not runtime.git(options.repo, 'status', '--porcelain')
        assert Path(pyspark_pecan.__file__).resolve().is_relative_to(options.repo)
        assert Path(runtime.__file__).resolve().is_relative_to(options.harness_repo)
        assert runtime.sha256(BINARY) == BINARY_SHA
        with runtime.server(BINARY, options.output, options.mode, 2, 2, 128*2**20,
                            cleanup, worker_task_slots=4, sail_pool_bytes=2**30) as (endpoint, _pid):
            spark = SparkSession.builder.remote(endpoint).create()
            spark.client.set_retry_policies([DefaultPolicy(max_retries=1, initial_backoff=100,
                                                          max_backoff=100, jitter=0)])
            try:
                vertices = spark.sql('SELECT CAST(id AS BIGINT) id FROM VALUES (-7),(42),(99),(1099511627776) AS v(id)')
                edges = spark.sql('SELECT CAST(src AS BIGINT) src, CAST(dst AS BIGINT) dst, CAST(weight AS DOUBLE) weight '
                                  'FROM VALUES (-7,42,0.0),(42,99,1.0),(-7,99,1.0) AS e(src,dst,weight)')
                graph = GraphAlgorithms(spark)
                with graph.sssp(vertices, edges, source=-7, method='delta_star', delta=1.,
                                max_iterations=10, partitions=2) as result:
                    rows = sorted(tuple(row) for row in result.frame.select('id', 'distance', 'hops', 'parent').collect())
                    assert rows == [(-7, 0., 0, -7), (42, 0., 1, -7), (99, 1., 1, -7), (1099511627776, None, None, None)]
                    assert result.iterations == 3 and result.converged
                    receipt['sssp'] = {'rows': rows, 'iterations': result.iterations}
                with graph.bfs(vertices, edges, source=-7, method='frontier', max_iterations=10, partitions=2) as result:
                    rows = sorted(tuple(row) for row in result.frame.select('id', 'distance').collect())
                    assert rows == [(-7, 0.), (42, 1.), (99, 1.), (1099511627776, None)]
                    assert result.converged
                    receipt['bfs'] = {'rows': rows, 'iterations': result.iterations}
                with graph.wcc(vertices, edges, method='randomized_fused', max_iterations=32, partitions=2) as result:
                    rows = sorted(tuple(row) for row in result.frame.select('id', 'component').collect())
                    assert rows == [(-7, -7), (42, -7), (99, -7), (1099511627776, 1099511627776)]
                    assert result.converged
                    receipt['wcc'] = {'rows': rows, 'iterations': result.iterations}
            finally:
                spark.stop()
        assert not cleanup
        assert not list((options.output/'staging').rglob('*.parquet'))
        assert runtime.git(options.repo, 'rev-parse', 'HEAD') == options.controller_sha
        assert not runtime.git(options.repo, 'status', '--porcelain')
        assert runtime.sha256(BINARY) == BINARY_SHA
        receipt['outcome'] = 'passed'
    except BaseException:
        receipt['error'] = traceback.format_exc()
    finally:
        signal.alarm(0)
        receipt['cleanup_errors'] = cleanup
        (options.output/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(receipt))
    return 0 if receipt['outcome'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
