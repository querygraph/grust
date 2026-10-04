"""Refuting unchanged/candidate SQL control of preconditions in the old _run."""
import pytest
from test_baseline import frames, spark


@pytest.mark.parametrize('case',['partitions0','partitions_bool','partitions_float',
                                  'vertices_int32','edges_int32','duplicate_names'])
def test_original_run_preconditions_remain_enforced(spark,tmp_path,case):
    from pyspark.sql.connect import functions as F
    from traversal_certificate import certify
    v,e,a=frames(spark,tmp_path,[0.,1.,2.],[0,0,1],[0,1,2],[(0,1,1.),(1,2,1.)])
    partitions=2;message='partitions'
    if case=='partitions0':partitions=0
    if case=='partitions_bool':partitions=True
    if case=='partitions_float':partitions=1.5
    if case=='vertices_int32':v=v.select(F.col('id').cast('int').alias('id'));message='BIGINT'
    if case=='edges_int32':e=e.select(F.col('src').cast('int').alias('src'),'dst','weight');message='BIGINT'
    if case=='duplicate_names':v=v.select('id',F.lit(1).alias('extra'),F.lit(2).alias('extra'));message='unique column'
    with pytest.raises(ValueError,match=message):
        certify(spark,a,v,e,source=0,weighted=True,partitions=partitions)
