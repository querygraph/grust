//! `MATCH ... [WHERE ...]` followed by one write clause: `DELETE`,
//! `CREATE`/`MERGE` of relationships between matched nodes, `SET`, or
//! `REMOVE`.
//!
//! The lowering decisions (id-resolved single-identity operations versus
//! row-producing matches, binding of node, relationship and path variables)
//! are the planner's; this module supplies them with patterns, predicates and
//! assignments read from the AST.

use super::convert::{
    checked_variable, literal_value, mark_last_leaf_followed_by_text, node_from_pattern,
    property_ref, props_from_entries, where_boolean_from_expr,
};
use super::*;
use crate::ast::{MatchClause, RemoveItem, SetItem};

/// A `MATCH`-led write statement's match part.
pub(super) struct MatchWrite<'q> {
    source: &'q str,
    match_clause: &'q MatchClause,
    /// Where unsupported text after the `MATCH` patterns ends, when the
    /// statement has clauses between `MATCH` and its write clause, or
    /// `DETACH`. The string planner read that text as part of the `WHERE`
    /// expression or the last pattern, so it is reported there.
    junk_end: Option<usize>,
    /// When the `MATCH` has no `WHERE` but that text has one (`MATCH (n) WITH
    /// n WHERE ...`): the string planner split the statement there and read
    /// the rest as the `MATCH`'s `WHERE`. True when more unsupported text
    /// follows that expression.
    junk_where: Option<(&'q Expr, bool)>,
}

impl MatchWrite<'_> {
    fn patterns(&self) -> &[PathPattern] {
        &self.match_clause.patterns
    }

    fn patterns_end(&self) -> usize {
        self.patterns()[self.patterns().len() - 1].span.end
    }

    /// The text after the first pattern's start node that the planner does
    /// not support, for suffix errors.
    fn suffix_after(&self, start: usize) -> &str {
        let end = self.junk_end.unwrap_or_else(|| self.patterns_end());
        self.source[start..end.max(start)].trim()
    }
}

/// The part of a statement the string planner searched for a path binding's
/// `=`.
#[derive(Clone, Copy, PartialEq)]
enum EqualsScope {
    /// Text after the `MATCH` patterns, up to its first `WHERE` (where the
    /// string planner split the `MATCH`).
    MatchPattern,
    /// Text after a `CREATE`/`MERGE` pattern, up to its first top-level
    /// comma (where the string planner cut the list of patterns).
    WritePattern,
}

/// True when `text` contains an `=` sign outside string literals, within
/// `scope`.
fn text_has_equals(text: &str, scope: EqualsScope) -> bool {
    let (tokens, _) = crate::lexer::tokenize_prefix(text);
    let mut depth = 0usize;
    for token in &tokens {
        match token.token {
            Token::LParen | Token::LBracket | Token::LBrace => depth += 1,
            Token::RParen | Token::RBracket | Token::RBrace => depth = depth.saturating_sub(1),
            Token::Comma if scope == EqualsScope::WritePattern && depth == 0 => return false,
            Token::Keyword(crate::lexer::Keyword::Where) if scope == EqualsScope::MatchPattern => {
                return false;
            }
            Token::Eq | Token::PlusEq | Token::Le | Token::Ge => return true,
            Token::Ne if token.span.text(text) == "!=" => return true,
            _ => {}
        }
    }
    false
}

/// True when `text` contains a `.` outside string literals.
fn text_has_dot(text: &str) -> bool {
    let (tokens, _) = crate::lexer::tokenize_prefix(text);
    tokens.iter().any(|token| match token.token {
        Token::Dot | Token::DotDot => true,
        Token::Float(_) => token.span.text(text).contains('.'),
        _ => false,
    })
}

/// True when `text` has an `=` and a `.` before it, outside string literals.
fn dot_before_equals(text: &str) -> bool {
    let (tokens, _) = crate::lexer::tokenize_prefix(text);
    let Some(equals) = tokens
        .iter()
        .position(|token| matches!(token.token, Token::Eq | Token::PlusEq))
    else {
        return false;
    };
    tokens[..equals].iter().any(|token| match token.token {
        Token::Dot | Token::DotDot => true,
        Token::Float(_) => token.span.text(text).contains('.'),
        _ => false,
    })
}

