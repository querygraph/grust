use super::*;
use grust_functions::Volatility;
use grust_lpg::GroupId;
use grust_optimized_plan::Estimate;
use grust_resolved_plan::query::Column;
pub(super) struct Est {
    pub(super) rows: f64,
    pub(super) cost: f64,
}
pub(super) fn estimate(
    node: &Node,
    stats: &dyn Statistics,
    cost: &dyn JoinCostModel,
) -> Option<Est> {
    let e = match &node.op {
        Op::Unit => Est {
            rows: 1.0,
            cost: 0.0,
        },
        Op::Empty => Est {
            rows: 0.0,
            cost: 0.0,
        },
        Op::Scan { graph, group, .. } => {
            let Estimate::Known(rows) = stats.rows(graph, *group) else {
                return None;
            };
            let rows = rows as f64;
            Est {
                rows,
                cost: cost.scan(rows),
            }
        }
        Op::Filter { input, predicate } => {
            let e = estimate(input, stats, cost)?;
            Est {
                rows: e.rows * selectivity(predicate, &origins(input), stats),
                cost: e.cost + e.rows,
            }
        }
        Op::Result { input, .. }
        | Op::Project { input, .. }
        | Op::Sort { input, .. }
        | Op::Slice { input, .. } => estimate(input, stats, cost)?,
        Op::Join {
            left,
            right,
            kind: JoinKind::Inner,
            condition,
        } => {
            let l = estimate(left, stats, cost)?;
            let r = estimate(right, stats, cost)?;
            let rows = l.rows
                * r.rows
                * condition
                    .as_ref()
                    .map(|e| selectivity(e, &origins(node), stats))
                    .unwrap_or(1.0);
            Est {
                rows,
                cost: l.cost + r.cost + cost.join(l.rows, r.rows, rows),
            }
        }
        Op::Union { inputs, .. } => {
            let mut e = Est {
                rows: 0.0,
                cost: 0.0,
            };
            for input in inputs {
                let c = estimate(input, stats, cost)?;
                e.rows += c.rows;
                e.cost += c.cost;
            }
            e
        }
        _ => return None,
    };
    (e.rows.is_finite() && e.cost.is_finite() && e.cost >= 0.0).then_some(e)
}
pub(super) type Origins = BTreeMap<Slot, (String, GroupId, Column)>;
pub(super) fn origins(node: &Node) -> Origins {
    match &node.op {
        Op::Scan {
            graph,
            group,
            columns,
        } => columns
            .iter()
            .map(|(s, c)| (*s, (graph.clone(), *group, c.clone())))
            .collect(),
        Op::Project { input, items, .. } => {
            let source = origins(input);
            items
                .iter()
                .filter_map(|(s, e)| {
                    if let Value::Slot(src) = e.kind {
                        source.get(&src).cloned().map(|o| (*s, o))
                    } else {
                        None
                    }
                })
                .collect()
        }
        Op::Result { input, .. }
        | Op::Filter { input, .. }
        | Op::Sort { input, .. }
        | Op::Slice { input, .. } => origins(input),
        Op::Join { left, right, .. } => {
            let mut m = origins(left);
            m.extend(origins(right));
            m
        }
        _ => BTreeMap::new(),
    }
}
fn ndv(e: &Expr, origins: &Origins, stats: &dyn Statistics) -> Option<f64> {
    let Value::Slot(s) = e.kind else {
        return None;
    };
    let (graph, group, column) = origins.get(&s)?;
    let estimate = match column {
        Column::Identity => stats.rows(graph, *group),
        Column::Property(name) => stats.distinct(graph, *group, name),
        Column::Source => stats.endpoint_distinct(graph, *group, true),
        Column::Target => stats.endpoint_distinct(graph, *group, false),
    };
    match estimate {
        Estimate::Known(n) if n > 0 => Some(n as f64),
        _ => None,
    }
}
pub(super) fn selectivity(expr: &Expr, origins: &Origins, stats: &dyn Statistics) -> f64 {
    match &expr.kind {
        Value::Binary {
            op: BinaryOp::And,
            left,
            right,
        } => selectivity(left, origins, stats) * selectivity(right, origins, stats),
        Value::Binary {
            op: BinaryOp::Eq,
            left,
            right,
        } => match (ndv(left, origins, stats), ndv(right, origins, stats)) {
            (Some(l), Some(r)) => 1.0 / l.max(r),
            (Some(n), None) if matches!(right.kind, Value::Literal(_)) => 1.0 / n,
            (None, Some(n)) if matches!(left.kind, Value::Literal(_)) => 1.0 / n,
            _ => 1.0,
        },
        _ => 1.0,
    }
}
pub fn references(e: &Expr) -> BTreeSet<Slot> {
    let mut slots = BTreeSet::new();
    walk(e, &mut |v| {
        if let Value::Slot(s) = v.kind {
            slots.insert(s);
        }
    });
    slots
}
fn walk(e: &Expr, visit: &mut impl FnMut(&Expr)) {
    visit(e);
    match &e.kind {
        Value::Binary { left, right, .. } | Value::ListDisjoint { left, right } => {
            walk(left, visit);
            walk(right, visit);
        }
        Value::Unary { argument, .. }
        | Value::ListDropFirst(argument)
        | Value::ListLength(argument)
        | Value::EntityList {
            identities: argument,
            ..
        }
        | Value::Cast { argument, .. } => walk(argument, visit),
        Value::Call {
            arguments, filter, ..
        } => {
            for a in arguments {
                walk(a, visit);
            }
            if let Some(f) = filter {
                walk(f, visit);
            }
        }
        Value::ListConcat(items) | Value::List(items) => {
            for a in items {
                walk(a, visit);
            }
        }
        Value::Struct(items) => {
            for (_, a) in items {
                walk(a, visit);
            }
        }
        Value::Property { object, .. } => walk(object, visit),
        Value::Case {
            branches,
            otherwise,
        } => {
            for (a, b) in branches {
                walk(a, visit);
                walk(b, visit);
            }
            walk(otherwise, visit);
        }
        _ => {}
    }
}
pub(super) fn pure(e: &Expr) -> bool {
    let mut result = true;
    walk(e, &mut |e| {
        if let Value::Call { function, .. } = &e.kind {
            result &= function.volatility == Volatility::Immutable;
        }
    });
    result
}
pub(super) fn pure_node(n: &Node) -> bool {
    match &n.op {
        Op::Project { input, items, .. } => pure_node(input) && items.iter().all(|(_, e)| pure(e)),
        Op::Filter { input, predicate } => pure_node(input) && pure(predicate),
        Op::Scan { .. } | Op::Unit | Op::Empty => true,
        _ => false,
    }
}
