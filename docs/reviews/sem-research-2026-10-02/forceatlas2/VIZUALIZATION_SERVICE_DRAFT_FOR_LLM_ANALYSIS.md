# Early design draft of the vizualization service

## Why?

Anyone who do analytics on graphs would like to see the vizualization. That is clear. There are plenty of solutions at the market like Gephi, but the limit is clear: Gephi cannot handle more than 100k nodes. As well cannot other local solutions. d3.js will probably die at attempt to parse json with 100k lines, etc.

At the same time, ppl who will use Sail have the whole cluster nearby and would be strange not to use it.

## How? 

### TLDR;

Service that can run in-process on driver (and reuse the session) or on the remote host (and talk with sail via Spark Connect). Service itselve <ins>never</ins> hold the graph and should not try any attempt to visualize the whole graph except smallg graphs (less than a fixed threshold, like 30-100k).

Let's imagine we solved anyhow the layout problem on cluster and have a table in the form <vid: long, x: double, y: double> (and maybe optional z: double). Now we can transform it to the quad-tree (for 2d case, or octree for 3d case) without materialization of the tree. Tree stays as table with "level" column. Maybe the "head" of the tree can be materialized.

UI in this case looks the following way:

- each "node" is not the original graph node but a level of the tree
- each "node"' size is proportional to the level's mass
- "nodes" are connected by pseudo-edges, which thickness is porportional to the amount of connections between corresponding levels
- user can zoom-in (for example, by clicking on a node) ---> this op "expands" the whole visualization to the corresponding level
- on "expanding" the service is fetching and caching (with reaosanable cache limit) all the new nodes
- when the mass of expanded level became less than the "small graph threshold" services fetches real nodes and vizualize
- user can zoom-out in the corresponding way

Language of speaking between service and Sail is of course apache arrow.

### Layout

I was thinking about distributed BH-simulations. LLM proposed negative sampling. I do not have a clear answe right now what is the best way. The ultimate goal should be graph with billions of nodes, so the whole flow should be scalable. Still need to be researched.

## Why?

People who run cypher/iso-gql 100% want to see results. But! We do not need to limit themselves to only 100k nodes. As well, the layout itself is important feature. If the graph is slowly changing, it is anough to compute/update the layout once and then serve to many users and their queries.

## P.S.

We build a similar system once in a more primitive way: d3.js on the front, json as a transport, spring boot at backend, my custom implementation of BH and FA2 in plain java. It worked, users were happy. Previous attempt to put "all in d3" literally killed the browser. From what I know, neo4j should do something very similar as well other systems.
