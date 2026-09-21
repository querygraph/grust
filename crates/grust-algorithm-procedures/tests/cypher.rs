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

#[test]
fn spanning_tree_is_an_ordinary_procedure() {
    // Undirected with costs: a-b 2.0, b-c 0.5, c-b 0.0. The lighter of the
    // parallel pair is taken.
    let query = |options: &str| {
        run(&format!(
            "CALL grust.algorithms.spanningTree({{orientation: 'undirected', weightProperty: 'cost'{options}}}) YIELD edgeOrdinal, weight, totalWeight RETURN edgeOrdinal, weight, totalWeight"
        ))
    };
    assert_eq!(
        query(""),
        vec![
            vec![Value::Int(0), Value::Float(2.0), Value::Float(2.0)],
            vec![Value::Int(2), Value::Float(0.0), Value::Float(2.0)],
        ]
    );
    assert_eq!(
        query(", objective: 'maximum'"),
        vec![
            vec![Value::Int(0), Value::Float(2.0), Value::Float(2.5)],
            vec![Value::Int(1), Value::Float(0.5), Value::Float(2.5)],
        ]
    );
    // The isolate's component has no edges.
    assert!(query(", sourceNode: 'isolate'").is_empty());
    assert_eq!(query(", sourceNode: 'c'").len(), 2);
}

#[test]
fn eigenvector_katz_and_hits_are_ordinary_procedures_with_convergence_evidence() {
    // Directed a->b, b->c, c->b. Nothing points at a, so a = 1; b and c solve
    // b = 1 + 0.25(a + c) and c = 1 + 0.25 b: 1.6 and 1.4.
    let rows = run(
        "CALL grust.algorithms.katz({alpha: 0.25, tolerance: 0.000000000001}) YIELD nodeId, score, converged RETURN nodeId, score, converged",
    );
    let score = |row: usize| match rows[row][1] {
        Value::Float(value) => value,
        ref other => panic!("{other:?}"),
    };
    assert!(rows.iter().all(|row| row[2] == Value::Bool(true)));
    assert_eq!(score(0), 1.0);
    assert!((score(1) - 1.6).abs() < 1e-9 && (score(2) - 1.4).abs() < 1e-9);
    assert_eq!(score(3), 1.0);

    // HITS: b is pointed at by a and c, so it is the authority.
    let rows = run(
        "CALL grust.algorithms.hits() YIELD nodeId, hub, authority, converged WHERE authority > 0.9 RETURN nodeId, converged",
    );
    assert_eq!(
        rows,
        vec![vec![Value::String("b".into()), Value::Bool(true)]]
    );

    // Eigenvector: a limit of one iteration is reported, not hidden.
    let rows = run(
        "CALL grust.algorithms.eigenvector({orientation: 'undirected', maxIterations: 1}) YIELD iterations, converged RETURN DISTINCT iterations, converged",
    );
    assert_eq!(rows, vec![vec![Value::Int(1), Value::Bool(false)]]);
}

#[test]
fn leiden_is_an_ordinary_procedure_with_louvains_shape() {
    let rows = run(
        "CALL grust.algorithms.leiden({orientation: 'undirected', seed: 7}) YIELD nodeId, communityId, modularity, converged RETURN nodeId, communityId, modularity, converged",
    );
    assert_eq!(rows.len(), 4);
    assert_eq!(rows[1][1], rows[2][1], "b and c share a community");
    assert_eq!(rows[3][1], Value::String("isolate".into()));
    assert!(rows.iter().all(|row| row[3] == Value::Bool(true)));
    // On this graph the two searches agree.
    let plain = run(
        "CALL grust.algorithms.louvain({orientation: 'undirected', seed: 7}) YIELD nodeId, communityId, modularity, converged RETURN nodeId, communityId, modularity, converged",
    );
    assert_eq!(rows, plain);
}

