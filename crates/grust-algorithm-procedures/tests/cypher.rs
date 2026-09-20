use grust_algorithm_procedures::register_algorithms;
use grust_core::{Edge, Graph, Node, Props, Value};
use grust_cypher::{CypherParameters, run_read_query_with_registry};
use grust_procedures::{ProcedureRegistry, RegistryBuilder, register_builtins};

fn registry() -> ProcedureRegistry {
    let mut builder = RegistryBuilder::default();
    register_builtins(&mut builder).unwrap();
    register_algorithms(&mut builder).unwrap();
    builder.build()
}

fn graph() -> Graph {
    Graph::new(
        ["a", "b", "c", "isolate"]
            .map(|id| Node::new("N", id, Props::new()))
            .into(),
        vec![
            Edge::new("R", "a", "b", [("cost".into(), Value::Float(2.0))]),
            Edge::new("R", "b", "c", [("cost".into(), Value::Float(0.5))]),
            Edge::new("R", "c", "b", [("cost".into(), Value::Float(0.0))]),
        ],
    )
}

fn run(query: &str) -> Vec<Vec<Value>> {
    run_read_query_with_registry(
        &graph(),
        "default",
        query,
        &CypherParameters::new(),
        &registry(),
    )
    .unwrap()
    .rows
}

#[test]
fn direct_kernels_are_reachable_through_ordinary_cypher() {
    assert_eq!(
        run("CALL grust.algorithms.bfs('a') YIELD nodeId, distance RETURN nodeId, distance"),
        vec![
            vec![Value::String("a".into()), Value::Float(0.0)],
            vec![Value::String("b".into()), Value::Float(1.0)],
            vec![Value::String("c".into()), Value::Float(2.0)],
            vec![Value::String("isolate".into()), Value::Null],
        ]
    );
    assert_eq!(
        run(
            "CALL grust.algorithms.dijkstra('a', {weightProperty: 'cost'}) YIELD nodeId, distance WHERE nodeId = 'c' RETURN distance"
        ),
        vec![vec![Value::Float(2.5)]]
    );
    assert_eq!(
        run("CALL grust.algorithms.wcc() YIELD nodeId, componentId RETURN componentId"),
        vec![
            vec![Value::String("a".into())],
            vec![Value::String("a".into())],
            vec![Value::String("a".into())],
            vec![Value::String("isolate".into())]
        ]
    );
    assert_eq!(
        run("CALL grust.algorithms.scc() YIELD nodeId, componentId RETURN componentId"),
        vec![
            vec![Value::String("a".into())],
            vec![Value::String("b".into())],
            vec![Value::String("b".into())],
            vec![Value::String("isolate".into())]
        ]
    );
    let rank = run(
        "CALL grust.algorithms.pagerank() YIELD score, converged RETURN sum(score), collect(converged)",
    );
    assert!(matches!(rank[0][0], Value::Float(value) if (value - 1.0).abs() < 1e-10));
}

#[test]
fn full_paths_use_normal_yield_unwind_and_aggregation() {
    assert_eq!(
        run(
            "CALL grust.algorithms.shortestPaths('a', {weightProperty: 'cost'}) YIELD nodeIds, costs, edgeOrdinals RETURN nodeIds, costs, edgeOrdinals"
        ),
        vec![
            vec![
                Value::StringArray(vec!["a".into()]),
                Value::FloatArray(vec![0.0]),
                Value::IntArray(vec![])
            ],
            vec![
                Value::StringArray(vec!["a".into(), "b".into()]),
                Value::FloatArray(vec![0.0, 2.0]),
                Value::IntArray(vec![0])
            ],
            vec![
                Value::StringArray(vec!["a".into(), "b".into(), "c".into()]),
                Value::FloatArray(vec![0.0, 2.0, 2.5]),
                Value::IntArray(vec![0, 1])
            ],
        ]
    );
    assert_eq!(
        run(
            "CALL grust.algorithms.shortestPaths('a', {weightProperty: 'cost'}) YIELD costs UNWIND costs AS cost RETURN count(cost), sum(cost)"
        ),
        vec![vec![Value::Int(6), Value::Float(6.5)]]
    );
}