/// The tokens of each `DELETE` target as written, split at top-level commas.
fn delete_target_texts(source: &str, delete: &ast::DeleteClause) -> Vec<Vec<Token>> {
    let (tokens, _) = crate::lexer::tokenize_prefix(delete.span.text(source));
    let mut targets = vec![Vec::new()];
    let mut depth = 0usize;
    let body = tokens
        .into_iter()
        .map(|token| token.token)
        .skip_while(|token| !matches!(token, Token::Keyword(crate::lexer::Keyword::Delete)));
    for token in body.skip(1) {
        match token {
            Token::Eof => break,
            Token::Comma if depth == 0 => {
                targets.push(Vec::new());
                continue;
            }
            Token::LParen | Token::LBracket | Token::LBrace => depth += 1,
            Token::RParen | Token::RBracket | Token::RBrace => depth = depth.saturating_sub(1),
            _ => {}
        }
        targets.last_mut().expect("one target list").push(token);
    }
    targets
}

fn statement_suffix_error(context: &str, rest: &str) -> GrustError {
    cypher_syntax(format!(
        "unsupported writable Cypher {context} pattern suffix: {rest}"
    ))
}

impl CypherMutationPlanner {
    /// A statement that starts with a non-optional `MATCH`.
    pub(super) fn plan_ast_match(
        &mut self,
        source: &str,
        match_clause: &MatchClause,
        rest: &[&Clause],
    ) -> Result<GraphMutationPlan> {
        // The write clause, in the precedence the planner has always used.
        let position = |found: fn(&Clause) -> bool| rest.iter().position(|clause| found(clause));
        let Some(index) = position(|clause| matches!(clause, Clause::Delete(_)))
            .or_else(|| position(|clause| matches!(clause, Clause::Merge(_))))
            .or_else(|| position(|clause| matches!(clause, Clause::Create(_))))
            .or_else(|| position(|clause| matches!(clause, Clause::Set(_))))
            .or_else(|| position(|clause| matches!(clause, Clause::Remove(_))))
        else {
            return Err(cypher_syntax(
                "only ID-resolved MATCH ... DELETE, MATCH ... CREATE/MERGE edge, MATCH ... SET, and MATCH ... REMOVE forms are supported in writable Cypher".to_string(),
            ));
        };
        let write = rest[index];
        // Unsupported text after the write clause: later clauses or a UNION.
        let tail = (index + 1 < rest.len()).then(|| write.span().end);
        let detach = matches!(write, Clause::Delete(delete) if delete.detach);
        let junk_end = (index > 0 || detach)
            .then(|| write.span().start + if detach { "DETACH".len() } else { 0 });
        let junk = &rest[..index];
        let junk_where = junk.iter().enumerate().find_map(|(position, clause)| {
            let expr = match clause {
                Clause::With(with) => with.where_clause.as_ref(),
                Clause::Match(other) => other.where_clause.as_ref(),
                _ => None,
            }?;
            Some((expr, detach || position + 1 < junk.len()))
        });
        let write_statement = MatchWrite {
            source,
            match_clause,
            junk_end,
            junk_where,
        };
        match write {
            Clause::Delete(delete) => self.plan_ast_match_delete(&write_statement, delete, tail),
            Clause::Merge(merge) => {
                let segment_junk = tail.map(|_| source.len()).or_else(|| {
                    (!merge.on_create.is_empty() || !merge.on_match.is_empty())
                        .then_some(merge.span.end)
                });
                self.plan_ast_match_upsert(
                    &write_statement,
                    std::slice::from_ref(&merge.pattern),
                    segment_junk,
                    "MERGE",
                    GraphMutationPlanKind::Merge,
                )
            }
            Clause::Create(create) => self.plan_ast_match_upsert(
                &write_statement,
                &create.patterns,
                tail.map(|_| source.len()),
                "CREATE",
                GraphMutationPlanKind::Create,
            ),
            Clause::Set(set) => self.plan_ast_match_set(&write_statement, set, tail),
            Clause::Remove(remove) => self.plan_ast_match_remove(&write_statement, remove, tail),
            _ => unreachable!("the write clause is one of the five matched above"),
        }
    }