#[test]
fn max_flow_and_min_cut_take_a_source_and_a_target() {
    // Directed with costs as capacities: a->b 2.0, b->c 0.5, c->b 0.0.
    let text = |value: &str| Value::String(value.into());
    assert_eq!(
        run(
            "CALL grust.algorithms.maxFlow('a', 'c', {weightProperty: 'cost'}) YIELD sourceNodeId, targetNodeId, edgeOrdinal, flow, maxFlow RETURN sourceNodeId, targetNodeId, edgeOrdinal, flow, maxFlow"
        ),
        vec![
            vec![
                text("a"),
                text("b"),
                Value::Int(0),
                Value::Float(0.5),
                Value::Float(0.5)
            ],
            vec![
                text("b"),
                text("c"),
                Value::Int(1),
                Value::Float(0.5),
                Value::Float(0.5)
            ],
        ]
    );
    // The bottleneck b->c is the cut: a and b stay with the source.
    assert_eq!(
        run(
            "CALL grust.algorithms.minCut('a', 'c', {weightProperty: 'cost'}) YIELD nodeId, sourceSide WHERE sourceSide RETURN nodeId"
        ),
        vec![vec![text("a")], vec![text("b")]]
    );
    // Nothing reaches the isolate: no rows, and that is an answer.
    assert!(run("CALL grust.algorithms.maxFlow('a', 'isolate') YIELD flow RETURN flow").is_empty());
    assert!(
        run_read_query_with_registry(
            &graph(),
            "default",
            "CALL grust.algorithms.maxFlow('a', 'a') YIELD flow RETURN flow",
            &CypherParameters::new(),
            &registry(),
        )
        .is_err()
    );
}

#[test]
fn fast_rp_returns_an_embedding_list_per_node() {
    let rows = run(
        "CALL grust.algorithms.fastRP({orientation: 'undirected', embeddingDimension: 16, seed: 4}) YIELD nodeId, embedding RETURN nodeId, embedding",
    );
    assert_eq!(rows.len(), 4);
    let vector = |row: usize| match &rows[row][1] {
        Value::FloatArray(values) => values.clone(),
        other => panic!("{other:?}"),
    };
    assert!((0..4).all(|row| vector(row).len() == 16));
    // The isolate averages nothing, so with no self-influence it is zero.
    assert!(vector(3).iter().all(|&value| value == 0.0));
    assert!(vector(1).iter().any(|&value| value != 0.0));
    // Seeded: the same call gives the same list; another seed does not.
    let again = run(
        "CALL grust.algorithms.fastRP({orientation: 'undirected', embeddingDimension: 16, seed: 4}) YIELD nodeId, embedding RETURN nodeId, embedding",
    );
    assert_eq!(rows, again);
    let other = run(
        "CALL grust.algorithms.fastRP({orientation: 'undirected', embeddingDimension: 16, seed: 5, iterationWeights: [1.0]}) YIELD embedding RETURN embedding",
    );
    assert_ne!(other[1][0], rows[1][1]);
}

