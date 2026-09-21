//! Owned Arrow result batches whose admission follows shared buffer ownership.

use std::sync::Arc;

use arrow_array::{
    ArrayRef, RecordBatch,
    builder::{
        BooleanBuilder, FixedSizeListBuilder, Float32Builder, Float64Builder, Int64Builder,
        LargeListBuilder, StringBuilder, UInt64Builder,
    },
};
use grust_procedures::MemoryReservation;

use crate::{
    AlgorithmError, Components, Degrees, Distances, GraphProjection, KShortestPaths, NodeOrder,
    NodeTable, PageRank, PathCursor, PathView, Result, ShortestPaths, TableType, TableValue,
    TopologicalOrder,
};

/// A bounded Arrow batch retaining its query memory reservation. Clone this
/// wrapper or its raw Arrow arrays to share buffers and admission together.
/// Physical buffers retain the reservation through slices and exported readers;
/// the wrapper additionally retains admission for metadata-only output.
#[derive(Clone)]
pub struct ArrowResultBatch {
    batch: RecordBatch,
    _reservation: MemoryReservation,
}

impl ArrowResultBatch {
    /// Borrow the interoperable Arrow record batch.
    pub fn record_batch(&self) -> &RecordBatch {
        &self.batch
    }
    /// Retained admission, including conservative buffer and metadata overhead.
    pub fn reserved_bytes(&self) -> usize {
        self._reservation.bytes()
    }
}

mod ordering;

enum Output {
    Order(NodeOrder),
    Topology(TopologicalOrder),
    Distances(Distances),
    Components(Components),
    PageRank(PageRank),
    Degrees(Degrees),
    Paths(PathCursor),
    /// Ranked paths, already materialized: one batch each, in rank order.
    RankedPaths(KShortestPaths),
    Table(NodeTable),
}

/// Pull Arrow results in projection row order. Scalar batches honor the query's
/// batch row bound. Each full path occupies one row with LargeList arrays.
pub struct ArrowResultCursor {
    graph: Option<GraphProjection>,
    output: Option<Output>,
    next: usize,
    emitted: bool,
    failed: bool,
}

impl Distances {
    /// Transfer distances into Arrow `nodeId: Utf8, distance: Float64?` batches.
    /// Unreachable distances become null.
    pub fn into_arrow_results(self) -> ArrowResultCursor {
        ArrowResultCursor::new(self.projection().clone(), Output::Distances(self))
    }
}
impl NodeOrder {
    /// Transfer discovery/order rows into external `nodeId` and UInt64 `visitIndex`.
    pub fn into_arrow_results(self) -> ArrowResultCursor {
        ArrowResultCursor::new(self.projection().clone(), Output::Order(self))
    }
}
impl TopologicalOrder {
    /// Produce one row with `acyclic`, `nodeIds` and `cycleNodeIds` LargeLists.
    pub fn into_arrow_results(self) -> ArrowResultCursor {
        let graph = match &self {
            Self::Acyclic(order) | Self::Cycle(order) => order.projection().clone(),
        };
        ArrowResultCursor::new(graph, Output::Topology(self))
    }
}
impl Components {
    /// Transfer canonical labels into external-ID `nodeId, componentId` batches.
    pub fn into_arrow_results(self) -> ArrowResultCursor {
        ArrowResultCursor::new(self.projection().clone(), Output::Components(self))
    }
}
impl PageRank {
    /// Transfer scores and convergence evidence into Arrow batches.
    pub fn into_arrow_results(self) -> ArrowResultCursor {
        ArrowResultCursor::new(self.projection().clone(), Output::PageRank(self))
    }
}
impl NodeTable {
    /// Convert without copying the result buffers; each batch is admitted.
    /// Columns are `nodeId`, then the table's columns in declared order.
    pub fn into_arrow_results(self) -> ArrowResultCursor {
        ArrowResultCursor::new(self.projection().clone(), Output::Table(self))
    }
}

