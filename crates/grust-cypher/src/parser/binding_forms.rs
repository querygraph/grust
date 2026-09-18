//! Binding syntax uses the ordinary expression parser for every operand.
use super::*;

impl Parser {
    pub(super) fn parse_quantifier(&mut self, kind: ListQuantifier) -> PResult<Expr> {
        self.expect(&Token::LParen, "'(' to start quantifier")?;
        let item = self.parse_name("quantifier item")?;
        self.expect(&Token::Keyword(Keyword::In), "IN before quantifier list")?;
        let list = Box::new(self.parse_expr()?);
        self.expect(
            &Token::Keyword(Keyword::Where),
            "WHERE before quantifier predicate",
        )?;
        let predicate = Box::new(self.parse_expr()?);
        self.expect(&Token::RParen, "')' to close quantifier")?;
        Ok(Expr::Quantifier {
            kind,
            item,
            list,
            predicate,
        })
    }

    pub(super) fn parse_list_comprehension(&mut self) -> PResult<Expr> {
        let item = self.parse_name("list comprehension item")?;
        self.expect(&Token::Keyword(Keyword::In), "IN before comprehension list")?;
        let list = Box::new(self.parse_expr()?);
        let predicate = if self.eat_keyword(Keyword::Where) {
            Some(Box::new(self.parse_expr()?))
        } else {
            None
        };
        let projection = if self.eat(&Token::Pipe) {
            Some(Box::new(self.parse_expr()?))
        } else {
            None
        };
        self.expect(&Token::RBracket, "']' to close list comprehension")?;
        Ok(Expr::ListComprehension {
            item,
            list,
            predicate,
            projection,
        })
    }

    pub(super) fn parse_reduce(&mut self) -> PResult<Expr> {
        self.expect(&Token::LParen, "'(' to start reduce")?;
        let accumulator = self.parse_name("reduce accumulator")?;
        self.expect(&Token::Eq, "'=' before reduce seed")?;
        let seed = Box::new(self.parse_expr()?);
        self.expect(&Token::Comma, "',' before reduce item")?;
        let item = self.parse_name("reduce item")?;
        self.expect(&Token::Keyword(Keyword::In), "IN before reduce list")?;
        let list = Box::new(self.parse_expr()?);
        self.expect(&Token::Pipe, "'|' before reduce body")?;
        let body = Box::new(self.parse_expr()?);
        self.expect(&Token::RParen, "')' to close reduce")?;
        Ok(Expr::Reduce {
            accumulator,
            seed,
            item,
            list,
            body,
        })
    }
}
