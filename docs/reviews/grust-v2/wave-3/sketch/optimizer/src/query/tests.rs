use super::*;
use grust_lpg::GroupId;
use grust_lpg::LogicalType;
use grust_optimized_plan::Estimate;
use grust_resolved_plan::query::Column;
use grust_resolved_plan::Field;
struct Stats;
impl Statistics for Stats {
    fn revision(&self) -> Option<&str> {
        Some("v1")
    }
    fn rows(&self, _: &str, group: GroupId) -> Estimate<u64> {
        Estimate::Known(match group.0 {
            1 => 100000,
            2 => 10000,
            _ => 10,
        })
    }
    fn distinct(&self, graph: &str, group: GroupId, _: &str) -> Estimate<u64> {
        self.rows(graph, group)
    }
    fn degree(&self, _: &str, _: GroupId) -> Estimate<crate::DegreeSummary> {
        Estimate::Unknown
    }
}
fn scan(id: u64) -> Node {
    Node {
        fields: vec![Field {
            slot: Slot(id as u32),
            name: format!("id{id}"),
            ty: LogicalType::Int64,
            nullable: false,
        }],
        op: Op::Scan {
            graph: "g".into(),
            group: GroupId(id),
            columns: vec![(Slot(id as u32), Column::Identity)],
        },
    }
}
fn equality(left: u32, right: u32) -> Expr {
    let field = |s| Expr {
        kind: Value::Slot(Slot(s)),
        ty: Some(LogicalType::Int64),
        nullable: false,
    };
    Expr {
        kind: Value::Binary {
            op: BinaryOp::Eq,
            left: Box::new(field(left)),
            right: Box::new(field(right)),
        },
        ty: Some(LogicalType::Boolean),
        nullable: false,
    }
}
fn join(left: Node, right: Node, condition: Expr, kind: JoinKind) -> Node {
    let mut fields = left.fields.clone();
    fields.extend(right.fields.clone());
    Node {
        fields,
        op: Op::Join {
            left: Box::new(left),
            right: Box::new(right),
            kind,
            condition: Some(condition),
        },
    }
}
#[test]
fn costs_choose_smaller_intermediate_and_preserve_output_slots() {
    let root = join(
        join(scan(1), scan(2), equality(1, 2), JoinKind::Inner),
        scan(3),
        equality(2, 3),
        JoinKind::Inner,
    );
    let before = estimate(&root, &Stats, &HashJoinCost).unwrap().cost;
    let fields = root.fields.clone();
    let opt = JoinOptimizer {
        statistics: Some(&Stats),
        cost: &HashJoinCost,
        max_relations: 8,
    }
    .optimize(Plan { root });
    assert!(!opt.trace.is_empty());
    assert!(opt.estimated_cost.unwrap() < before);
    assert_eq!(opt.logical.root.fields, fields);
    assert_eq!(opt.statistics_revision.as_deref(), Some("v1"));
}
#[test]
fn optional_join_boundary_is_preserved() {
    let root = join(scan(1), scan(2), equality(1, 2), JoinKind::Left);
    let opt = JoinOptimizer {
        statistics: Some(&Stats),
        cost: &HashJoinCost,
        max_relations: 8,
    }
    .optimize(Plan { root: root.clone() });
    assert_eq!(opt.logical.root, root);
}
#[test]
fn missing_statistics_keeps_exact_tree() {
    let root = join(scan(1), scan(2), equality(1, 2), JoinKind::Inner);
    let opt = JoinOptimizer {
        statistics: None,
        cost: &HashJoinCost,
        max_relations: 8,
    }
    .optimize(Plan { root: root.clone() });
    assert_eq!(opt.logical.root, root);
    assert_eq!(opt.estimated_cost, None);
}

struct Unknown;
impl Statistics for Unknown {
    fn revision(&self) -> Option<&str> {
        None
    }
    fn rows(&self, _: &str, _: GroupId) -> Estimate<u64> {
        Estimate::Unknown
    }
    fn distinct(&self, _: &str, _: GroupId, _: &str) -> Estimate<u64> {
        Estimate::Unknown
    }
    fn degree(&self, _: &str, _: GroupId) -> Estimate<crate::DegreeSummary> {
        Estimate::Unknown
    }
}
#[test]
fn unknown_rows_and_bounded_search_preserve_tree() {
    let root = join(
        join(scan(1), scan(2), equality(1, 2), JoinKind::Inner),
        scan(3),
        equality(2, 3),
        JoinKind::Inner,
    );
    for (stats, cap) in [
        (&Unknown as &dyn Statistics, 8),
        (&Stats as &dyn Statistics, 2),
    ] {
        let result = JoinOptimizer {
            statistics: Some(stats),
            cost: &HashJoinCost,
            max_relations: cap,
        }
        .optimize(Plan { root: root.clone() });
        assert_eq!(result.logical.root, root);
    }
}
#[test]
fn volatile_join_condition_is_never_reordered() {
    use grust_functions::*;
    let predicate = Expr {
        kind: Value::Call {
            function: Box::new(FunctionDescriptor {
                name: FunctionName::new("random_bool"),
                kind: FunctionKind::Scalar,
                signature: Signature {
                    arguments: vec![],
                    variadic: None,
                    result: ReturnType::Exact(LogicalType::Boolean),
                },
                nulls: NullSemantics::NonNull,
                backends: BackendSupport::Any,
                volatility: Volatility::Volatile,
                provider: "test".into(),
            }),
            arguments: vec![],
            distinct: false,
            filter: None,
        },
        ty: Some(LogicalType::Boolean),
        nullable: false,
    };
    let root = join(scan(1), scan(2), predicate, JoinKind::Inner);
    let result = JoinOptimizer {
        statistics: Some(&Stats),
        cost: &HashJoinCost,
        max_relations: 8,
    }
    .optimize(Plan { root: root.clone() });
    assert_eq!(result.logical.root, root);
}
