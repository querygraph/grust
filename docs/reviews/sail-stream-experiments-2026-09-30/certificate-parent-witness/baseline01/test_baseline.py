"""Actual-SQL controls of unchanged fc094a certificate acceptance boundaries."""
import os
import pytest


@pytest.fixture(scope='module')
def spark():
    from pyspark.sql.connect.session import SparkSession
    session=SparkSession.builder.remote(os.environ['SAIL_GRAPH_TEST_REMOTE']).create()
    yield session
    session.stop()


def frames(spark, distances, parents, hops, edges):
    vertices=spark.createDataFrame([(i,) for i in range(len(distances))],'id long')
    actual=spark.createDataFrame([(i,d,p,h) for i,(d,p,h) in enumerate(zip(distances,parents,hops))],
                                 'id long,distance double,parent long,hops long')
    edge_frame=spark.createDataFrame(edges,'src long,dst long,weight double')
    return vertices,edge_frame,actual


def parent_check(spark,tmp_path,actual,edges):
    from traversal_cell import validate_parents
    edges.write.mode('error').parquet((tmp_path/'edges.parquet').as_uri())
    return validate_parents(spark,actual,tmp_path,'sssp',actual.count(),0,True,False)


def test_supplied_parent_depth_above_cap_does_not_reject_shorter_tight_path(spark,tmp_path):
    from traversal_certificate import certify
    v,e,a=frames(spark,[0.,0.,0.],[0,0,1],[0,1,2],[(0,1,0.),(1,2,0.),(0,2,0.)])
    proof=certify(spark,a,v,e,source=0,weighted=True,max_rounds=1,partitions=2)
    assert proof['witness_rounds']==1
    assert parent_check(spark,tmp_path,a,e)


def test_certificate_tolerance_does_not_replace_stricter_parent_predicate(spark,tmp_path):
    from traversal_certificate import certify
    v,e,a=frames(spark,[0.,1.,2.+4e-12],[0,0,1],[0,1,2],[(0,1,1.),(1,2,1.)])
    assert certify(spark,a,v,e,source=0,weighted=True,tolerance=1e-12,partitions=2)['reached']==3
    with pytest.raises(AssertionError,match='invalid parent edge'):
        parent_check(spark,tmp_path,a,e)


@pytest.mark.parametrize('parents,hops', [([0,None,1],[0,1,2]),([0,0,1],[0,None,2]),([0,99,1],[0,1,2])])
def test_null_or_missing_parent_metadata_is_not_silently_proved(spark,tmp_path,parents,hops):
    from traversal_certificate import certify
    v,e,a=frames(spark,[0.,1.,2.],parents,hops,[(0,1,1.),(1,2,1.)])
    assert certify(spark,a,v,e,source=0,weighted=True,partitions=2)['reached']==3
    with pytest.raises(AssertionError,match='invalid rooted parent chain'):
        parent_check(spark,tmp_path,a,e)


def test_distance_only_native_keeps_bfs_witness_and_optional_parent_contract(spark,tmp_path):
    from traversal_certificate import certify
    from traversal_cell import validate_parents
    v,e,a=frames(spark,[0.,1.,2.],[0,0,1],[0,1,2],[(0,1,1.),(1,2,1.)])
    a=a.select('id','distance')
    assert certify(spark,a,v,e,source=0,weighted=True,partitions=2)['witness_rounds']==2
    assert validate_parents(spark,a,tmp_path,'sssp',3,0,True,True) is False
    with pytest.raises(AssertionError,match='portable traversal'):
        validate_parents(spark,a,tmp_path,'sssp',3,0,True,False)
