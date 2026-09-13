//! Bounded owned rows adapted from the same results used by direct Rust callers.

use super::*;

pub(super) enum AlgorithmOutput {
    Distances(algorithms::Distances),
    Components(algorithms::Components),
    PageRank(algorithms::PageRank),
    Paths(algorithms::PathCursor),
    Order(algorithms::NodeOrder),
    Topology(algorithms::TopologicalOrder),
}

pub(super) struct AlgorithmCursor {
    graph: algorithms::GraphProjection,
    output: AlgorithmOutput,
    next: usize,
}

impl AlgorithmCursor {
    pub(super) fn new(graph: algorithms::GraphProjection, output: AlgorithmOutput) -> Self {
        Self {
            graph,
            output,
            next: 0,
        }
    }
}

impl ProcedureCursor for AlgorithmCursor {
    fn next_batch(&mut self) -> Result<Option<ProcedureBatch>> {
        let context = self.graph.execution();
        context.checkpoint()?;
        if let AlgorithmOutput::Paths(cursor) = &mut self.output {
            return match cursor.next_path()? {
                Some(path) => path_batch(&self.graph, path).map(Some),
                None => Ok(None),
            };
        }
        if let AlgorithmOutput::Topology(result) = &self.output {
            if self.next != 0 {
                return Ok(None);
            }
            let batch = topology_batch(result)?;
            self.next = 1;
            return Ok(Some(batch));
        }
        let count = match &self.output {
            AlgorithmOutput::Order(result) => result.values().len(),
            _ => self.graph.node_count(),
        };
        if self.next == count {
            return Ok(None);
        }
        let index = self.next;
        context.charge_work(1)?;
        let node = match &self.output {
            AlgorithmOutput::Order(result) => result.values()[index],
            _ => index,
        };
        let id = self.graph.node_ids()[node].as_str();
        let (fields, extra) = match &self.output {
            AlgorithmOutput::Distances(_) | AlgorithmOutput::Order(_) => (2, 0),
            AlgorithmOutput::Components(result) => (
                2,
                self.graph.node_ids()[result.values()[index]].as_str().len(),
            ),
            AlgorithmOutput::PageRank(_) => (5, 0),
            AlgorithmOutput::Paths(_) | AlgorithmOutput::Topology(_) => {
                return Err(ProcedureError::OutputContract(
                    "path output reached scalar adapter".into(),
                ));
            }
        };
        let reservation = context.reserve(
            row_bytes(fields)
                .saturating_add(id.len())
                .saturating_add(extra),
        )?;
        let mut row = Vec::new();
        row.try_reserve_exact(fields)?;
        row.push(Value::String(id.into()));
        match &self.output {
            AlgorithmOutput::Order(_) => row.push(Value::Int(integer(index)?)),
            AlgorithmOutput::Distances(result) => {
                let value = result.values()[index];
                row.push(if value.is_infinite() {
                    Value::Null
                } else {
                    Value::Float(value)
                });
            }
            AlgorithmOutput::Components(result) => row.push(Value::String(
                self.graph.node_ids()[result.values()[index]]
                    .as_str()
                    .into(),
            )),
            AlgorithmOutput::PageRank(result) => {
                row.push(Value::Float(result.values()[index]));
                row.push(Value::Int(integer(result.iterations())?));
                row.push(Value::Bool(result.converged()));
                row.push(Value::Float(result.residual()));
            }
            AlgorithmOutput::Paths(_) | AlgorithmOutput::Topology(_) => {
                return Err(ProcedureError::OutputContract(
                    "path output reached scalar adapter".into(),
                ));
            }
        }
        self.next += 1;
        batch(row, reservation).map(Some)
    }
}

fn row_bytes(fields: usize) -> usize {
    size_of::<Vec<Value>>().saturating_add(fields.saturating_mul(size_of::<Value>()))
}

