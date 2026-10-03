//! Write-plan construction from the typed AST.
//!
//! Every writable statement is parsed by [`crate::parser`]; this module walks
//! the resulting [`ast::Query`] and builds the [`GraphMutationPlan`] (and the
//! variable bindings the `RETURN` surface reads) with the same
//! [`CypherMutationPlanner`] state and lowering helpers the planner has always
//! used. No statement text is searched for keywords, split on commas, or cut
//! at parentheses: clause boundaries, patterns, map keys, quoted names and
//! literals all come from the parser.
//!
//! # Statement shapes
//!
//! A script is split at top-level `;` and each statement is planned against
//! the bindings left by the statements before it. The accepted shapes, and
//! where each is planned:
//!
//! | Shape | Planned by | Operations |
//! |---|---|---|
//! | `CREATE`/`MERGE (n:L {id: ..})` | `plan_ast_upsert` | `UpsertNode` (an id may be generated for `CREATE`) |
//! | `CREATE`/`MERGE (a)-[r:T]->(b)`, endpoints by `id` or bound variable | `plan_ast_upsert` | `UpsertEdge` |
//! | `DELETE (n)`, `n` bound by an earlier statement | `plan_ast_delete` | `DeleteNode` |
//! | `MATCH <node> [WHERE] DELETE n` | `plan_ast_match_delete` | `DeleteNode`, `DeleteMatchingNodes` |
//! | `MATCH [p =] <edge> [WHERE] DELETE r, a, b` | `plan_ast_match_delete` | `DeleteEdge`, `DeleteMatchingEdges`, `DeleteRelationshipRows`, `DeleteNode` |
//! | `MATCH (a), (b) [WHERE] CREATE`/`MERGE [p =] (a)-[r:T]->(b), ...` | `plan_ast_match_upsert` | `UpsertEdge`, `UpsertEdgesFromNodeMatches` |
//! | `MATCH <node> [WHERE] SET n.k = v, n += {..}, n.k = n.j <op> x` | `plan_ast_match_set` | `PatchNode`, `PatchMatchingNodes`, `RemoveNodeProps`, `RemoveMatchingNodeProps`, `UpdateMatchingNodeProperty` |
//! | `MATCH [p =] <edge> [WHERE] SET r.k = ...` | `plan_ast_match_set` | `PatchEdge`, `PatchMatchingEdges`, `RemoveEdgeProps`, `RemoveMatchingEdgeProps`, `UpdateMatchingEdgeProperty` |
//! | `MATCH (a), (b)` or `(a)-[:T]-(b)`, `SET a.k = b.j <op> x` | `plan_ast_match_set` | `SetMatchingNodeFromNode` |
//! | `MATCH <node or edge> [WHERE] REMOVE x.k` | `plan_ast_match_remove` | `RemoveNodeProps`, `RemoveMatchingNodeProps`, `RemoveEdgeProps`, `RemoveMatchingEdgeProps` |
//!
//! A returning write (`..._with_return_options`) is the same script with a
//! `RETURN` on its final statement; the `RETURN` text is handed to the
//! projection parser in `returning.rs` with the bindings the plan produced.
//!
//! The choice between an id-resolved single-identity operation and a
//! row-producing match, and the binding of node, relationship and path
//! variables, are the planner's lowering helpers in `planner.rs`
//! (`lower_match_*`, `plan_match_edge_segment`, `resolve_node_id`,
//! `bind_*`); this module supplies them with patterns, predicates and
//! assignments read from the AST. `WHERE` expressions are lowered by the
//! boolean normaliser in `where_clause.rs`, whose leaves are AST expressions
//! ([`where_predicate_from_expr`]).
//!
//! # Unsupported clauses
//!
//! The string planner cut each statement at the first write keyword and
//! read everything after it as part of that clause. A statement with a
//! clause it does not support (`WITH`, a second write clause, `UNION`, a
//! `RETURN` in the non-returning entry point) therefore failed while
//! reading a value, a pattern or a `WHERE` comparison, and the error's
//! variant depended on where. The AST planner keeps those variants (see
//! [`trailing_value_error`] and [`convert::leaf_followed_by_text_error`]).

mod convert;
mod entry;
mod match_write;

use crate::ast::{self, Clause, Expr, PathPattern, RelationshipPattern};
use crate::lexer::{Keyword, Token};
use crate::*;

use convert::{checked_variable, describe_expr, node_from_pattern, relationship_from_pattern};
pub(crate) use convert::{leaf_followed_by_text_error, where_predicate_from_expr};
pub(crate) use entry::{ast_mutation_plan_with_options, ast_mutation_plan_with_return_options};