    /// The `WHERE` predicates of the `MATCH`, canonicalised.
    fn ast_match_where(&self, write: &MatchWrite<'_>) -> Result<Vec<ParsedWherePredicate>> {
        let (expr, followed_by_text) = match (&write.match_clause.where_clause, write.junk_where) {
            (Some(expr), _) => (expr, write.junk_end.is_some()),
            (None, Some((expr, followed_by_text))) => (expr, followed_by_text),
            (None, None) => return Ok(Vec::new()),
        };
        let mut tree = where_boolean_from_expr(expr);
        if followed_by_text {
            mark_last_leaf_followed_by_text(&mut tree);
        }
        let mut predicates = lower_where_boolean_ast(&tree, &self.parameters)?;
        if followed_by_text {
            // Lowering reaches the marked leaf unless an earlier one failed.
            return Err(cypher_syntax(
                "MATCH WHERE is followed by an unsupported clause",
            ));
        }
        canonicalize_where_predicates(&mut predicates)?;
        Ok(predicates)
    }

    /// The path variable of `MATCH p = (...)`.
    fn ast_path_binding(&self, write: &MatchWrite<'_>, context: &str) -> Result<Option<String>> {
        let patterns = write.patterns();
        if let Some(variable) = &patterns[0].variable {
            let variable = checked_variable(variable)?;
            if patterns[0].shortest.is_some() {
                return Err(cypher_syntax(format!(
                    "{context} path variable must bind a relationship pattern"
                )));
            }
            return Ok(Some(variable));
        }
        let stray_equals = write.match_clause.where_clause.is_none()
            && write.junk_end.is_some_and(|end| {
                text_has_equals(
                    &write.source[write.patterns_end()..end],
                    EqualsScope::MatchPattern,
                )
            });
        if patterns[1..]
            .iter()
            .any(|pattern| pattern.variable.is_some())
            || stray_equals
        {
            return Err(GrustError::Unsupported(format!(
                "{context} path variable must be the first pattern's"
            )));
        }
        Ok(None)
    }

    fn plan_ast_match_delete(
        &mut self,
        write: &MatchWrite<'_>,
        delete: &ast::DeleteClause,
        tail: Option<usize>,
    ) -> Result<GraphMutationPlan> {
        let written = delete_target_texts(write.source, delete);
        let mut targets = Vec::with_capacity(delete.targets.len());
        for (index, target) in delete.targets.iter().enumerate() {
            // A target is a variable name as written: `DELETE n`, not `(n)`.
            let bare_name = written.get(index).is_some_and(|tokens| {
                matches!(
                    tokens.as_slice(),
                    [Token::Identifier(_) | Token::QuotedIdentifier(_)]
                )
            });
            let (Expr::Variable(variable), true) = (target, bare_name) else {
                return Err(GrustError::Unsupported(format!(
                    "MATCH DELETE target must be a variable, found {}",
                    describe_expr(target)
                )));
            };
            targets.push(checked_variable(variable)?);
        }
        if let Some(tail) = tail {
            return Err(GrustError::Unsupported(format!(
                "MATCH DELETE target is followed by unsupported text: {}",
                write.source[tail..].trim()
            )));
        }
        let where_predicates = self.ast_match_where(write)?;
        let path_variable = self.ast_path_binding(write, "MATCH DELETE")?;
        let patterns = write.patterns();

        if has_directed_relationship(patterns) {
            let mut parsed = self.ast_edge_match(
                write.source,
                patterns,
                path_variable.is_some(),
                write.junk_end,
            )?;
            apply_edge_where_predicates(&mut parsed, where_predicates, "MATCH edge DELETE")?;
            return self.lower_match_edge_delete_targets(parsed, targets, path_variable);
        }

        if path_variable.is_some() {
            return Err(cypher_syntax(
                "MATCH node DELETE does not support path variables",
            ));
        }
        if targets.len() != 1 {
            return Err(cypher_syntax(
                "MATCH node DELETE supports one target for a single-node pattern",
            ));
        }
        let target = targets
            .into_iter()
            .next()
            .expect("checked one delete target");
        let first = &patterns[0];
        let mut node = node_from_pattern(plain_start_node(first, false)?, &self.parameters)?;
        apply_node_where_predicates(&mut node, where_predicates, "MATCH node DELETE")?;
        if !first.segments.is_empty() || patterns.len() > 1 || write.junk_end.is_some() {
            return Err(statement_suffix_error(
                "MATCH DELETE",
                write.suffix_after(first.start.span.end),
            ));
        }
        self.lower_match_node_delete(node, target)
    }