fn integer(value: usize) -> Result<i64> {
    i64::try_from(value).map_err(|_| {
        ProcedureError::Numerical("algorithm output exceeds Cypher integer domain".into())
    })
}

fn batch(row: Vec<Value>, reservation: MemoryReservation) -> Result<ProcedureBatch> {
    let mut rows = Vec::new();
    rows.try_reserve_exact(1)?;
    rows.push(row);
    Ok(ProcedureBatch::new(rows, reservation))
}

fn path_batch(
    graph: &algorithms::GraphProjection,
    path: algorithms::PathView<'_>,
) -> Result<ProcedureBatch> {
    let context = graph.execution();
    let source = path
        .nodes
        .first()
        .copied()
        .ok_or_else(|| ProcedureError::OutputContract("empty reachable path".into()))?;
    let total_cost = path
        .costs
        .last()
        .copied()
        .ok_or_else(|| ProcedureError::OutputContract("missing path cost".into()))?;
    let mut bytes = row_bytes(6)
        .saturating_add(graph.node_ids()[source].as_str().len())
        .saturating_add(graph.node_ids()[path.target].as_str().len())
        .saturating_add(
            path.nodes
                .len()
                .saturating_mul(size_of::<String>() + size_of::<f64>()),
        )
        .saturating_add(path.edges.len().saturating_mul(size_of::<i64>()));
    for &node in path.nodes {
        context.charge_work(1)?;
        bytes = bytes.saturating_add(graph.node_ids()[node].as_str().len());
    }
    let reservation = context.reserve(bytes)?;
    let mut node_ids = Vec::new();
    node_ids.try_reserve_exact(path.nodes.len())?;
    let mut costs = Vec::new();
    costs.try_reserve_exact(path.costs.len())?;
    let mut ordinals = Vec::new();
    ordinals.try_reserve_exact(path.edges.len())?;
    for (&node, &cost) in path.nodes.iter().zip(path.costs) {
        context.charge_work(1)?;
        node_ids.push(graph.node_ids()[node].as_str().into());
        costs.push(cost);
    }
    for &edge in path.edges {
        context.charge_work(1)?;
        ordinals.push(integer(graph.edges()[edge].ordinal)?);
    }
    let mut row = Vec::new();
    row.try_reserve_exact(6)?;
    row.push(Value::String(graph.node_ids()[source].as_str().into()));
    row.push(Value::String(graph.node_ids()[path.target].as_str().into()));
    row.push(Value::Float(total_cost));
    row.push(Value::StringArray(node_ids));
    row.push(Value::FloatArray(costs));
    row.push(Value::IntArray(ordinals));
    batch(row, reservation)
}

fn topology_batch(result: &algorithms::TopologicalOrder) -> Result<ProcedureBatch> {
    let (acyclic, order) = match result {
        algorithms::TopologicalOrder::Acyclic(order) => (true, order),
        algorithms::TopologicalOrder::Cycle(order) => (false, order),
    };
    let graph = order.projection();
    let context = graph.execution();
    let mut bytes =
        row_bytes(3).saturating_add(order.values().len().saturating_mul(size_of::<String>()));
    for &node in order.values() {
        context.charge_work(1)?;
        bytes = bytes.saturating_add(graph.node_ids()[node].as_str().len());
    }
    let reservation = context.reserve(bytes)?;
    let mut ids = Vec::new();
    ids.try_reserve_exact(order.values().len())?;
    for &node in order.values() {
        context.charge_work(1)?;
        ids.push(graph.node_ids()[node].as_str().to_owned());
    }
    let mut row = Vec::new();
    row.try_reserve_exact(3)?;
    row.push(Value::Bool(acyclic));
    if acyclic {
        row.push(Value::StringArray(ids));
        row.push(Value::StringArray(Vec::new()));
    } else {
        row.push(Value::StringArray(Vec::new()));
        row.push(Value::StringArray(ids));
    }
    batch(row, reservation)
}