#[test]
fn bellman_ford_reads_negative_weights_that_every_other_procedure_refuses() {
    let graph = Graph::new(
        ["s", "a", "b", "t", "far"]
            .map(|id| Node::new("N", id, Props::new()))
            .into(),
        vec![
            Edge::new("R", "s", "a", [("cost".into(), Value::Float(4.0))]),
            Edge::new("R", "s", "b", [("cost".into(), Value::Float(5.0))]),
            Edge::new("R", "b", "a", [("cost".into(), Value::Float(-3.0))]),
            Edge::new("R", "a", "t", [("cost".into(), Value::Int(1))]),
        ],
    );
    let run_on = |query: &str| {
        run_read_query_with_registry(
            &graph,
            "default",
            query,
            &CypherParameters::new(),
            &registry(),
        )
    };
    let text = |value: &str| Value::String(value.into());
    // Through b is cheaper than the direct arc, by way of a negative weight.
    assert_eq!(
        run_on(
            "CALL grust.algorithms.bellmanFord('s', {weightProperty: 'cost'}) YIELD nodeId, distance, cycleIndex, negativeCycle RETURN nodeId, distance, cycleIndex, negativeCycle"
        )
        .unwrap()
        .rows,
        vec![
            vec![text("s"), Value::Float(0.0), Value::Int(-1), Value::Bool(false)],
            vec![text("a"), Value::Float(2.0), Value::Int(-1), Value::Bool(false)],
            vec![text("b"), Value::Float(5.0), Value::Int(-1), Value::Bool(false)],
            vec![text("t"), Value::Float(3.0), Value::Int(-1), Value::Bool(false)],
            vec![text("far"), Value::Null, Value::Int(-1), Value::Bool(false)],
        ]
    );
    // Undirected, the negative edge is a cycle of two, reported as the result.
    let rows = run_on(
        "CALL grust.algorithms.bellmanFord('s', {weightProperty: 'cost', orientation: 'undirected'}) YIELD nodeId, distance, cycleIndex, negativeCycle WHERE cycleIndex >= 0 RETURN nodeId, distance, negativeCycle ORDER BY nodeId",
    )
    .unwrap()
    .rows;
    assert_eq!(
        rows,
        vec![
            vec![text("a"), Value::Null, Value::Bool(true)],
            vec![text("b"), Value::Null, Value::Bool(true)],
        ]
    );
    // The same property is refused when the projection is built for any other kernel.
    let refused = run_on("CALL grust.algorithms.dijkstra('s', {weightProperty: 'cost'}) YIELD distance RETURN distance")
        .unwrap_err()
        .to_string();
    assert!(refused.contains("nonnegative"), "{refused}");
}

#[test]
fn modularity_reads_its_communities_from_a_node_property() {
    // Two triangles joined by one edge, with the partition on the nodes.
    let community = |id: &str, c: i64| Node::new("N", id, [("c".to_string(), Value::Int(c))]);
    let edge = |a: &str, b: &str| Edge::new("R", a, b, Props::new());
    let graph = Graph::new(
        vec![
            community("a", 10),
            community("b", 10),
            community("c", 10),
            community("d", 20),
            community("e", 20),
            community("f", 20),
        ],
        vec![
            edge("a", "b"),
            edge("b", "c"),
            edge("c", "a"),
            edge("d", "e"),
            edge("e", "f"),
            edge("f", "d"),
            edge("c", "d"),
        ],
    );
    let run_on = |query: &str| {
        run_read_query_with_registry(
            &graph,
            "default",
            query,
            &CypherParameters::new(),
            &registry(),
        )
    };
    let rows = run_on(
        "CALL grust.algorithms.modularity({orientation: 'undirected', communityProperty: 'c'}) YIELD nodeId, communityId, size, modularity, conductance, totalModularity RETURN nodeId, communityId, size, conductance, totalModularity",
    )
    .unwrap()
    .rows;
    // One row per community, led by its smallest member.
    assert_eq!(rows.len(), 2);
    assert_eq!(rows[0][0], Value::String("a".into()));
    assert_eq!(rows[0][1], Value::Int(10));
    assert_eq!(rows[1][1], Value::Int(20));
    assert_eq!(rows[0][2], Value::Int(3));
    // Seven edges, and one of a triangle's seven arc-ends leaves it.
    assert_eq!(rows[0][3], Value::Float(1.0 / 7.0));
    // Q = 5/14, reached by summing the two communities' parts rather than by
    // dividing, so it is one unit in the last place from the literal. The
    // kernel's own test pins the stronger property: the parts sum to the total.
    match rows[0][4] {
        Value::Float(total) => assert!((total - 5.0 / 14.0).abs() < 1e-15, "{total}"),
        ref other => panic!("{other:?}"),
    }

    // A resolution high enough makes one big community worse than nothing.
    let split = run_on(
        "CALL grust.algorithms.modularity({orientation: 'undirected', communityProperty: 'c', resolution: 10.0}) YIELD totalModularity RETURN DISTINCT totalModularity",
    )
    .unwrap()
    .rows;
    match split[0][0] {
        Value::Float(value) => assert!(value < 0.0, "{value}"),
        ref other => panic!("{other:?}"),
    }

    // A property no node has is an error naming the node, not a zero.
    let missing = run_on(
        "CALL grust.algorithms.modularity({orientation: 'undirected', communityProperty: 'absent'}) YIELD nodeId RETURN nodeId",
    )
    .unwrap_err()
    .to_string();
    assert!(
        missing.contains("absent") && missing.contains("a"),
        "{missing}"
    );
}

