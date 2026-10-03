//! A small social-network schema, in the shape of the LDBC SNB: the examples
//! Sem's proposal names, resolved against it.

use grust_lpg::*;

fn snb() -> Schema {
    let id = || Property::required("id", LogicalType::Int64);
    Schema::builder()
        .vertex_group(
            "person",
            &["Person"],
            vec![id(), Property::new("name", LogicalType::String)],
            &["id"],
        )
        .vertex_group(
            "post",
            &["Post", "Message"],
            vec![id(), Property::new("content", LogicalType::String)],
            &["id"],
        )
        .vertex_group("comment", &["Comment", "Message"], vec![id()], &["id"])
        .vertex_group(
            "forum",
            &["Forum"],
            vec![id(), Property::new("title", LogicalType::String)],
            &["id"],
        )
        .vertex_group("tag", &["Tag"], vec![id()], &["id"])
        .edge_group(
            "knows",
            "KNOWS",
            "person",
            "person",
            Direction::Undirected,
            vec![],
        )
        .edge_group(
            "likes_post",
            "LIKES",
            "person",
            "post",
            Direction::Directed,
            vec![],
        )
        .edge_group(
            "likes_comment",
            "LIKES",
            "person",
            "comment",
            Direction::Directed,
            vec![],
        )
        .edge_group(
            "post_creator",
            "HAS_CREATOR",
            "post",
            "person",
            Direction::Directed,
            vec![],
        )
        .edge_group(
            "comment_creator",
            "HAS_CREATOR",
            "comment",
            "person",
            Direction::Directed,
            vec![],
        )
        .edge_group(
            "reply_of_post",
            "REPLY_OF",
            "comment",
            "post",
            Direction::Directed,
            vec![],
        )
        .edge_group(
            "reply_of_comment",
            "REPLY_OF",
            "comment",
            "comment",
            Direction::Directed,
            vec![],
        )
        .edge_group(
            "container_of",
            "CONTAINER_OF",
            "forum",
            "post",
            Direction::Directed,
            vec![],
        )
        .edge_group(
            "has_member",
            "HAS_MEMBER",
            "forum",
            "person",
            Direction::Directed,
            vec![],
        )
        .edge_group(
            "post_tag",
            "HAS_TAG",
            "post",
            "tag",
            Direction::Directed,
            vec![],
        )
        .constraint(
            "post_creator",
            Constraint::Cardinality(EdgeCardinality {
                max_out: Some(1),
                max_in: None,
            }),
        )
        .build()
        .unwrap()
}

fn names(schema: &Schema, groups: &[VpgId]) -> Vec<String> {
    groups
        .iter()
        .map(|g| schema.vertex(*g).unwrap().name.clone())
        .collect()
}

fn edge_names(schema: &Schema, groups: &[EpgId]) -> Vec<String> {
    groups
        .iter()
        .map(|g| schema.edge(*g).unwrap().name.clone())
        .collect()
}

#[test]
fn an_anonymous_edge_between_two_persons_is_knows() {
    let s = snb();
    let p = Pattern::node(LabelExpr::label("Person")).edge(
        LabelExpr::Any,
        PatternDirection::Either,
        Hops::ONE,
        LabelExpr::label("Person"),
    );
    let r = s.resolve(&p, &ResolveOptions::default());
    assert_eq!(edge_names(&s, &r.edge_groups[0]), ["knows"]);
    assert_eq!(
        r.paths.len(),
        1,
        "an undirected self-loop group is one hop, not two: {:?}",
        r.paths
    );
}

#[test]
fn an_anonymous_target_of_likes_is_every_message_group() {
    let s = snb();
    let p = Pattern::node(LabelExpr::label("Person")).edge(
        LabelExpr::label("LIKES"),
        PatternDirection::Outgoing,
        Hops::ONE,
        LabelExpr::Any,
    );
    let r = s.resolve(&p, &ResolveOptions::default());
    assert_eq!(names(&s, &r.node_groups[1]), ["post", "comment"]);
    assert_eq!(r.paths.len(), 2);
}

