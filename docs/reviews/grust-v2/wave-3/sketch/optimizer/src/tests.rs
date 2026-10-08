use super::*;
struct Stats;
impl Statistics for Stats {
    fn revision(&self) -> Option<&str> {
        Some("fixture")
    }
    fn rows(&self, _: &str, group: GroupId) -> Estimate<u64> {
        match group.0 {
            1 => Estimate::Unknown,
            2 => Estimate::Known(100),
            _ => Estimate::Known(0),
        }
    }
    fn distinct(&self, _: &str, _: GroupId, _: &str) -> Estimate<u64> {
        Estimate::Unknown
    }
    fn degree(&self, _: &str, _: GroupId) -> Estimate<DegreeSummary> {
        Estimate::Unknown
    }
}
#[test]
fn unknown_is_not_zero_and_ties_are_stable() {
    let ranked = rank_scans(
        "g",
        &[GroupId(1), GroupId(2), GroupId(3), GroupId(4)],
        &Stats,
    );
    assert_eq!(
        ranked.iter().map(|r| r.group).collect::<Vec<_>>(),
        vec![GroupId(3), GroupId(4), GroupId(2), GroupId(1)]
    );
    assert_eq!(ranked[3].rows, Estimate::Unknown);
}
#[test]
fn baseline_preserves_plan_and_explain_names_schema_paths() {
    use grust_resolved_plan::{Orientation, SchemaPath};
    let root = Relation::Match {
        input: Box::new(Relation::Unit),
        graph: "g".into(),
        alternatives: vec![SchemaPath {
            vertices: vec![GroupId(1), GroupId(2)],
            edges: vec![(GroupId(3), Orientation::Reversed)],
        }],
        bindings: vec![],
        predicates: vec![],
        optional: true,
    };
    let logical = Resolved {
        root,
        output: vec![],
    };
    let p = preserve(
        logical.clone(),
        Provenance {
            catalog_revision: "c".into(),
            statistics_revision: None,
        },
    );
    assert_eq!(p.logical, logical);
    assert!(p.rewrites.is_empty());
    let text = p.explain();
    assert!(text.contains("optional=true"));
    assert!(text.contains("Reversed"));
    assert!(text.contains("GroupId(3)"));
}
