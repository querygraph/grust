//! Alternative 2: chumsky 0.13 over Grust's *existing* lexer tokens
//! (`grust_cypher::lexer::tokenize`, v0.24.0). This shows the "one shared
//! lexer, separate parser front end" layout. Error recovery is enabled on node
//! patterns and bracketed expressions, so one query can report several errors.

use subset_ast::*;
use chumsky::input::ValueInput;
use chumsky::pratt::{infix, left, postfix, prefix};
use chumsky::prelude::*;
use grust_cypher::lexer::{Keyword as K, Token as T, tokenize};

type Span = SimpleSpan;
type Extra<'t> = extra::Err<Rich<'t, T, Span>>;

fn parser<'t, I>() -> impl Parser<'t, I, Query, Extra<'t>> + Clone
where
    I: ValueInput<'t, Token = T, Span = Span>,
{
    let kw = |k: K| just(T::Keyword(k));
    let name = select! { T::Identifier(s) => s, T::QuotedIdentifier(s) => s }.labelled("name");

    let expr = recursive(|expr| {
        let map_lit = name
            .then_ignore(just(T::Colon))
            .then(expr.clone())
            .separated_by(just(T::Comma))
            .collect::<Vec<_>>()
            .delimited_by(just(T::LBrace), just(T::RBrace))
            .labelled("map literal");

        let literal = select! {
            T::Integer(n) => Expr::Int(n),
            T::Float(f) => Expr::Float(f),
            T::String(s) => Expr::Str(s),
            T::Parameter(p) => Expr::Param(p),
            T::Keyword(K::True) => Expr::Bool(true),
            T::Keyword(K::False) => Expr::Bool(false),
            T::Keyword(K::Null) => Expr::Null,
        };

        let args = just(T::Star).to(None).or(kw(K::Distinct)
            .or_not()
            .then(expr.clone().separated_by(just(T::Comma)).collect::<Vec<_>>())
            .map(Some));
        let call = name
            .then(args.delimited_by(just(T::LParen), just(T::RParen)))
            .map(|(f, a)| match a {
                None => Expr::CountStar,
                Some((d, a)) => Expr::Call(f, d.is_some(), a),
            });

        let atom = choice((
            literal,
            call,
            name.map(Expr::Var),
            expr.clone()
                .separated_by(just(T::Comma))
                .collect::<Vec<_>>()
                .delimited_by(just(T::LBracket), just(T::RBracket))
                .map(Expr::List),
            map_lit.clone().map(Expr::Map),
            expr.clone().delimited_by(just(T::LParen), just(T::RParen)),
        ))
        .recover_with(via_parser(nested_delimiters(
            T::LParen,
            T::RParen,
            [(T::LBracket, T::RBracket), (T::LBrace, T::RBrace)],
            |_| Expr::Error,
        )))
        .labelled("expression");

        let prop = atom.foldl(just(T::Dot).ignore_then(name).repeated(), |e, p| {
            Expr::Prop(Box::new(e), p)
        });

        let word = |w: &'static str| {
            select! { T::Identifier(s) if s.eq_ignore_ascii_case(w) => () }
        };
        let cmp = choice((
            just(T::Eq).to(Op::Eq),
            just(T::Ne).to(Op::Ne),
            just(T::Le).to(Op::Le),
            just(T::Ge).to(Op::Ge),
            just(T::Lt).to(Op::Lt),
            just(T::Gt).to(Op::Gt),
            kw(K::In).to(Op::In),
            kw(K::Contains).to(Op::Contains),
            word("starts").then(kw(K::With)).to(Op::StartsWith),
            word("ends").then(kw(K::With)).to(Op::EndsWith),
        ));
        prop.pratt((
            infix(left(1), kw(K::Or), |l, _, r, _| bin(Op::Or, l, r)),
            infix(left(2), kw(K::Xor), |l, _, r, _| bin(Op::Xor, l, r)),
            infix(left(3), kw(K::And), |l, _, r, _| bin(Op::And, l, r)),
            prefix(4, kw(K::Not), |_, e, _| Expr::Not(Box::new(e))),
            infix(left(5), cmp, |l, op, r, _| bin(op, l, r)),
            postfix(
                5,
                kw(K::Is).ignore_then(kw(K::Not).or_not()).then_ignore(kw(K::Null)),
                |l, n: Option<T>, _| Expr::IsNull(Box::new(l), n.is_some()),
            ),
            infix(left(6), just(T::Plus), |l, _, r, _| bin(Op::Add, l, r)),
            infix(left(6), just(T::Minus), |l, _, r, _| bin(Op::Sub, l, r)),
            infix(left(7), just(T::Star), |l, _, r, _| bin(Op::Mul, l, r)),
            infix(left(7), just(T::Slash), |l, _, r, _| bin(Op::Div, l, r)),
            infix(left(7), just(T::Percent), |l, _, r, _| bin(Op::Mod, l, r)),
            prefix(8, just(T::Minus), |_, e, _| Expr::Neg(Box::new(e))),
        ))
        .labelled("expression")
    });

    let map_lit = name
        .then_ignore(just(T::Colon))
        .then(expr.clone())
        .separated_by(just(T::Comma))
        .collect::<Vec<_>>()
        .delimited_by(just(T::LBrace), just(T::RBrace));

    let node = name
        .or_not()
        .then(just(T::Colon).ignore_then(name).repeated().collect::<Vec<_>>())
        .then(map_lit.clone().or_not())
        .map(|((var, labels), props)| Node { var, labels, props: props.unwrap_or_default() })
        .delimited_by(just(T::LParen), just(T::RParen))
        .recover_with(via_parser(nested_delimiters(
            T::LParen,
            T::RParen,
            [(T::LBracket, T::RBracket), (T::LBrace, T::RBrace)],
            |_| Node::default(),
        )))
        .labelled("node pattern");

    let uint = select! { T::Integer(n) if n >= 0 => n as u64 };
    let range = uint
        .or_not()
        .then(just(T::DotDot).ignore_then(uint.or_not()).or_not())
        .map(|(min, max)| (min, max.unwrap_or(min)));
    let detail = name
        .or_not()
        .then(just(T::Colon).ignore_then(name.separated_by(just(T::Pipe)).at_least(1).collect::<Vec<_>>()).or_not())
        .then(just(T::Star).ignore_then(range).or_not())
        .then(map_lit.or_not())
        .delimited_by(just(T::LBracket), just(T::RBracket));
    let rel = just(T::ArrowLeft)
        .to(true)
        .or(just(T::Minus).to(false))
        .then(detail.or_not())
        .then(just(T::Arrow).to(true).or(just(T::Minus).to(false)))
        .try_map(|((l, d), r), span| {
            let dir = match (l, r) {
                (true, false) => Dir::In,
                (false, true) => Dir::Out,
                (false, false) => Dir::Both,
                (true, true) => return Err(Rich::custom(span, "a relationship cannot point both ways")),
            };
            let (((var, types), range), props) = d.unwrap_or_default();
            Ok(Rel { var, types: types.unwrap_or_default(), range, props: props.unwrap_or_default(), dir })
        })
        .labelled("relationship pattern");

    let path = name
        .then_ignore(just(T::Eq))
        .or_not()
        .then(node.clone())
        .then(rel.then(node).repeated().collect::<Vec<_>>())
        .map(|((var, start), hops)| Path { var, start, hops });

    let match_clause = kw(K::Optional)
        .or_not()
        .then_ignore(kw(K::Match))
        .then(path.separated_by(just(T::Comma)).at_least(1).collect::<Vec<_>>())
        .then(kw(K::Where).ignore_then(expr.clone()).or_not())
        .map(|((o, patterns), filter)| Match { optional: o.is_some(), patterns, filter });

    let item = expr.clone().then(kw(K::As).ignore_then(name).or_not());
    let order_item = expr
        .clone()
        .then(kw(K::Asc).to(true).or(kw(K::Desc).to(false)).or_not())
        .map(|(e, a)| (e, a.unwrap_or(true)));
    let int = select! { T::Integer(n) => n };
    let ret = kw(K::Return)
        .ignore_then(kw(K::Distinct).or_not())
        .then(item.separated_by(just(T::Comma)).at_least(1).collect::<Vec<_>>())
        .then(kw(K::Order).ignore_then(kw(K::By)).ignore_then(order_item.separated_by(just(T::Comma)).at_least(1).collect::<Vec<_>>()).or_not())
        .then(kw(K::Skip).ignore_then(int).or_not())
        .then(kw(K::Limit).ignore_then(int).or_not())
        .map(|((((d, items), order), skip), limit)| Return {
            distinct: d.is_some(),
            items,
            order: order.unwrap_or_default(),
            skip,
            limit,
        });

    match_clause
        .repeated()
        .at_least(1)
        .collect::<Vec<_>>()
        .then(ret)
        .then_ignore(just(T::Semicolon).or_not())
        .then_ignore(end())
        .map(|(matches, ret)| Query { matches, ret })
}

/// Parse one query; on error return every (span start, span end, message).
pub fn parse(source: &str) -> Result<Query, Vec<(usize, usize, String)>> {
    let tokens = tokenize(source).map_err(|e| vec![(e.span.start, e.span.end, e.message.clone())])?;
    let toks: Vec<(T, Span)> = tokens
        .into_iter()
        .filter(|t| t.token != T::Eof)
        .map(|t| (t.token, Span::from(t.span.start..t.span.end)))
        .collect();
    let n = source.len();
    let (out, errs) = parser()
        .parse(toks.as_slice().map(Span::from(n..n), |(t, s)| (t, s)))
        .into_output_errors();
    match out {
        Some(q) if errs.is_empty() => Ok(q),
        _ => Err(errs
            .into_iter()
            .map(|e| {
                let e = e.map_token(|t| format!("{t:?}"));
                (e.span().start, e.span().end, e.to_string())
            })
            .collect()),
    }
}
