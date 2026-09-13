use super::*;

pub(super) fn topology_batch(result: &TopologicalOrder) -> Result<ArrowResultBatch> {
    let (acyclic, order) = match result {
        TopologicalOrder::Acyclic(order) => (true, order),
        TopologicalOrder::Cycle(order) => (false, order),
    };
    let graph = order.projection();
    let context = graph.execution();
    let mut id_bytes = 0usize;
    for &node in order.values() {
        context.charge_work(1)?;
        id_bytes = id_bytes.saturating_add(graph.node_ids()[node].as_str().len());
    }
    utf8_size(id_bytes)?;
    i64::try_from(order.values().len())
        .map_err(|_| AlgorithmError::Numerical("order exceeds LargeList offset domain".into()))?;
    let reservation = context.reserve(overhead(order.values().len()).saturating_add(id_bytes))?;
    let mut ids = LargeListBuilder::with_capacity(
        StringBuilder::with_capacity(order.values().len(), id_bytes),
        1,
    );
    for &node in order.values() {
        context.charge_work(1)?;
        ids.values().append_value(graph.node_ids()[node].as_str());
    }
    ids.append(true);
    let mut empty = LargeListBuilder::with_capacity(StringBuilder::with_capacity(0, 0), 1);
    empty.append(true);
    let mut status = BooleanBuilder::with_capacity(1);
    status.append_value(acyclic);
    let ids = Arc::new(ids.finish()) as ArrayRef;
    let empty = Arc::new(empty.finish()) as ArrayRef;
    let (nodes, cycle) = if acyclic { (ids, empty) } else { (empty, ids) };
    finish(
        vec![
            ("acyclic", Arc::new(status.finish()) as ArrayRef),
            ("nodeIds", nodes),
            ("cycleNodeIds", cycle),
        ],
        reservation,
    )
}
