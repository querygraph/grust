use grust_programmatic::{Graph, PlanBuilder};
use grust_unresolved_plan::{Expr, GraphRef, NamedExpr};
fn main() {
    let plan = Graph::new(GraphRef::Default)
        .vertices()
        .has_label("Person")
        .as_("person")
        .expect("nonempty binding")
        .out("KNOWS")
        .as_("friend")
        .expect("nonempty binding")
        .select(vec![NamedExpr {
            name: "name".into(),
            expression: Expr::variable("friend").property("name"),
        }])
        .limit(10)
        .finish();
    println!("{plan:#?}");
}
