//! Provider-neutral incremental clause consumption selected from the ordinary AST.
//! Unsupported blocking shapes continue through the existing budgeted executor.

use super::streaming_aggregate::AggregateState;
use super::*;
use grust_procedures::{Invocation, LocalSnapshot, MemoryAccount};
use std::ops::ControlFlow;

pub(super) fn try_execute(
    graph: GraphRef<'_>,
    query: &SingleQuery,
    params: &CypherParameters,
    procedures: &ProcedureExecution,
) -> Option<Result<CypherResultTable>> {
    let (clauses, projection, aggregate) = classify(query)?;
    Some(execute(
        graph, clauses, projection, params, procedures, aggregate,
    ))
}

pub(super) fn classify(query: &SingleQuery) -> Option<(&[Clause], &Projection, bool)> {
    let (Clause::Return(return_clause), clauses) = query.clauses.split_last()? else {
        return None;
    };
    let projection = &return_clause.projection;
    if !clauses
        .iter()
        .any(|clause| matches!(clause, Clause::Call(_)))
        || projection.star
        || projection.distinct
        || !projection.order_by.is_empty()
        || clauses.iter().any(|clause| !supported(clause))
    {
        return None;
    }
    let aggregate = projection
        .items
        .iter()
        .any(|item| expr_has_aggregate(&item.expr));
    if aggregate
        && !projection
            .items
            .iter()
            .all(|item| AggregateState::supports(&item.expr))
    {
        return None;
    }
    Some((clauses, projection, aggregate))
}

fn supported(clause: &Clause) -> bool {
    match clause {
        Clause::Use(_) | Clause::Call(_) | Clause::Unwind(_) => true,
        Clause::With(with) => {
            let projection = &with.projection;
            !projection.distinct
                && projection.order_by.is_empty()
                && projection.skip.is_none()
                && projection.limit.is_none()
                && !projection
                    .items
                    .iter()
                    .any(|item| expr_has_aggregate(&item.expr))
        }
        _ => false,
    }
}

type Flow = ControlFlow<()>;

trait RowSink {
    fn consume(&mut self, row: &Row) -> Result<Flow>;
    fn unwind(
        &mut self,
        _unwind: &UnwindClause,
        _row: &Row,
        _context: &grust_procedures::ExecutionContext,
    ) -> Option<Result<Flow>> {
        None
    }
}

impl<F: FnMut(&Row) -> Result<Flow>> RowSink for F {
    fn consume(&mut self, row: &Row) -> Result<Flow> {
        self(row)
    }
}

struct AggregateSink<'a> {
    states: &'a mut [AggregateState],
    items: &'a [ReturnItem],
    params: &'a CypherParameters,
}

impl RowSink for AggregateSink<'_> {
    fn consume(&mut self, row: &Row) -> Result<Flow> {
        for (state, item) in self.states.iter_mut().zip(self.items) {
            state.update(&item.expr, row, self.params)?;
        }
        Ok(Flow::Continue(()))
    }
    fn unwind(
        &mut self,
        unwind: &UnwindClause,
        row: &Row,
        context: &grust_procedures::ExecutionContext,
    ) -> Option<Result<Flow>> {
        super::streaming_fusion::try_unwind(
            self.states,
            self.items,
            unwind,
            row,
            self.params,
            context,
        )
    }
}

struct Pipeline<'a> {
    graph: GraphRef<'a>,
    clauses: &'a [Clause],
    params: &'a CypherParameters,
    procedures: &'a ProcedureExecution,
}

