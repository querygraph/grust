//! Sail SQL generation for the executable resolved IR.
mod expressions;
use crate::EmitError;
use grust_functions::{BackendSupport, FunctionDescriptor};
use grust_lpg::{GroupId, LogicalType};
use grust_resolved_plan::query::{Column, Expr, Node, Op, Plan, Value};
use grust_resolved_plan::{Field, Slot};
use grust_unresolved_plan::JoinKind;
use std::collections::{BTreeMap, HashMap};
pub trait QueryStorage {
    fn table(&self, graph: &str, group: GroupId) -> Option<Vec<String>>;
    fn column(&self, graph: &str, group: GroupId, column: &Column) -> Option<String>;
    fn function(&self, function: &FunctionDescriptor) -> Option<Vec<String>>;
}
pub struct SailSql<'a> {
    pub storage: &'a dyn QueryStorage,
    pub parameters: &'a HashMap<String, Expr>,
}
impl SailSql<'_> {
    pub fn emit(&self, plan: &Plan) -> Result<String, EmitError> {
        if plan.root.fields.is_empty() {
            return Err(refusal(
                "zero-column root requires an explicit row-envelope adapter",
            ));
        }
        let mut emitter = Emitter {
            adapter: self,
            ctes: Vec::new(),
            next: 0,
        };
        let root = emitter.node(&plan.root)?;
        let columns = if plan.root.fields.is_empty() {
            "1 AS `@unit`".into()
        } else {
            plan.root
                .fields
                .iter()
                .map(|f| format!("{} AS {}", slot(f.slot), quote(&f.name)))
                .collect::<Vec<_>>()
                .join(", ")
        };
        let keys = match &plan.root.op {
            Op::Sort { keys, .. } => Some(keys),
            Op::Slice { input, .. } => {
                if let Op::Sort { keys, .. } = &input.op {
                    Some(keys)
                } else {
                    None
                }
            }
            _ => None,
        };
        let mut sql = format!(
            "WITH {} SELECT {columns} FROM {root}",
            emitter.ctes.join(",\n")
        );
        if let Some(keys) = keys {
            if !keys.is_empty() {
                let env = environment(&plan.root.fields, "");
                sql.push_str(" ORDER BY ");
                sql.push_str(
                    &keys
                        .iter()
                        .map(|k| {
                            Ok(format!(
                                "{} {} NULLS {}",
                                emitter.expression(&k.expression, &env)?,
                                if k.descending { "DESC" } else { "ASC" },
                                if k.nulls_first { "FIRST" } else { "LAST" }
                            ))
                        })
                        .collect::<Result<Vec<_>, EmitError>>()?
                        .join(", "),
                );
            }
        }
        Ok(sql)
    }
}
struct Emitter<'a, 'b> {
    adapter: &'a SailSql<'b>,
    ctes: Vec<String>,
    next: usize,
}
impl Emitter<'_, '_> {
    fn node(&mut self, node: &Node) -> Result<String, EmitError> {
        let sql = match &node.op {
            Op::Unit => "SELECT 1 AS `@unit`".into(),
            Op::Empty => format!(
                "SELECT {} WHERE FALSE",
                node.fields
                    .iter()
                    .map(|f| Ok(format!(
                        "CAST(NULL AS {}) AS {}",
                        data_type(&f.ty)?,
                        slot(f.slot)
                    )))
                    .collect::<Result<Vec<_>, EmitError>>()?
                    .join(", ")
            ),
            Op::Scan {
                graph,
                group,
                columns,
            } => {
                let table = self
                    .adapter
                    .storage
                    .table(graph, *group)
                    .filter(|parts| !parts.is_empty())
                    .ok_or_else(|| EmitError::MissingStorage {
                        graph: graph.clone(),
                        group: *group,
                    })?;
                let cols = columns
                    .iter()
                    .map(|(s, c)| {
                        self.adapter
                            .storage
                            .column(graph, *group, c)
                            .map(|c| format!("{} AS {}", quote(&c), slot(*s)))
                            .ok_or_else(|| refusal("physical column mapping"))
                    })
                    .collect::<Result<Vec<_>, _>>()?;
                format!(
                    "SELECT {} FROM {}",
                    if cols.is_empty() {
                        "1 AS `@unit`".into()
                    } else {
                        cols.join(", ")
                    },
                    table.iter().map(|p| quote(p)).collect::<Vec<_>>().join(".")
                )
            }
            Op::Project {
                input,
                items,
                distinct,
            } => {
                let child = self.node(input)?;
                let env = environment(&input.fields, "");
                let items = items
                    .iter()
                    .map(|(s, e)| Ok(format!("{} AS {}", self.expression(e, &env)?, slot(*s))))
                    .collect::<Result<Vec<_>, EmitError>>()?;
                format!(
                    "SELECT {}{} FROM {child}",
                    if *distinct { "DISTINCT " } else { "" },
                    if items.is_empty() {
                        "1 AS `@unit`".into()
                    } else {
                        items.join(", ")
                    }
                )
            }
            Op::Filter { input, predicate } => {
                let child = self.node(input)?;
                format!(
                    "SELECT * FROM {child} WHERE {}",
                    self.expression(predicate, &environment(&input.fields, ""))?
                )
            }
            Op::Aggregate {
                input,
                groups,
                aggregates,
            } => {
                let child = self.node(input)?;
                let env = environment(&input.fields, "");
                let items = groups
                    .iter()
                    .chain(aggregates)
                    .map(|(s, e)| Ok(format!("{} AS {}", self.expression(e, &env)?, slot(*s))))
                    .collect::<Result<Vec<_>, EmitError>>()?;
                if items.is_empty() {
                    return Err(refusal("zero-column aggregation"));
                }
                let grouping = groups
                    .iter()
                    .map(|(_, e)| self.expression(e, &env))
                    .collect::<Result<Vec<_>, _>>()?;
                format!(
                    "SELECT {} FROM {child}{}",
                    items.join(", "),
                    if grouping.is_empty() {
                        String::new()
                    } else {
                        format!(" GROUP BY {}", grouping.join(", "))
                    }
                )
            }
            Op::Join {
                left,
                right,
                kind,
                condition,
            } => {
                let l = self.node(left)?;
                let r = self.node(right)?;
                let mut env = environment(&left.fields, "l.");
                env.extend(environment(&right.fields, "r."));
                let mut cols = left
                    .fields
                    .iter()
                    .map(|f| format!("l.{} AS {}", slot(f.slot), slot(f.slot)))
                    .collect::<Vec<_>>();
                if !matches!(kind, JoinKind::Semi | JoinKind::Anti) {
                    cols.extend(
                        right
                            .fields
                            .iter()
                            .map(|f| format!("r.{} AS {}", slot(f.slot), slot(f.slot))),
                    );
                }
                let (join, on) = match kind {
                    JoinKind::Cross => ("CROSS JOIN", String::new()),
                    other => (
                        match other {
                            JoinKind::Inner => "INNER JOIN",
                            JoinKind::Left => "LEFT JOIN",
                            JoinKind::Right => "RIGHT JOIN",
                            JoinKind::Full => "FULL JOIN",
                            JoinKind::Semi => "LEFT SEMI JOIN",
                            JoinKind::Anti => "LEFT ANTI JOIN",
                            JoinKind::Cross => unreachable!(),
                        },
                        format!(
                            " ON {}",
                            condition
                                .as_ref()
                                .map(|e| self.expression(e, &env))
                                .transpose()?
                                .unwrap_or_else(|| "TRUE".into())
                        ),
                    ),
                };
                format!(
                    "SELECT {} FROM {l} l {join} {r} r{on}",
                    if cols.is_empty() {
                        "1 AS `@unit`".into()
                    } else {
                        cols.join(", ")
                    }
                )
            }
            Op::Union { inputs, all } => {
                let mut branches = Vec::new();
                for input in inputs {
                    let child = self.node(input)?;
                    if input.fields.len() != node.fields.len() {
                        return Err(refusal("union schema mismatch"));
                    }
                    let cols = input
                        .fields
                        .iter()
                        .zip(&node.fields)
                        .map(|(src, dst)| {
                            let value = if src.ty == dst.ty {
                                slot(src.slot)
                            } else {
                                format!("CAST({} AS {})", slot(src.slot), data_type(&dst.ty)?)
                            };
                            Ok(format!("{value} AS {}", slot(dst.slot)))
                        })
                        .collect::<Result<Vec<_>, EmitError>>()?;
                    branches.push(format!(
                        "SELECT {} FROM {child}",
                        if cols.is_empty() {
                            "1 AS `@unit`".into()
                        } else {
                            cols.join(", ")
                        }
                    ));
                }
                if branches.is_empty() {
                    return Err(refusal("empty union"));
                }
                branches.join(if *all { " UNION ALL " } else { " UNION " })
            }
            Op::Unwind {
                input,
                list,
                slot: s,
            } => {
                let child = self.node(input)?;
                let env = environment(&input.fields, "");
                let cols = input
                    .fields
                    .iter()
                    .map(|f| slot(f.slot))
                    .collect::<Vec<_>>();
                format!(
                    "SELECT {}explode({}) AS {} FROM {child}",
                    if cols.is_empty() {
                        String::new()
                    } else {
                        format!("{}, ", cols.join(", "))
                    },
                    self.expression(list, &env)?,
                    slot(*s)
                )
            }
            Op::Sort { input, keys } => {
                let child = self.node(input)?;
                let env = environment(&input.fields, "");
                let keys = keys
                    .iter()
                    .map(|k| {
                        Ok(format!(
                            "{} {} NULLS {}",
                            self.expression(&k.expression, &env)?,
                            if k.descending { "DESC" } else { "ASC" },
                            if k.nulls_first { "FIRST" } else { "LAST" }
                        ))
                    })
                    .collect::<Result<Vec<_>, EmitError>>()?;
                format!(
                    "SELECT * FROM {child}{}",
                    if keys.is_empty() {
                        String::new()
                    } else {
                        format!(" ORDER BY {}", keys.join(", "))
                    }
                )
            }
            Op::PathSelect {
                input,
                partitions,
                length,
                all_ties,
            } => {
                let child = self.node(input)?;
                let env = environment(&input.fields, "");
                let partition = partitions
                    .iter()
                    .map(|e| self.expression(e, &env))
                    .collect::<Result<Vec<_>, _>>()?
                    .join(", ");
                let order = self.expression(length, &env)?;
                let columns = node
                    .fields
                    .iter()
                    .map(|f| slot(f.slot))
                    .collect::<Vec<_>>()
                    .join(", ");
                let function = if *all_ties { "rank" } else { "row_number" };
                format!("SELECT {columns} FROM (SELECT *, {function}() OVER (PARTITION BY {partition} ORDER BY {order}) AS `@path_rank` FROM {child}) ranked WHERE `@path_rank` = 1")
            }
            Op::Slice {
                input,
                offset,
                limit,
            } => {
                // ORDER BY and LIMIT must share a SQL level; a sorted subquery alone is insufficient.
                let (base, keys) = if let Op::Sort { input, keys } = &input.op {
                    (input.as_ref(), Some(keys))
                } else {
                    (input.as_ref(), None)
                };
                let child = self.node(base)?;
                let env = environment(&base.fields, "");
                let mut sql = format!("SELECT * FROM {child}");
                if let Some(keys) = keys {
                    if !keys.is_empty() {
                        sql.push_str(" ORDER BY ");
                        sql.push_str(
                            &keys
                                .iter()
                                .map(|k| {
                                    Ok(format!(
                                        "{} {} NULLS {}",
                                        self.expression(&k.expression, &env)?,
                                        if k.descending { "DESC" } else { "ASC" },
                                        if k.nulls_first { "FIRST" } else { "LAST" }
                                    ))
                                })
                                .collect::<Result<Vec<_>, EmitError>>()?
                                .join(", "),
                        );
                    }
                }
                if let Some(limit) = limit {
                    sql.push_str(&format!(" LIMIT {}", self.expression(limit, &env)?));
                }
                if let Some(offset) = offset {
                    sql.push_str(&format!(" OFFSET {}", self.expression(offset, &env)?));
                }
                sql
            }
        };
        let name = format!("q{}", self.next);
        self.next += 1;
        self.ctes.push(format!("{name} AS ({sql})"));
        Ok(name)
    }
}
fn environment(fields: &[Field], prefix: &str) -> BTreeMap<Slot, String> {
    fields
        .iter()
        .map(|f| (f.slot, format!("{prefix}{}", slot(f.slot))))
        .collect()
}
fn slot(s: Slot) -> String {
    format!("`s{}`", s.0)
}
fn quote(value: &str) -> String {
    format!("`{}`", value.replace('`', "``"))
}
fn refusal(operator: &str) -> EmitError {
    EmitError::Unsupported {
        backend: "sail-sql".into(),
        operator: operator.into(),
    }
}
fn data_type(ty: &LogicalType) -> Result<String, EmitError> {
    if grust_resolved_plan::query::is_null_type(ty) {
        return Ok("VOID".into());
    }
    Ok(match ty {
        LogicalType::Boolean => "BOOLEAN".into(),
        LogicalType::Int32 => "INT".into(),
        LogicalType::Int64 => "BIGINT".into(),
        LogicalType::Float32 => "FLOAT".into(),
        LogicalType::Float64 => "DOUBLE".into(),
        LogicalType::String => "STRING".into(),
        LogicalType::Binary => "BINARY".into(),
        LogicalType::Date => "DATE".into(),
        LogicalType::Decimal { precision, scale }
            if *precision > 0
                && *precision <= 38
                && *scale >= 0
                && (*scale as u8) <= *precision =>
        {
            format!("DECIMAL({precision},{scale})")
        }
        LogicalType::List(ty) => format!("ARRAY<{}>", data_type(ty)?),
        LogicalType::Struct(fields) => format!(
            "STRUCT<{}>",
            fields
                .iter()
                .map(|f| Ok(format!("{}:{}", quote(&f.name), data_type(&f.ty)?)))
                .collect::<Result<Vec<_>, EmitError>>()?
                .join(",")
        ),
        _ => return Err(refusal("logical type has no qualified Sail mapping")),
    })
}

/// Associated output keeps SQL and future physical formats outside the core IR.
pub trait QueryEmitter {
    type Output;
    fn emit_query(&self, plan: &Plan) -> Result<Self::Output, EmitError>;
}
impl QueryEmitter for SailSql<'_> {
    type Output = String;
    fn emit_query(&self, plan: &Plan) -> Result<String, EmitError> {
        self.emit(plan)
    }
}
