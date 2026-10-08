//! Planning controls for the contracts whose exact bags are checked on native Sail.
use crate::fixtures::{registry, values, FixtureCatalog, Parameters, RelationPlugins, Storage};
use grust_backend::query::SailSql;
use grust_resolution::{query::QueryResolver, Context};
#[test]
fn all_semantics_sources_resolve_with_typed_public_outputs() {
    let registry = registry();
    let catalog = FixtureCatalog::default();
    let parameters = values();
    for case in crate::semantics_cases::cases(&registry).unwrap() {
        let plan = QueryResolver
            .resolve_iterative(
                &case.plan,
                &Context {
                    catalog: &catalog,
                    functions: &registry,
                    parameters: &Parameters,
                },
                &RelationPlugins,
            )
            .unwrap_or_else(|errors| panic!("{}: {errors:?}", case.name));
        assert!(
            plan.output().iter().all(|f| !f.name.starts_with('@')),
            "{} exposes an internal field",
            case.name
        );
        let program = SailSql {
            storage: &Storage,
            parameters: &parameters,
        }
        .emit_program(&plan)
        .unwrap_or_else(|error| panic!("{}: {error:?}", case.name));
        if case.name == "path_length" {
            assert!(
                program.steps.is_empty(),
                "length must not hydrate unrequested entities"
            );
        }
        if case.name == "full_path_value" {
            assert_eq!(
                program.steps.len(),
                2,
                "one ordered columnar lookup each for nodes and relationships"
            );
        }
        if case.name == "subquery_scalar_bag" {
            assert_eq!(
                program.steps.len(),
                1,
                "duplicate outer rows need a single stable materialized row identity"
            );
        }
    }
}