#[test]
fn link_prediction_scores_pairs_through_ordinary_cypher() {
    // A square a-b-c-d-a with community ids on some nodes only: the two
    // diagonals are the pairs at distance two, each sharing two neighbours.
    let node = |id: &str, community: Option<i64>| match community {
        Some(c) => Node::new("N", id, [("c".to_string(), Value::Int(c))]),
        None => Node::new("N", id, Props::new()),
    };
    let edge = |a: &str, b: &str| Edge::new("R", a, b, Props::new());
    let with_ids = |d: Option<i64>| {
        Graph::new(
            vec![
                node("a", Some(1)),
                node("b", Some(2)),
                node("c", Some(1)),
                node("d", d),
            ],
            vec![
                edge("a", "b"),
                edge("b", "c"),
                edge("c", "d"),
                edge("d", "a"),
            ],
        )
    };
    let run_on = |graph: &Graph, query: &str| {
        run_read_query_with_registry(
            graph,
            "default",
            query,
            &CypherParameters::new(),
            &registry(),
        )
    };
    let partial = with_ids(None);
    let rows = run_on(
        &partial,
        "CALL grust.algorithms.linkPrediction({orientation: 'undirected', metric: 'resourceAllocation'}) YIELD node1, node2, score RETURN node1, node2, score",
    )
    .unwrap()
    .rows;
    assert_eq!(
        rows,
        [
            vec![Value::from("a"), Value::from("c"), Value::Float(1.0)],
            vec![Value::from("b"), Value::from("d"), Value::Float(1.0)],
        ]
    );
    // Explicit pairs; a graph where d has no community still serves every
    // metric but sameCommunity, which reads the property and names the gap.
    let rows = run_on(
        &partial,
        "CALL grust.algorithms.linkPrediction({orientation: 'undirected', metric: 'preferentialAttachment', node1: ['a'], node2: ['b']}) YIELD score RETURN score",
    )
    .unwrap()
    .rows;
    assert_eq!(rows, [vec![Value::Float(4.0)]]);
    let missing = run_on(
        &partial,
        "CALL grust.algorithms.linkPrediction({orientation: 'undirected', metric: 'sameCommunity', communityProperty: 'c'}) YIELD score RETURN score",
    )
    .unwrap_err()
    .to_string();
    assert!(missing.contains('d') && missing.contains('c'), "{missing}");
    let rows = run_on(
        &with_ids(Some(2)),
        "CALL grust.algorithms.linkPrediction({orientation: 'undirected', metric: 'sameCommunity', communityProperty: 'c'}) YIELD node1, node2, score RETURN node1, node2, score",
    )
    .unwrap()
    .rows;
    assert_eq!(
        rows,
        [
            vec![Value::from("a"), Value::from("c"), Value::Float(1.0)],
            vec![Value::from("b"), Value::from("d"), Value::Float(1.0)],
        ]
    );
}

