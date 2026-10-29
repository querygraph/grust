#[test]
fn persisted_view_retains_original_query_text_and_comment() -> SparkResult<()> {
    let mut graph = graph();
    register_sql(
        &mut graph,
        "CREATE VIEW b COMMENT 'my persisted comment' AS SELECT * FROM range(1, 4);",
        "view.sql",
    )?;
    let [output] = graph.definition.outputs.as_slice() else {
        return Err(SparkError::internal("expected one persisted view"));
    };
    assert_eq!(output.name, name("b"));
    assert_ne!(output.kind, OutputType::TemporaryView);
    let Some(view) = &output.view else {
        return Err(SparkError::internal("expected persisted view definition"));
    };
    assert_eq!(view.definition, "SELECT * FROM range(1, 4)");
    assert_eq!(view.comment.as_deref(), Some("my persisted comment"));
    Ok(())
}

