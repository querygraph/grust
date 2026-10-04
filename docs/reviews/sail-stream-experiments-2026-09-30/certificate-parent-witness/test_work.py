"""Matched actual-SQL work counters, not elapsed time or distributed jobs."""
import json
import os
import pytest
from test_baseline import frames, spark


@pytest.mark.parametrize('case',['depth0','depth1','depth2','depth4','depth8','distance_only','cap_fallback'])
def test_matched_certificate_work(spark,tmp_path,monkeypatch,record_property,case):
    from traversal_certificate import certify
    from pyspark_pecan import GraphAlgorithms
    from pyspark_pecan.staging import StagingRun
    from pyspark.sql.connect.client.core import SparkConnectClient
    variant=os.environ['CERTIFICATE_WITNESS_VARIANT']
    assert variant in ('baseline','candidate')
    depth=int(case.removeprefix('depth')) if case.startswith('depth') else 4
    distances=[float(i) for i in range(depth+1)]+[None]
    parents=[0]+list(range(depth))+[None]
    hops=list(range(depth+1))+[None]
    edges=[(i,i+1,1.) for i in range(depth)]
    cap=10000
    if case=='cap_fallback':
        distances=[0.,0.,0.];parents=[0,0,1];hops=[0,1,2]
        edges=[(0,1,0.),(1,2,0.),(0,2,0.)];cap=1
    v,e,a=frames(spark,tmp_path,distances,parents,hops,edges)
    if case=='distance_only':a=a.select('id','distance')
    counters=dict(graph_runs=0,materializations=0,execute_plan_iterator_calls=0)
    def wrap(cls,name,key):
        original=getattr(cls,name)
        def count(*args,**kwargs):
            counters[key]+=1
            return original(*args,**kwargs)
        monkeypatch.setattr(cls,name,count)
    wrap(GraphAlgorithms,'_run','graph_runs')
    wrap(StagingRun,'materialize','materializations')
    wrap(SparkConnectClient,'_execute_and_fetch_as_iterator','execute_plan_iterator_calls')
    proof=certify(spark,a,v,e,source=0,weighted=True,partitions=2,max_rounds=cap)
    fast=variant=='candidate' and case not in ('distance_only','cap_fallback')
    assert counters['graph_runs']==(0 if fast else 1)
    if fast:
        assert counters['materializations']==0
        assert proof['witness_method']=='parent_hops' and proof['witness_rounds'] is None
        assert proof['parent_witness_max_hops']==depth
    else:
        assert counters['materializations']>=3
        assert proof['witness_rounds']==(1 if case=='cap_fallback' else depth)
    record_property('witness_work',json.dumps(dict(variant=variant,case=case,vertices=len(distances),
        counters=counters,proof=proof,scope='certify only; local client ExecutePlan iterator calls and Pecan staging calls, excluding input fixture construction, schema/config RPCs, existing subsequent parent validator, retries/worker task counts/timing'),sort_keys=True))
