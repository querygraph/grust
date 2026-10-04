//! Alternative 1: winnow 1.0 (the maintained nom-style combinator library),
//! parsing characters directly. No separate lexer. Fail-fast: one error.

use subset_ast::*;
use winnow::ascii::{Caseless, digit1, multispace0};
use winnow::combinator::{alt, cut_err, delimited, eof, not, opt, preceded, repeat, separated, terminated};
use winnow::error::{ContextError, ErrMode, StrContext, StrContextValue};
use winnow::prelude::*;
use winnow::token::{literal, one_of, take_while};

type In<'i> = &'i str;
type R<T> = ModalResult<T>;

fn ws(i: &mut In) -> R<()> {
    multispace0.void().parse_next(i)
}

fn sym<'i>(s: &'static str) -> impl Parser<In<'i>, (), ErrMode<ContextError>> {
    preceded(ws, literal(s))
        .void()
        .context(StrContext::Expected(StrContextValue::StringLiteral(s)))
}

fn is_ident_char(c: char) -> bool {
    c.is_ascii_alphanumeric() || c == '_'
}

fn kw<'i>(k: &'static str) -> impl Parser<In<'i>, (), ErrMode<ContextError>> {
    preceded(ws, terminated(literal(Caseless(k)), not(one_of(is_ident_char))))
        .void()
        .context(StrContext::Expected(StrContextValue::StringLiteral(k)))
}

fn raw_ident<'i>(i: &mut In<'i>) -> R<&'i str> {
    preceded(
        ws,
        (
            one_of(|c: char| c.is_ascii_alphabetic() || c == '_'),
            take_while(0.., is_ident_char),
        )
            .take(),
    )
    .parse_next(i)
}

fn backticked(i: &mut In) -> R<String> {
    preceded(ws, delimited('`', take_while(0.., |c| c != '`'), '`'))
        .map(String::from)
        .parse_next(i)
}

/// A variable: an identifier that is not a reserved word.
fn name(i: &mut In) -> R<String> {
    alt((
        raw_ident.verify(|s: &str| !is_reserved(s)).map(String::from),
        backticked,
    ))
    .context(StrContext::Label("name"))
    .parse_next(i)
}

/// A label, type or map key: any identifier.
fn any_name(i: &mut In) -> R<String> {
    alt((raw_ident.map(String::from), backticked))
        .context(StrContext::Label("name"))
        .parse_next(i)
}

fn uint(i: &mut In) -> R<u64> {
    preceded(ws, digit1).parse_to().parse_next(i)
}

fn int(i: &mut In) -> R<i64> {
    preceded(ws, digit1).parse_to().parse_next(i)
}

fn map_lit(i: &mut In) -> R<Vec<(String, Expr)>> {
    preceded(
        sym("{"),
        cut_err(terminated(
            separated(0.., (any_name, preceded(cut_err(sym(":")), cut_err(expr))), sym(",")),
            sym("}"),
        )),
    )
    .context(StrContext::Label("map literal"))
    .parse_next(i)
}

fn node(i: &mut In) -> R<Node> {
    sym("(").parse_next(i)?;
    let var = opt(name).parse_next(i)?;
    let labels = repeat(0.., preceded(sym(":"), cut_err(any_name))).parse_next(i)?;
    let props = opt(map_lit).parse_next(i)?.unwrap_or_default();
    cut_err(sym(")"))
        .context(StrContext::Label("node pattern"))
        .parse_next(i)?;
    Ok(Node { var, labels, props })
}

fn rel(i: &mut In) -> R<Rel> {
    let left_in = alt((sym("<-").value(true), sym("-").value(false))).parse_next(i)?;
    let mut rel = Rel { var: None, types: vec![], range: None, props: vec![], dir: Dir::Both };
    if opt(sym("[")).parse_next(i)?.is_some() {
        rel.var = opt(name).parse_next(i)?;
        if opt(sym(":")).parse_next(i)?.is_some() {
            rel.types = cut_err(separated(1.., any_name, sym("|"))).parse_next(i)?;
        }
        if opt(sym("*")).parse_next(i)?.is_some() {
            let min = opt(uint).parse_next(i)?;
            let max = if opt(sym("..")).parse_next(i)?.is_some() { opt(uint).parse_next(i)? } else { min };
            rel.range = Some((min, max));
        }
        rel.props = opt(map_lit).parse_next(i)?.unwrap_or_default();
        cut_err(sym("]"))
            .context(StrContext::Label("relationship pattern"))
            .parse_next(i)?;
    }
    let right_out = cut_err(alt((sym("->").value(true), sym("-").value(false))))
        .context(StrContext::Label("relationship pattern"))
        .parse_next(i)?;
    rel.dir = match (left_in, right_out) {
        (true, false) => Dir::In,
        (false, true) => Dir::Out,
        (false, false) => Dir::Both,
        (true, true) => return Err(ErrMode::Cut(ContextError::new())),
    };
    Ok(rel)
}

