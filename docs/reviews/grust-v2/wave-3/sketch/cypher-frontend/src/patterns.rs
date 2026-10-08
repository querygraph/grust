use crate::{refusal, CypherLowering};
use grust_cypher::{ast as a, lexer::Span};
use grust_syntax::Diagnostic;
use grust_unresolved_plan::{
    BinaryOp, Binding, EdgePattern, Expr, Hops, LabelExpr, PathMode, PathPattern, PathSelector,
    PatternDirection, VertexPattern,
};
impl CypherLowering<'_> {
    pub(crate) fn pattern(
        &self,
        p: &a::PathPattern,
        scope: &mut Vec<String>,
        next: &mut u64,
    ) -> Result<PathPattern, Diagnostic> {
        let mut vertices = vec![self.vertex(&p.start, scope, next)?];
        let mut edges = Vec::new();
        for s in &p.segments {
            let r = &s.relationship;
            let hops = r
                .length
                .as_ref()
                .map(|h| Hops {
                    min: h.min.unwrap_or(1),
                    max: h.max,
                })
                .unwrap_or(Hops::ONE);
            if !hops.is_valid() {
                return Err(refusal(r.span, "invalid relationship range"));
            }
            edges.push(EdgePattern {
                binding_list: r.length.is_some(),
                binding: binding(&r.variable, scope, next, r.span)?,
                labels: labels(&r.types, false),
                direction: match r.direction {
                    a::Direction::Outgoing => PatternDirection::Outgoing,
                    a::Direction::Incoming => PatternDirection::Incoming,
                    a::Direction::Undirected => PatternDirection::Either,
                },
                hops,
                predicates: self.properties(&r.properties, r.span)?,
            });
            vertices.push(self.vertex(&s.node, scope, next)?);
        }
        let path_binding =
            if p.variable.is_some() || p.segments.iter().any(|s| s.relationship.length.is_some()) {
                Some(binding(&p.variable, scope, next, p.span)?)
            } else {
                None
            };
        Ok(PathPattern {
            binding: path_binding,
            vertices,
            edges,
            mode: PathMode::Trail,
            selector: match p.shortest {
                None => PathSelector::All,
                Some(a::ShortestKind::Single) => PathSelector::Shortest,
                Some(a::ShortestKind::All) => PathSelector::AllShortest,
            },
        })
    }
    fn vertex(
        &self,
        n: &a::NodePattern,
        scope: &mut Vec<String>,
        next: &mut u64,
    ) -> Result<VertexPattern, Diagnostic> {
        Ok(VertexPattern {
            binding: binding(&n.variable, scope, next, n.span)?,
            labels: labels(&n.labels, true),
            predicates: self.properties(&n.properties, n.span)?,
        })
    }
    fn properties(&self, map: &Option<a::MapLiteral>, at: Span) -> Result<Vec<Expr>, Diagnostic> {
        map.as_ref()
            .map(|m| {
                m.entries
                    .iter()
                    .map(|(key, value)| {
                        Ok(Expr::CurrentElement
                            .property(key)
                            .binary(BinaryOp::Eq, self.expression(value, at)?))
                    })
                    .collect()
            })
            .unwrap_or(Ok(vec![]))
    }
}
fn labels(names: &[String], conjunction: bool) -> LabelExpr {
    match names {
        [] => LabelExpr::Any,
        [one] => LabelExpr::label(one),
        many => {
            let names = many.iter().map(LabelExpr::label).collect();
            if conjunction {
                LabelExpr::And(names)
            } else {
                LabelExpr::Or(names)
            }
        }
    }
}
fn binding(
    name: &Option<String>,
    scope: &mut Vec<String>,
    next: &mut u64,
    at: Span,
) -> Result<Binding, Diagnostic> {
    if let Some(name) = name {
        if !scope.contains(name) {
            scope.push(name.clone());
        }
        Ok(Binding::Named(name.clone()))
    } else {
        let id = *next;
        *next = next
            .checked_add(1)
            .ok_or_else(|| refusal(at, "anonymous binding id overflow"))?;
        Ok(Binding::Anonymous(id))
    }
}
