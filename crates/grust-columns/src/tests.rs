use super::*;

// The schema and selections mirror Spark 4.2.1 `ChangeArgsSuite`
// (sql/pipelines/src/test/scala/org/apache/spark/sql/pipelines/autocdc/ChangeArgsSuite.scala),
// whose source schema is `id INT NOT NULL, Name STRING, age INT`. ASCII
// case-insensitive equality stands in for the engine's comparator here.
const SOURCE: [&str; 3] = ["id", "Name", "age"];

fn ignore_case(left: &str, right: &str) -> bool {
    left.eq_ignore_ascii_case(right)
}

fn selected(
    selection: Selection<'_, &str>,
    matches: fn(&str, &str) -> bool,
) -> Result<Vec<&'static str>, Unresolved> {
    select(&SOURCE, selection, matches)
        .map(|indices| indices.into_iter().map(|i| SOURCE[i]).collect())
}

#[test]
fn include_empty_keeps_nothing_and_exclude_empty_keeps_everything() {
    let none: [&str; 0] = [];
    assert_eq!(selected(Selection::Include(&none), exact), Ok(vec![]));
    assert_eq!(
        selected(Selection::Exclude(&none), exact),
        Ok(vec!["id", "Name", "age"])
    );
}

#[test]
fn include_filters_by_exact_name_in_schema_order() {
    assert_eq!(
        selected(Selection::Include(&["age", "Name"]), exact),
        Ok(vec!["Name", "age"])
    );
}

#[test]
fn exclude_filters_by_exact_name() {
    assert_eq!(
        selected(Selection::Exclude(&["id"]), exact),
        Ok(vec!["Name", "age"])
    );
}

#[test]
fn include_reports_every_unresolved_name_in_request_order() {
    // Under exact matching, "name" does not match the field "Name".
    assert_eq!(
        selected(Selection::Include(&["name", "missing"]), exact),
        Err(Unresolved {
            names: vec!["name".into(), "missing".into()]
        })
    );
}

#[test]
fn exclude_reports_every_unresolved_name_in_request_order() {
    assert_eq!(
        selected(Selection::Exclude(&["NAME", "missing"]), exact),
        Err(Unresolved {
            names: vec!["NAME".into(), "missing".into()]
        })
    );
}

#[test]
fn include_matches_through_the_comparator_and_keeps_schema_casing() {
    assert_eq!(
        selected(Selection::Include(&["AGE", "NAME"]), ignore_case),
        Ok(vec!["Name", "age"])
    );
}

#[test]
fn names_matching_one_field_keep_it_once() {
    assert_eq!(
        selected(Selection::Include(&["name", "NAME"]), ignore_case),
        Ok(vec!["Name"])
    );
}

#[test]
fn exclude_matches_through_the_comparator() {
    assert_eq!(
        selected(Selection::Exclude(&["name"]), ignore_case),
        Ok(vec!["id", "age"])
    );
}

#[test]
fn unresolved_names_keep_the_callers_spelling() {
    assert_eq!(
        selected(Selection::Include(&["NAME", "Missing"]), ignore_case),
        Err(Unresolved {
            names: vec!["Missing".into()]
        })
    );
}

#[test]
fn repeated_unresolved_names_are_reported_once() {
    assert_eq!(
        selected(Selection::Include(&["x", "x", "y"]), exact),
        Err(Unresolved {
            names: vec!["x".into(), "y".into()]
        })
    );
}

#[test]
fn literal_dot_and_mixed_case_names_match_exactly() {
    let fields = ["a.b", "c"];
    assert_eq!(
        select(&fields, Selection::Include(&["a.b"]), exact),
        Ok(vec![0])
    );
    assert_eq!(
        select(&SOURCE, Selection::Include(&["Name"]), exact),
        Ok(vec![1])
    );
}

#[test]
fn field_index_uses_the_comparator() {
    assert_eq!(field_index(&SOURCE, "Name", exact), Some(1));
    assert_eq!(field_index(&SOURCE, "name", exact), None);
    assert_eq!(field_index(&SOURCE, "name", ignore_case), Some(1));
    assert_eq!(field_index(&SOURCE, "NAME", ignore_case), Some(1));
    assert_eq!(field_index(&SOURCE, "absent", ignore_case), None);
}

#[test]
fn duplicate_field_names_resolve_to_the_first_occurrence() {
    let fields = ["a", "A", "a"];
    assert_eq!(field_index(&fields, "a", exact), Some(0));
    assert_eq!(field_index(&fields, "A", ignore_case), Some(0));
    assert_eq!(
        select(&fields, Selection::Include(&["A"]), ignore_case),
        Ok(vec![0])
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
