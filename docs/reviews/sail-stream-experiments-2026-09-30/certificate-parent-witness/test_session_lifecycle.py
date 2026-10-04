"""Refuting control for a stopped Connect session finalized after a new one."""
import gc
import json
import os
import weakref


def test_late_old_session_finalization(record_property):
    from pyspark.sql.connect.session import SparkSession
    from pyspark.sql.connect.client.reattach import ExecutePlanResponseReattachableIterator as Iterator
    endpoint=os.environ['SAIL_GRAPH_TEST_REMOTE']
    old=SparkSession.builder.remote(endpoint).create()
    assert old.sql('SELECT 1 AS value').collect()[0].value==1
    old.stop()
    current=SparkSession.builder.remote(endpoint).create()
    try:
        assert current.sql('SELECT 2 AS value').collect()[0].value==2
        pool=Iterator._release_thread_pool_instance
        assert pool is not None and not pool._shutdown
        submit=pool.submit
        reference=weakref.ref(old)
        del old
        collected=gc.collect()
        observation=dict(old_finalized=reference() is None,gc_collected=collected,
                         previously_selected_pool_shutdown=pool._shutdown,
                         global_pool_reset=Iterator._release_thread_pool_instance is None)
        # This call represents an already selected executor, not a SQL query.
        try:
            submit(lambda:1).result()
            observation['selected_submit']='accepted'
        except RuntimeError as error:
            observation['selected_submit']=str(error)
        assert current.sql('SELECT 3 AS value').collect()[0].value==3
        observation['subsequent_fresh_query']='passed'
        print('SESSION_LIFECYCLE',json.dumps(observation,sort_keys=True))
        record_property('session_lifecycle',json.dumps(observation,sort_keys=True))
        assert observation['old_finalized']
        assert observation['previously_selected_pool_shutdown']
        assert observation['global_pool_reset']
        assert observation['selected_submit']=='cannot schedule new futures after shutdown'
    finally:
        current.stop()