    fn plan_ast_match_upsert(
        &mut self,
        write: &MatchWrite<'_>,
        segments: &[PathPattern],
        segment_junk_end: Option<usize>,
        keyword: &str,
        kind: GraphMutationPlanKind,
    ) -> Result<GraphMutationPlan> {
        let where_predicates = self.ast_match_where(write)?;
        let patterns = write.patterns();
        let mut matched_nodes = BTreeMap::new();
        for (index, pattern) in patterns.iter().enumerate() {
            let node = node_from_pattern(plain_start_node(pattern, false)?, &self.parameters)?;
            let last = index + 1 == patterns.len();
            if !pattern.segments.is_empty() || (last && write.junk_end.is_some()) {
                let end = if last {
                    write.junk_end.unwrap_or(pattern.span.end)
                } else {
                    pattern.span.end
                };
                return Err(statement_suffix_error(
                    "MATCH",
                    write.source[pattern.start.span.end..end].trim(),
                ));
            }
            let Some(variable) = node.variable.clone() else {
                return Err(cypher_syntax(format!(
                    "MATCH {keyword} requires each matched node pattern to bind a variable"
                )));
            };
            if matched_nodes.insert(variable.clone(), node).is_some() {
                return Err(cypher_unresolved_identity(format!(
                    "MATCH {keyword} cannot bind variable '{variable}' more than once"
                )));
            }
        }
        apply_match_where_predicates(
            &mut matched_nodes,
            where_predicates,
            &format!("MATCH {keyword}"),
        )?;

        let multi = segments.len() > 1;
        let mut ops = Vec::with_capacity(segments.len());
        for (index, segment) in segments.iter().enumerate() {
            let junk_end = if index + 1 == segments.len() {
                segment_junk_end
            } else {
                None
            };
            let path_variable = match &segment.variable {
                Some(variable) => {
                    let variable = checked_variable(variable)?;
                    if segment.shortest.is_some() {
                        return Err(cypher_syntax(
                            "MATCH CREATE/MERGE path variable must bind a relationship pattern",
                        ));
                    }
                    Some(variable)
                }
                None if junk_end.is_some_and(|end| {
                    text_has_equals(
                        &write.source[segment.span.end..end],
                        EqualsScope::WritePattern,
                    )
                }) =>
                {
                    return Err(GrustError::Unsupported(format!(
                        "MATCH {keyword} relationship pattern is followed by an unsupported clause"
                    )));
                }
                None => None,
            };
            if multi && path_variable.is_some() {
                return Err(cypher_syntax(format!(
                    "MATCH {keyword} does not support a path variable with multiple relationship patterns"
                )));
            }
            if !has_directed_relationship(std::slice::from_ref(segment)) {
                return Err(cypher_syntax(format!(
                    "MATCH {keyword} requires a relationship pattern"
                )));
            }
            let parsed = self.ast_edge_match(
                write.source,
                std::slice::from_ref(segment),
                path_variable.is_some(),
                junk_end,
            )?;
            ops.push(self.plan_match_edge_segment(
                parsed,
                path_variable,
                &matched_nodes,
                keyword,
                kind,
            )?);
        }
        Ok(GraphMutationPlan::new(ops))
    }

    fn plan_ast_match_set(
        &mut self,
        write: &MatchWrite<'_>,
        set: &ast::SetClause,
        tail: Option<usize>,
    ) -> Result<GraphMutationPlan> {
        let mut assignments = Vec::with_capacity(set.items.len());
        for (index, item) in set.items.iter().enumerate() {
            let tail = tail.filter(|_| index + 1 == set.items.len());
            assignments.push(self.ast_patch_assignment(write.source, item, tail)?);
        }
        let mut plan = GraphMutationPlan::default();
        for assignment in assignments {
            plan.operations.extend(
                self.lower_ast_match_set_assignment(write, assignment)?
                    .operations,
            );
        }
        Ok(plan)
    }

