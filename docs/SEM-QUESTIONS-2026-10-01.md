<!-- Provenance: opened by Sem Sinchenko as querygraph/sail pull request #31
     (commit f94f96a39746b7c59e5817fb9dc3ddd05b55377c, 2026-10-01, file
     docs/development/extensions/sem-questions-2026-10-01.md). Moved here
     verbatim because documents of this review live in grust, not in a Sail
     tree. Answers and status are tracked in SEM-REVIEW-2.md. -->

# What I want to check

## unnest / explode versus `unionByName`

In vanilla Spark the following is better:

```scala
        val msgDF: DataFrame = tripletsDF
          .select(explode(array(sendMsgsColList: _*)).as("msg"))
          .select(col("msg.id"), col("msg.msg").as(Pregel.MSG_COL_NAME))
          .filter(Pregel.msg.isNotNull)
```

In vanilla DataFusion I found on my benchmarks, that this one is better:

```rust
            let messages_df = messages
                .iter()
                .map(|(name, message)| {
                    triplets.clone().select(vec![
                        message.clone().field(VERTEX_ID).alias(VERTEX_ID),
                        message
                            .clone()
                            .field(*name)
                            .alias(format!("{}_{}", PREGEL_MSG, name)),
                    ])
                })
                .reduce(|a, b| match (a, b) {
                    (Ok(adf), Ok(bdf)) => adf.union_by_name(bdf),
                    _ => Err(datafusion::error::DataFusionError::Plan(
                        "Error in Pregel algorithm".to_string(),
                    )),
                })
                .ok_or(datafusion::error::DataFusionError::Plan(
                    "generated messages_df is None".to_string(),
                ))??;
```

I found that *vanilla* DataFusion spent more on array building while columnar scans looks cheaper.

**Question:** what about Sail? I would like to see numbers, because this pattern is common.

## how to force sail to skip sort & repartition if we write edges *in specific way*?

I see some numbers from 16M rows tests that shows, that write amplification is costly and it was rejected. I would like to raise this question again.

1. Even if the writing the new pregel state per iteration will be x3 more expensive, it may still make sense to still do so, because vertices in graphs are **always** less than edges and most often **order of magnitude** less. If we pay 5 more seconds per write but save 15 seconds on shuffle (in the case of HJ) or shuffle+sort (in the case of SMJ) it is a clear win, isn't it?
2. 16M does not sound serious. I'm afraid we are measuring here the Sail's planning/serde machinery overhead (that is obviously bigger than with plain write)
3. As an alternative scenario would be nice to check something like `vortex` that is promising better performance (if sail supports it)


# How I see the Pecan

If we are talking about the pure "graph on relations" (that in my opinion the only thing that make sense on Sail), it should be Pregel no questions. Wise people made GraphX and it is a piece of engineering art and source of knowledge. As well, PageRank (Personalized PageRank), Power Iteration Clustering, FastRP, Label Propagation, HyperANF-like, K-Core, Rocha-Thatte, SSSP (MSSP), and a lot of other are expressed in Pregel.

It is much easier to write, read and maintain when we have one optimized low-level routine and implementations on top.

Please, try to implement a **proper** Pregel. Use the best you can find from GraphX Pregel, GraphFrames Pregel, graphframes-rs Pregel because they are bringing different optimizations. Try to find the best fit for Sail.

**Just as a crazy idea** --- have Pregel as a low-level rust-sail extension with PySpark API exposed (similar to what GraphFrames do via py4j). Not sure if it is feasible, but at least worst to think about it.


Two algorithms: PageRank and SSSP. Both are perfect fit for Pregel and will show it peak perfromanceof the abstraction itself (CDLP, KCore and friends are much more tricky and require own microbenchmarks of expressions, better to postpone). PageRank shows the shrinking frontier and simple sum with full support of partial agg, SSSP shows the growing frontier with passing single column.

Without pre-sorting edges optimization, performance will be bad. But! We can consider not only parquet checkpointing but the GraphFrames style with "persist". We should consider multiple options and that is exactly the reason we need the Pregel abstraction: analyze plans, take a chain and run propagation in microbenchmarks, implement pagerank and run on cit-Patents / kgs / wiki-Talks from LDBC. I'm not so deep expert in Sail to say how exactly should it be implemented but when we implement itright we will get "out of the box" around 10 algorithms almost "for free" + a user facing API that allows ppl write own.

## Note about WCC

Start from clear re-implemnentation of what exists in graphframes-rs. Cool thing is it does not rely on pre-sorting edges, so *in theory* we should see something like *same perf class*. As well WCC is one of the most important algorithms in the world of the "big data graphs": right now people are forced to run WCC as part of the Entity Resolution at hundred billion scale using Spark GraphFrames. If Sail can do the same better it is already a big win.

Follow the code that exists, achieve the *same perfromance* class or understand what are blockers and why Sail cannot be as performant as DataFusion on a single node. When we have *same class*, we can go distributed, we can run profiling and have all the fun. But at first we need to achieve the parity with manual written DataFusion code or understand what blocks us from achieving the parity.