/// Parse one `;`-free writable statement with the typed parser.
pub(crate) fn parse_write_statement(statement: &str) -> Result<ast::Query> {
    crate::parser::parse_query(statement).map_err(|error| error.into_grust(statement))
}

/// The byte span of the first top-level `RETURN` keyword in `statement`, if
/// any. "Top level" means outside parentheses, brackets and braces, and not a
/// property key after `.` (`{return: 1}` and `n.return` are names). Tokens
/// after a lexical error are not examined.
pub(crate) fn top_level_return(statement: &str) -> Option<crate::lexer::Span> {
    let (tokens, _) = crate::lexer::tokenize_prefix(statement);
    let mut depth = 0usize;
    let mut previous = None;
    for token in &tokens {
        match &token.token {
            Token::LParen | Token::LBracket | Token::LBrace => depth += 1,
            Token::RParen | Token::RBracket | Token::RBrace => depth = depth.saturating_sub(1),
            Token::Keyword(Keyword::Return) if depth == 0 && previous != Some(&Token::Dot) => {
                return Some(token.span);
            }
            _ => {}
        }
        previous = Some(&token.token);
    }
    None
}

/// Split the final statement of a returning write into its mutation part and
/// the text of its `RETURN` projection.
pub(crate) fn split_final_return_ast(statement: &str) -> Result<(&str, &str)> {
    let Some(span) = top_level_return(statement) else {
        return Err(cypher_syntax(
            "writable Cypher returning execution requires a final RETURN clause",
        ));
    };
    let mutation = statement[..span.start].trim();
    let return_clause = statement[span.end..].trim();
    if return_clause.is_empty() {
        return Err(cypher_syntax("RETURN requires at least one projection"));
    }
    Ok((mutation, return_clause))
}

/// True when `relationship` was written with brackets (`-[...]->`), not as a
/// bare arrow (`-->`).
fn has_brackets(source: &str, relationship: &RelationshipPattern) -> bool {
    relationship.span.text(source).contains('[')
}

/// The error for a `SET` value that unsupported text (a later clause, or a
/// `UNION`) follows, starting at byte `tail`: the string planner read that
/// text as part of the value.
pub(crate) fn trailing_value_error(source: &str, value: &Expr, tail: usize) -> GrustError {
    let mut rightmost = value;
    while let Expr::Binary { rhs, .. } = rightmost {
        rightmost = rhs;
    }
    let tail = source[tail..].trim();
    if matches!(rightmost, Expr::Parameter(_)) {
        return cypher_syntax(format!(
            "unsupported Cypher parameter reference: {} {tail}",
            describe_expr(rightmost)
        ));
    }
    GrustError::Unsupported(format!(
        "unsupported Cypher literal value: {} {tail}",
        describe_expr(value)
    ))
}

/// A pattern's start node, which must be a plain `( ... )`: no `shortestPath`
/// wrapper, and no path variable unless the caller has already taken it as
/// the statement's path binding (`path_bound`).
fn plain_start_node(pattern: &PathPattern, path_bound: bool) -> Result<&ast::NodePattern> {
    if (pattern.variable.is_some() && !path_bound) || pattern.shortest.is_some() {
        return Err(GrustError::Unsupported(
            "writable Cypher node pattern must start with '('".to_string(),
        ));
    }
    Ok(&pattern.start)
}

/// True when any pattern has a directed (`->` or `<-`) relationship.
fn has_directed_relationship(patterns: &[PathPattern]) -> bool {
    patterns.iter().any(|pattern| {
        pattern
            .segments
            .iter()
            .any(|segment| segment.relationship.direction != ast::Direction::Undirected)
    })
}

impl CypherMutationPlanner {
    /// Plan one parsed writable statement.
    pub(crate) fn plan_ast_statement(
        &mut self,
        source: &str,
        query: &ast::Query,
    ) -> Result<GraphMutationPlan> {
        // The clauses in source order. A `UNION` arm is not a write form; its
        // clauses are reported as unsupported text after the write clause.
        let clauses = query
            .parts
            .iter()
            .flat_map(|part| part.query.clauses.iter())
            .collect::<Vec<_>>();
        match clauses.split_first() {
            Some((Clause::Match(match_clause), rest)) if !match_clause.optional => {
                self.plan_ast_match(source, match_clause, rest)
            }
            _ => self.plan_ast_bare(source, &clauses),
        }
    }

