use super::*;
#[test]
fn edge_timestamps_and_vertex_embeddings_have_separate_alignment() {
    let c = InputContract {
        edge_fields: vec![Feature {
            name: "time".into(),
            data_type: LogicalType::Int64,
            alignment: Alignment::Edge,
        }],
        vertex_fields: vec![Feature {
            name: "embedding".into(),
            data_type: LogicalType::List(Box::new(LogicalType::Float32)),
            alignment: Alignment::Vertex,
        }],
    };
    assert_eq!(c.validate(), Ok(()));
}
#[test]
fn wrong_alignment_and_duplicate_features_are_metadata_errors() {
    let field = Feature {
        name: "embedding".into(),
        data_type: LogicalType::Int64,
        alignment: Alignment::Vertex,
    };
    assert!(matches!(
        InputContract {
            edge_fields: vec![field.clone()],
            vertex_fields: vec![]
        }
        .validate(),
        Err(ContractError::WrongAlignment(_))
    ));
    assert!(matches!(
        InputContract {
            edge_fields: vec![],
            vertex_fields: vec![field.clone(), field]
        }
        .validate(),
        Err(ContractError::RepeatedFeature(_))
    ));
}
#[test]
fn estimate_includes_bookkeeping_and_reverse_storage_without_overflow() {
    assert_eq!(
        Estimate {
            scratch: 1,
            output: 2,
            bookkeeping: 3,
            reverse_adjacency: 4
        }
        .total(),
        Some(10)
    );
    assert_eq!(
        Estimate {
            scratch: u64::MAX,
            output: 1,
            bookkeeping: 0,
            reverse_adjacency: 0
        }
        .total(),
        None
    );
}
struct InlineHost;
impl HostExecutor for InlineHost {
    fn for_each(
        &self,
        range: Range<usize>,
        f: &(dyn Fn(usize) -> Result<(), ContractError> + Sync),
    ) -> Result<(), ContractError> {
        for i in range {
            f(i)?;
        }
        Ok(())
    }
}
#[test]
fn host_executor_completes_callbacks_and_returns_errors_without_spawning() {
    let count = std::sync::atomic::AtomicUsize::new(0);
    InlineHost
        .for_each(0..10, &|_| {
            count.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
            Ok(())
        })
        .unwrap();
    assert_eq!(count.load(std::sync::atomic::Ordering::SeqCst), 10);
    assert_eq!(
        InlineHost.for_each(0..10, &|_| Err(ContractError::Cancelled)),
        Err(ContractError::Cancelled)
    );
}