fn path(i: &mut In) -> R<Path> {
    let var = opt(terminated(name, sym("="))).parse_next(i)?;
    let start = node(i)?;
    let hops = repeat(0.., (rel, cut_err(node))).parse_next(i)?;
    Ok(Path { var, start, hops })
}

fn match_clause(i: &mut In) -> R<Match> {
    let optional = opt(kw("OPTIONAL")).parse_next(i)?.is_some();
    if optional {
        cut_err(kw("MATCH")).parse_next(i)?;
    } else {
        kw("MATCH").parse_next(i)?;
    }
    let patterns = cut_err(separated(1.., path, sym(","))).parse_next(i)?;
    let filter = opt(preceded(kw("WHERE"), cut_err(expr))).parse_next(i)?;
    Ok(Match { optional, patterns, filter })
}

fn order_item(i: &mut In) -> R<(Expr, bool)> {
    let e = expr(i)?;
    let asc = opt(alt((
        kw("ASCENDING").value(true),
        kw("ASC").value(true),
        kw("DESCENDING").value(false),
        kw("DESC").value(false),
    )))
    .parse_next(i)?;
    Ok((e, asc.unwrap_or(true)))
}

pub fn query(i: &mut In) -> R<Query> {
    let matches = repeat(1.., match_clause).parse_next(i)?;
    cut_err(kw("RETURN")).parse_next(i)?;
    let distinct = opt(kw("DISTINCT")).parse_next(i)?.is_some();
    let items = cut_err(separated(
        1..,
        (expr, opt(preceded(kw("AS"), cut_err(name)))),
        sym(","),
    ))
    .context(StrContext::Label("RETURN item"))
    .parse_next(i)?;
    let order = opt(preceded((kw("ORDER"), cut_err(kw("BY"))), cut_err(separated(1.., order_item, sym(",")))))
        .parse_next(i)?
        .unwrap_or_default();
    let skip = opt(preceded(kw("SKIP"), cut_err(int))).parse_next(i)?;
    let limit = opt(preceded(kw("LIMIT"), cut_err(int))).parse_next(i)?;
    opt(sym(";")).parse_next(i)?;
    ws(i)?;
    cut_err(eof).context(StrContext::Label("end of query")).parse_next(i)?;
    Ok(Query { matches, ret: Return { distinct, items, order, skip, limit } })
}

// ---- expressions: precedence climbing, loosest first ----

fn expr(i: &mut In) -> R<Expr> {
    or_expr.context(StrContext::Label("expression")).parse_next(i)
}

fn left_assoc(
    i: &mut In,
    next: fn(&mut In) -> R<Expr>,
    op: fn(&mut In) -> R<Op>,
) -> R<Expr> {
    let mut acc = next(i)?;
    while let Some(o) = opt(op).parse_next(i)? {
        let rhs = cut_err(next).parse_next(i)?;
        acc = bin(o, acc, rhs);
    }
    Ok(acc)
}

fn or_expr(i: &mut In) -> R<Expr> {
    left_assoc(i, xor_expr, |i| kw("OR").value(Op::Or).parse_next(i))
}

fn xor_expr(i: &mut In) -> R<Expr> {
    left_assoc(i, and_expr, |i| kw("XOR").value(Op::Xor).parse_next(i))
}

fn and_expr(i: &mut In) -> R<Expr> {
    left_assoc(i, not_expr, |i| kw("AND").value(Op::And).parse_next(i))
}

fn not_expr(i: &mut In) -> R<Expr> {
    if opt(kw("NOT")).parse_next(i)?.is_some() {
        Ok(Expr::Not(Box::new(cut_err(not_expr).parse_next(i)?)))
    } else {
        comparison(i)
    }
}

fn comparison_op(i: &mut In) -> R<Op> {
    alt((symbol_op, word_op)).parse_next(i)
}

fn symbol_op(i: &mut In) -> R<Op> {
    alt((
        sym("<>").value(Op::Ne),
        sym("<=").value(Op::Le),
        sym(">=").value(Op::Ge),
        sym("<").value(Op::Lt),
        sym(">").value(Op::Gt),
        sym("=").value(Op::Eq),
    ))
    .parse_next(i)
}