#[test]
fn correlation_and_unknown_configuration_follow_registry_rules() {
    assert_eq!(
        run(
            "UNWIND ['a', 'c'] AS source CALL grust.algorithms.bfs(source) YIELD nodeId, distance WHERE nodeId = 'b' RETURN source, distance"
        ),
        vec![
            vec![Value::String("a".into()), Value::Float(1.0)],
            vec![Value::String("c".into()), Value::Float(1.0)]
        ]
    );
    for query in [
        "CALL grust.algorithms.bfs('a', {bogus: 1}) YIELD distance RETURN distance",
        "CALL grust.algorithms.bfs('missing') YIELD distance RETURN distance",
        "CALL grust.algorithms.bfs('a', {orientation: 'sideways'}) YIELD distance RETURN distance",
        "CALL grust.algorithms.bfs('a', {defaultWeight: 1.0}) YIELD distance RETURN distance",
    ] {
        assert!(
            run_read_query_with_registry(
                &graph(),
                "default",
                query,
                &CypherParameters::new(),
                &registry()
            )
            .is_err()
        );
    }
}

#[test]
fn option_arrays_use_declared_types_and_empty_selection_is_explicit() {
    assert_eq!(
        run("CALL grust.algorithms.wcc({nodeLabels: []}) YIELD nodeId RETURN count(nodeId)"),
        vec![vec![Value::Int(0)]]
    );
    let scores = run(
        "CALL grust.algorithms.pagerank({damping: 0.0, personalization: [1, 0, 0, 0]}) YIELD score RETURN score",
    );
    assert_eq!(
        scores,
        vec![
            vec![Value::Float(1.0)],
            vec![Value::Float(0.0)],
            vec![Value::Float(0.0)],
            vec![Value::Float(0.0)]
        ]
    );
    assert!(run_read_query_with_registry(&graph(), "default", "CALL grust.algorithms.pagerank({personalization: [9223372036854775807, 0, 0, 0]}) YIELD score RETURN score", &CypherParameters::new(), &registry()).is_err());
}

#[test]
fn catalog_expansion_uses_the_same_registration_and_execution_contracts() {
    assert_eq!(
        run("CALL grust.algorithms.dfs('a') YIELD nodeId RETURN nodeId"),
        vec![
            vec![Value::String("a".into())],
            vec![Value::String("b".into())],
            vec![Value::String("c".into())]
        ]
    );
    assert_eq!(
        run("CALL grust.algorithms.multiSourceBfs(['a', 'c']) YIELD distance RETURN distance"),
        vec![
            vec![Value::Float(0.0)],
            vec![Value::Float(1.0)],
            vec![Value::Float(0.0)],
            vec![Value::Null]
        ]
    );
    let topology = run(
        "CALL grust.algorithms.topologicalSort() YIELD acyclic, nodeIds, cycleNodeIds RETURN acyclic, nodeIds, cycleNodeIds",
    );
    assert_eq!(
        topology,
        vec![vec![
            Value::Bool(false),
            Value::StringArray(vec![]),
            Value::StringArray(vec!["b".into(), "c".into(), "b".into()])
        ]]
    );
}

#[test]
fn projection_inspection_and_csr_estimates_disclose_their_scope() {
    let word = size_of::<usize>() as i64;
    assert_eq!(
        run(
            "CALL grust.algorithms.projectionStats({orientation: 'undirected'}) YIELD nodes, edges, arcs, selfLoops, csrBytes RETURN nodes, edges, arcs, selfLoops, csrBytes"
        ),
        vec![vec![
            Value::Int(4),
            Value::Int(3),
            Value::Int(6),
            Value::Int(0),
            Value::Int(17 * word)
        ]]
    );
    assert_eq!(
        run(
            "CALL grust.algorithms.estimateCsr({orientation: 'undirected', nodeLabels: []}) YIELD nodesUpperBound, edgesUpperBound, maxArcs, outgoingCsrBytes, reverseCsrBytes, positionsBytes RETURN nodesUpperBound, edgesUpperBound, maxArcs, outgoingCsrBytes, reverseCsrBytes, positionsBytes"
        ),
        vec![vec![
            Value::Int(4),
            Value::Int(3),
            Value::Int(6),
            Value::Int(17 * word),
            Value::Int(11 * word),
            Value::Int(4 * word)
        ]]
    );
    assert_eq!(
        run(
            "CALL grust.algorithms.projectionStats({nodeLabels: []}) YIELD nodes, edges, arcs RETURN nodes, edges, arcs"
        ),
        vec![vec![Value::Int(0), Value::Int(0), Value::Int(0)]]
    );
    assert!(
        grust_algorithms::CsrEstimate::upper_bound(
            usize::MAX,
            0,
            grust_algorithms::Orientation::Outgoing,
            false
        )
        .is_err()
    );
}