impl Pipeline<'_> {
    fn walk(&self, position: usize, row: &Row, sink: &mut dyn RowSink) -> Result<Flow> {
        let context = self.procedures.execution();
        read_budget::with_live_intermediates(context, || {
            read_budget::charge_candidate_work(1, "consuming streaming clauses")?;
            let Some(clause) = self.clauses.get(position) else {
                return sink.consume(row);
            };
            match clause {
                Clause::Use(_) => self.walk(position + 1, row, sink),
                Clause::Call(call) => {
                    let procedure = self.procedures.resolve(call)?;
                    let columns = procedure
                        .definition()
                        .outputs
                        .iter()
                        .map(|field| field.name.clone())
                        .collect::<Vec<_>>();
                    let (columns, indices) = yield_projection(&call.name, &columns, &call.yields)?;
                    let args = call
                        .args
                        .iter()
                        .map(|arg| eval(arg, row, self.params))
                        .collect::<Result<Vec<_>>>()?;
                    let mut cursor = procedure
                        .open(
                            args,
                            Invocation {
                                snapshot: Some(LocalSnapshot::new(
                                    self.graph.local_graph(),
                                    self.procedures.identity(),
                                )),
                                execution: context,
                                cache: Some(self.procedures.cache()),
                            },
                        )
                        .map_err(|error| procedures::invocation_error(error, call))?;
                    while let Some(batch) = cursor
                        .next_batch()
                        .map_err(|error| procedures::invocation_error(error, call))?
                    {
                        for values in batch.rows() {
                            let flow = read_budget::with_live_intermediates(context, || {
                                let mut next = clone_row(row, "binding streaming procedure rows")?;
                                for (column, &index) in columns.iter().zip(&indices) {
                                    next.insert(
                                        column.clone(),
                                        Bound::Value(clone_value(
                                            &values[index],
                                            "binding streaming procedure values",
                                        )?),
                                    );
                                }
                                if let Some(predicate) = &call.where_clause
                                    && !matches!(
                                        eval(predicate, &next, self.params)?,
                                        Value::Bool(true)
                                    )
                                {
                                    return Ok(Flow::Continue(()));
                                }
                                self.walk(position + 1, &next, sink)
                            })?;
                            if flow.is_break() {
                                return Ok(flow);
                            }
                        }
                    }
                    Ok(Flow::Continue(()))
                }
                Clause::With(with) => {
                    let rows = project_to_bindings(
                        &with.projection,
                        vec![clone_row(row, "streaming WITH")?],
                        self.params,
                    )?;
                    for next in &rows {
                        if let Some(predicate) = &with.where_clause
                            && !matches!(eval(predicate, next, self.params)?, Value::Bool(true))
                        {
                            continue;
                        }
                        let flow = self.walk(position + 1, next, sink)?;
                        if flow.is_break() {
                            return Ok(flow);
                        }
                    }
                    Ok(Flow::Continue(()))
                }
                Clause::Unwind(unwind) => {
                    if position + 1 == self.clauses.len()
                        && let Some(result) = sink.unwind(unwind, row, context)
                    {
                        return result;
                    }
                    // Keep one row and update only the scalar binding. Retained
                    // arrays are never cloned once per expanded list element.
                    let mut next = clone_row(row, "streaming UNWIND input")?;
                    next.insert(unwind.alias.clone(), Bound::Value(Value::Null));
                    let mut consume = |value| {
                        read_budget::with_live_intermediates(context, || {
                            read_budget::charge_candidate_work(1, "expanding UNWIND rows")?;
                            let binding = next
                                .get_mut(&unwind.alias)
                                .ok_or_else(|| gql_execution("missing UNWIND binding"))?;
                            *binding = Bound::Value(value);
                            let outcome = self.walk(position + 1, &next, sink);
                            if let Some(binding) = next.get_mut(&unwind.alias) {
                                *binding = Bound::Value(Value::Null);
                            }
                            outcome
                        })
                    };
                    if let Expr::List(items) = &unwind.expr {
                        for item in items {
                            let flow = consume(eval(item, row, self.params)?)?;
                            if flow.is_break() {
                                return Ok(flow);
                            }
                        }
                        Ok(Flow::Continue(()))
                    } else {
                        unwind_value(eval(&unwind.expr, row, self.params)?, &mut consume)
                    }
                }
                _ => Err(gql_execution("unsupported clause entered streaming plan")),
            }
        })
    }
}

