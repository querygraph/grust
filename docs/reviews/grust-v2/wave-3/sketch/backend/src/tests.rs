use super::*;
use grust_lpg::LogicalType;
use grust_optimized_plan::Provenance;
use grust_resolved_plan::{Field, Plan as Resolved, Slot};
struct Storage;
impl StorageMapping for Storage {
    fn table(&self, _: &str, group: GroupId) -> Option<Vec<String>> {
        (group == GroupId(1)).then(|| vec!["schema.dot".into(), "odd`table".into()])
    }
}
fn plan(root: Relation) -> Plan {
    Plan {
        logical: Resolved {
            root,
            output: vec![],
        },
        access_order: vec![],
        rewrites: vec![],
        provenance: Provenance {
            catalog_revision: "c".into(),
            statistics_revision: None,
        },
    }
}
#[test]
fn dialect_quotes_identifiers_without_splitting_components() {
    let p = plan(Relation::Scan {
        graph: "g".into(),
        group: GroupId(1),
        fields: vec![Field {
            slot: Slot(0),
            name: "name`x".into(),
            ty: LogicalType::String,
            nullable: false,
        }],
    });
    assert_eq!(
        SailScanSql { storage: &Storage }.emit(&p).unwrap(),
        "SELECT `name``x` FROM `schema.dot`.`odd``table`"
    );
}
#[test]
fn graph_operator_is_refused_without_fallback() {
    let p = plan(Relation::GraphOperator {
        name: "shortest_path".into(),
        input: Box::new(Relation::Unit),
        arguments: vec![],
    });
    assert_eq!(
        SailScanSql { storage: &Storage }.emit(&p),
        Err(EmitError::Unsupported {
            backend: "sail-sql".into(),
            operator: "GraphOperator".into()
        })
    );
}
#[test]
fn unknown_storage_is_not_a_logical_group_name() {
    let p = plan(Relation::Scan {
        graph: "g".into(),
        group: GroupId(7),
        fields: vec![Field {
            slot: Slot(0),
            name: "x".into(),
            ty: LogicalType::Int64,
            nullable: false,
        }],
    });
    assert_eq!(
        SailScanSql { storage: &Storage }.emit(&p),
        Err(EmitError::MissingStorage {
            graph: "g".into(),
            group: GroupId(7)
        })
    );
}
