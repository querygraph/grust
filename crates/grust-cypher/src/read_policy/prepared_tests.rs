use super::*;
use grust_core::{Node, Props, Value};
use std::{sync::Arc, time::Duration};

const QUERY: &str = "MATCH (n) RETURN id(n) AS id LIMIT 1";

#[test]
fn request_retains_parameters_and_policy_without_encoding_copies() {
    let parameters = CypherParameters::from([("text".into(), Value::String("a\"b".into()))]);
    let bytes = serde_json::to_vec(&parameters).unwrap().len();
    let policy = ReadQueryPolicy {
        max_parameter_bytes: bytes,
        ..ReadQueryPolicy::default()
    };
    let request = PreparedReadRequest::new(QUERY, &parameters, &policy).unwrap();
    assert!(std::ptr::eq(request.parameters(), &parameters));
    assert_eq!(request.policy(), &policy);
    assert!(request.deadline() > Instant::now());
    assert!(
        PreparedReadRequest::new(
            QUERY,
            &parameters,
            &ReadQueryPolicy {
                max_parameter_bytes: bytes - 1,
                ..policy
            }
        )
        .is_err()
    );
    assert!(
        PreparedReadRequest::new("MATCH (n) RETURN absent.x LIMIT 1", &parameters, &policy)
            .is_err()
    );
}

#[test]
fn graph_and_index_admission_agree_at_exact_byte_boundary() {
    let graph = Arc::new(Graph::new(vec![Node::new("N", "a", Props::new())], vec![]));
    let index = TypedGraphIndex::new(graph.clone()).unwrap();
    let parameters = CypherParameters::new();
    for offset in [0, 1] {
        let policy = ReadQueryPolicy {
            max_graph_bytes: index.serialized_graph_bytes() - offset,
            ..ReadQueryPolicy::default()
        };
        let request = PreparedReadRequest::new(QUERY, &parameters, &policy).unwrap();
        assert_eq!(request.check_graph(&graph).is_ok(), offset == 0);
        assert_eq!(request.check_index(&index).is_ok(), offset == 0);
    }
}

#[test]
fn output_and_input_checks_keep_the_original_deadline() {
    let parameters = CypherParameters::new();
    let table = CypherResultTable {
        columns: vec!["id".into()],
        rows: vec![vec![Value::String("a".into())]],
    };
    let bytes = serde_json::to_vec(&EncodedResultSize {
        columns: &table.columns,
        rows: &table.rows,
    })
    .unwrap()
    .len();
    let policy = ReadQueryPolicy {
        max_output_bytes: bytes,
        ..ReadQueryPolicy::default()
    };
    let mut request = PreparedReadRequest::new(QUERY, &parameters, &policy).unwrap();
    request.check_output(&table).unwrap();
    request.policy.max_output_bytes = bytes - 1;
    assert!(request.check_output(&table).is_err());
    request.deadline = Instant::now() - Duration::from_secs(1);
    assert!(
        request
            .check_output(&table)
            .unwrap_err()
            .to_string()
            .contains("timed out")
    );
    assert!(
        request
            .check_graph(&Graph::new(vec![], vec![]))
            .unwrap_err()
            .to_string()
            .contains("timed out")
    );
}

#[test]
fn prepared_request_retains_the_validated_registry_generation() {
    let mut builder = grust_procedures::RegistryBuilder::default();
    grust_procedures::register_builtins(&mut builder).unwrap();
    let registry = builder.build();
    let parameters = CypherParameters::new();
    let policy = ReadQueryPolicy {
        require_match: false,
        allow_catalog_procedures: true,
        ..ReadQueryPolicy::default()
    };
    let query = "CALL db.labels() YIELD label RETURN label LIMIT 1";
    let request =
        PreparedReadRequest::with_registry(query, &parameters, &policy, &registry).unwrap();
    drop(registry);
    assert!(request.registry().unwrap().resolve("db.labels").is_ok());
    assert!(
        PreparedReadRequest::new(
            query,
            &parameters,
            &ReadQueryPolicy {
                allow_catalog_procedures: false,
                ..policy
            }
        )
        .is_err()
    );
}

#[test]
fn graph_count_rejection_precedes_native_serialization() {
    struct MustNotSerialize;
    impl serde::Serialize for MustNotSerialize {
        fn serialize<S: serde::Serializer>(&self, _: S) -> std::result::Result<S::Ok, S::Error> {
            panic!("row admission must precede serialization")
        }
    }
    let parameters = CypherParameters::new();
    let policy = ReadQueryPolicy {
        max_graph_nodes: 1,
        max_graph_edges: 1,
        ..ReadQueryPolicy::default()
    };
    let request = PreparedReadRequest::new(QUERY, &parameters, &policy).unwrap();
    assert!(
        request
            .check_serializable_graph(2, 0, &MustNotSerialize)
            .is_err()
    );
    assert!(
        request
            .check_serializable_graph(0, 2, &MustNotSerialize)
            .is_err()
    );
    assert!(request.check_measured_graph(2, 0, 0).is_err());
}