#[test]
fn degree_counts_and_strengths_use_projection_orientation() {
    assert_eq!(
        run(
            "CALL grust.algorithms.degree() YIELD nodeId, degree, strength RETURN degree, strength"
        ),
        vec![
            vec![Value::Int(1), Value::Null],
            vec![Value::Int(1), Value::Null],
            vec![Value::Int(1), Value::Null],
            vec![Value::Int(0), Value::Null]
        ]
    );
    assert_eq!(
        run(
            "CALL grust.algorithms.degree({orientation: 'incoming', weightProperty: 'cost'}) YIELD nodeId, degree, strength RETURN degree, strength"
        ),
        vec![
            vec![Value::Int(0), Value::Float(0.0)],
            vec![Value::Int(2), Value::Float(2.0)],
            vec![Value::Int(1), Value::Float(0.5)],
            vec![Value::Int(0), Value::Float(0.0)]
        ]
    );
}

#[test]
fn k_core_is_an_ordinary_procedure_with_explicit_orientation() {
    // The fixture's b<->c pair is two edges, so undirected b and c form a
    // 2-core; a hangs off it, and the isolate has core 0.
    assert_eq!(
        run(
            "CALL grust.algorithms.kCore({orientation: 'undirected'}) YIELD nodeId, coreValue, degeneracy RETURN nodeId, coreValue, degeneracy"
        ),
        vec![
            vec![Value::String("a".into()), Value::Int(1), Value::Int(2)],
            vec![Value::String("b".into()), Value::Int(2), Value::Int(2)],
            vec![Value::String("c".into()), Value::Int(2), Value::Int(2)],
            vec![
                Value::String("isolate".into()),
                Value::Int(0),
                Value::Int(2)
            ],
        ]
    );
    // Aggregation over the result is ordinary Cypher.
    assert_eq!(
        run(
            "CALL grust.algorithms.kCore({orientation: 'undirected'}) YIELD coreValue RETURN max(coreValue), count(coreValue)"
        ),
        vec![vec![Value::Int(2), Value::Int(4)]]
    );
}

#[test]
fn triangles_and_clustering_are_ordinary_procedures_on_the_simple_graph() {
    // Undirected, the fixture is the path a-b-c with b-c doubled: no triangle,
    // and the doubled edge does not invent one.
    assert_eq!(
        run(
            "CALL grust.algorithms.triangleCount({orientation: 'undirected'}) YIELD nodeId, triangles, triangleCount RETURN nodeId, triangles, triangleCount"
        ),
        vec![
            vec![Value::String("a".into()), Value::Int(0), Value::Int(0)],
            vec![Value::String("b".into()), Value::Int(0), Value::Int(0)],
            vec![Value::String("c".into()), Value::Int(0), Value::Int(0)],
            vec![
                Value::String("isolate".into()),
                Value::Int(0),
                Value::Int(0)
            ],
        ]
    );
    // b has two distinct neighbours and no triangle: coefficient 0. The others
    // have fewer than two neighbours: no coefficient, which is null, not 0.
    assert_eq!(
        run(
            "CALL grust.algorithms.localClusteringCoefficient({orientation: 'undirected'}) YIELD nodeId, coefficient RETURN nodeId, coefficient"
        ),
        vec![
            vec![Value::String("a".into()), Value::Null],
            vec![Value::String("b".into()), Value::Float(0.0)],
            vec![Value::String("c".into()), Value::Null],
            vec![Value::String("isolate".into()), Value::Null],
        ]
    );
    // maxDegree 1 leaves b out: -1 triangles, no coefficient.
    assert_eq!(
        run(
            "CALL grust.algorithms.triangleCount({orientation: 'undirected', maxDegree: 1}) YIELD nodeId, triangles RETURN nodeId, triangles"
        )[1],
        vec![Value::String("b".into()), Value::Int(-1)]
    );
}

