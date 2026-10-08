//! Numeric expressions keep exact integer comparisons and expose arithmetic errors.
use super::*;
use grust_unresolved_plan::BinaryOp as B;
pub(super) fn is_integer(ty: &Option<LogicalType>) -> bool {
    matches!(ty, Some(LogicalType::Int32 | LogicalType::Int64))
}
pub(super) fn is_float(ty: &Option<LogicalType>) -> bool {
    matches!(ty, Some(LogicalType::Float32 | LogicalType::Float64))
}
pub(super) fn compare(
    op: B,
    l: &str,
    r: &str,
    left: &Option<LogicalType>,
    right: &Option<LogicalType>,
) -> Option<String> {
    let operator = match op {
        B::Eq => "=",
        B::NotEq => "<>",
        B::Lt => "<",
        B::Le => "<=",
        B::Gt => ">",
        B::Ge => ">=",
        _ => return None,
    };
    if is_float(left) && is_float(right) {
        return Some(format!("CASE WHEN {l} IS NULL OR {r} IS NULL THEN CAST(NULL AS BOOLEAN) WHEN isnan({l}) OR isnan({r}) THEN {} ELSE ({l} {operator} {r}) END",op==B::NotEq));
    }
    let (i, f, op) = if is_integer(left) && is_float(right) {
        (l, r, op)
    } else if is_float(left) && is_integer(right) {
        (
            r,
            l,
            match op {
                B::Lt => B::Gt,
                B::Le => B::Ge,
                B::Gt => B::Lt,
                B::Ge => B::Le,
                _ => op,
            },
        )
    } else {
        return None;
    };
    let truncated = format!("TRY_CAST({f} AS BIGINT)");
    let fractional = format!("CAST({truncated} AS DOUBLE)");
    let inner = match op {
        B::Eq => format!("{i}={truncated} AND {fractional}={f}"),
        B::NotEq => format!("{i}<>{truncated} OR {fractional}<>{f}"),
        B::Lt => format!("{i}<{truncated} OR ({i}={truncated} AND {fractional}<{f})"),
        B::Le => format!("{i}<{truncated} OR ({i}={truncated} AND {fractional}<={f})"),
        B::Gt => format!("{i}>{truncated} OR ({i}={truncated} AND {fractional}>{f})"),
        B::Ge => format!("{i}>{truncated} OR ({i}={truncated} AND {fractional}>={f})"),
        _ => unreachable!(),
    };
    let above = matches!(op, B::Lt | B::Le | B::NotEq);
    let below = matches!(op, B::Gt | B::Ge | B::NotEq);
    Some(format!("CASE WHEN {i} IS NULL OR {f} IS NULL THEN CAST(NULL AS BOOLEAN) WHEN isnan({f}) THEN {} WHEN {f}>=CAST('9223372036854775808' AS DOUBLE) THEN {above} WHEN {f}<CAST('-9223372036854775808' AS DOUBLE) THEN {below} ELSE ({inner}) END",op==B::NotEq))
}
pub(super) fn arithmetic(
    op: B,
    l: &str,
    r: &str,
    result: &Option<LogicalType>,
    right: &Option<LogicalType>,
) -> Option<String> {
    let int = is_integer(result);
    let null = if int {
        "CAST(NULL AS BIGINT)"
    } else {
        "CAST(NULL AS DOUBLE)"
    };
    if int && matches!(op, B::Add | B::Subtract | B::Multiply) {
        let operator = match op {
            B::Add => "+",
            B::Subtract => "-",
            _ => "*",
        };
        let value = format!("(CAST({l} AS DECIMAL(38,0)){operator}CAST({r} AS DECIMAL(38,0)))");
        return Some(format!("CASE WHEN {l} IS NULL OR {r} IS NULL THEN {null} WHEN {value} BETWEEN CAST('-9223372036854775808' AS DECIMAL(38,0)) AND CAST('9223372036854775807' AS DECIMAL(38,0)) THEN CAST({value} AS BIGINT) ELSE CAST(raise_error('grust numeric integer overflow') AS BIGINT) END"));
    }
    if !matches!(op, B::TruncatingDivide | B::Modulo) {
        return None;
    }
    let zero = if is_integer(right) {
        format!(
            "CAST(raise_error('grust numeric integer division by zero') AS {})",
            if int { "BIGINT" } else { "DOUBLE" }
        )
    } else if op == B::Modulo {
        "CAST('NaN' AS DOUBLE)".into()
    } else {
        format!("CASE WHEN {l}=0 THEN CAST('NaN' AS DOUBLE) WHEN ({l}<0)<>(atan2(CAST(0 AS DOUBLE),CAST({r} AS DOUBLE))>0) THEN CAST('-Infinity' AS DOUBLE) ELSE CAST('Infinity' AS DOUBLE) END")
    };
    let value = if int {
        if op == B::Modulo {
            format!("CASE WHEN {r}=-1 THEN CAST(0 AS BIGINT) ELSE ({l}%{r}) END")
        } else {
            format!("CASE WHEN {l}=CAST('-9223372036854775808' AS BIGINT) AND {r}=-1 THEN CAST('-9223372036854775808' AS BIGINT) ELSE ({l} DIV {r}) END")
        }
    } else {
        format!(
            "(CAST({l} AS DOUBLE){}CAST({r} AS DOUBLE))",
            if op == B::Modulo { "%" } else { "/" }
        )
    };
    Some(format!(
        "CASE WHEN {l} IS NULL OR {r} IS NULL THEN {null} WHEN {r}=0 THEN {zero} ELSE {value} END"
    ))
}