fn unwind_value(value: Value, consume: &mut dyn FnMut(Value) -> Result<Flow>) -> Result<Flow> {
    fn each(
        values: impl IntoIterator<Item = Value>,
        consume: &mut dyn FnMut(Value) -> Result<Flow>,
    ) -> Result<Flow> {
        for value in values {
            let flow = consume(value)?;
            if flow.is_break() {
                return Ok(flow);
            }
        }
        Ok(Flow::Continue(()))
    }
    match value {
        Value::Null => Ok(Flow::Continue(())),
        Value::StringArray(values) => each(values.into_iter().map(Value::String), consume),
        Value::IntArray(values) => each(values.into_iter().map(Value::Int), consume),
        Value::FloatArray(values) => each(values.into_iter().map(Value::Float), consume),
        Value::Json(serde_json::Value::Array(values)) => {
            each(values.into_iter().map(Value::from_json), consume)
        }
        other => Err(gql_type(format!("UNWIND expects a list, got {other:?}"))),
    }
}

fn execute(
    graph: GraphRef<'_>,
    clauses: &[Clause],
    projection: &Projection,
    params: &CypherParameters,
    procedures: &ProcedureExecution,
    aggregate: bool,
) -> Result<CypherResultTable> {
    let context = procedures.execution();
    let pipeline = Pipeline {
        graph,
        clauses,
        params,
        procedures,
    };
    let mut output = RetainedRows {
        rows: Vec::new(),
        account: context.memory_account(),
    };
    if aggregate {
        let mut states = projection
            .items
            .iter()
            .map(|item| AggregateState::new(&item.expr))
            .collect::<Result<Vec<_>>>()?;
        let _ = pipeline.walk(
            0,
            &Row::new(),
            &mut AggregateSink {
                states: &mut states,
                items: &projection.items,
                params,
            },
        )?;
        output.push(
            states
                .into_iter()
                .map(AggregateState::finish)
                .collect::<Result<Vec<_>>>()?,
        )?;
        apply_skip_limit(&mut output.rows, projection, params)?;
    } else {
        let mut skip = projection
            .skip
            .as_ref()
            .map(|expr| eval_usize(expr, params, "SKIP"))
            .transpose()?
            .unwrap_or(0);
        let limit = projection
            .limit
            .as_ref()
            .map(|expr| eval_usize(expr, params, "LIMIT"))
            .transpose()?
            .unwrap_or(usize::MAX);
        if limit != 0 {
            let _ = pipeline.walk(0, &Row::new(), &mut |row: &Row| {
                if skip != 0 {
                    skip -= 1;
                    return Ok(Flow::Continue(()));
                }
                output.push(
                    projection
                        .items
                        .iter()
                        .map(|item| eval(&item.expr, row, params))
                        .collect::<Result<Vec<_>>>()?,
                )?;
                Ok(if output.rows.len() >= limit {
                    Flow::Break(())
                } else {
                    Flow::Continue(())
                })
            })?;
        }
    }
    let columns = projection
        .items
        .iter()
        .map(|item| {
            item.alias
                .clone()
                .unwrap_or_else(|| column_name(&item.expr))
        })
        .collect();
    Ok(CypherResultTable {
        columns,
        rows: output.rows,
    })
}

struct RetainedRows {
    rows: Vec<Vec<Value>>,
    account: MemoryAccount,
}
impl RetainedRows {
    fn push(&mut self, values: Vec<Value>) -> Result<()> {
        let bytes = values.iter().fold(
            values.capacity().saturating_mul(size_of::<Value>()),
            |bytes, value| bytes.saturating_add(read_budget::value_copy_bytes(value)),
        );
        self.account
            .charge(bytes)
            .map_err(procedures::translate_error)?;
        if self.rows.len() == self.rows.capacity() {
            let additional = self.rows.capacity().max(1);
            self.account
                .charge(additional.saturating_mul(size_of::<Vec<Value>>()))
                .map_err(procedures::translate_error)?;
            self.rows
                .try_reserve_exact(additional)
                .map_err(|error| procedures::translate_error(error.into()))?;
        }
        self.rows.push(values);
        Ok(())
    }
}