#[test]
fn louvain_is_an_ordinary_procedure_in_every_orientation() {
    // Undirected, the fixture is a-b with b-c doubled: the heavy pair b,c is one
    // community and a joins it or not by modularity; the isolate stays alone.
    let rows = run(
        "CALL grust.algorithms.louvain({orientation: 'undirected'}) YIELD nodeId, communityId, modularity, converged RETURN nodeId, communityId, modularity, converged",
    );
    assert_eq!(rows.len(), 4);
    assert_eq!(rows[1][1], rows[2][1], "b and c share a community");
    assert_eq!(rows[3][1], Value::String("isolate".into()));
    assert!(rows.iter().all(|row| row[3] == Value::Bool(true)));
    // The default orientation is directed: Leicht-Newman modularity, not an error.
    let directed =
        run("CALL grust.algorithms.louvain() YIELD communityId RETURN count(communityId)");
    assert_eq!(directed, vec![vec![Value::Int(4)]]);
    // Options are named and typed; a huge resolution leaves every node alone.
    assert_eq!(
        run(
            "CALL grust.algorithms.louvain({orientation: 'undirected', resolution: 1000000.0, seed: 7}) YIELD nodeId, communityId WHERE nodeId <> communityId RETURN count(nodeId)"
        ),
        vec![vec![Value::Int(0)]]
    );
}

#[test]
fn betweenness_is_an_ordinary_procedure_exact_or_sampled() {
    // a-b, b-c doubled, and an isolate: only b lies between two other nodes.
    let expected = vec![
        vec![Value::String("a".into()), Value::Float(0.0)],
        vec![Value::String("b".into()), Value::Float(1.0)],
        vec![Value::String("c".into()), Value::Float(0.0)],
        vec![Value::String("isolate".into()), Value::Float(0.0)],
    ];
    let query = |options: &str| {
        run(&format!(
            "CALL grust.algorithms.betweenness({options}) YIELD nodeId, score RETURN nodeId, score"
        ))
    };
    assert_eq!(query("{orientation: 'undirected'}"), expected);
    // A sample of every node is the exact answer.
    assert_eq!(
        query("{orientation: 'undirected', samplingSize: 4, seed: 3}"),
        expected
    );
    // One pair of three possible: a-c, normalised by (n-1)(n-2)/2 = 3.
    assert_eq!(
        query("{orientation: 'undirected', normalized: true}")[1][1],
        Value::Float(1.0 / 3.0)
    );
    assert!(
        run_read_query_with_registry(
            &graph(),
            "default",
            "CALL grust.algorithms.betweenness({samplingSize: 0}) YIELD score RETURN score",
            &CypherParameters::new(),
            &registry(),
        )
        .is_err()
    );
}

#[test]
fn closeness_and_harmonic_are_ordinary_procedures() {
    // Undirected a-b-c plus an isolate, so n-1 = 3.
    let scores = |call: &str| {
        run(&format!(
            "CALL grust.algorithms.{call} YIELD nodeId, score RETURN nodeId, score"
        ))
        .into_iter()
        .map(|row| row[1].clone())
        .collect::<Vec<_>>()
    };
    let floats = |values: [f64; 4]| values.map(Value::Float).to_vec();
    assert_eq!(
        scores("closeness({orientation: 'undirected'})"),
        floats([2.0 / 3.0, 1.0, 2.0 / 3.0, 0.0])
    );
    assert_eq!(
        scores("closeness({orientation: 'undirected', useWassermanFaust: true})"),
        floats([4.0 / 9.0, 2.0 / 3.0, 4.0 / 9.0, 0.0])
    );
    assert_eq!(
        scores("harmonic({orientation: 'undirected', normalized: false})"),
        floats([1.5, 2.0, 1.5, 0.0])
    );
    assert_eq!(
        scores("harmonic({orientation: 'undirected'})"),
        floats([0.5, 2.0 / 3.0, 0.5, 0.0])
    );
}