#[test]
fn astar_reads_coordinates_and_returns_the_route() {
    // Three points on a line of longitude, so the great-circle distances are
    // easy to reason about: a is north of b, b north of c.
    let place = |id: &str, lat: f64| {
        Node::new(
            "P",
            id,
            [
                ("lat".to_string(), Value::Float(lat)),
                ("lon".to_string(), Value::Float(0.0)),
            ],
        )
    };
    // One degree of latitude is about 111.2 km.
    let degree = 111_194.93;
    let graph = Graph::new(
        vec![place("a", 2.0), place("b", 1.0), place("c", 0.0)],
        vec![
            Edge::new("R", "a", "b", [("m".to_string(), Value::Float(degree))]),
            Edge::new("R", "b", "c", [("m".to_string(), Value::Float(degree))]),
            // A direct edge that is longer than going through b.
            Edge::new(
                "R",
                "a",
                "c",
                [("m".to_string(), Value::Float(3.0 * degree))],
            ),
        ],
    );
    let run_on = |query: &str| {
        run_read_query_with_registry(
            &graph,
            "default",
            query,
            &CypherParameters::new(),
            &registry(),
        )
    };
    let rows = run_on(
        "CALL grust.algorithms.astar('a', 'c', {orientation: 'undirected', weightProperty: 'm', latitudeProperty: 'lat', longitudeProperty: 'lon'}) YIELD nodeId, costFromSource, edgeOrdinal, totalCost, settled RETURN nodeId, edgeOrdinal, totalCost",
    )
    .unwrap()
    .rows;
    // The route is a, b, c: one row per node, the source entered by no edge.
    assert_eq!(rows.len(), 3);
    assert_eq!(rows[0][0], Value::String("a".into()));
    assert_eq!(rows[0][1], Value::Int(-1));
    assert_eq!(rows[1][0], Value::String("b".into()));
    assert_eq!(rows[1][1], Value::Int(0));
    assert_eq!(rows[2][0], Value::String("c".into()));
    assert_eq!(rows[2][1], Value::Int(1));
    match rows[2][2] {
        Value::Float(total) => assert!((total - 2.0 * degree).abs() < 1.0, "{total}"),
        ref other => panic!("{other:?}"),
    }

    // It agrees with dijkstra, which is the oracle the kernel is written against.
    let by_dijkstra = run_on(
        "CALL grust.algorithms.dijkstra('a', {orientation: 'undirected', weightProperty: 'm'}) YIELD nodeId, distance WHERE nodeId = 'c' RETURN distance",
    )
    .unwrap()
    .rows;
    assert_eq!(by_dijkstra[0][0], rows[2][2]);

    // A coordinate property no node has is an error naming the node.
    let missing = run_on(
        "CALL grust.algorithms.astar('a', 'c', {weightProperty: 'm', latitudeProperty: 'absent', longitudeProperty: 'lon'}) YIELD totalCost RETURN totalCost",
    )
    .unwrap_err()
    .to_string();
    assert!(missing.contains("absent"), "{missing}");
}

#[test]
fn yens_ranks_its_paths_and_stops_when_there_are_no_more() {
    // Two routes from a to d, and a third through both middles:
    //   a b d   1+1 = 2
    //   a c d   2+1 = 3
    //   a b c d 1+1+1 = 3, which ties with a c d and ranks *first* of the two:
    // the tie-break compares node rows, and b comes before c at the second
    // node. A shorter path is not preferred; a smaller sequence is.
    //
    // The rank column is `pathIndex`, not `index`: `index` is a reserved word
    // in this dialect, so the plain spelling every caller reaches for first
    // would be a syntax error.
    let graph = Graph::new(
        ["a", "b", "c", "d"]
            .map(|id| Node::new("N", id, Props::new()))
            .into(),
        vec![
            Edge::new("R", "a", "b", [("cost".into(), Value::Float(1.0))]),
            Edge::new("R", "a", "c", [("cost".into(), Value::Float(2.0))]),
            Edge::new("R", "b", "d", [("cost".into(), Value::Float(1.0))]),
            Edge::new("R", "c", "d", [("cost".into(), Value::Float(1.0))]),
            Edge::new("R", "b", "c", [("cost".into(), Value::Float(1.0))]),
        ],
    );
    let run_on = |query: &str| {
        run_read_query_with_registry(
            &graph,
            "default",
            query,
            &CypherParameters::new(),
            &registry(),
        )
    };
    let rows = run_on(
        "CALL grust.algorithms.yens('a', 'd', {weightProperty: 'cost', k: 5}) YIELD pathIndex, sourceNodeId, targetNodeId, totalCost, nodeIds RETURN pathIndex, sourceNodeId, targetNodeId, totalCost, nodeIds",
    )
    .unwrap()
    .rows;
    assert_eq!(
        rows,
        vec![
            vec![
                Value::Int(0),
                Value::String("a".into()),
                Value::String("d".into()),
                Value::Float(2.0),
                Value::StringArray(vec!["a".into(), "b".into(), "d".into()]),
            ],
            vec![
                Value::Int(1),
                Value::String("a".into()),
                Value::String("d".into()),
                Value::Float(3.0),
                Value::StringArray(vec!["a".into(), "b".into(), "c".into(), "d".into()]),
            ],
            vec![
                Value::Int(2),
                Value::String("a".into()),
                Value::String("d".into()),
                Value::Float(3.0),
                Value::StringArray(vec!["a".into(), "c".into(), "d".into()]),
            ],
        ]
    );
    // `k` defaults to one path.
    let one = run_on(
        "CALL grust.algorithms.yens('a', 'd', {weightProperty: 'cost'}) YIELD pathIndex, costs, edgeOrdinals RETURN pathIndex, costs, edgeOrdinals",
    )
    .unwrap()
    .rows;
    assert_eq!(
        one,
        vec![vec![
            Value::Int(0),
            Value::FloatArray(vec![0.0, 1.0, 2.0]),
            Value::IntArray(vec![0, 2]),
        ]]
    );
    // Nothing reaches a from d: no rows, and that is an answer, not an error.
    assert!(
        run_on("CALL grust.algorithms.yens('d', 'a') YIELD pathIndex RETURN pathIndex")
            .unwrap()
            .rows
            .is_empty()
    );
    // Asking for no paths is refused rather than answered with nothing.
    let refused =
        run_on("CALL grust.algorithms.yens('a', 'd', {k: 0}) YIELD pathIndex RETURN pathIndex")
            .unwrap_err()
            .to_string();
    assert!(
        refused.contains("k must be a positive integer"),
        "{refused}"
    );
}