impl Degrees {
    /// Transfer exact UInt64 `degree` and nullable Float64 `strength` columns.
    pub fn into_arrow_results(self) -> ArrowResultCursor {
        ArrowResultCursor::new(self.projection().clone(), Output::Degrees(self))
    }
}
impl ShortestPaths {
    /// Transfer full paths into Arrow lists, preserving external node IDs and
    /// original UInt64 edge ordinals. No generic Value conversion occurs.
    pub fn into_arrow_results(self) -> Result<ArrowResultCursor> {
        let graph = self.distances().projection().clone();
        Ok(ArrowResultCursor::new(
            graph,
            Output::Paths(self.into_cursor()?),
        ))
    }
}
impl KShortestPaths {
    /// As [`ShortestPaths::into_arrow_results`], with the path's rank in a
    /// trailing `index` column. A result with no paths still emits one empty
    /// batch, so a consumer reading the schema off the first batch has one.
    pub fn into_arrow_results(self) -> ArrowResultCursor {
        let graph = self.projection().clone();
        ArrowResultCursor::new(graph, Output::RankedPaths(self))
    }
}

impl ArrowResultCursor {
    fn new(graph: GraphProjection, output: Output) -> Self {
        Self {
            graph: Some(graph),
            output: Some(output),
            next: 0,
            emitted: false,
            failed: false,
        }
    }

    /// Produce a batch or finish. Errors are terminal and immediately release
    /// projection and working storage; retained earlier batches remain charged.
    pub fn next_batch(&mut self) -> Result<Option<ArrowResultBatch>> {
        if self.failed {
            return Err(AlgorithmError::CursorFailed);
        }
        let outcome = self.advance();
        if !matches!(outcome, Ok(Some(_))) {
            self.graph = None;
            self.output = None;
            self.failed = outcome.is_err();
        }
        outcome
    }