#[test]
fn sems_example_resolves_to_paths_of_one_to_five_hops() {
    // (a:Person)-[]-(b:Person){1,5}-[:KNOWS]-()
    let s = snb();
    let p = Pattern::node(LabelExpr::label("Person"))
        .edge(
            LabelExpr::Any,
            PatternDirection::Either,
            Hops::range(1, 5),
            LabelExpr::label("Person"),
        )
        .edge(
            LabelExpr::label("KNOWS"),
            PatternDirection::Either,
            Hops::ONE,
            LabelExpr::Any,
        );
    let r = s.resolve(&p, &ResolveOptions::default());
    assert!(!r.truncated);
    assert!(!r.paths.is_empty());
    for path in &r.paths {
        let hops = path.segments[0].len();
        assert!((1..=5).contains(&hops), "{path:?}");
        assert_eq!(s.vertex(path.nodes[1]).unwrap().name, "person");
        assert_eq!(edge_names(&s, &[path.segments[1][0].edge]), ["knows"]);
    }
    // The last node can only be a Person: KNOWS is Person-Person.
    assert_eq!(names(&s, &r.node_groups[2]), ["person"]);
    // Two hops through a post: Person -LIKES-> Post -HAS_CREATOR-> Person.
    assert!(r.paths.iter().any(|path| path.segments[0].len() == 2
        && edge_names(&s, &[path.segments[0][0].edge, path.segments[0][1].edge])
            == ["likes_post", "post_creator"]));
}

#[test]
fn infeasible_patterns_are_rejected_without_enumerating() {
    let s = snb();
    // A Tag has no outgoing edges.
    let p = Pattern::node(LabelExpr::label("Tag")).edge(
        LabelExpr::Any,
        PatternDirection::Outgoing,
        Hops::ONE,
        LabelExpr::Any,
    );
    assert!(!s.is_feasible(&p));
    assert!(s.resolve(&p, &ResolveOptions::default()).is_empty());
    let forum = s.vertex_by_name("forum").unwrap().id;
    let tag_from_forum = Pattern::node(LabelExpr::Any).edge(
        LabelExpr::Any,
        PatternDirection::Outgoing,
        Hops::range(1, 2),
        LabelExpr::label("Tag"),
    );
    assert!(s.is_feasible_from(forum, &tag_from_forum));
}

#[test]
fn label_expressions_and_unbounded_steps() {
    let s = snb();
    // (m:Message & !Post)-[:REPLY_OF]->{1,}(root:Post): a comment thread down to its post.
    let p = Pattern::node(LabelExpr::And(vec![
        LabelExpr::label("Message"),
        LabelExpr::Not(Box::new(LabelExpr::label("Post"))),
    ]))
    .edge(
        LabelExpr::label("REPLY_OF"),
        PatternDirection::Outgoing,
        Hops { min: 1, max: None },
        LabelExpr::label("Post"),
    );
    let r = s.resolve(
        &p,
        &ResolveOptions {
            max_paths: 100,
            unbounded_limit: 4,
        },
    );
    assert_eq!(names(&s, &r.node_groups[0]), ["comment"]);
    // comment->post, comment->comment->post, ... up to the enumeration cap of 1 + 4 hops.
    assert_eq!(r.paths.len(), 5);
}

#[test]
fn find_path_between_groups() {
    let s = snb();
    let (forum, tag) = (
        s.vertex_by_name("forum").unwrap().id,
        s.vertex_by_name("tag").unwrap().id,
    );
    let path = s.find_path(forum, tag, 3).unwrap();
    assert_eq!(
        edge_names(&s, &path.iter().map(|h| h.edge).collect::<Vec<_>>()),
        ["container_of", "post_tag"]
    );
    assert!(s.find_path(forum, tag, 1).is_none());
}

#[test]
fn validation_and_set_accessors() {
    let missing = Schema::builder()
        .vertex_group("v", &["V"], vec![], &["id"])
        .build();
    assert_eq!(
        missing,
        Err(LpgError::UnknownProperty {
            group: "v".into(),
            property: "id".into()
        })
    );
    let nullable = Schema::builder()
        .vertex_group(
            "v",
            &["V"],
            vec![Property::new("id", LogicalType::Int64)],
            &["id"],
        )
        .build();
    assert!(matches!(nullable, Err(LpgError::NullableKey { .. })));
    let s = snb()
        .to_builder()
        .set_property("person", Property::new("age", LogicalType::Int32))
        .build()
        .unwrap();
    assert_eq!(
        s.vertex_by_name("person")
            .unwrap()
            .property("age")
            .unwrap()
            .ty,
        LogicalType::Int32
    );
}
