use super::*;

/// Pull up to `batch_rows` pairs into `block` and build one batch from them.
/// `None` once the kernel is exhausted, except that a result with no pairs at
/// all emits one empty batch first, so its schema is never lost.
pub(super) fn pairs_batch(
    graph: &GraphProjection,
    pairs: &mut AllPairsShortestPaths,
    block: &mut Buffer<ShortestPair>,
    emitted: bool,
) -> Result<Option<ArrowResultBatch>> {
    let context = graph.execution();
    let limit = context.limits().batch_rows;
    block.values.clear();
    while block.values.len() < limit {
        match pairs.next_pair()? {
            Some(pair) => block.values.push(pair),
            None => break,
        }
    }
    if block.values.is_empty() && emitted {
        return Ok(None);
    }
    let count = block.values.len();
    context.charge_work(count)?;
    let (mut source_bytes, mut target_bytes) = (0usize, 0usize);
    for pair in &block.values {
        source_bytes = source_bytes.saturating_add(graph.node_ids()[pair.source].as_str().len());
        target_bytes = target_bytes.saturating_add(graph.node_ids()[pair.target].as_str().len());
    }
    utf8_size(source_bytes)?;
    utf8_size(target_bytes)?;
    let reservation = context.reserve(
        overhead(count)
            .saturating_add(source_bytes)
            .saturating_add(target_bytes),
    )?;
    context.charge_work(count)?;
    let mut sources = StringBuilder::with_capacity(count, source_bytes);
    let mut targets = StringBuilder::with_capacity(count, target_bytes);
    let mut distances = Float64Builder::with_capacity(count);
    for pair in &block.values {
        sources.append_value(graph.node_ids()[pair.source].as_str());
        targets.append_value(graph.node_ids()[pair.target].as_str());
        distances.append_value(pair.distance);
    }
    finish(
        vec![
            ("sourceNodeId", Arc::new(sources.finish()) as ArrayRef),
            ("targetNodeId", Arc::new(targets.finish())),
            ("distance", Arc::new(distances.finish())),
        ],
        reservation,
    )
    .map(Some)
}