    /// A statement without a leading `MATCH`.
    fn plan_ast_bare(&mut self, source: &str, clauses: &[&Clause]) -> Result<GraphMutationPlan> {
        let has_set = clauses.iter().any(|clause| match clause {
            Clause::Set(_) => true,
            Clause::Merge(merge) => !merge.on_create.is_empty() || !merge.on_match.is_empty(),
            _ => false,
        });
        if has_set {
            return Err(cypher_syntax("writable Cypher SET is not supported in v1"));
        }
        if clauses
            .iter()
            .any(|clause| matches!(clause, Clause::Remove(_)))
        {
            return Err(cypher_syntax(
                "writable Cypher REMOVE is not supported in v1",
            ));
        }
        let tail = (clauses.len() > 1).then(|| clauses[0].span().end);
        match clauses.first() {
            Some(Clause::Create(create)) => self.plan_ast_upsert(
                source,
                &create.patterns,
                tail,
                GraphMutationPlanKind::Create,
            ),
            Some(Clause::Merge(merge)) => self.plan_ast_upsert(
                source,
                std::slice::from_ref(&merge.pattern),
                tail,
                GraphMutationPlanKind::Merge,
            ),
            Some(Clause::Delete(delete)) if !delete.detach => {
                self.plan_ast_delete(source, delete, tail)
            }
            _ => Err(cypher_syntax(format!(
                "unsupported writable Cypher statement; expected CREATE, MERGE, or DELETE: {source}"
            ))),
        }
    }

    /// `CREATE`/`MERGE` of one node, or of one edge between id-resolved
    /// endpoints.
    fn plan_ast_upsert(
        &mut self,
        source: &str,
        patterns: &[PathPattern],
        tail: Option<usize>,
        kind: GraphMutationPlanKind,
    ) -> Result<GraphMutationPlan> {
        let junk_end = tail.map(|_| source.len());
        if has_directed_relationship(patterns) {
            let (from, relationship, to) =
                self.ast_directed_edge(source, patterns, false, junk_end, "edge mutation")?;
            let from_id = self.resolve_node_id(&from, "edge mutation source node")?;
            let to_id = self.resolve_node_id(&to, "edge mutation destination node")?;
            let relationship = relationship_from_pattern(relationship, &self.parameters)?;
            let edge = self.bind_created_edge(&relationship, from_id, to_id)?;
            return Ok(GraphMutationPlan::new(vec![
                GraphMutationPlanOp::UpsertEdge { kind, edge },
            ]));
        }

        let first = &patterns[0];
        let node = node_from_pattern(plain_start_node(first, false)?, &self.parameters)?;
        if !first.segments.is_empty() || patterns.len() > 1 || junk_end.is_some() {
            let end = junk_end.unwrap_or_else(|| patterns[patterns.len() - 1].span.end);
            return Err(cypher_syntax(format!(
                "unsupported writable Cypher node pattern suffix: {}",
                source[first.start.span.end..end].trim()
            )));
        }
        let label = node
            .label
            .clone()
            .ok_or_else(|| cypher_syntax("node CREATE/MERGE requires a label"))?;
        let id = match optional_string_prop(&node.props, "id") {
            Some(id) => id,
            None if kind == GraphMutationPlanKind::Create
                && self.node_id_policy == CypherNodeIdPolicy::GenerateForCreate =>
            {
                let id = format!("node-{}", uuid::Uuid::new_v4());
                self.generated_node_ids.push(CypherGeneratedNodeId {
                    variable: node.variable.clone(),
                    id: NodeId::new(id.clone()),
                });
                id
            }
            None => {
                return Err(cypher_unresolved_identity(
                    "node CREATE/MERGE requires explicit string property 'id'",
                ));
            }
        };
        self.bind_node_variable(&node, &NodeId::new(id.clone()))?;
        Ok(GraphMutationPlan::new(vec![
            GraphMutationPlanOp::UpsertNode {
                kind,
                node: Node::new(label, id, node.props),
            },
        ]))
    }

