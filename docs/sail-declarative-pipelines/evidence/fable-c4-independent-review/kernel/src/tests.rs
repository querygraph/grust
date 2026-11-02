use super::*;

// The schema and selections mirror Spark 4.2.1 `ChangeArgsSuite`
// (sql/pipelines/src/test/scala/org/apache/spark/sql/pipelines/autocdc/ChangeArgsSuite.scala),
// whose source schema is `id INT NOT NULL, Name STRING, age INT`. Two toy
// resolvers stand in for the engine's: exact spelling, and ASCII
// case-insensitive, each returning the last field a name resolves to.
const SOURCE: [&str; 3] = ["id", "Name", "age"];

fn resolver(fields: &'static [&'static str], ignore_case: bool) -> impl Fn(&str) -> Option<usize> {
    move |name| {
        fields.iter().rposition(|field| {
            if ignore_case {
                field.eq_ignore_ascii_case(name)
            } else {
                *field == name
            }
        })
    }
}

fn exact_names(name: &str) -> Option<usize> {
    resolver(&SOURCE, false)(name)
}

fn ascii_names(name: &str) -> Option<usize> {
    resolver(&SOURCE, true)(name)
}

fn ignore_case(left: &str, right: &str) -> bool {
    left.eq_ignore_ascii_case(right)
}

fn selected(
    selection: Selection<'_, &str>,
    resolve: fn(&str) -> Option<usize>,
) -> Result<Vec<&'static str>, Unresolved> {
    select(SOURCE.len(), selection, resolve)
        .map(|indices| indices.into_iter().map(|i| SOURCE[i]).collect())
}

#[test]
fn include_empty_keeps_nothing_and_exclude_empty_keeps_everything() {
    let none: [&str; 0] = [];
    assert_eq!(selected(Selection::Include(&none), exact_names), Ok(vec![]));
    assert_eq!(
        selected(Selection::Exclude(&none), exact_names),
        Ok(vec!["id", "Name", "age"])
    );
}

#[test]
fn include_filters_by_exact_name_in_schema_order() {
    assert_eq!(
        selected(Selection::Include(&["age", "Name"]), exact_names),
        Ok(vec!["Name", "age"])
    );
}

#[test]
fn exclude_filters_by_exact_name() {
    assert_eq!(
        selected(Selection::Exclude(&["id"]), exact_names),
        Ok(vec!["Name", "age"])
    );
}

#[test]
fn include_reports_every_unresolved_name_in_request_order() {
    // Under exact resolution, "name" does not resolve to the field "Name".
    assert_eq!(
        selected(Selection::Include(&["name", "missing"]), exact_names),
        Err(Unresolved {
            names: vec!["name".into(), "missing".into()]
        })
    );
}

#[test]
fn exclude_reports_every_unresolved_name_in_request_order() {
    assert_eq!(
        selected(Selection::Exclude(&["NAME", "missing"]), exact_names),
        Err(Unresolved {
            names: vec!["NAME".into(), "missing".into()]
        })
    );
}

#[test]
fn include_resolves_through_the_resolver_and_keeps_schema_casing() {
    assert_eq!(
        selected(Selection::Include(&["AGE", "NAME"]), ascii_names),
        Ok(vec!["Name", "age"])
    );
}

#[test]
fn names_resolving_to_one_field_keep_it_once() {
    assert_eq!(
        selected(Selection::Include(&["name", "NAME"]), ascii_names),
        Ok(vec!["Name"])
    );
}

#[test]
fn exclude_resolves_through_the_resolver() {
    assert_eq!(
        selected(Selection::Exclude(&["name"]), ascii_names),
        Ok(vec!["id", "age"])
    );
}

#[test]
fn unresolved_names_keep_the_callers_spelling() {
    assert_eq!(
        selected(Selection::Include(&["NAME", "Missing"]), ascii_names),
        Err(Unresolved {
            names: vec!["Missing".into()]
        })
    );
}

#[test]
fn repeated_unresolved_names_are_reported_once() {
    assert_eq!(
        selected(Selection::Include(&["x", "x", "y"]), exact_names),
        Err(Unresolved {
            names: vec!["x".into(), "y".into()]
        })
    );
}

#[test]
fn literal_dot_and_mixed_case_names_resolve_exactly() {
    assert_eq!(
        select(
            2,
            Selection::Include(&["a.b"]),
            resolver(&["a.b", "c"], false)
        ),
        Ok(vec![0])
    );
    assert_eq!(
        select(SOURCE.len(), Selection::Include(&["Name"]), exact_names),
        Ok(vec![1])
    );
}

#[test]
fn the_resolver_decides_which_duplicate_field_a_name_selects() {
    // The kernel keeps whatever index the engine's policy returns; here the
    // toy resolvers return the last field, as an exact Spark map would.
    const FIELDS: [&str; 3] = ["a", "A", "a"];
    assert_eq!(
        select(3, Selection::Include(&["a"]), resolver(&FIELDS, false)),
        Ok(vec![2])
    );
    assert_eq!(
        select(3, Selection::Include(&["A"]), resolver(&FIELDS, true)),
        Ok(vec![2])
    );
    assert_eq!(
        select(3, Selection::Exclude(&["A"]), resolver(&FIELDS, true)),
        Ok(vec![0, 1])
    );
    assert_eq!(
        select(3, Selection::Include(&["a"]), |_| Some(1)),
        Ok(vec![1])
    );
}

#[test]
fn an_index_beyond_the_field_count_is_reported_as_unresolved() {
    assert_eq!(
        select(2, Selection::Include(&["x", "y"]), |name| (name == "x")
            .then_some(5)),
        Err(Unresolved {
            names: vec!["x".into(), "y".into()]
        })
    );
    assert_eq!(
        select(0, Selection::Include(&["x"]), |_| Some(0)).ok(),
        None
    );
}

#[test]
fn exact_is_plain_string_equality() {
    assert!(exact("a", "a"));
    assert!(!exact("a", "A"));
    assert!(!exact("", "a"));
}

#[test]
fn reserved_prefix_is_found_through_the_comparator() {
    let prefix = "__spark_autocdc_";
    assert_eq!(
        reserved(&["id", "__spark_autocdc_foo"], prefix, ignore_case),
        Some(1)
    );
    assert_eq!(
        reserved(&["id", "__SPARK_AUTOCDC_FOO"], prefix, ignore_case),
        Some(1)
    );
    assert_eq!(
        reserved(&["id", "__SPARK_AUTOCDC_FOO"], prefix, exact),
        None
    );
    // Exactly the prefix, and a field shorter than the prefix.
    assert_eq!(reserved(&["__spark_autocdc_"], prefix, exact), Some(0));
    assert_eq!(reserved(&["__spark_autocdc"], prefix, exact), None);
    assert_eq!(reserved(&["id", "seq"], prefix, ignore_case), None);
}

#[test]
fn unresolved_reports_the_first_missing_name() {
    assert_eq!(unresolved(&SOURCE, &["id", "name"], ignore_case), None);
    assert_eq!(unresolved(&SOURCE, &["id", "name"], exact), Some(1));
    assert_eq!(unresolved(&SOURCE, &["absent", "id"], ignore_case), Some(0));
    let none: [&str; 0] = [];
    assert_eq!(unresolved(&SOURCE, &none, exact), None);
}