    fn advance(&mut self) -> Result<Option<ArrowResultBatch>> {
        let (Some(graph), Some(output)) = (&self.graph, &mut self.output) else {
            return Ok(None);
        };
        let context = graph.execution();
        context.checkpoint()?;
        if let Output::Paths(cursor) = output {
            return cursor
                .next_path()?
                .map(|path| path_batch(graph, path, None))
                .transpose();
        }
        if let Output::RankedPaths(paths) = output {
            let rank = self.next;
            self.next += 1;
            return match paths.path(rank) {
                Some(path) => path_batch(graph, path, Some(unsigned(rank)?)).map(Some),
                // No paths at all is an answer, and it keeps its schema.
                None if rank == 0 => empty_path_batch(graph).map(Some),
                None => Ok(None),
            };
        }
        if let Output::Topology(result) = output {
            if self.next != 0 {
                return Ok(None);
            }
            let batch = ordering::topology_batch(result)?;
            self.next = 1;
            return Ok(Some(batch));
        }
        let total = match output {
            Output::Order(result) => result.values().len(),
            Output::Table(table) => table.rows(),
            _ => graph.node_count(),
        };
        // A table that found nothing still says what its columns are: one empty
        // batch, so a consumer reading the schema off the first batch has one.
        let empty_table = total == 0 && !self.emitted && matches!(output, Output::Table(_));
        if self.next == total && !empty_table {
            return Ok(None);
        }
        let start = self.next;
        let end = start + context.limits().batch_rows.min(total - start);
        let count = end - start;
        let mut id_bytes = 0usize;
        let mut component_bytes = 0usize;
        for index in start..end {
            context.charge_work(1)?;
            let node = match output {
                Output::Order(result) => result.values()[index],
                Output::Table(table) => table.key(index),
                _ => index,
            };
            id_bytes = id_bytes.saturating_add(graph.node_ids()[node].as_str().len());
            if let Output::Components(result) = output {
                component_bytes = component_bytes
                    .saturating_add(graph.node_ids()[result.values()[index]].as_str().len());
            }
            if let Output::Table(table) = output {
                for column in 0..table.width() {
                    if let TableValue::Node(id) = table.value(column, index) {
                        component_bytes = component_bytes.saturating_add(id.as_str().len());
                    }
                }
            }
        }
        // The fixed overhead covers six arrays; a wider table admits its own.
        let width_bytes = match output {
            Output::Table(table) => (0..table.width())
                .map(|column| match table.field(column).1 {
                    TableType::Vector(dimension) => 16 + 4 * dimension,
                    _ => 16,
                })
                .fold(0usize, usize::saturating_add)
                .saturating_mul(count),
            _ => 0,
        };
        let reservation = context.reserve(
            overhead(count)
                .saturating_add(id_bytes)
                .saturating_add(component_bytes)
                .saturating_add(width_bytes),
        )?;
        utf8_size(id_bytes)?;
        utf8_size(component_bytes)?;
        let mut ids = StringBuilder::with_capacity(count, id_bytes);
        for index in start..end {
            context.charge_work(1)?;
            let node = match output {
                Output::Order(result) => result.values()[index],
                Output::Table(table) => table.key(index),
                _ => index,
            };
            ids.append_value(graph.node_ids()[node].as_str());
        }
        let key_name = match output {
            Output::Table(table) => table.key_name(),
            _ => "nodeId",
        };
        let mut columns = vec![(key_name, Arc::new(ids.finish()) as ArrayRef)];
        match output {
            Output::Order(_) => {
                let mut values = UInt64Builder::with_capacity(count);
                for index in start..end {
                    context.charge_work(1)?;
                    values.append_value(unsigned(index)?);
                }
                columns.push(("visitIndex", Arc::new(values.finish())));
            }
            Output::Distances(result) => {
                let mut values = Float64Builder::with_capacity(count);
                for &value in &result.values()[start..end] {
                    context.charge_work(1)?;
                    values.append_option(value.is_finite().then_some(value));
                }
                columns.push(("distance", Arc::new(values.finish())));
            }
            Output::Components(result) => {
                let mut values = StringBuilder::with_capacity(count, component_bytes);
                for &component in &result.values()[start..end] {
                    context.charge_work(1)?;
                    values.append_value(graph.node_ids()[component].as_str());
                }
                columns.push(("componentId", Arc::new(values.finish())));
            }
            Output::Degrees(result) => {
                let mut counts = UInt64Builder::with_capacity(count);
                let mut strengths = Float64Builder::with_capacity(count);
                for index in start..end {
                    context.charge_work(1)?;
                    counts.append_value(unsigned(result.counts()[index])?);
                    strengths.append_option(result.strengths().map(|values| values[index]));
                }
                columns.extend([
                    ("degree", Arc::new(counts.finish()) as ArrayRef),
                    ("strength", Arc::new(strengths.finish())),
                ]);
            }
            Output::PageRank(result) => {
                let mut scores = Float64Builder::with_capacity(count);
                let mut iterations = UInt64Builder::with_capacity(count);
                let mut converged = BooleanBuilder::with_capacity(count);
                let mut residual = Float64Builder::with_capacity(count);
                let iteration = unsigned(result.iterations())?;
                for &score in &result.values()[start..end] {
                    context.charge_work(1)?;
                    scores.append_value(score);
                    iterations.append_value(iteration);
                    converged.append_value(result.converged());
                    residual.append_value(result.residual());
                }
                columns.extend([
                    ("score", Arc::new(scores.finish()) as ArrayRef),
                    ("iterations", Arc::new(iterations.finish())),
                    ("converged", Arc::new(converged.finish())),
                    ("residual", Arc::new(residual.finish())),
                ]);
            }
            Output::Table(table) => {
                for column in 0..table.width() {
                    context.charge_work(count)?;
                    let (name, kind) = table.field(column);
                    let array: ArrayRef = match kind {
                        TableType::Integer => {
                            let mut values = Int64Builder::with_capacity(count);
                            for row in start..end {
                                match table.value(column, row) {
                                    TableValue::Integer(value) => values.append_value(value),
                                    _ => values.append_null(),
                                }
                            }
                            Arc::new(values.finish())
                        }
                        TableType::Number => {
                            let mut values = Float64Builder::with_capacity(count);
                            for row in start..end {
                                match table.value(column, row) {
                                    TableValue::Number(value) => values.append_value(value),
                                    _ => values.append_null(),
                                }
                            }
                            Arc::new(values.finish())
                        }
                        TableType::Boolean => {
                            let mut values = BooleanBuilder::with_capacity(count);
                            for row in start..end {
                                match table.value(column, row) {
                                    TableValue::Boolean(value) => values.append_value(value),
                                    _ => values.append_null(),
                                }
                            }
                            Arc::new(values.finish())
                        }
                        TableType::Vector(dimension) => {
                            let width = i32::try_from(dimension).map_err(|_| {
                                AlgorithmError::OutputContract(
                                    "vector dimension exceeds Arrow's list size".into(),
                                )
                            })?;
                            let mut values = FixedSizeListBuilder::with_capacity(
                                Float32Builder::with_capacity(count * dimension),
                                width,
                                count,
                            );
                            for row in start..end {
                                match table.value(column, row) {
                                    TableValue::Vector(vector) => {
                                        values.values().append_slice(vector);
                                        values.append(true);
                                    }
                                    _ => {
                                        values.values().append_nulls(dimension);
                                        values.append(false);
                                    }
                                }
                            }
                            Arc::new(values.finish())
                        }
                        TableType::Node => {
                            let mut values = StringBuilder::with_capacity(count, component_bytes);
                            for row in start..end {
                                match table.value(column, row) {
                                    TableValue::Node(id) => values.append_value(id.as_str()),
                                    _ => values.append_null(),
                                }
                            }
                            Arc::new(values.finish())
                        }
                    };
                    columns.push((name, array));
                }
            }
            Output::Paths(_) | Output::RankedPaths(_) | Output::Topology(_) => {
                return Err(AlgorithmError::OutputContract(
                    "path output reached scalar Arrow adapter".into(),
                ));
            }
        }
        self.next = end;
        self.emitted = true;
        finish(columns, reservation).map(Some)
    }
}

