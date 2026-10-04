"""Graph relations compiled entirely to ordinary Spark Connect plans in Sail."""
from pyspark.sql import functions as F


def _column(frame, name):
    return frame["`" + name.replace("`", "``") + "`"]


def _rename(frame, mapping):
    names = frame.columns
    if len(names) != len(set(names)):
        raise ValueError("graph relations require unique column names")
    missing = set(mapping) - set(names)
    if missing:
        raise ValueError(f"graph columns not found: {sorted(missing)}")
    renamed = [mapping.get(name, name) for name in names]
    if len(renamed) != len(set(renamed)):
        raise ValueError("graph column mapping collides with a property column")
    return frame.select(*[_column(frame, name).alias(mapping.get(name, name)) for name in names])


class GraphTables:
    """A directed multigraph backed by ordinary Sail DataFrames.

    Nodes must have unique, non-null IDs, and every non-null edge endpoint must
    reference a node. IDs retain their input type. Duplicate edges and self-loops
    are preserved. Call validate() to check this contract against current data.

    These are lazy table/query references, not an immutable data snapshot. Their
    normal Sail table consistency rules apply at execution. To capture a native
    snapshot explicitly, pass nodes and edges to Nutmeg.stage(). No method here
    constructs CSR or invokes a native extension.
    """

    def __init__(self, nodes, edges, *, node_id="node_id", source="source", target="target"):
        if nodes.sparkSession is not edges.sparkSession:
            raise ValueError("graph tables must belong to the same Spark session")
        if source == target:
            raise ValueError("source and target must identify different columns")
        self.nodes = _rename(nodes, {node_id: "node_id"})
        self.edges = _rename(edges, {source: "source", target: "target"})
        node_type = self.nodes.schema["node_id"].dataType
        if any(self.edges.schema[name].dataType != node_type for name in ("source", "target")):
            raise ValueError("node IDs and edge endpoints must have the same data type")

    def validate(self):
        """Eagerly reject invalid IDs/endpoints; leaves both relations unchanged."""
        nodes, edges = self.nodes, self.edges
        if nodes.filter(nodes.node_id.isNull()).limit(1).count():
            raise ValueError("graph node IDs must not be null")
        if nodes.groupBy("node_id").count().filter(F.col("count") > 1).limit(1).count():
            raise ValueError("graph node IDs must be unique")
        if edges.filter(edges.source.isNull() | edges.target.isNull()).limit(1).count():
            raise ValueError("graph edge endpoints must not be null")
        ids = nodes.select("node_id")
        for endpoint in ("source", "target"):
            if edges.join(ids, edges[endpoint] == ids.node_id, "left_anti").limit(1).count():
                raise ValueError(f"graph {endpoint} endpoint does not reference a node")
        return self

    def _degree(self, endpoint, output):
        counts = self.edges.groupBy(endpoint).count().alias("degree_counts")
        nodes = self.nodes.select("node_id").alias("degree_nodes")
        return nodes.join(counts, nodes.node_id == counts[endpoint], "left").select(
            nodes.node_id.alias("nodeId"),
            F.coalesce(counts["count"], F.lit(0)).cast("long").alias(output),
        )

    def out_degrees(self):
        """Count outgoing edges, including duplicate edges and isolated nodes."""
        return self._degree("source", "outDegree")

    def in_degrees(self):
        """Count incoming edges, including duplicate edges and isolated nodes."""
        return self._degree("target", "inDegree")

    def degrees(self):
        """Return both directed degrees and their sum; a loop contributes two."""
        return self.out_degrees().join(self.in_degrees(), "nodeId").select(
            "nodeId", "outDegree", "inDegree",
            (F.col("outDegree") + F.col("inDegree")).alias("degree"),
        )

    def triplets(self):
        """Return source node, edge and target node structs with all properties."""
        source = self.nodes.alias("triplet_source")
        edge = self.edges.alias("triplet_edge")
        target = self.nodes.alias("triplet_target")
        joined = edge.join(source, edge.source == source.node_id).join(
            target, edge.target == target.node_id
        )
        return joined.select(
            F.struct(*[_column(source, name) for name in source.columns]).alias("src"),
            F.struct(*[_column(edge, name) for name in edge.columns]).alias("edge"),
            F.struct(*[_column(target, name) for name in target.columns]).alias("dst"),
        )

    def walks(self, hops):
        """Return one (source, target) row per fixed-length walk, with multiplicity.

        Vertices/edges may repeat. This is a bounded sequence of joins, not a
        recursive traversal or a simple-path enumeration.
        """
        if isinstance(hops, bool) or not isinstance(hops, int) or hops < 1:
            raise ValueError("hops must be a positive integer")
        result = self.edges.select("source", "target")
        for step in range(1, hops):
            previous = result.alias(f"walk_{step}")
            following = self.edges.select("source", "target").alias(f"edge_{step}")
            result = previous.join(following, previous.target == following.source).select(
                previous.source.alias("source"), following.target.alias("target")
            )
        return result

    def closed_walks(self, hops):
        """Return closed walks, retaining starting-point and edge multiplicity."""
        walks = self.walks(hops)
        return walks.filter(walks.source == walks.target)