#[test]
fn all_pairs_shortest_paths_streams_reachable_pairs_through_ordinary_cypher() {
    let row = |source: &str, target: &str, distance: f64| {
        vec![
            Value::String(source.into()),
            Value::String(target.into()),
            Value::Float(distance),
        ]
    };
    // a -2-> b -0.5-> c -0-> b. Unreachable pairs are omitted, the isolate
    // reaches itself, and c reaches b at zero through the zero-weight edge.
    let all = vec![
        row("a", "a", 0.0),
        row("a", "b", 2.0),
        row("a", "c", 2.5),
        row("b", "b", 0.0),
        row("b", "c", 0.5),
        row("c", "b", 0.0),
        row("c", "c", 0.0),
        row("isolate", "isolate", 0.0),
    ];
    assert_eq!(
        run(
            "CALL grust.algorithms.allPairsShortestPaths({weightProperty: 'cost'}) YIELD sourceNodeId, targetNodeId, distance RETURN sourceNodeId, targetNodeId, distance"
        ),
        all
    );
    // Sources in row order, whatever order the caller names them in.
    let mut chosen = all[..3].to_vec();
    chosen.extend_from_slice(&all[5..7]);
    assert_eq!(
        run(
            "CALL grust.algorithms.allPairsShortestPaths({weightProperty: 'cost', sourceNodes: ['c', 'a']}) YIELD sourceNodeId, targetNodeId, distance RETURN sourceNodeId, targetNodeId, distance"
        ),
        chosen
    );
    // An empty selection is explicit, and selects nothing.
    assert_eq!(
        run(
            "CALL grust.algorithms.allPairsShortestPaths({sourceNodes: []}) YIELD sourceNodeId RETURN count(sourceNodeId)"
        ),
        vec![vec![Value::Int(0)]]
    );
    for (bad, says) in [("['a', 'a']", "more than once"), ("['nobody']", "nobody")] {
        let error = run_read_query_with_registry(
            &graph(),
            "default",
            &format!(
                "CALL grust.algorithms.allPairsShortestPaths({{sourceNodes: {bad}}}) YIELD sourceNodeId RETURN sourceNodeId"
            ),
            &CypherParameters::new(),
            &registry(),
        )
        .unwrap_err()
        .to_string();
        assert!(error.contains(says), "{bad}: {error}");
    }
}