// Up to six Arrow arrays plus schemas/builders/offset and validity buffers.
// This is a disclosed conservative admission bound, not an RSS estimate.
fn overhead(rows: usize) -> usize {
    32_768usize.saturating_add(rows.saturating_mul(64))
}

fn unsigned(value: usize) -> Result<u64> {
    u64::try_from(value)
        .map_err(|_| AlgorithmError::Numerical("Arrow result exceeds UInt64 domain".into()))
}

fn finish(
    columns: Vec<(&str, ArrayRef)>,
    reservation: MemoryReservation,
) -> Result<ArrowResultBatch> {
    let batch = RecordBatch::try_from_iter(columns)
        .map_err(|error| AlgorithmError::Provider(Box::new(error)))?;
    if batch.get_array_memory_size() > reservation.bytes() {
        return Err(AlgorithmError::OutputContract(
            "Arrow result exceeds admitted buffer bound".into(),
        ));
    }
    let owner = Arc::new(reservation.clone());
    let columns = batch
        .columns()
        .iter()
        .map(|array| grust_arrow::retain_array_owner(array, Arc::clone(&owner)))
        .collect::<std::result::Result<Vec<_>, _>>()
        .map_err(|error| AlgorithmError::Provider(Box::new(error)))?;
    let batch = RecordBatch::try_new(batch.schema(), columns)
        .map_err(|error| AlgorithmError::Provider(Box::new(error)))?;
    Ok(ArrowResultBatch {
        batch,
        _reservation: reservation,
    })
}