fn word_op(i: &mut In) -> R<Op> {
    alt((
        kw("IN").value(Op::In),
        (kw("STARTS"), cut_err(kw("WITH"))).value(Op::StartsWith),
        (kw("ENDS"), cut_err(kw("WITH"))).value(Op::EndsWith),
        kw("CONTAINS").value(Op::Contains),
    ))
    .parse_next(i)
}

fn comparison(i: &mut In) -> R<Expr> {
    let mut acc = additive(i)?;
    loop {
        if opt(kw("IS")).parse_next(i)?.is_some() {
            let negated = opt(kw("NOT")).parse_next(i)?.is_some();
            cut_err(kw("NULL")).parse_next(i)?;
            acc = Expr::IsNull(Box::new(acc), negated);
        } else if let Some(o) = opt(comparison_op).parse_next(i)? {
            let rhs = cut_err(additive).parse_next(i)?;
            acc = bin(o, acc, rhs);
        } else {
            return Ok(acc);
        }
    }
}

fn additive(i: &mut In) -> R<Expr> {
    left_assoc(i, multiplicative, |i| {
        alt((sym("+").value(Op::Add), sym("-").value(Op::Sub))).parse_next(i)
    })
}

fn multiplicative(i: &mut In) -> R<Expr> {
    left_assoc(i, unary, |i| {
        alt((sym("*").value(Op::Mul), sym("/").value(Op::Div), sym("%").value(Op::Mod))).parse_next(i)
    })
}

fn unary(i: &mut In) -> R<Expr> {
    if opt(sym("-")).parse_next(i)?.is_some() {
        Ok(Expr::Neg(Box::new(cut_err(unary).parse_next(i)?)))
    } else {
        postfix(i)
    }
}

fn postfix(i: &mut In) -> R<Expr> {
    let mut e = atom(i)?;
    while opt(sym(".")).parse_next(i)?.is_some() {
        e = Expr::Prop(Box::new(e), cut_err(any_name).parse_next(i)?);
    }
    Ok(e)
}

fn number(i: &mut In) -> R<Expr> {
    preceded(ws, (digit1, opt(('.', digit1))).take())
        .verify_map(|s: &str| {
            if s.contains('.') { s.parse().ok().map(Expr::Float) } else { s.parse().ok().map(Expr::Int) }
        })
        .parse_next(i)
}

fn string(i: &mut In) -> R<Expr> {
    preceded(
        ws,
        alt((
            delimited('\'', take_while(0.., |c| c != '\''), cut_err('\'')),
            delimited('"', take_while(0.., |c| c != '"'), cut_err('"')),
        )),
    )
    .map(|s: &str| Expr::Str(s.to_string()))
    .parse_next(i)
}

fn param(i: &mut In) -> R<Expr> {
    preceded(sym("$"), cut_err(any_name)).map(Expr::Param).parse_next(i)
}

fn call_or_var(i: &mut In) -> R<Expr> {
    let f = name(i)?;
    if opt(sym("(")).parse_next(i)?.is_none() {
        return Ok(Expr::Var(f));
    }
    if opt(sym("*")).parse_next(i)?.is_some() {
        cut_err(sym(")")).parse_next(i)?;
        return Ok(Expr::CountStar);
    }
    let distinct = opt(kw("DISTINCT")).parse_next(i)?.is_some();
    let args = cut_err(terminated(separated(0.., expr, sym(",")), sym(")"))).parse_next(i)?;
    Ok(Expr::Call(f, distinct, args))
}

fn atom(i: &mut In) -> R<Expr> {
    alt((simple_atom, compound))
        .context(StrContext::Expected(StrContextValue::Description("an expression")))
        .parse_next(i)
}

fn simple_atom(i: &mut In) -> R<Expr> {
    alt((
        number,
        string,
        param,
        kw("TRUE").value(Expr::Bool(true)),
        kw("FALSE").value(Expr::Bool(false)),
        kw("NULL").value(Expr::Null),
    ))
    .parse_next(i)
}

fn compound(i: &mut In) -> R<Expr> {
    alt((
        call_or_var,
        preceded(sym("["), cut_err(terminated(separated(0.., expr, sym(",")), sym("]")))).map(Expr::List),
        map_lit.map(Expr::Map),
        preceded(sym("("), cut_err(terminated(expr, sym(")")))),
    ))
    .parse_next(i)
}

/// Parse one query; on error return (byte offset, rendered message).
pub fn parse(source: &str) -> Result<Query, (usize, String)> {
    query.parse(source).map_err(|e| (e.offset(), e.inner().to_string()))
}