    /// One `SET` item as a patch: a `+=` map, a literal (or `null`)
    /// assignment, or `x.k = y.k <op> number`.
    fn ast_patch_assignment(
        &self,
        source: &str,
        item: &SetItem,
        tail: Option<usize>,
    ) -> Result<PatchAssignment> {
        match item {
            SetItem::Properties {
                variable,
                merge: true,
                value,
            } => {
                let target = checked_variable(variable)?;
                let Expr::Map(entries) = value else {
                    return Err(GrustError::Unsupported(
                        "MATCH SET += requires a Cypher property map".to_string(),
                    ));
                };
                if tail.is_some() {
                    return Err(GrustError::Unsupported(
                        "unsupported content after MATCH SET property map".to_string(),
                    ));
                }
                Ok(PatchAssignment {
                    target,
                    kind: PatchAssignmentKind::Props(props_from_entries(
                        entries,
                        &self.parameters,
                    )?),
                })
            }
            SetItem::Properties { merge: false, .. } => Err(cypher_syntax(
                "MATCH SET target requires property syntax target.key",
            )),
            // The string planner read `n:Label <tail>` up to an `=` as a
            // property reference: a variable name when that text has a dot.
            SetItem::Labels { .. }
                if tail.is_some_and(|tail| dot_before_equals(&source[tail..])) =>
            {
                Err(GrustError::Unsupported(
                    "MATCH SET label assignment is followed by unsupported text".to_string(),
                ))
            }
            SetItem::Labels { .. } => Err(cypher_syntax(
                "MATCH SET only supports map patch or literal property assignment",
            )),
            SetItem::Property { target, value } => {
                let (target, key) = property_ref(target, "MATCH SET target")?;
                if let Some(tail) = tail {
                    return Err(trailing_value_error(source, value, tail));
                }
                if let Some(kind) = self.ast_numeric_expression(&key, value)? {
                    return Ok(PatchAssignment { target, kind });
                }
                let value = literal_value(value, &self.parameters)?;
                if value == Value::Null
                    && self.null_assignment == CypherNullAssignment::RemoveProperty
                {
                    return Ok(PatchAssignment {
                        target,
                        kind: PatchAssignmentKind::RemoveProperty { key },
                    });
                }
                Ok(PatchAssignment {
                    target,
                    kind: PatchAssignmentKind::Props(Props::from([(key, value)])),
                })
            }
        }
    }

    /// `source.key <+|-|*|/> number`, the one computed `SET` value.
    fn ast_numeric_expression(
        &self,
        key: &str,
        value: &Expr,
    ) -> Result<Option<PatchAssignmentKind>> {
        let Expr::Binary { op, lhs, rhs } = value else {
            return Ok(None);
        };
        let op = match op {
            ast::BinaryOp::Add => GraphNumericOp::Add,
            ast::BinaryOp::Subtract => GraphNumericOp::Subtract,
            ast::BinaryOp::Multiply => GraphNumericOp::Multiply,
            ast::BinaryOp::Divide => GraphNumericOp::Divide,
            _ => return Ok(None),
        };
        let Ok((source_target, source_key)) = property_ref(lhs, "MATCH SET expression") else {
            return Ok(None);
        };
        let operand = literal_value(rhs, &self.parameters)?;
        if !matches!(operand, Value::Int(_) | Value::Float(_)) {
            return Err(cypher_syntax(
                "MATCH SET numeric expression operand must be an integer or float",
            ));
        }
        Ok(Some(PatchAssignmentKind::NumericExpression {
            key: key.to_string(),
            source_target,
            source_key,
            op,
            operand,
        }))
    }

    fn lower_ast_match_set_assignment(
        &mut self,
        write: &MatchWrite<'_>,
        assignment: PatchAssignment,
    ) -> Result<GraphMutationPlan> {
        let where_predicates = self.ast_match_where(write)?;
        let path_variable = self.ast_path_binding(write, "MATCH SET")?;

        // Unit 10b/W3: cross-variable correlated SET — `SET a.x = b.y <op> N` where
        // the numeric expression reads a *different* bound variable. Handled before
        // the single-target paths (which assume source == target).
        if let PatchAssignmentKind::NumericExpression { source_target, .. } = &assignment.kind
            && source_target != &assignment.target
        {
            return self.lower_ast_cross_variable_set(
                write,
                path_variable,
                where_predicates,
                assignment,
            );
        }

        let patterns = write.patterns();
        if has_directed_relationship(patterns) {
            let mut parsed = self.ast_edge_match(
                write.source,
                patterns,
                path_variable.is_some(),
                write.junk_end,
            )?;
            apply_edge_where_predicates(&mut parsed, where_predicates, "MATCH edge SET")?;
            return self.lower_match_edge_set(parsed, path_variable, assignment);
        }

        let first = &patterns[0];
        let mut node = node_from_pattern(
            plain_start_node(first, path_variable.is_some())?,
            &self.parameters,
        )?;
        apply_node_where_predicates(&mut node, where_predicates, "MATCH node SET")?;
        if !first.segments.is_empty() || patterns.len() > 1 || write.junk_end.is_some() {
            return Err(statement_suffix_error(
                "MATCH SET",
                write.suffix_after(first.start.span.end),
            ));
        }
        self.lower_match_node_set(node, assignment)
    }