/// The columns a path row carries, with no rows: what a kernel that found no
/// path emits so that its schema survives.
fn empty_path_batch(graph: &GraphProjection) -> Result<ArrowResultBatch> {
    let reservation = graph.execution().reserve(overhead(0))?;
    // Zero capacity throughout: a builder's default capacity would allocate
    // more than the admitted overhead of a batch with nothing in it.
    let mut sources = StringBuilder::with_capacity(0, 0);
    let mut targets = StringBuilder::with_capacity(0, 0);
    let mut totals = Float64Builder::with_capacity(0);
    let mut nodes = LargeListBuilder::with_capacity(StringBuilder::with_capacity(0, 0), 0);
    let mut costs = LargeListBuilder::with_capacity(Float64Builder::with_capacity(0), 0);
    let mut edges = LargeListBuilder::with_capacity(UInt64Builder::with_capacity(0), 0);
    let mut ranks = UInt64Builder::with_capacity(0);
    finish(
        vec![
            ("sourceNodeId", Arc::new(sources.finish()) as ArrayRef),
            ("targetNodeId", Arc::new(targets.finish())),
            ("totalCost", Arc::new(totals.finish())),
            ("nodeIds", Arc::new(nodes.finish())),
            ("costs", Arc::new(costs.finish())),
            ("edgeOrdinals", Arc::new(edges.finish())),
            ("index", Arc::new(ranks.finish())),
        ],
        reservation,
    )
}

fn path_batch(
    graph: &GraphProjection,
    path: PathView<'_>,
    rank: Option<u64>,
) -> Result<ArrowResultBatch> {
    let context = graph.execution();
    let source = path
        .nodes
        .first()
        .copied()
        .ok_or_else(|| AlgorithmError::OutputContract("empty reachable path".into()))?;
    let total = path
        .costs
        .last()
        .copied()
        .ok_or_else(|| AlgorithmError::OutputContract("missing path cost".into()))?;
    let mut id_bytes = 0usize;
    for &node in path.nodes {
        context.charge_work(1)?;
        id_bytes = id_bytes.saturating_add(graph.node_ids()[node].as_str().len());
    }
    utf8_size(id_bytes)?;
    i64::try_from(path.nodes.len())
        .map_err(|_| AlgorithmError::Numerical("path exceeds LargeList offset domain".into()))?;
    let source_id = graph.node_ids()[source].as_str();
    let target_id = graph.node_ids()[path.target].as_str();
    let bytes = overhead(path.nodes.len())
        .saturating_add(id_bytes)
        .saturating_add(source_id.len())
        .saturating_add(target_id.len());
    let reservation = context.reserve(bytes)?;
    let mut sources = StringBuilder::with_capacity(1, source_id.len());
    sources.append_value(source_id);
    let mut targets = StringBuilder::with_capacity(1, target_id.len());
    targets.append_value(target_id);
    let mut totals = Float64Builder::with_capacity(1);
    totals.append_value(total);
    let mut nodes = LargeListBuilder::with_capacity(
        StringBuilder::with_capacity(path.nodes.len(), id_bytes),
        1,
    );
    let mut costs =
        LargeListBuilder::with_capacity(Float64Builder::with_capacity(path.costs.len()), 1);
    let mut edges =
        LargeListBuilder::with_capacity(UInt64Builder::with_capacity(path.edges.len()), 1);
    for (&node, &cost) in path.nodes.iter().zip(path.costs) {
        context.charge_work(1)?;
        nodes.values().append_value(graph.node_ids()[node].as_str());
        costs.values().append_value(cost);
    }
    for &edge in path.edges {
        context.charge_work(1)?;
        edges
            .values()
            .append_value(unsigned(graph.edges()[edge].ordinal)?);
    }
    nodes.append(true);
    costs.append(true);
    edges.append(true);
    let mut columns: Vec<(&str, ArrayRef)> = vec![
        ("sourceNodeId", Arc::new(sources.finish()) as ArrayRef),
        ("targetNodeId", Arc::new(targets.finish())),
        ("totalCost", Arc::new(totals.finish())),
        ("nodeIds", Arc::new(nodes.finish())),
        ("costs", Arc::new(costs.finish())),
        ("edgeOrdinals", Arc::new(edges.finish())),
    ];
    if let Some(rank) = rank {
        let mut ranks = UInt64Builder::with_capacity(1);
        ranks.append_value(rank);
        columns.push(("index", Arc::new(ranks.finish())));
    }
    finish(columns, reservation)
}

fn utf8_size(bytes: usize) -> Result<()> {
    i32::try_from(bytes).map(|_| ()).map_err(|_| {
        AlgorithmError::Numerical(
            "result strings exceed Utf8 offset domain; reduce batch size".into(),
        )
    })
}
