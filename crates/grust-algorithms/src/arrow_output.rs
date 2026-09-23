//! Owned Arrow result batches whose admission follows shared buffer ownership.

use std::sync::Arc;

use arrow_array::{
    ArrayRef, RecordBatch,
    builder::{
        BooleanBuilder, FixedSizeListBuilder, Float32Builder, Float64Builder, Int64Builder,
        LargeListBuilder, PrimitiveBuilder, StringBuilder,
    },
    types::ArrowPrimitiveType,
};
use arrow_schema::{Field, Schema};
use grust_procedures::{ExecutionContext, MemoryReservation};

use crate::{
    AlgorithmError, AllPairsShortestPaths, Components, Degrees, Distances, GraphProjection,
    KShortestPaths, NodeOrder, NodeTable, PageRank, PathCursor, PathView, Result, Score,
    ShortestPair, ShortestPaths, TableType, TableValue, TopologicalOrder, buffer::Buffer,
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

mod apsp;
mod ordering;

enum Output {
    Order(NodeOrder),
    Topology(TopologicalOrder),
    Distances(Distances),
    Components(Components),
    PageRank(PageRank),
    /// `f32` scores: the `score` column is Float32, the rest as at `f64`.
    PageRankF32(PageRank<f32>),
    Degrees(Degrees),
    Paths(PathCursor),
    /// Ranked paths, already materialized: one batch each, in rank order.
    RankedPaths(KShortestPaths),
    /// Pairs pulled from the kernel a batch at a time, through one reused block.
    AllPairs(AllPairsShortestPaths, Buffer<ShortestPair>),
    Table(NodeTable),
}

/// Pull Arrow results in projection row order. Scalar batches honor the query's
/// batch row bound. Each full path occupies one row with LargeList arrays.
///
/// A column's nullability is never read off the rows: a batch whose nullable
/// column happens to be full has the same schema as one where it is not, and
/// so does an empty batch. Without a declaration every top-level column is
/// nullable, the one claim that holds whatever the rows are. A caller that
/// knows which columns can hold nulls states it once, through
/// [`ArrowResultCursor::with_declared_columns`], and every batch then carries
/// exactly that.
pub struct ArrowResultCursor {
    graph: Option<GraphProjection>,
    output: Option<Output>,
    next: usize,
    emitted: bool,
    failed: bool,
    declared: Option<Vec<(String, bool)>>,
}

impl Distances {
    /// Transfer distances into Arrow `nodeId: Utf8, distance: Float64?` batches.
    /// Unreachable distances become null.
    pub fn into_arrow_results(self) -> ArrowResultCursor {
        ArrowResultCursor::new(self.projection().clone(), Output::Distances(self))
    }
}
impl NodeOrder {
    /// Transfer discovery/order rows into external `nodeId` and Int64 `visitIndex`.
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
    /// Transfer scores and convergence evidence into Arrow batches: `score`
    /// and `residual` Float64, `iterations` Int64, `converged` Boolean.
    pub fn into_arrow_results(self) -> ArrowResultCursor {
        ArrowResultCursor::new(self.projection().clone(), Output::PageRank(self))
    }
}
impl PageRank<f32> {
    /// As [`PageRank::into_arrow_results`], with `score` Float32: the scores
    /// are handed over at the precision they were computed at, never widened.
    /// The residual was summed in `f64` and stays Float64.
    pub fn into_arrow_results(self) -> ArrowResultCursor {
        ArrowResultCursor::new(self.projection().clone(), Output::PageRankF32(self))
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
    /// Transfer exact Int64 `degree` and nullable Float64 `strength` columns.
    pub fn into_arrow_results(self) -> ArrowResultCursor {
        ArrowResultCursor::new(self.projection().clone(), Output::Degrees(self))
    }
}
impl ShortestPaths {
    /// Transfer full paths into Arrow lists, preserving external node IDs and
    /// original Int64 edge ordinals. No generic Value conversion occurs.
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
    /// trailing `pathIndex` column. A result with no paths still emits one empty
    /// batch, so a consumer reading the schema off the first batch has one.
    pub fn into_arrow_results(self) -> ArrowResultCursor {
        let graph = self.projection().clone();
        ArrowResultCursor::new(graph, Output::RankedPaths(self))
    }
}

impl AllPairsShortestPaths {
    /// Stream `sourceNodeId: Utf8, targetNodeId: Utf8, distance: Float64`
    /// batches. Each batch is computed when it is pulled, so admitted memory is
    /// the kernel's workspace plus one block of `batch_rows` pairs, whatever
    /// the total. A result with no pairs still emits one empty batch.
    pub fn into_arrow_results(self) -> Result<ArrowResultCursor> {
        let graph = self.projection().clone();
        let block = Buffer::capacity(graph.execution().limits().batch_rows, graph.execution())?;
        Ok(ArrowResultCursor::new(graph, Output::AllPairs(self, block)))
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
            declared: None,
        }
    }

    /// Declare the result's columns, in order, each with whether it may hold
    /// nulls; every batch then carries this nullability, whatever its rows
    /// hold, and an empty batch carries it too. A registry that declares a
    /// kernel's outputs passes that declaration here, so the schema a caller
    /// reads is the one the kernel was registered with. A batch whose column
    /// names differ from the declaration, or that holds a null in a column
    /// declared non-nullable, fails the cursor with
    /// [`AlgorithmError::OutputContract`] instead of being handed on.
    pub fn with_declared_columns<N: Into<String>>(
        mut self,
        columns: impl IntoIterator<Item = (N, bool)>,
    ) -> Self {
        self.declared = Some(
            columns
                .into_iter()
                .map(|(name, nullable)| (name.into(), nullable))
                .collect(),
        );
        self
    }

    /// Produce a batch or finish. Errors are terminal and immediately release
    /// projection and working storage; retained earlier batches remain charged.
    pub fn next_batch(&mut self) -> Result<Option<ArrowResultBatch>> {
        if self.failed {
            return Err(AlgorithmError::CursorFailed);
        }
        let outcome = self.advance().and_then(|batch| match &self.declared {
            Some(declared) => batch.map(|batch| declare(batch, declared)).transpose(),
            None => Ok(batch),
        });
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
                Some(path) => path_batch(graph, path, Some(signed(rank, "pathIndex")?)).map(Some),
                // No paths at all is an answer, and it keeps its schema.
                None if rank == 0 => empty_path_batch(graph).map(Some),
                None => Ok(None),
            };
        }
        if let Output::AllPairs(pairs, block) = output {
            let batch = apsp::pairs_batch(graph, pairs, block, self.emitted)?;
            self.emitted = true;
            return Ok(batch);
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
                let mut values = Int64Builder::with_capacity(count);
                for index in start..end {
                    context.charge_work(1)?;
                    values.append_value(signed(index, "visitIndex")?);
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
                let mut counts = Int64Builder::with_capacity(count);
                let mut strengths = Float64Builder::with_capacity(count);
                for index in start..end {
                    context.charge_work(1)?;
                    counts.append_value(signed(result.counts()[index], "degree")?);
                    strengths.append_option(result.strengths().map(|values| values[index]));
                }
                columns.extend([
                    ("degree", Arc::new(counts.finish()) as ArrayRef),
                    ("strength", Arc::new(strengths.finish())),
                ]);
            }
            Output::PageRank(result) => {
                let scores = Float64Builder::with_capacity(count);
                rank_columns(context, &mut columns, result, start..end, scores)?;
            }
            Output::PageRankF32(result) => {
                let scores = Float32Builder::with_capacity(count);
                rank_columns(context, &mut columns, result, start..end, scores)?;
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
            Output::Paths(_)
            | Output::RankedPaths(_)
            | Output::AllPairs(..)
            | Output::Topology(_) => {
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

/// PageRank's four columns after `nodeId`, for rows `start..end`. The score
/// column's Arrow type is the builder's, which is the scores' own precision;
/// `iterations`, `converged` and `residual` are Int64, Boolean and Float64 at
/// either.
fn rank_columns<F, T>(
    context: &ExecutionContext,
    columns: &mut Vec<(&str, ArrayRef)>,
    result: &PageRank<F>,
    rows: std::ops::Range<usize>,
    mut scores: PrimitiveBuilder<T>,
) -> Result<()>
where
    F: Score,
    T: ArrowPrimitiveType<Native = F>,
{
    let count = rows.len();
    let mut iterations = Int64Builder::with_capacity(count);
    let mut converged = BooleanBuilder::with_capacity(count);
    let mut residual = Float64Builder::with_capacity(count);
    let iteration = signed(result.iterations(), "iterations")?;
    for &score in &result.values()[rows] {
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
    Ok(())
}

// Up to six Arrow arrays plus schemas/builders/offset and validity buffers.
// This is a disclosed conservative admission bound, not an RSS estimate.
fn overhead(rows: usize) -> usize {
    32_768usize.saturating_add(rows.saturating_mul(64))
}

/// Integer columns are Int64, as the registry declares them (`Integer` is
/// `i64`): Arrow's unsigned types have no counterpart in Spark, SQL or most
/// dataframe libraries. Every value written through here is an index, a count
/// or an ordinal bounded by memory, far below `i64::MAX`, so this refuses
/// rather than wraps only a value no graph that fits in memory produces.
fn signed(value: usize, column: &str) -> Result<i64> {
    i64::try_from(value).map_err(|_| {
        AlgorithmError::Numerical(format!(
            "`{column}` value {value} exceeds Arrow's Int64 domain"
        ))
    })
}

/// Build a batch whose schema is fixed by its column names and data types,
/// never by its rows: every top-level column is nullable until a declaration
/// narrows it (see [`declare`]). `RecordBatch::try_from_iter` would instead
/// mark a column nullable only where that batch holds a null.
fn finish(
    columns: Vec<(&str, ArrayRef)>,
    reservation: MemoryReservation,
) -> Result<ArrowResultBatch> {
    let bytes = columns
        .iter()
        .map(|(_, array)| array.get_array_memory_size())
        .fold(0usize, usize::saturating_add);
    if bytes > reservation.bytes() {
        return Err(AlgorithmError::OutputContract(
            "Arrow result exceeds admitted buffer bound".into(),
        ));
    }
    let owner = Arc::new(reservation.clone());
    let mut fields = Vec::with_capacity(columns.len());
    let mut arrays = Vec::with_capacity(columns.len());
    for (name, array) in columns {
        fields.push(Field::new(name, array.data_type().clone(), true));
        arrays.push(
            grust_arrow::retain_array_owner(&array, Arc::clone(&owner))
                .map_err(|error| AlgorithmError::Provider(Box::new(error)))?,
        );
    }
    let batch = RecordBatch::try_new(Arc::new(Schema::new(fields)), arrays)
        .map_err(|error| AlgorithmError::Provider(Box::new(error)))?;
    Ok(ArrowResultBatch {
        batch,
        _reservation: reservation,
    })
}

/// Restate a batch with the declared nullability of each column. The arrays
/// and their retained admission are shared, not copied.
fn declare(batch: ArrowResultBatch, declared: &[(String, bool)]) -> Result<ArrowResultBatch> {
    let schema = batch.batch.schema();
    let names: Vec<&str> = schema.fields().iter().map(|f| f.name().as_str()).collect();
    let expected: Vec<&str> = declared.iter().map(|(name, _)| name.as_str()).collect();
    if names != expected {
        return Err(AlgorithmError::OutputContract(format!(
            "Arrow columns {names:?} differ from the declared {expected:?}"
        )));
    }
    let fields: Vec<Field> = schema
        .fields()
        .iter()
        .zip(declared)
        .map(|(field, (_, nullable))| field.as_ref().clone().with_nullable(*nullable))
        .collect();
    for ((name, nullable), array) in declared.iter().zip(batch.batch.columns()) {
        if !nullable && array.null_count() > 0 {
            return Err(AlgorithmError::OutputContract(format!(
                "column `{name}` is declared non-nullable and holds {} null(s)",
                array.null_count()
            )));
        }
    }
    let restated = RecordBatch::try_new(
        Arc::new(Schema::new_with_metadata(fields, schema.metadata().clone())),
        batch.batch.columns().to_vec(),
    )
    .map_err(|error| AlgorithmError::Provider(Box::new(error)))?;
    Ok(ArrowResultBatch {
        batch: restated,
        _reservation: batch._reservation,
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
    let mut edges = LargeListBuilder::with_capacity(Int64Builder::with_capacity(0), 0);
    let mut ranks = Int64Builder::with_capacity(0);
    finish(
        vec![
            ("sourceNodeId", Arc::new(sources.finish()) as ArrayRef),
            ("targetNodeId", Arc::new(targets.finish())),
            ("totalCost", Arc::new(totals.finish())),
            ("nodeIds", Arc::new(nodes.finish())),
            ("costs", Arc::new(costs.finish())),
            ("edgeOrdinals", Arc::new(edges.finish())),
            ("pathIndex", Arc::new(ranks.finish())),
        ],
        reservation,
    )
}

fn path_batch(
    graph: &GraphProjection,
    path: PathView<'_>,
    rank: Option<i64>,
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
        LargeListBuilder::with_capacity(Int64Builder::with_capacity(path.edges.len()), 1);
    for (&node, &cost) in path.nodes.iter().zip(path.costs) {
        context.charge_work(1)?;
        nodes.values().append_value(graph.node_ids()[node].as_str());
        costs.values().append_value(cost);
    }
    for &edge in path.edges {
        context.charge_work(1)?;
        edges
            .values()
            .append_value(signed(graph.edges()[edge].ordinal, "edgeOrdinals")?);
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
        let mut ranks = Int64Builder::with_capacity(1);
        ranks.append_value(rank);
        columns.push(("pathIndex", Arc::new(ranks.finish())));
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