#[test]
fn label_propagation_is_an_ordinary_procedure() {
    let rows = run(
        "CALL grust.algorithms.labelPropagation({orientation: 'undirected', maxIterations: 20, seed: 5}) YIELD nodeId, communityId, iterations, converged RETURN nodeId, communityId, converged",
    );
    // a-b-c is one connected piece and ends as one community; the isolate is its own.
    let community = |row: usize| rows[row][1].clone();
    assert_eq!(community(0), community(1));
    assert_eq!(community(1), community(2));
    assert_eq!(community(3), Value::String("isolate".into()));
    assert!(rows.iter().all(|row| row[2] == Value::Bool(true)));
    // Directed by default, and still an answer rather than an error.
    assert_eq!(
        run("CALL grust.algorithms.labelPropagation() YIELD communityId RETURN count(communityId)"),
        vec![vec![Value::Int(4)]]
    );
}

#[test]
fn node_similarity_returns_pair_rows_through_ordinary_cypher() {
    // Undirected a-b-c: a and c share their only neighbour, b.
    let pairs = vec![
        vec![
            Value::String("a".into()),
            Value::String("c".into()),
            Value::Float(1.0),
        ],
        vec![
            Value::String("c".into()),
            Value::String("a".into()),
            Value::Float(1.0),
        ],
    ];
    assert_eq!(
        run(
            "CALL grust.algorithms.nodeSimilarity({orientation: 'undirected'}) YIELD node1, node2, similarity RETURN node1, node2, similarity"
        ),
        pairs
    );
    assert_eq!(
        run(
            "CALL grust.algorithms.nodeSimilarity({orientation: 'undirected', metric: 'cosine', topN: 1}) YIELD node1, node2, similarity RETURN node1, node2, similarity"
        ),
        pairs[..1]
    );
    // Directed, a and c still both point at b, and b shares nothing with them.
    assert_eq!(
        run(
            "CALL grust.algorithms.nodeSimilarity() YIELD node1, node2, similarity RETURN node1, node2, similarity"
        ),
        pairs
    );
    // A degree floor of two leaves no one to compare.
    assert_eq!(
        run(
            "CALL grust.algorithms.nodeSimilarity({degreeCutoff: 2}) YIELD node1 RETURN count(node1)"
        ),
        vec![vec![Value::Int(0)]]
    );
    assert!(
        run_read_query_with_registry(
            &graph(),
            "default",
            "CALL grust.algorithms.nodeSimilarity({metric: 'pearson'}) YIELD node1 RETURN node1",
            &CypherParameters::new(),
            &registry(),
        )
        .is_err()
    );
}

#[test]
fn bridges_articulation_points_and_components_are_ordinary_procedures() {
    // Undirected: a-b is edge 0; b-c and c-b are edges 1 and 2, a cycle of two.
    let text = |value: &str| Value::String(value.into());
    assert_eq!(
        run(
            "CALL grust.algorithms.bridges({orientation: 'undirected'}) YIELD sourceNodeId, targetNodeId, edgeOrdinal RETURN sourceNodeId, targetNodeId, edgeOrdinal"
        ),
        vec![vec![text("a"), text("b"), Value::Int(0)]]
    );
    assert_eq!(
        run(
            "CALL grust.algorithms.articulationPoints({orientation: 'undirected'}) YIELD nodeId RETURN nodeId"
        ),
        vec![vec![text("b")]]
    );
    assert_eq!(
        run(
            "CALL grust.algorithms.biconnectedComponents({orientation: 'undirected'}) YIELD edgeOrdinal, componentId RETURN edgeOrdinal, componentId"
        ),
        vec![
            vec![Value::Int(0), Value::Int(0)],
            vec![Value::Int(1), Value::Int(1)],
            vec![Value::Int(2), Value::Int(1)],
        ]
    );
    assert!(
        run_read_query_with_registry(
            &graph(),
            "default",
            "CALL grust.algorithms.bridges() YIELD edgeOrdinal RETURN edgeOrdinal",
            &CypherParameters::new(),
            &registry(),
        )
        .unwrap_err()
        .to_string()
        .contains("undirected")
    );
}