    /// `DELETE (n)` of a node bound by an earlier statement.
    fn plan_ast_delete(
        &mut self,
        source: &str,
        delete: &ast::DeleteClause,
        tail: Option<usize>,
    ) -> Result<GraphMutationPlan> {
        // The target is a node pattern naming a bound variable, `(n)`.
        let (tokens, _) = crate::lexer::tokenize_prefix(delete.span.text(source));
        let parenthesized = matches!(
            tokens
                .get(1..4)
                .map(|tokens| tokens.iter().map(|token| &token.token).collect::<Vec<_>>())
                .as_deref(),
            Some([
                Token::LParen,
                Token::Identifier(_) | Token::QuotedIdentifier(_),
                Token::RParen
            ])
        );
        let (Expr::Variable(variable), true) = (&delete.targets[0], parenthesized) else {
            return Err(GrustError::Unsupported(
                "writable Cypher node pattern must start with '('".to_string(),
            ));
        };
        let node = ParsedCypherNode {
            variable: Some(checked_variable(variable)?),
            label: None,
            props: Props::new(),
            predicates: Vec::new(),
        };
        if delete.targets.len() > 1 || tail.is_some() {
            return Err(cypher_syntax(
                "unsupported writable Cypher delete pattern suffix: only one DELETE target is supported",
            ));
        }
        let id = self.resolve_node_id(&node, "node DELETE")?;
        Ok(GraphMutationPlan::new(vec![
            GraphMutationPlanOp::DeleteNode(id),
        ]))
    }

    /// The edge of a resolved-endpoint `CREATE`/`MERGE`, with its relationship
    /// variable bound.
    pub(crate) fn bind_created_edge(
        &mut self,
        relationship: &ParsedCypherRelationship,
        from: NodeId,
        to: NodeId,
    ) -> Result<Edge> {
        let mut edge = Edge::new(
            relationship.label.clone(),
            from,
            to,
            relationship.props.clone(),
        );
        if let Some(id) = edge
            .props
            .get("id")
            .and_then(Value::as_str)
            .map(str::to_string)
        {
            edge = edge.with_id(id);
        }
        self.bind_edge_variable(
            relationship,
            CypherBoundEdgeIdentity {
                from: edge.from.clone(),
                label: edge.label.clone(),
                to: edge.to.clone(),
                id: edge.id.clone(),
            },
        )?;
        Ok(edge)
    }

    /// The first pattern's directed relationship, normalised so `from` is the
    /// arrow's source: `(a)-[r]->(b)` and `(b)<-[r]-(a)` both give `(a, r, b)`.
    /// Anything after the second node (another segment, another pattern, or
    /// unsupported text ending at `junk_end`) is a syntax error.
    pub(crate) fn ast_directed_edge<'p>(
        &self,
        source: &str,
        patterns: &'p [PathPattern],
        path_bound: bool,
        junk_end: Option<usize>,
        context: &str,
    ) -> Result<(ParsedCypherNode, &'p RelationshipPattern, ParsedCypherNode)> {
        let first_pattern = &patterns[0];
        let first = node_from_pattern(
            plain_start_node(first_pattern, path_bound)?,
            &self.parameters,
        )?;
        let directed_error = || {
            cypher_syntax(format!(
                "{context} requires a directed -[...]-> or <-[...]- pattern"
            ))
        };
        let Some(segment) = first_pattern.segments.first() else {
            return Err(directed_error());
        };
        if !has_brackets(source, &segment.relationship) {
            return Err(directed_error());
        }
        let incoming = match segment.relationship.direction {
            ast::Direction::Incoming => true,
            ast::Direction::Outgoing => false,
            ast::Direction::Undirected => {
                return Err(cypher_syntax(format!(
                    "{context} requires outgoing '->' direction"
                )));
            }
        };
        let second = node_from_pattern(&segment.node, &self.parameters)?;
        if first_pattern.segments.len() > 1 || patterns.len() > 1 || junk_end.is_some() {
            let end = junk_end.unwrap_or_else(|| patterns[patterns.len() - 1].span.end);
            return Err(cypher_syntax(format!(
                "unsupported writable Cypher edge pattern suffix: {}",
                source[segment.node.span.end..end].trim()
            )));
        }
        Ok(if incoming {
            (second, &segment.relationship, first)
        } else {
            (first, &segment.relationship, second)
        })
    }

    /// [`Self::ast_directed_edge`] plus the relationship's type and
    /// properties.
    pub(crate) fn ast_edge_match(
        &self,
        source: &str,
        patterns: &[PathPattern],
        path_bound: bool,
        junk_end: Option<usize>,
    ) -> Result<ParsedCypherEdgeMatch> {
        let (from, relationship, to) =
            self.ast_directed_edge(source, patterns, path_bound, junk_end, "edge mutation")?;
        let relationship = relationship_from_pattern(relationship, &self.parameters)?;
        Ok(ParsedCypherEdgeMatch {
            from,
            relationship,
            to,
        })
    }
}