    /// Lower a cross-variable correlated `SET a.x = b.y <op> N` (Unit 10b/W3).
    /// Supports both cartesian (`MATCH (a:..),(b:..)`) and path-correlated
    /// (`MATCH (a)-[:R]->(b)`) two-variable matches over node targets.
    fn lower_ast_cross_variable_set(
        &mut self,
        write: &MatchWrite<'_>,
        path_variable: Option<String>,
        where_predicates: Vec<ParsedWherePredicate>,
        assignment: PatchAssignment,
    ) -> Result<GraphMutationPlan> {
        if path_variable.is_some() {
            return Err(cypher_syntax(
                "MATCH SET cross-variable updates do not support path variables",
            ));
        }
        let patterns = write.patterns();
        let (target_node, source_node, correlation) = if has_directed_relationship(patterns) {
            let parsed = self.ast_edge_match(write.source, patterns, false, write.junk_end)?;
            cross_variable_edge_endpoints(parsed, &assignment)?
        } else {
            let mut by_var: BTreeMap<String, ParsedCypherNode> = BTreeMap::new();
            for (index, pattern) in patterns.iter().enumerate() {
                let node = node_from_pattern(plain_start_node(pattern, false)?, &self.parameters)?;
                let last = index + 1 == patterns.len();
                if !pattern.segments.is_empty() || (last && write.junk_end.is_some()) {
                    let end = if last {
                        write.junk_end.unwrap_or(pattern.span.end)
                    } else {
                        pattern.span.end
                    };
                    return Err(statement_suffix_error(
                        "MATCH SET",
                        write.source[pattern.start.span.end..end].trim(),
                    ));
                }
                let Some(variable) = node.variable.clone() else {
                    return Err(cypher_syntax(
                        "MATCH SET requires each matched node pattern to bind a variable",
                    ));
                };
                by_var.insert(variable, node);
            }
            cross_variable_cartesian_nodes(by_var, &assignment)?
        };
        lower_cross_variable_nodes(
            target_node,
            source_node,
            correlation,
            where_predicates,
            assignment,
        )
    }

    fn plan_ast_match_remove(
        &mut self,
        write: &MatchWrite<'_>,
        remove: &ast::RemoveClause,
        tail: Option<usize>,
    ) -> Result<GraphMutationPlan> {
        let where_predicates = self.ast_match_where(write)?;
        let path_variable = self.ast_path_binding(write, "MATCH REMOVE")?;
        let (target, key) = match remove.items.as_slice() {
            [RemoveItem::Property { target }] if tail.is_none() => {
                property_ref(target, "MATCH REMOVE target")?
            }
            // The string planner read `n:Label <tail>` as a property
            // reference: a variable name when the tail has a dot.
            [RemoveItem::Labels { .. }]
                if !tail.is_some_and(|tail| text_has_dot(&write.source[tail..])) =>
            {
                return Err(cypher_syntax(
                    "MATCH REMOVE target requires property syntax target.key",
                ));
            }
            _ => {
                return Err(GrustError::Unsupported(
                    "MATCH REMOVE supports exactly one property target".to_string(),
                ));
            }
        };

        let patterns = write.patterns();
        if has_directed_relationship(patterns) {
            let mut parsed = self.ast_edge_match(
                write.source,
                patterns,
                path_variable.is_some(),
                write.junk_end,
            )?;
            apply_edge_where_predicates(&mut parsed, where_predicates, "MATCH edge REMOVE")?;
            return self.lower_match_edge_remove(parsed, path_variable, target, key);
        }

        let first = &patterns[0];
        let mut node = node_from_pattern(
            plain_start_node(first, path_variable.is_some())?,
            &self.parameters,
        )?;
        apply_node_where_predicates(&mut node, where_predicates, "MATCH node REMOVE")?;
        if !first.segments.is_empty() || patterns.len() > 1 || write.junk_end.is_some() {
            return Err(statement_suffix_error(
                "MATCH REMOVE",
                write.suffix_after(first.start.span.end),
            ));
        }
        self.lower_match_node_remove(node, target, key)
    }
}
